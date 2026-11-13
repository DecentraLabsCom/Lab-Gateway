#include "fmi3/fmi3Functions.h"

#include <limits>
#include <cmath>
#include <cstring>
#include <memory>
#include <new>
#include <string>
#include <type_traits>
#include <vector>

#include "decentralabs_proxy/runtime.hpp"

namespace decentralabs::proxy {

namespace {

enum class Fmi3Mode {
    kInstantiated,
    kConfiguration,
    kInitialization,
    kEvent,
    kStep,
    kContinuous,
    kTerminated,
};

struct Fmi3Instance {
    fmi3InstanceEnvironment environment = nullptr;
    fmi3LogMessageCallback logger = nullptr;
    bool logging_enabled = false;
    bool event_mode_used = false;
    bool model_exchange = false;
    bool event_mode_pending = false;
    Fmi3Mode configuration_return_mode = Fmi3Mode::kInstantiated;
    Fmi3Mode mode = Fmi3Mode::kInstantiated;
    std::string instance_name;
    ProxyRuntime runtime;
    std::vector<std::string> string_cache;
};

struct Fmi3StateHandle {
    std::string checkpoint;
    Fmi3Mode mode = Fmi3Mode::kStep;
    Fmi3Mode configuration_return_mode = Fmi3Mode::kInstantiated;
    bool event_mode_pending = false;
};

bool IsModelExchangeEvaluationMode(const Fmi3Mode mode) {
    return mode == Fmi3Mode::kInitialization
        || mode == Fmi3Mode::kEvent
        || mode == Fmi3Mode::kContinuous;
}

constexpr size_t kMaximumSerializedStateTokenBytes = 16 * 1024 * 1024;

std::string SerializeFmi3State(const Fmi3StateHandle& state) {
    JsonObject object = {
        {"checkpoint", JsonValue(state.checkpoint)},
        {"mode", JsonValue(static_cast<int>(state.mode))},
        {"configurationReturnMode", JsonValue(static_cast<int>(state.configuration_return_mode))},
        {"eventModePending", JsonValue(state.event_mode_pending)},
    };
    return SerializeJson(JsonValue(std::move(object)));
}

bool ParseFmi3State(const std::string& serialized, Fmi3StateHandle* state) {
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
    const JsonValue* return_mode = FindObjectValue(*object, "configurationReturnMode");
    const JsonValue* pending = FindObjectValue(*object, "eventModePending");
    if (checkpoint == nullptr || !checkpoint->IsString()
        || mode == nullptr || !mode->IsNumber()
        || return_mode == nullptr || !return_mode->IsNumber()
        || pending == nullptr || !pending->IsBool()) {
        return false;
    }
    const double raw_mode = mode->AsNumber(-1.0);
    const double raw_return_mode = return_mode->AsNumber(-1.0);
    if (raw_mode < 0 || raw_mode > static_cast<int>(Fmi3Mode::kTerminated)
        || std::floor(raw_mode) != raw_mode
        || raw_return_mode < 0 || raw_return_mode > static_cast<int>(Fmi3Mode::kTerminated)
        || std::floor(raw_return_mode) != raw_return_mode) {
        return false;
    }
    state->checkpoint = checkpoint->AsString();
    state->mode = static_cast<Fmi3Mode>(static_cast<int>(raw_mode));
    state->configuration_return_mode = static_cast<Fmi3Mode>(static_cast<int>(raw_return_mode));
    state->event_mode_pending = pending->AsBool();
    return true;
}

Fmi3Instance* AsInstance(fmi3Instance instance) {
    return static_cast<Fmi3Instance*>(instance);
}

bool HasClock(const Fmi3Instance* instance) {
    if (instance == nullptr) {
        return false;
    }
    const auto& variables = instance->runtime.Model().variables;
    for (const auto& variable : variables) {
        if (variable.type == ScalarType::kClock) {
            return true;
        }
    }
    return false;
}

bool HasStructuralParameter(const Fmi3Instance* instance, const bool tunable_only) {
    if (instance == nullptr) {
        return false;
    }
    const auto& variables = instance->runtime.Model().variables;
    for (const auto& variable : variables) {
        if (variable.causality == "structuralParameter"
            && (!tunable_only || variable.variability == "tunable")) {
            return true;
        }
    }
    return false;
}

void Log(Fmi3Instance* instance, const fmi3Status status, const char* category, const std::string& message) {
    if (instance == nullptr || instance->logger == nullptr) {
        return;
    }
    instance->logger(
        instance->environment,
        status,
        category,
        message.c_str());
}

fmi3Status ToFmiStatus(Fmi3Instance* instance, const OperationResult& status) {
    if (status) {
        return fmi3OK;
    }
    if (status.code == "INPUT_UPDATE_RATE_LIMIT" || status.code == "OUTPUT_READ_RATE_LIMITED"
        || status.code == "NO_ADVANCE") {
        Log(instance, fmi3Warning, "logStatusWarning", status.message);
        return fmi3Discard;
    }
    Log(instance, fmi3Error, "logStatusError", status.message);
    return fmi3Error;
}

void AttachLogger(Fmi3Instance* instance) {
    instance->runtime.SetLogger([instance](const std::string& category, const std::string& message) {
        if (instance->logging_enabled) {
            Log(instance, fmi3OK, category.c_str(), message);
        }
    });
}

fmi3Status Unsupported(Fmi3Instance* instance, const std::string& message) {
    Log(instance, fmi3Error, "logStatusError", message);
    return fmi3Error;
}

bool ValidateValueCounts(Fmi3Instance* instance,
                         const fmi3ValueReference valueReferences[],
                         const size_t nValueReferences,
                         const size_t nValues) {
    if (instance == nullptr) {
        return false;
    }
    std::size_t expected = 0;
    if (instance->runtime.TryExpectedValueCount(valueReferences, nValueReferences, &expected) && expected == nValues) {
        return true;
    }
    Log(instance, fmi3Error, "logStatusError", "FMI 3 value buffer length does not match referenced scalar/array variables");
    return false;
}

template <typename FmiInteger>
fmi3Status GetSignedIntegerValues(Fmi3Instance* instance,
                                  const fmi3ValueReference valueReferences[],
                                  const size_t nValueReferences,
                                  FmiInteger values[],
                                  const size_t nValues) {
    if (instance == nullptr || (nValues > 0 && values == nullptr)) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(instance, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    std::vector<std::int64_t> temp(nValues);
    const auto status = instance->runtime.GetSignedInteger(valueReferences, nValueReferences, temp.data(), nValues);
    if (!status) {
        return ToFmiStatus(instance, status);
    }
    for (size_t index = 0; index < nValues; ++index) {
        if (temp[index] < static_cast<std::int64_t>(std::numeric_limits<FmiInteger>::min()) ||
            temp[index] > static_cast<std::int64_t>(std::numeric_limits<FmiInteger>::max())) {
            Log(instance, fmi3Error, "logStatusError", "Cached integer value does not fit the requested FMI 3 integer width");
            return fmi3Error;
        }
        values[index] = static_cast<FmiInteger>(temp[index]);
    }
    return fmi3OK;
}

template <typename FmiInteger>
fmi3Status GetUnsignedIntegerValues(Fmi3Instance* instance,
                                    const fmi3ValueReference valueReferences[],
                                    const size_t nValueReferences,
                                    FmiInteger values[],
                                    const size_t nValues) {
    if (instance == nullptr || (nValues > 0 && values == nullptr)) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(instance, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    std::vector<std::uint64_t> temp(nValues);
    const auto status = instance->runtime.GetUnsignedInteger(valueReferences, nValueReferences, temp.data(), nValues);
    if (!status) {
        return ToFmiStatus(instance, status);
    }
    for (size_t index = 0; index < nValues; ++index) {
        if (temp[index] > static_cast<std::uint64_t>(std::numeric_limits<FmiInteger>::max())) {
            Log(instance, fmi3Error, "logStatusError", "Cached unsigned integer value does not fit the requested FMI 3 integer width");
            return fmi3Error;
        }
        values[index] = static_cast<FmiInteger>(temp[index]);
    }
    return fmi3OK;
}

template <typename FmiInteger>
fmi3Status SetSignedIntegerValues(Fmi3Instance* instance,
                                  const fmi3ValueReference valueReferences[],
                                  const size_t nValueReferences,
                                  const FmiInteger values[],
                                  const size_t nValues) {
    if (instance == nullptr || (nValues > 0 && values == nullptr)) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(instance, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    std::vector<std::int64_t> temp(nValues);
    for (size_t index = 0; index < nValues; ++index) {
        temp[index] = static_cast<std::int64_t>(values[index]);
    }
    return ToFmiStatus(instance, instance->runtime.SetSignedInteger(valueReferences, nValueReferences, temp.data(), nValues));
}

template <typename FmiInteger>
fmi3Status SetUnsignedIntegerValues(Fmi3Instance* instance,
                                    const fmi3ValueReference valueReferences[],
                                    const size_t nValueReferences,
                                    const FmiInteger values[],
                                    const size_t nValues) {
    if (instance == nullptr || (nValues > 0 && values == nullptr)) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(instance, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    std::vector<std::uint64_t> temp(nValues);
    for (size_t index = 0; index < nValues; ++index) {
        temp[index] = static_cast<std::uint64_t>(values[index]);
    }
    return ToFmiStatus(instance, instance->runtime.SetUnsignedInteger(valueReferences, nValueReferences, temp.data(), nValues));
}

fmi3Status ModelExchangeVector(Fmi3Instance* instance,
                               const std::string& operation,
                               const fmi3Float64 input[],
                               fmi3Float64 output[],
                               const size_t count) {
    if (instance == nullptr || (count > 0 && input != nullptr && operation != "setContinuousStates")
        || (count > 0 && output != nullptr && operation == "setContinuousStates")) {
        return fmi3Fatal;
    }
    JsonObject arguments;
    if (operation == "setContinuousStates") {
        if (count > 0 && input == nullptr) return fmi3Fatal;
        JsonArray values;
        values.reserve(count);
        for (size_t index = 0; index < count; ++index) {
            if (!std::isfinite(input[index])) return fmi3Error;
            values.emplace_back(input[index]);
        }
        arguments.emplace("values", JsonValue(std::move(values)));
    } else if (count > 0 && output == nullptr) {
        return fmi3Fatal;
    }
    const auto response = instance->runtime.ModelExchangeCall(operation, arguments);
    if (!response) return ToFmiStatus(instance, response.status);
    if (operation == "setContinuousStates") return fmi3OK;
    const JsonValue* raw_values = FindObjectValue(response.value, "values");
    const JsonArray* values = raw_values == nullptr ? nullptr : raw_values->AsArray();
    if (values == nullptr || values->size() != count) {
        return Unsupported(instance, "Gateway returned an invalid Model Exchange vector");
    }
    for (size_t index = 0; index < count; ++index) {
        if (!(*values)[index].IsNumber() || !std::isfinite((*values)[index].AsNumber())) {
            return Unsupported(instance, "Gateway returned a non-finite Model Exchange vector value");
        }
        output[index] = (*values)[index].AsNumber();
    }
    return fmi3OK;
}

fmi3Status ModelExchangeSetTime(Fmi3Instance* instance, const fmi3Float64 time) {
    if (instance == nullptr || !std::isfinite(time)) return fmi3Fatal;
    const JsonObject arguments = {{"time", JsonValue(time)}};
    const auto response = instance->runtime.ModelExchangeCall("setTime", arguments);
    return response ? fmi3OK : ToFmiStatus(instance, response.status);
}

}  // namespace

}  // namespace decentralabs::proxy

using decentralabs::proxy::AsInstance;
using decentralabs::proxy::AttachLogger;
using decentralabs::proxy::Fmi3Mode;
using decentralabs::proxy::Fmi3Instance;
using decentralabs::proxy::Fmi3StateHandle;
using decentralabs::proxy::FindObjectValue;
using decentralabs::proxy::HasClock;
using decentralabs::proxy::kMaximumSerializedStateTokenBytes;
using decentralabs::proxy::JsonObject;
using decentralabs::proxy::JsonValue;
using decentralabs::proxy::OperationResult;
using decentralabs::proxy::ParseJson;
using decentralabs::proxy::ToFmiStatus;
using decentralabs::proxy::Unsupported;
using decentralabs::proxy::ValidateValueCounts;

extern "C" {

const char* fmi3GetVersion(void) {
    return "3.0";
}

fmi3Status fmi3SetDebugLogging(
    fmi3Instance instance,
    fmi3Boolean loggingOn,
    size_t,
    const fmi3String[]) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    impl->logging_enabled = loggingOn != fmi3False;
    return fmi3OK;
}

fmi3Instance fmi3InstantiateCoSimulation(
    fmi3String instanceName,
    fmi3String,
    fmi3String resourcePath,
    fmi3Boolean,
    fmi3Boolean loggingOn,
    fmi3Boolean eventModeUsed,
    fmi3Boolean earlyReturnAllowed,
    const fmi3ValueReference[],
    size_t,
    fmi3InstanceEnvironment instanceEnvironment,
    fmi3LogMessageCallback logMessage,
    fmi3IntermediateUpdateCallback) {
    if (instanceName == nullptr || resourcePath == nullptr) {
        return nullptr;
    }

    auto* instance = new Fmi3Instance();
    instance->environment = instanceEnvironment;
    instance->logger = logMessage;
    instance->logging_enabled = loggingOn != fmi3False;
    instance->event_mode_used = eventModeUsed != fmi3False;
    instance->instance_name = instanceName;
    AttachLogger(instance);

    const OperationResult status = instance->runtime.Configure(instanceName, resourcePath);
    if (!status) {
        Log(instance, fmi3Error, "logStatusError", status.message);
        delete instance;
        return nullptr;
    }
    if (HasClock(instance) && !instance->event_mode_used) {
        Log(instance, fmi3Error, "logStatusError", "Clock variables require Event Mode to be negotiated at instantiation");
        delete instance;
        return nullptr;
    }
    instance->runtime.SetEarlyReturnAllowed(earlyReturnAllowed != fmi3False);
    return instance;
}

fmi3Instance fmi3InstantiateModelExchange(
    fmi3String instanceName,
    fmi3String,
    fmi3String resourcePath,
    fmi3Boolean,
    fmi3Boolean loggingOn,
    fmi3InstanceEnvironment instanceEnvironment,
    fmi3LogMessageCallback logMessage) {
    if (instanceName == nullptr || resourcePath == nullptr) return nullptr;
    auto* instance = new (std::nothrow) Fmi3Instance();
    if (instance == nullptr) return nullptr;
    instance->environment = instanceEnvironment;
    instance->logger = logMessage;
    instance->logging_enabled = loggingOn != fmi3False;
    instance->event_mode_used = true;
    instance->model_exchange = true;
    instance->instance_name = instanceName;
    AttachLogger(instance);
    auto status = instance->runtime.Configure(instanceName, resourcePath);
    if (status) status = instance->runtime.SetModelExchangeMode(true);
    if (!status) {
        Log(instance, fmi3Error, "logStatusError", status.message);
        delete instance;
        return nullptr;
    }
    return instance;
}

FMI3_Export fmi3Instance fmi3InstantiateScheduledExecution(...) {
    return nullptr;
}

void fmi3FreeInstance(fmi3Instance instance) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return;
    }
    const auto status = impl->runtime.Close();
    if (!status) {
        Log(impl, fmi3Warning, "logStatusError", status.message);
    }
    delete impl;
}

fmi3Status fmi3EnterInitializationMode(
    fmi3Instance instance,
    fmi3Boolean,
    fmi3Float64,
    fmi3Float64 startTime,
    fmi3Boolean stopTimeDefined,
    fmi3Float64 stopTime) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    if (impl->mode != Fmi3Mode::kInstantiated) {
        return Unsupported(impl, "Initialization Mode can only be entered from Instantiated Mode");
    }
    const auto& model = impl->runtime.Model();
    const std::optional<double> effective_stop = stopTimeDefined != fmi3False
        ? std::optional<double>(stopTime)
        : std::nullopt;
    const double step = model.default_step_size.value_or(0.01);
    auto status = impl->runtime.SetupExperiment(startTime, effective_stop, step);
    if (!status) {
        return ToFmiStatus(impl, status);
    }
    const auto init_status = impl->runtime.EnterInitializationMode();
    if (!init_status) {
        return ToFmiStatus(impl, init_status);
    }
    impl->mode = Fmi3Mode::kInitialization;
    return fmi3OK;
}

fmi3Status fmi3ExitInitializationMode(fmi3Instance instance) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    if (impl->mode != Fmi3Mode::kInitialization) {
        return Unsupported(impl, "Initialization Mode has not been entered");
    }
    const auto status = impl->runtime.ExitInitializationMode();
    if (!status) {
        return ToFmiStatus(impl, status);
    }
    impl->mode = (impl->model_exchange || impl->event_mode_used) ? Fmi3Mode::kEvent : Fmi3Mode::kStep;
    return fmi3OK;
}

fmi3Status fmi3EnterEventMode(fmi3Instance instance) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    if (impl->model_exchange) {
        if (impl->mode != Fmi3Mode::kContinuous) {
            return Unsupported(impl, "Model Exchange Event Mode can only be entered from Continuous-Time Mode");
        }
        const auto status = impl->runtime.EnterModelExchangeEventMode();
        if (!status) return ToFmiStatus(impl, status);
    } else if (!impl->event_mode_used || impl->mode != Fmi3Mode::kStep) {
        return Unsupported(impl, "Event Mode can only be entered from Step Mode when Event Mode is enabled");
    }
    impl->event_mode_pending = false;
    impl->mode = Fmi3Mode::kEvent;
    return fmi3OK;
}

fmi3Status fmi3EnterConfigurationMode(fmi3Instance instance) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    const bool initialization_configuration = impl->mode == Fmi3Mode::kInstantiated;
    const bool model_exchange_reconfiguration = impl->model_exchange && impl->mode == Fmi3Mode::kEvent;
    const bool co_simulation_reconfiguration = !impl->model_exchange && impl->mode == Fmi3Mode::kStep;
    if (!initialization_configuration && !model_exchange_reconfiguration && !co_simulation_reconfiguration) {
        return Unsupported(impl, "Reconfiguration Mode requires a tunable structural parameter and an allowed FMI mode");
    }
    if (!HasStructuralParameter(impl, !initialization_configuration)) {
        return Unsupported(
            impl,
            initialization_configuration
                ? "Configuration Mode requires a structural parameter"
                : "Reconfiguration Mode requires a tunable structural parameter");
    }
    const auto status = impl->runtime.EnterConfigurationMode();
    if (!status) {
        return ToFmiStatus(impl, status);
    }
    impl->configuration_return_mode = impl->mode;
    impl->mode = Fmi3Mode::kConfiguration;
    return fmi3OK;
}

fmi3Status fmi3ExitConfigurationMode(fmi3Instance instance) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    if (impl->mode != Fmi3Mode::kConfiguration) {
        return Unsupported(impl, "Configuration Mode has not been entered");
    }
    const auto status = impl->runtime.ExitConfigurationMode();
    if (!status) {
        return ToFmiStatus(impl, status);
    }
    impl->mode = impl->configuration_return_mode;
    impl->configuration_return_mode = Fmi3Mode::kInstantiated;
    return fmi3OK;
}

fmi3Status fmi3EnterStepMode(fmi3Instance instance) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    if (impl->model_exchange || impl->mode != Fmi3Mode::kEvent) {
        return Unsupported(impl, "Step Mode can only be entered from Event Mode");
    }
    impl->mode = Fmi3Mode::kStep;
    return fmi3OK;
}

fmi3Status fmi3UpdateDiscreteStates(
    fmi3Instance instance,
    fmi3Boolean* discreteStatesNeedUpdate,
    fmi3Boolean* terminateSimulation,
    fmi3Boolean* nominalsOfContinuousStatesChanged,
    fmi3Boolean* valuesOfContinuousStatesChanged,
    fmi3Boolean* nextEventTimeDefined,
    fmi3Float64* nextEventTime) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    if (impl->mode != Fmi3Mode::kEvent) {
        return Unsupported(impl, "Discrete states can only be updated in Event Mode");
    }
    bool terminate = false;
    bool next_event_time_defined = false;
    double next_event_time = 0.0;
    bool discrete_states_need_update = false;
    bool nominal_states_changed = false;
    bool continuous_states_changed = false;
    const auto status = impl->runtime.UpdateDiscreteStates(
        &terminate,
        &next_event_time_defined,
        &next_event_time,
        &discrete_states_need_update,
        &nominal_states_changed,
        &continuous_states_changed);
    if (!status) {
        return ToFmiStatus(impl, status);
    }
    if (discreteStatesNeedUpdate != nullptr) *discreteStatesNeedUpdate = discrete_states_need_update ? fmi3True : fmi3False;
    if (terminateSimulation != nullptr) *terminateSimulation = terminate ? fmi3True : fmi3False;
    if (nominalsOfContinuousStatesChanged != nullptr) *nominalsOfContinuousStatesChanged = nominal_states_changed ? fmi3True : fmi3False;
    if (valuesOfContinuousStatesChanged != nullptr) *valuesOfContinuousStatesChanged = continuous_states_changed ? fmi3True : fmi3False;
    if (nextEventTimeDefined != nullptr) *nextEventTimeDefined = next_event_time_defined ? fmi3True : fmi3False;
    if (nextEventTime != nullptr) *nextEventTime = next_event_time_defined ? next_event_time : 0.0;
    return fmi3OK;
}

fmi3Status fmi3EnterContinuousTimeMode(fmi3Instance instance) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) return fmi3Fatal;
    if (!impl->model_exchange || impl->mode != Fmi3Mode::kEvent) {
        return Unsupported(impl, "Continuous-Time Mode can only be entered from Event Mode for Model Exchange");
    }
    const auto status = impl->runtime.EnterModelExchangeContinuousTimeMode();
    if (!status) return ToFmiStatus(impl, status);
    impl->mode = Fmi3Mode::kContinuous;
    return fmi3OK;
}

fmi3Status fmi3CompletedIntegratorStep(
    fmi3Instance instance,
    fmi3Boolean noSetFMUStatePriorToCurrentPoint,
    fmi3Boolean* enterEventMode,
    fmi3Boolean* terminateSimulation) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) return fmi3Fatal;
    if (!impl->model_exchange || impl->mode != Fmi3Mode::kContinuous) {
        return Unsupported(impl, "completedIntegratorStep requires Model Exchange Continuous-Time Mode");
    }
    const JsonObject arguments = {
        {"noSetFMUStatePriorToCurrentPoint", JsonValue(noSetFMUStatePriorToCurrentPoint != fmi3False)},
    };
    const auto response = impl->runtime.ModelExchangeCall("completedIntegratorStep", arguments);
    if (!response) return ToFmiStatus(impl, response.status);
    const JsonValue* enter = FindObjectValue(response.value, "enterEventMode");
    const JsonValue* terminate = FindObjectValue(response.value, "terminateSimulation");
    if (enter == nullptr || !enter->IsBool() || terminate == nullptr || !terminate->IsBool()) {
        return Unsupported(impl, "Gateway returned invalid completedIntegratorStep flags");
    }
    if (enterEventMode != nullptr) *enterEventMode = enter->AsBool() ? fmi3True : fmi3False;
    if (terminateSimulation != nullptr) *terminateSimulation = terminate->AsBool() ? fmi3True : fmi3False;
    return fmi3OK;
}

fmi3Status fmi3SetTime(fmi3Instance instance, fmi3Float64 time) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) return fmi3Fatal;
    if (!impl->model_exchange || impl->mode != Fmi3Mode::kContinuous) {
        return Unsupported(impl, "setTime requires Model Exchange Continuous-Time Mode");
    }
    return ModelExchangeSetTime(impl, time);
}

fmi3Status fmi3GetNumberOfContinuousStates(fmi3Instance instance, size_t* nContinuousStates) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || nContinuousStates == nullptr) return fmi3Fatal;
    if (!impl->model_exchange) return Unsupported(impl, "Continuous states are available only for Model Exchange");
    *nContinuousStates = impl->runtime.NumberOfContinuousStates();
    return fmi3OK;
}

fmi3Status fmi3GetNumberOfEventIndicators(fmi3Instance instance, size_t* nEventIndicators) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || nEventIndicators == nullptr) return fmi3Fatal;
    if (!impl->model_exchange) return Unsupported(impl, "Event indicators are available only for Model Exchange");
    *nEventIndicators = impl->runtime.NumberOfEventIndicators();
    return fmi3OK;
}

fmi3Status fmi3GetContinuousStates(fmi3Instance instance, fmi3Float64 continuousStates[], size_t nContinuousStates) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) return fmi3Fatal;
    if (!impl->model_exchange || !IsModelExchangeEvaluationMode(impl->mode)
        || nContinuousStates != impl->runtime.NumberOfContinuousStates()) {
        return Unsupported(impl, "getContinuousStates received an invalid mode or vector size");
    }
    return ModelExchangeVector(impl, "getContinuousStates", nullptr, continuousStates, nContinuousStates);
}

fmi3Status fmi3SetContinuousStates(fmi3Instance instance, const fmi3Float64 continuousStates[], size_t nContinuousStates) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) return fmi3Fatal;
    if (!impl->model_exchange || impl->mode != Fmi3Mode::kContinuous
        || nContinuousStates != impl->runtime.NumberOfContinuousStates()) {
        return Unsupported(impl, "setContinuousStates received an invalid mode or vector size");
    }
    return ModelExchangeVector(impl, "setContinuousStates", continuousStates, nullptr, nContinuousStates);
}

fmi3Status fmi3GetContinuousStateDerivatives(fmi3Instance instance, fmi3Float64 derivatives[], size_t nContinuousStates) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) return fmi3Fatal;
    if (!impl->model_exchange || !IsModelExchangeEvaluationMode(impl->mode)
        || nContinuousStates != impl->runtime.NumberOfContinuousStates()) {
        return Unsupported(impl, "getContinuousStateDerivatives received an invalid mode or vector size");
    }
    return ModelExchangeVector(impl, "getContinuousStateDerivatives", nullptr, derivatives, nContinuousStates);
}

fmi3Status fmi3GetEventIndicators(fmi3Instance instance, fmi3Float64 eventIndicators[], size_t nEventIndicators) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) return fmi3Fatal;
    if (!impl->model_exchange || !IsModelExchangeEvaluationMode(impl->mode)
        || nEventIndicators != impl->runtime.NumberOfEventIndicators()) {
        return Unsupported(impl, "getEventIndicators received an invalid mode or vector size");
    }
    return ModelExchangeVector(impl, "getEventIndicators", nullptr, eventIndicators, nEventIndicators);
}

fmi3Status fmi3GetNominalsOfContinuousStates(fmi3Instance instance, fmi3Float64 nominals[], size_t nContinuousStates) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) return fmi3Fatal;
    if (!impl->model_exchange
        || (impl->mode != Fmi3Mode::kInitialization
            && impl->mode != Fmi3Mode::kEvent
            && impl->mode != Fmi3Mode::kContinuous)
        || nContinuousStates != impl->runtime.NumberOfContinuousStates()) {
        return Unsupported(impl, "getNominalsOfContinuousStates received an invalid mode or vector size");
    }
    return ModelExchangeVector(impl, "getNominalsOfContinuousStates", nullptr, nominals, nContinuousStates);
}

fmi3Status fmi3Terminate(fmi3Instance instance) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    const auto status = impl->runtime.Terminate();
    if (!status) {
        return ToFmiStatus(impl, status);
    }
    impl->mode = Fmi3Mode::kTerminated;
    return fmi3OK;
}

fmi3Status fmi3Reset(fmi3Instance instance) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    const auto status = impl->runtime.Reset();
    if (!status) {
        return ToFmiStatus(impl, status);
    }
    impl->event_mode_pending = false;
    impl->configuration_return_mode = Fmi3Mode::kInstantiated;
    impl->mode = Fmi3Mode::kInstantiated;
    return fmi3OK;
}

fmi3Status fmi3GetFloat32(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Float32 values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || (nValues > 0 && values == nullptr)) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    std::vector<double> temp(nValues);
    const auto status = impl->runtime.GetReal(valueReferences, nValueReferences, temp.data(), nValues);
    if (!status) {
        return ToFmiStatus(impl, status);
    }
    for (size_t index = 0; index < nValues; ++index) {
        values[index] = static_cast<fmi3Float32>(temp[index]);
    }
    return fmi3OK;
}

fmi3Status fmi3GetFloat64(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Float64 values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    return ToFmiStatus(impl, impl->runtime.GetReal(valueReferences, nValueReferences, values, nValues));
}

fmi3Status fmi3GetInt32(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Int32 values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    return ToFmiStatus(impl, impl->runtime.GetInteger(valueReferences, nValueReferences, values, nValues));
}

fmi3Status fmi3GetInt8(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Int8 values[],
    size_t nValues) {
    return GetSignedIntegerValues(AsInstance(instance), valueReferences, nValueReferences, values, nValues);
}

fmi3Status fmi3GetInt16(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Int16 values[],
    size_t nValues) {
    return GetSignedIntegerValues(AsInstance(instance), valueReferences, nValueReferences, values, nValues);
}

fmi3Status fmi3GetInt64(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Int64 values[],
    size_t nValues) {
    return GetSignedIntegerValues(AsInstance(instance), valueReferences, nValueReferences, values, nValues);
}

fmi3Status fmi3GetUInt32(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3UInt32 values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || (nValues > 0 && values == nullptr)) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    std::vector<std::uint64_t> temp(nValues);
    const auto status = impl->runtime.GetUnsignedInteger(valueReferences, nValueReferences, temp.data(), nValues);
    if (!status) {
        return ToFmiStatus(impl, status);
    }
    for (size_t index = 0; index < nValues; ++index) {
        values[index] = static_cast<fmi3UInt32>(temp[index]);
    }
    return fmi3OK;
}

fmi3Status fmi3GetUInt8(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3UInt8 values[],
    size_t nValues) {
    return GetUnsignedIntegerValues(AsInstance(instance), valueReferences, nValueReferences, values, nValues);
}

fmi3Status fmi3GetUInt16(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3UInt16 values[],
    size_t nValues) {
    return GetUnsignedIntegerValues(AsInstance(instance), valueReferences, nValueReferences, values, nValues);
}

fmi3Status fmi3GetUInt64(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3UInt64 values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || (nValues > 0 && values == nullptr)) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    return ToFmiStatus(impl, impl->runtime.GetUnsignedInteger(valueReferences, nValueReferences, values, nValues));
}

fmi3Status fmi3GetBoolean(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Boolean values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || (nValues > 0 && values == nullptr)) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    std::unique_ptr<bool[]> buffer(new bool[nValues]);
    const auto status = impl->runtime.GetBoolean(valueReferences, nValueReferences, buffer.get(), nValues);
    if (!status) {
        return ToFmiStatus(impl, status);
    }
    for (size_t index = 0; index < nValues; ++index) {
        values[index] = buffer[index] ? fmi3True : fmi3False;
    }
    return fmi3OK;
}

fmi3Status fmi3GetString(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3String values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    std::vector<const char*> raw(nValues);
    const auto status = impl->runtime.GetString(valueReferences, nValueReferences, raw.data(), nValues);
    if (!status) {
        return ToFmiStatus(impl, status);
    }
    for (size_t index = 0; index < nValues; ++index) {
        values[index] = raw[index];
    }
    return fmi3OK;
}

fmi3Status fmi3GetBinary(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    size_t valueSizes[],
    fmi3Binary values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || (nValues > 0 && (valueSizes == nullptr || values == nullptr))) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    return ToFmiStatus(impl, impl->runtime.GetBinary(valueReferences, nValueReferences, valueSizes, values, nValues));
}

fmi3Status fmi3GetClock(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Clock values[]) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || (nValueReferences > 0 && values == nullptr)) {
        return fmi3Fatal;
    }
    if (impl->mode != Fmi3Mode::kEvent) {
        return Unsupported(impl, "Clock values can only be read in Event Mode");
    }
    std::unique_ptr<bool[]> buffer(new bool[nValueReferences]);
    const auto status = impl->runtime.GetClock(valueReferences, nValueReferences, buffer.get());
    if (!status) {
        return ToFmiStatus(impl, status);
    }
    for (size_t index = 0; index < nValueReferences; ++index) {
        values[index] = buffer[index] ? fmi3True : fmi3False;
    }
    return fmi3OK;
}

fmi3Status fmi3SetFloat32(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Float32 values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || (nValues > 0 && values == nullptr)) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    std::vector<double> temp(nValues);
    for (size_t index = 0; index < nValues; ++index) {
        temp[index] = static_cast<double>(values[index]);
    }
    return ToFmiStatus(impl, impl->runtime.SetReal(valueReferences, nValueReferences, temp.data(), nValues));
}

fmi3Status fmi3SetFloat64(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Float64 values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    return ToFmiStatus(impl, impl->runtime.SetReal(valueReferences, nValueReferences, values, nValues));
}

fmi3Status fmi3SetInt32(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Int32 values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    return ToFmiStatus(impl, impl->runtime.SetInteger(valueReferences, nValueReferences, values, nValues));
}

fmi3Status fmi3SetInt8(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Int8 values[],
    size_t nValues) {
    return SetSignedIntegerValues(AsInstance(instance), valueReferences, nValueReferences, values, nValues);
}

fmi3Status fmi3SetInt16(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Int16 values[],
    size_t nValues) {
    return SetSignedIntegerValues(AsInstance(instance), valueReferences, nValueReferences, values, nValues);
}

fmi3Status fmi3SetInt64(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Int64 values[],
    size_t nValues) {
    return SetSignedIntegerValues(AsInstance(instance), valueReferences, nValueReferences, values, nValues);
}

fmi3Status fmi3SetUInt32(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3UInt32 values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || (nValues > 0 && values == nullptr)) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    return SetUnsignedIntegerValues(impl, valueReferences, nValueReferences, values, nValues);
}

fmi3Status fmi3SetUInt64(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3UInt64 values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || (nValues > 0 && values == nullptr)) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    return SetUnsignedIntegerValues(impl, valueReferences, nValueReferences, values, nValues);
}

fmi3Status fmi3SetUInt8(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3UInt8 values[],
    size_t nValues) {
    return SetUnsignedIntegerValues(AsInstance(instance), valueReferences, nValueReferences, values, nValues);
}

fmi3Status fmi3SetUInt16(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3UInt16 values[],
    size_t nValues) {
    return SetUnsignedIntegerValues(AsInstance(instance), valueReferences, nValueReferences, values, nValues);
}

fmi3Status fmi3SetBoolean(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Boolean values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || (nValues > 0 && values == nullptr)) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    std::unique_ptr<bool[]> buffer(new bool[nValues]);
    for (size_t index = 0; index < nValues; ++index) {
        buffer[index] = values[index] != fmi3False;
    }
    return ToFmiStatus(impl, impl->runtime.SetBoolean(valueReferences, nValueReferences, buffer.get(), nValues));
}

fmi3Status fmi3SetString(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3String values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    return ToFmiStatus(impl, impl->runtime.SetString(valueReferences, nValueReferences, values, nValues));
}

fmi3Status fmi3SetBinary(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const size_t valueSizes[],
    const fmi3Binary values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || (nValues > 0 && (valueSizes == nullptr || values == nullptr))) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    return ToFmiStatus(impl, impl->runtime.SetBinary(valueReferences, nValueReferences, valueSizes, values, nValues));
}

fmi3Status fmi3SetClock(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Clock values[]) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || (nValueReferences > 0 && values == nullptr)) {
        return fmi3Fatal;
    }
    if (impl->mode != Fmi3Mode::kEvent) {
        return Unsupported(impl, "Input Clocks can only be set in Event Mode");
    }
    std::unique_ptr<bool[]> buffer(new bool[nValueReferences]);
    for (size_t index = 0; index < nValueReferences; ++index) {
        buffer[index] = values[index] != fmi3False;
    }
    return ToFmiStatus(impl, impl->runtime.SetClock(valueReferences, nValueReferences, buffer.get()));
}

fmi3Status fmi3DoStep(
    fmi3Instance instance,
    fmi3Float64 currentCommunicationPoint,
    fmi3Float64 communicationStepSize,
    fmi3Boolean,
    fmi3Boolean* eventHandlingNeeded,
    fmi3Boolean* terminateSimulation,
    fmi3Boolean* earlyReturn,
    fmi3Float64* lastSuccessfulTime) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    if (impl->mode != Fmi3Mode::kStep || impl->event_mode_pending) {
        return Unsupported(impl, "fmi3DoStep can only be called in Step Mode");
    }
    const auto status = impl->runtime.DoStep(currentCommunicationPoint, communicationStepSize);
    if (!status) {
        const auto fmi_status = ToFmiStatus(impl, status);
        if (fmi_status == fmi3Discard) {
            if (eventHandlingNeeded != nullptr) {
                *eventHandlingNeeded = fmi3False;
            }
            if (terminateSimulation != nullptr) {
                *terminateSimulation = fmi3False;
            }
            if (earlyReturn != nullptr) {
                *earlyReturn = fmi3False;
            }
            if (lastSuccessfulTime != nullptr) {
                *lastSuccessfulTime = impl->runtime.CurrentTime();
            }
        }
        return fmi_status;
    }
    if (eventHandlingNeeded != nullptr) {
        *eventHandlingNeeded = impl->runtime.LastStepEventHandlingNeeded() ? fmi3True : fmi3False;
    }
    impl->event_mode_pending = impl->event_mode_used
        && impl->runtime.LastStepEventHandlingNeeded();
    if (terminateSimulation != nullptr) {
        *terminateSimulation = impl->runtime.LastStepTerminated() ? fmi3True : fmi3False;
    }
    if (earlyReturn != nullptr) {
        *earlyReturn = impl->runtime.LastStepEarlyReturn() ? fmi3True : fmi3False;
    }
    if (lastSuccessfulTime != nullptr) {
        *lastSuccessfulTime = impl->runtime.CurrentTime();
    }
    return fmi3OK;
}

fmi3Status fmi3GetFMUState(fmi3Instance instance, fmi3FMUState* FMUState) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || FMUState == nullptr) {
        return fmi3Fatal;
    }
    *FMUState = nullptr;
    std::string checkpoint;
    const OperationResult status = impl->runtime.CaptureFmuState(checkpoint);
    if (!status) {
        return ToFmiStatus(impl, status);
    }
    auto state = std::unique_ptr<Fmi3StateHandle>(new (std::nothrow) Fmi3StateHandle{
        std::move(checkpoint), impl->mode, impl->configuration_return_mode, impl->event_mode_pending});
    if (!state) {
        return fmi3Error;
    }
    *FMUState = static_cast<fmi3FMUState>(state.release());
    return fmi3OK;
}

fmi3Status fmi3SetFMUState(fmi3Instance instance, fmi3FMUState FMUState) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || FMUState == nullptr) {
        return fmi3Fatal;
    }
    const auto* state = static_cast<const Fmi3StateHandle*>(FMUState);
    const auto status = impl->runtime.RestoreFmuState(state->checkpoint);
    if (!status) {
        return ToFmiStatus(impl, status);
    }
    impl->mode = state->mode;
    impl->configuration_return_mode = state->configuration_return_mode;
    impl->event_mode_pending = state->event_mode_pending;
    return fmi3OK;
}

fmi3Status fmi3FreeFMUState(fmi3Instance instance, fmi3FMUState* FMUState) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || FMUState == nullptr) {
        return fmi3Fatal;
    }
    delete static_cast<Fmi3StateHandle*>(*FMUState);
    *FMUState = nullptr;
    return fmi3OK;
}

fmi3Status fmi3SerializedFMUStateSize(fmi3Instance instance, fmi3FMUState FMUState, size_t* size) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || size == nullptr || FMUState == nullptr) {
        return fmi3Fatal;
    }
    const auto* state = static_cast<const Fmi3StateHandle*>(FMUState);
    const size_t serialized_size = SerializeFmi3State(*state).size();
    if (serialized_size > kMaximumSerializedStateTokenBytes) {
        return Unsupported(impl, "Serialized FMU state exceeds the supported size limit");
    }
    *size = serialized_size;
    return fmi3OK;
}

fmi3Status fmi3SerializeFMUState(fmi3Instance instance, fmi3FMUState FMUState, fmi3Byte serializedState[], size_t size) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || FMUState == nullptr || serializedState == nullptr) {
        return fmi3Fatal;
    }
    const auto* state = static_cast<const Fmi3StateHandle*>(FMUState);
    const std::string serialized = SerializeFmi3State(*state);
    if (serialized.size() > kMaximumSerializedStateTokenBytes || size != serialized.size()) {
        return Unsupported(impl, "Serialized FMU state buffer has the wrong size");
    }
    std::memcpy(serializedState, serialized.data(), size);
    return fmi3OK;
}

fmi3Status fmi3DeserializeFMUState(fmi3Instance instance, const fmi3Byte serializedState[], size_t size, fmi3FMUState* FMUState) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || FMUState == nullptr || serializedState == nullptr) {
        return fmi3Fatal;
    }
    *FMUState = nullptr;
    if (size == 0 || size > kMaximumSerializedStateTokenBytes) {
        return Unsupported(impl, "Serialized FMU state token has an invalid size");
    }
    std::string serialized(reinterpret_cast<const char*>(serializedState), size);
    auto state = std::unique_ptr<Fmi3StateHandle>(new (std::nothrow) Fmi3StateHandle());
    if (!state || !ParseFmi3State(serialized, state.get())) {
        return Unsupported(impl, "Serialized FMU state token is invalid");
    }
    *FMUState = static_cast<fmi3FMUState>(state.release());
    return fmi3OK;
}

fmi3Status fmi3GetDirectionalDerivative(
    fmi3Instance instance,
    const fmi3ValueReference[],
    size_t,
    const fmi3ValueReference[],
    size_t,
    const fmi3Float64[],
    size_t,
    fmi3Float64[],
    size_t) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    return Unsupported(impl, "Directional derivatives are not supported");
}

fmi3Status fmi3GetAdjointDerivative(
    fmi3Instance instance,
    const fmi3ValueReference[],
    size_t,
    const fmi3ValueReference[],
    size_t,
    const fmi3Float64[],
    size_t,
    fmi3Float64[],
    size_t) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    return Unsupported(impl, "Adjoint derivatives are not supported");
}

FMI3_Export fmi3Status fmi3ActivateModelPartition(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3EvaluateDiscreteStates(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetIntervalDecimal(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetIntervalFraction(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetNumberOfVariableDependencies(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetOutputDerivatives(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetShiftDecimal(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetShiftFraction(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetVariableDependencies(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetIntervalDecimal(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetIntervalFraction(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetShiftDecimal(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetShiftFraction(...) { return fmi3Error; }

}  // extern "C"
