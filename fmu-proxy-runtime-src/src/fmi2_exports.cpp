#include "fmi2/fmi2Functions.h"

#include <memory>
#include <cstring>
#include <cmath>
#include <new>
#include <string>

#include "decentralabs_proxy/runtime.hpp"

namespace decentralabs::proxy {

namespace {

struct Fmi2Instance {
    fmi2CallbackFunctions callbacks{};
    bool logging_enabled = false;
    bool model_exchange = false;
    enum class Mode { kInstantiated, kInitialization, kEvent, kContinuous, kStep, kTerminated } mode = Mode::kInstantiated;
    std::string instance_name;
    ProxyRuntime runtime;
    std::string last_string_status;
};

bool IsModelExchangeEvaluationMode(const Fmi2Instance::Mode mode) {
    return mode == Fmi2Instance::Mode::kInitialization
        || mode == Fmi2Instance::Mode::kEvent
        || mode == Fmi2Instance::Mode::kContinuous;
}

struct Fmi2StateHandle {
    std::string checkpoint;
    Fmi2Instance::Mode mode = Fmi2Instance::Mode::kInstantiated;
};

constexpr size_t kMaximumSerializedStateTokenBytes = 64 * 1024;

std::string SerializeFmi2State(const Fmi2StateHandle& state) {
    JsonObject object = {
        {"checkpoint", JsonValue(state.checkpoint)},
        {"mode", JsonValue(static_cast<int>(state.mode))},
    };
    return SerializeJson(JsonValue(std::move(object)));
}

bool ParseFmi2State(const std::string& serialized, Fmi2StateHandle* state) {
    if (state == nullptr) {
        return false;
    }
    const auto parsed = ParseJson(serialized);
    const JsonObject* object = parsed ? parsed.value.AsObject() : nullptr;
    if (object == nullptr) {
        return false;
    }
    const JsonValue* checkpoint = FindObjectValue(*object, "checkpoint");
    const JsonValue* mode = FindObjectValue(*object, "mode");
    if (checkpoint == nullptr || !checkpoint->IsString() || mode == nullptr || !mode->IsNumber()) {
        return false;
    }
    const double raw_mode = mode->AsNumber(-1.0);
    if (!std::isfinite(raw_mode) || std::floor(raw_mode) != raw_mode
        || raw_mode < 0 || raw_mode > static_cast<int>(Fmi2Instance::Mode::kTerminated)) {
        return false;
    }
    state->checkpoint = checkpoint->AsString();
    state->mode = static_cast<Fmi2Instance::Mode>(static_cast<int>(raw_mode));
    return true;
}

Fmi2Instance* AsInstance(fmi2Component component) {
    return static_cast<Fmi2Instance*>(component);
}

void Log(Fmi2Instance* instance, const fmi2Status status, const char* category, const std::string& message) {
    if (instance == nullptr || instance->callbacks.logger == nullptr) {
        return;
    }
    instance->callbacks.logger(
        instance->callbacks.componentEnvironment,
        instance->instance_name.c_str(),
        status,
        category,
        "%s",
        message.c_str());
}

fmi2Status ToFmiStatus(Fmi2Instance* instance, const OperationResult& status) {
    if (status) {
        return fmi2OK;
    }
    if (status.code == "INPUT_UPDATE_RATE_LIMIT" || status.code == "OUTPUT_READ_RATE_LIMITED"
        || status.code == "NO_ADVANCE") {
        Log(instance, fmi2Warning, "logStatusWarning", status.message);
        return fmi2Discard;
    }
    Log(instance, fmi2Error, "logStatusError", status.message);
    return fmi2Error;
}

void AttachLogger(Fmi2Instance* instance) {
    instance->runtime.SetLogger([instance](const std::string& category, const std::string& message) {
        if (instance->logging_enabled) {
            Log(instance, fmi2OK, category.c_str(), message);
        }
    });
}

fmi2Status ModelExchangeVector(Fmi2Instance* instance,
                               const std::string& operation,
                               const fmi2Real input[],
                               fmi2Real output[],
                               const size_t count) {
    if (instance == nullptr || (count > 0 && input != nullptr && operation != "setContinuousStates")
        || (count > 0 && output != nullptr && operation == "setContinuousStates")) return fmi2Fatal;
    JsonObject arguments;
    if (operation == "setContinuousStates") {
        if (count > 0 && input == nullptr) return fmi2Fatal;
        JsonArray values;
        values.reserve(count);
        for (size_t index = 0; index < count; ++index) {
            if (!std::isfinite(input[index])) return fmi2Error;
            values.emplace_back(input[index]);
        }
        arguments.emplace("values", JsonValue(std::move(values)));
    } else if (count > 0 && output == nullptr) {
        return fmi2Fatal;
    }
    const auto response = instance->runtime.ModelExchangeCall(operation, arguments);
    if (!response) return ToFmiStatus(instance, response.status);
    if (operation == "setContinuousStates") return fmi2OK;
    const JsonValue* raw_values = FindObjectValue(response.value, "values");
    const JsonArray* values = raw_values == nullptr ? nullptr : raw_values->AsArray();
    if (values == nullptr || values->size() != count) {
        Log(instance, fmi2Error, "logStatusError", "Gateway returned an invalid Model Exchange vector");
        return fmi2Error;
    }
    for (size_t index = 0; index < count; ++index) {
        if (!(*values)[index].IsNumber() || !std::isfinite((*values)[index].AsNumber())) {
            Log(instance, fmi2Error, "logStatusError", "Gateway returned a non-finite Model Exchange vector value");
            return fmi2Error;
        }
        output[index] = (*values)[index].AsNumber();
    }
    return fmi2OK;
}

}  // namespace

}  // namespace decentralabs::proxy

using decentralabs::proxy::AsInstance;
using decentralabs::proxy::AttachLogger;
using decentralabs::proxy::Fmi2Instance;
using decentralabs::proxy::Fmi2StateHandle;
using decentralabs::proxy::FindObjectValue;
using decentralabs::proxy::JsonObject;
using decentralabs::proxy::JsonValue;
using decentralabs::proxy::kMaximumSerializedStateTokenBytes;
using decentralabs::proxy::Log;
using decentralabs::proxy::OperationResult;
using decentralabs::proxy::ParseJson;
using decentralabs::proxy::SessionState;
using decentralabs::proxy::SerializeJson;
using decentralabs::proxy::ToFmiStatus;

extern "C" {

const char* fmi2GetTypesPlatform(void) {
    return fmi2TypesPlatform;
}

const char* fmi2GetVersion(void) {
    return "2.0";
}

fmi2Component fmi2Instantiate(fmi2String instanceName,
                              fmi2Type fmuType,
                              fmi2String,
                              fmi2String fmuResourceLocation,
                              const fmi2CallbackFunctions* functions,
                              fmi2Boolean,
                              fmi2Boolean loggingOn) {
    if ((fmuType != fmi2CoSimulation && fmuType != fmi2ModelExchange)
        || instanceName == nullptr || fmuResourceLocation == nullptr || functions == nullptr) {
        return nullptr;
    }

    auto* instance = new Fmi2Instance();
    instance->callbacks = *functions;
    instance->logging_enabled = loggingOn == fmi2True;
    instance->instance_name = instanceName;
    AttachLogger(instance);

    const OperationResult status = instance->runtime.Configure(instanceName, fmuResourceLocation);
    if (!status) {
        Log(instance, fmi2Error, "logStatusError", status.message);
        delete instance;
        return nullptr;
    }
    instance->model_exchange = fmuType == fmi2ModelExchange;
    const OperationResult interface_status = instance->runtime.SetModelExchangeMode(instance->model_exchange);
    if (!interface_status) {
        Log(instance, fmi2Error, "logStatusError", interface_status.message);
        delete instance;
        return nullptr;
    }

    return instance;
}

void fmi2FreeInstance(fmi2Component c) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return;
    }
    const auto status = instance->runtime.Close();
    if (!status) {
        Log(instance, fmi2Warning, "logStatusError", status.message);
    }
    delete instance;
}

fmi2Status fmi2SetupExperiment(fmi2Component c,
                               fmi2Boolean,
                               fmi2Real,
                               fmi2Real startTime,
                               fmi2Boolean stopTimeDefined,
                               fmi2Real stopTime) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    const auto& model = instance->runtime.Model();
    const std::optional<double> effective_stop = stopTimeDefined == fmi2True
        ? std::optional<double>(stopTime)
        : std::nullopt;
    const double step = model.default_step_size.value_or(0.01);
    const auto status = instance->runtime.SetupExperiment(startTime, effective_stop, step);
    if (status) instance->mode = Fmi2Instance::Mode::kInstantiated;
    return ToFmiStatus(instance, status);
}

fmi2Status fmi2EnterInitializationMode(fmi2Component c) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    const auto status = instance->runtime.EnterInitializationMode();
    if (status) instance->mode = Fmi2Instance::Mode::kInitialization;
    return ToFmiStatus(instance, status);
}

fmi2Status fmi2ExitInitializationMode(fmi2Component c) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    const auto status = instance->runtime.ExitInitializationMode();
    if (status) instance->mode = instance->model_exchange ? Fmi2Instance::Mode::kEvent : Fmi2Instance::Mode::kStep;
    return ToFmiStatus(instance, status);
}

fmi2Status fmi2EnterEventMode(fmi2Component c) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) return fmi2Fatal;
    if (!instance->model_exchange || instance->mode != Fmi2Instance::Mode::kContinuous) {
        Log(instance, fmi2Error, "logStatusError", "Event Mode requires Model Exchange Continuous-Time Mode");
        return fmi2Error;
    }
    const auto status = instance->runtime.EnterModelExchangeEventMode();
    if (status) instance->mode = Fmi2Instance::Mode::kEvent;
    return ToFmiStatus(instance, status);
}

fmi2Status fmi2NewDiscreteStates(fmi2Component c, fmi2EventInfo* eventInfo) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr || eventInfo == nullptr) return fmi2Fatal;
    if (!instance->model_exchange || instance->mode != Fmi2Instance::Mode::kEvent) {
        Log(instance, fmi2Error, "logStatusError", "newDiscreteStates requires Model Exchange Event Mode");
        return fmi2Error;
    }
    bool terminate = false;
    bool next_defined = false;
    bool next_update = false;
    bool nominals_changed = false;
    bool states_changed = false;
    double next_time = 0.0;
    const auto status = instance->runtime.UpdateDiscreteStates(
        &terminate, &next_defined, &next_time, &next_update, &nominals_changed, &states_changed);
    if (!status) return ToFmiStatus(instance, status);
    eventInfo->newDiscreteStatesNeeded = next_update ? fmi2True : fmi2False;
    eventInfo->terminateSimulation = terminate ? fmi2True : fmi2False;
    eventInfo->nominalsOfContinuousStatesChanged = nominals_changed ? fmi2True : fmi2False;
    eventInfo->valuesOfContinuousStatesChanged = states_changed ? fmi2True : fmi2False;
    eventInfo->nextEventTimeDefined = next_defined ? fmi2True : fmi2False;
    eventInfo->nextEventTime = next_defined ? next_time : 0.0;
    return fmi2OK;
}

fmi2Status fmi2EnterContinuousTimeMode(fmi2Component c) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) return fmi2Fatal;
    if (!instance->model_exchange || instance->mode != Fmi2Instance::Mode::kEvent) {
        Log(instance, fmi2Error, "logStatusError", "Continuous-Time Mode requires Model Exchange Event Mode");
        return fmi2Error;
    }
    const auto status = instance->runtime.EnterModelExchangeContinuousTimeMode();
    if (status) instance->mode = Fmi2Instance::Mode::kContinuous;
    return ToFmiStatus(instance, status);
}

fmi2Status fmi2SetTime(fmi2Component c, fmi2Real time) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) return fmi2Fatal;
    if (!instance->model_exchange
        || (instance->mode != Fmi2Instance::Mode::kContinuous && instance->mode != Fmi2Instance::Mode::kEvent)
        || !std::isfinite(time)) {
        Log(instance, fmi2Error, "logStatusError", "setTime requires Model Exchange Event or Continuous-Time Mode and a finite time");
        return fmi2Error;
    }
    const JsonObject arguments = {{"time", JsonValue(time)}};
    const auto result = instance->runtime.ModelExchangeCall("setTime", arguments);
    return result ? fmi2OK : ToFmiStatus(instance, result.status);
}

fmi2Status fmi2SetContinuousStates(fmi2Component c, const fmi2Real x[], size_t nx) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) return fmi2Fatal;
    if (!instance->model_exchange
        || (instance->mode != Fmi2Instance::Mode::kContinuous && instance->mode != Fmi2Instance::Mode::kEvent)
        || nx != instance->runtime.NumberOfContinuousStates()) return fmi2Error;
    return ModelExchangeVector(instance, "setContinuousStates", x, nullptr, nx);
}

fmi2Status fmi2GetContinuousStates(fmi2Component c, fmi2Real x[], size_t nx) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) return fmi2Fatal;
    if (!instance->model_exchange || !IsModelExchangeEvaluationMode(instance->mode)
        || nx != instance->runtime.NumberOfContinuousStates()) return fmi2Error;
    return ModelExchangeVector(instance, "getContinuousStates", nullptr, x, nx);
}

fmi2Status fmi2GetDerivatives(fmi2Component c, fmi2Real derivatives[], size_t nx) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) return fmi2Fatal;
    if (!instance->model_exchange || !IsModelExchangeEvaluationMode(instance->mode)
        || nx != instance->runtime.NumberOfContinuousStates()) return fmi2Error;
    return ModelExchangeVector(instance, "getDerivatives", nullptr, derivatives, nx);
}

fmi2Status fmi2GetEventIndicators(fmi2Component c, fmi2Real eventIndicators[], size_t ni) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) return fmi2Fatal;
    if (!instance->model_exchange || !IsModelExchangeEvaluationMode(instance->mode)
        || ni != instance->runtime.NumberOfEventIndicators()) return fmi2Error;
    return ModelExchangeVector(instance, "getEventIndicators", nullptr, eventIndicators, ni);
}

fmi2Status fmi2GetNominalsOfContinuousStates(fmi2Component c, fmi2Real x_nominal[], size_t nx) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) return fmi2Fatal;
    if (!instance->model_exchange
        || (instance->mode != Fmi2Instance::Mode::kContinuous && instance->mode != Fmi2Instance::Mode::kEvent)
        || nx != instance->runtime.NumberOfContinuousStates()) return fmi2Error;
    return ModelExchangeVector(instance, "getNominalsOfContinuousStates", nullptr, x_nominal, nx);
}

fmi2Status fmi2CompletedIntegratorStep(fmi2Component c,
                                        fmi2Boolean noSetFMUStatePriorToCurrentPoint,
                                        fmi2Boolean* enterEventMode,
                                        fmi2Boolean* terminateSimulation) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) return fmi2Fatal;
    if (!instance->model_exchange || instance->mode != Fmi2Instance::Mode::kContinuous) return fmi2Error;
    const JsonObject arguments = {{"noSetFMUStatePriorToCurrentPoint", JsonValue(noSetFMUStatePriorToCurrentPoint == fmi2True)}};
    const auto response = instance->runtime.ModelExchangeCall("completedIntegratorStep", arguments);
    if (!response) return ToFmiStatus(instance, response.status);
    const JsonValue* enter = FindObjectValue(response.value, "enterEventMode");
    const JsonValue* terminate = FindObjectValue(response.value, "terminateSimulation");
    if (enter == nullptr || !enter->IsBool() || terminate == nullptr || !terminate->IsBool()) return fmi2Error;
    if (enterEventMode != nullptr) *enterEventMode = enter->AsBool() ? fmi2True : fmi2False;
    if (terminateSimulation != nullptr) *terminateSimulation = terminate->AsBool() ? fmi2True : fmi2False;
    return fmi2OK;
}

fmi2Status fmi2Terminate(fmi2Component c) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    const auto status = instance->runtime.Terminate();
    if (status) {
        instance->mode = Fmi2Instance::Mode::kTerminated;
    }
    return ToFmiStatus(instance, status);
}

fmi2Status fmi2Reset(fmi2Component c) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    const auto status = instance->runtime.Reset();
    if (status) {
        instance->mode = Fmi2Instance::Mode::kInstantiated;
    }
    return ToFmiStatus(instance, status);
}

fmi2Status fmi2SetDebugLogging(fmi2Component c,
                               fmi2Boolean loggingOn,
                               size_t,
                               const fmi2String[]) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    instance->logging_enabled = loggingOn == fmi2True;
    return fmi2OK;
}

fmi2Status fmi2SetReal(fmi2Component c,
                       const fmi2ValueReference vr[],
                       size_t nvr,
                       const fmi2Real value[]) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    return ToFmiStatus(instance, instance->runtime.SetReal(vr, nvr, value));
}

fmi2Status fmi2SetInteger(fmi2Component c,
                          const fmi2ValueReference vr[],
                          size_t nvr,
                          const fmi2Integer value[]) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    return ToFmiStatus(instance, instance->runtime.SetInteger(vr, nvr, value));
}

fmi2Status fmi2SetBoolean(fmi2Component c,
                          const fmi2ValueReference vr[],
                          size_t nvr,
                          const fmi2Boolean value[]) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    std::unique_ptr<bool[]> converted(new bool[nvr]);
    for (size_t index = 0; index < nvr; ++index) {
        converted[index] = value[index] != fmi2False;
    }
    return ToFmiStatus(instance, instance->runtime.SetBoolean(vr, nvr, converted.get()));
}

fmi2Status fmi2SetString(fmi2Component c,
                         const fmi2ValueReference vr[],
                         size_t nvr,
                         const fmi2String value[]) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    return ToFmiStatus(instance, instance->runtime.SetString(vr, nvr, value));
}

fmi2Status fmi2GetFMUstate(fmi2Component c, fmi2FMUstate* value) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr || value == nullptr) {
        return fmi2Fatal;
    }
    *value = nullptr;
    std::string checkpoint;
    const OperationResult status = instance->runtime.CaptureFmuState(checkpoint);
    if (!status) {
        return ToFmiStatus(instance, status);
    }
    auto state = std::unique_ptr<Fmi2StateHandle>(new (std::nothrow) Fmi2StateHandle{
        std::move(checkpoint), instance->mode});
    if (!state) {
        return fmi2Error;
    }
    *value = static_cast<fmi2FMUstate>(state.release());
    return fmi2OK;
}

fmi2Status fmi2SetFMUstate(fmi2Component c, fmi2FMUstate value) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr || value == nullptr) {
        return fmi2Fatal;
    }
    const auto* state = static_cast<const Fmi2StateHandle*>(value);
    const auto status = instance->runtime.RestoreFmuState(state->checkpoint);
    if (status) {
        instance->mode = state->mode;
    }
    return ToFmiStatus(instance, status);
}

fmi2Status fmi2FreeFMUstate(fmi2Component c, fmi2FMUstate* value) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr || value == nullptr) {
        return fmi2Fatal;
    }
    delete static_cast<Fmi2StateHandle*>(*value);
    *value = nullptr;
    return fmi2OK;
}

fmi2Status fmi2SerializedFMUstateSize(fmi2Component c, fmi2FMUstate value, size_t* size) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr || size == nullptr || value == nullptr) {
        return fmi2Fatal;
    }
    const auto* state = static_cast<const Fmi2StateHandle*>(value);
    const std::string serialized = SerializeFmi2State(*state);
    if (serialized.size() > kMaximumSerializedStateTokenBytes) {
        Log(instance, fmi2Error, "logStatusError", "Serialized FMU state exceeds the supported size limit");
        return fmi2Error;
    }
    *size = serialized.size();
    return fmi2OK;
}

fmi2Status fmi2SerializeFMUstate(fmi2Component c,
                                 fmi2FMUstate value,
                                 fmi2Byte serialized_state[],
                                 size_t size) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr || value == nullptr || serialized_state == nullptr) {
        return fmi2Fatal;
    }
    const auto* state = static_cast<const Fmi2StateHandle*>(value);
    const std::string serialized = SerializeFmi2State(*state);
    if (serialized.size() > kMaximumSerializedStateTokenBytes || size != serialized.size()) {
        Log(instance, fmi2Error, "logStatusError", "Serialized FMU state buffer has the wrong size");
        return fmi2Error;
    }
    std::memcpy(serialized_state, serialized.data(), size);
    return fmi2OK;
}

fmi2Status fmi2DeSerializeFMUstate(fmi2Component c,
                                   const fmi2Byte serialized_state[],
                                   size_t size,
                                   fmi2FMUstate* value) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr || value == nullptr) {
        return fmi2Fatal;
    }
    *value = nullptr;
    if (size == 0 || size > kMaximumSerializedStateTokenBytes) {
        Log(instance, fmi2Error, "logStatusError", "Serialized FMU state token has an invalid size");
        return fmi2Error;
    }
    if (serialized_state == nullptr) {
        return fmi2Fatal;
    }
    std::string serialized(reinterpret_cast<const char*>(serialized_state), size);
    auto state = std::unique_ptr<Fmi2StateHandle>(new (std::nothrow) Fmi2StateHandle());
    if (!state || !ParseFmi2State(serialized, state.get())) {
        Log(instance, fmi2Error, "logStatusError", "Serialized FMU state token is invalid");
        return fmi2Error;
    }
    *value = static_cast<fmi2FMUstate>(state.release());
    return fmi2OK;
}

fmi2Status fmi2GetDirectionalDerivative(fmi2Component c,
                                        const fmi2ValueReference[],
                                        size_t,
                                        const fmi2ValueReference[],
                                        size_t,
                                        const fmi2Real[],
                                        fmi2Real[]) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    Log(instance, fmi2Error, "logStatusError", "Directional derivatives are not supported");
    return fmi2Error;
}

fmi2Status fmi2GetReal(fmi2Component c,
                       const fmi2ValueReference vr[],
                       size_t nvr,
                       fmi2Real value[]) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    return ToFmiStatus(instance, instance->runtime.GetReal(vr, nvr, value));
}

fmi2Status fmi2GetInteger(fmi2Component c,
                          const fmi2ValueReference vr[],
                          size_t nvr,
                          fmi2Integer value[]) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    return ToFmiStatus(instance, instance->runtime.GetInteger(vr, nvr, value));
}

fmi2Status fmi2GetBoolean(fmi2Component c,
                          const fmi2ValueReference vr[],
                          size_t nvr,
                          fmi2Boolean value[]) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    std::unique_ptr<bool[]> converted(new bool[nvr]);
    const fmi2Status status = ToFmiStatus(instance, instance->runtime.GetBoolean(vr, nvr, converted.get()));
    if (status != fmi2OK) {
        return status;
    }
    for (size_t index = 0; index < nvr; ++index) {
        value[index] = converted[index] ? fmi2True : fmi2False;
    }
    return fmi2OK;
}

fmi2Status fmi2GetString(fmi2Component c,
                         const fmi2ValueReference vr[],
                         size_t nvr,
                         fmi2String value[]) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    return ToFmiStatus(instance, instance->runtime.GetString(vr, nvr, value));
}

fmi2Status fmi2DoStep(fmi2Component c,
                      fmi2Real currentCommunicationPoint,
                      fmi2Real communicationStepSize,
                      fmi2Boolean) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    const auto status = instance->runtime.DoStep(currentCommunicationPoint, communicationStepSize);
    const auto fmi_status = ToFmiStatus(instance, status);
    if (fmi_status != fmi2OK) {
        return fmi_status;
    }
    return instance->runtime.LastStepEarlyReturn() || instance->runtime.LastStepTerminated()
        ? fmi2Discard
        : fmi2OK;
}

fmi2Status fmi2CancelStep(fmi2Component) {
    return fmi2Error;
}

fmi2Status fmi2GetStatus(fmi2Component c, const fmi2StatusKind s, fmi2Status* value) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr || value == nullptr) {
        return fmi2Fatal;
    }
    if (s == fmi2DoStepStatus) {
        *value = fmi2OK;
        return fmi2OK;
    }
    return fmi2Discard;
}

fmi2Status fmi2GetRealStatus(fmi2Component c, const fmi2StatusKind s, fmi2Real* value) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr || value == nullptr) {
        return fmi2Fatal;
    }
    if (s == fmi2LastSuccessfulTime) {
        *value = instance->runtime.CurrentTime();
        return fmi2OK;
    }
    return fmi2Discard;
}

fmi2Status fmi2GetIntegerStatus(fmi2Component, const fmi2StatusKind, fmi2Integer*) {
    return fmi2Discard;
}

fmi2Status fmi2GetBooleanStatus(fmi2Component c, const fmi2StatusKind s, fmi2Boolean* value) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr || value == nullptr) {
        return fmi2Fatal;
    }
    if (s == fmi2Terminated) {
        *value = instance->runtime.LastStepTerminated() ? fmi2True : fmi2False;
        return fmi2OK;
    }
    return fmi2Discard;
}

fmi2Status fmi2GetStringStatus(fmi2Component c, const fmi2StatusKind, fmi2String* value) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr || value == nullptr) {
        return fmi2Fatal;
    }
    instance->last_string_status = instance->runtime.LastError();
    *value = instance->last_string_status.empty() ? "" : instance->last_string_status.c_str();
    return fmi2OK;
}

fmi2Status fmi2SetRealInputDerivatives(fmi2Component,
                                       const fmi2ValueReference[],
                                       size_t,
                                       const fmi2Integer[],
                                       const fmi2Real[]) {
    return fmi2Error;
}

fmi2Status fmi2GetRealOutputDerivatives(fmi2Component,
                                        const fmi2ValueReference[],
                                        size_t,
                                        const fmi2Integer[],
                                        fmi2Real[]) {
    return fmi2Error;
}

}  // extern "C"
