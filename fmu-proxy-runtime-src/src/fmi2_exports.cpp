#include "fmi2/fmi2Functions.h"

#include <memory>
#include <string>

#include "decentralabs_proxy/runtime.hpp"

namespace decentralabs::proxy {

namespace {

struct Fmi2Instance {
    fmi2CallbackFunctions callbacks{};
    bool logging_enabled = false;
    std::string instance_name;
    ProxyRuntime runtime;
    std::string last_string_status;
};

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

}  // namespace

}  // namespace decentralabs::proxy

using decentralabs::proxy::AsInstance;
using decentralabs::proxy::AttachLogger;
using decentralabs::proxy::Fmi2Instance;
using decentralabs::proxy::Log;
using decentralabs::proxy::OperationResult;
using decentralabs::proxy::SessionState;
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
    if (fmuType != fmi2CoSimulation || instanceName == nullptr || fmuResourceLocation == nullptr || functions == nullptr) {
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

    return instance;
}

void fmi2FreeInstance(fmi2Component c) {
    delete AsInstance(c);
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
    const double effective_stop = stopTimeDefined == fmi2True
        ? stopTime
        : model.default_stop_time.value_or(10.0);
    const double step = model.default_step_size.value_or(0.01);
    return ToFmiStatus(instance, instance->runtime.SetupExperiment(startTime, effective_stop, step));
}

fmi2Status fmi2EnterInitializationMode(fmi2Component c) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    return ToFmiStatus(instance, instance->runtime.EnterInitializationMode());
}

fmi2Status fmi2ExitInitializationMode(fmi2Component c) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    return ToFmiStatus(instance, instance->runtime.ExitInitializationMode());
}

fmi2Status fmi2Terminate(fmi2Component c) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    return ToFmiStatus(instance, instance->runtime.Terminate());
}

fmi2Status fmi2Reset(fmi2Component c) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    return ToFmiStatus(instance, instance->runtime.Reset());
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
    Log(instance, fmi2Error, "logStatusError", "FMU state snapshots are not supported");
    return fmi2Error;
}

fmi2Status fmi2SetFMUstate(fmi2Component c, fmi2FMUstate) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    Log(instance, fmi2Error, "logStatusError", "FMU state snapshots are not supported");
    return fmi2Error;
}

fmi2Status fmi2FreeFMUstate(fmi2Component c, fmi2FMUstate* value) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr || value == nullptr) {
        return fmi2Fatal;
    }
    *value = nullptr;
    return fmi2OK;
}

fmi2Status fmi2SerializedFMUstateSize(fmi2Component c, fmi2FMUstate, size_t* size) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr || size == nullptr) {
        return fmi2Fatal;
    }
    *size = 0;
    Log(instance, fmi2Error, "logStatusError", "FMU state serialization is not supported");
    return fmi2Error;
}

fmi2Status fmi2SerializeFMUstate(fmi2Component c,
                                 fmi2FMUstate,
                                 fmi2Byte[],
                                 size_t) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr) {
        return fmi2Fatal;
    }
    Log(instance, fmi2Error, "logStatusError", "FMU state serialization is not supported");
    return fmi2Error;
}

fmi2Status fmi2DeSerializeFMUstate(fmi2Component c,
                                   const fmi2Byte[],
                                   size_t,
                                   fmi2FMUstate* value) {
    Fmi2Instance* instance = AsInstance(c);
    if (instance == nullptr || value == nullptr) {
        return fmi2Fatal;
    }
    *value = nullptr;
    Log(instance, fmi2Error, "logStatusError", "FMU state serialization is not supported");
    return fmi2Error;
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
    return ToFmiStatus(instance, instance->runtime.DoStep(currentCommunicationPoint, communicationStepSize));
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
        *value = instance->runtime.State() == SessionState::kTerminated ? fmi2True : fmi2False;
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
