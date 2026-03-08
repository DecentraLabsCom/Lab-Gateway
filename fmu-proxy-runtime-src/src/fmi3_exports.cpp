#include "fmi3/fmi3Functions.h"

#include <memory>
#include <string>
#include <vector>

#include "decentralabs_proxy/runtime.hpp"

namespace decentralabs::proxy {

namespace {

struct Fmi3Instance {
    fmi3InstanceEnvironment environment = nullptr;
    fmi3LogMessageCallback logger = nullptr;
    bool logging_enabled = false;
    std::string instance_name;
    ProxyRuntime runtime;
    std::vector<std::string> string_cache;
};

Fmi3Instance* AsInstance(fmi3Instance instance) {
    return static_cast<Fmi3Instance*>(instance);
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
    const std::size_t expected = instance->runtime.ExpectedValueCount(valueReferences, nValueReferences);
    if (expected == nValues && expected != 0) {
        return true;
    }
    Log(instance, fmi3Error, "logStatusError", "FMI 3 value buffer length does not match referenced scalar/array variables");
    return false;
}

}  // namespace

}  // namespace decentralabs::proxy

using decentralabs::proxy::AsInstance;
using decentralabs::proxy::AttachLogger;
using decentralabs::proxy::Fmi3Instance;
using decentralabs::proxy::OperationResult;
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
    fmi3Boolean,
    fmi3Boolean,
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
    instance->instance_name = instanceName;
    AttachLogger(instance);

    const OperationResult status = instance->runtime.Configure(instanceName, resourcePath);
    if (!status) {
        Log(instance, fmi3Error, "logStatusError", status.message);
        delete instance;
        return nullptr;
    }
    return instance;
}

fmi3Instance fmi3InstantiateModelExchange(
    fmi3String,
    fmi3String,
    fmi3String,
    fmi3Boolean,
    fmi3Boolean,
    fmi3InstanceEnvironment,
    fmi3LogMessageCallback) {
    return nullptr;
}

FMI3_Export fmi3Instance fmi3InstantiateScheduledExecution(...) {
    return nullptr;
}

void fmi3FreeInstance(fmi3Instance instance) {
    delete AsInstance(instance);
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
    const auto& model = impl->runtime.Model();
    const double effective_stop = stopTimeDefined != fmi3False
        ? stopTime
        : model.default_stop_time.value_or(10.0);
    const double step = model.default_step_size.value_or(0.01);
    auto status = impl->runtime.SetupExperiment(startTime, effective_stop, step);
    if (!status) {
        return ToFmiStatus(impl, status);
    }
    return ToFmiStatus(impl, impl->runtime.EnterInitializationMode());
}

fmi3Status fmi3ExitInitializationMode(fmi3Instance instance) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    return ToFmiStatus(impl, impl->runtime.ExitInitializationMode());
}

fmi3Status fmi3EnterEventMode(fmi3Instance instance) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    return Unsupported(impl, "Event mode is not supported by the proxy runtime");
}

fmi3Status fmi3Terminate(fmi3Instance instance) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    return ToFmiStatus(impl, impl->runtime.Terminate());
}

fmi3Status fmi3Reset(fmi3Instance instance) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    return ToFmiStatus(impl, impl->runtime.Reset());
}

fmi3Status fmi3GetFloat32(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Float32 values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || values == nullptr) {
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

fmi3Status fmi3GetUInt32(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3UInt32 values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || values == nullptr) {
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

fmi3Status fmi3GetUInt64(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3UInt64 values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || values == nullptr) {
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
    if (impl == nullptr || values == nullptr) {
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

fmi3Status fmi3SetFloat32(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Float32 values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || values == nullptr) {
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

fmi3Status fmi3SetUInt32(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3UInt32 values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || values == nullptr) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    std::vector<std::int32_t> temp(nValues);
    for (size_t index = 0; index < nValues; ++index) {
        temp[index] = static_cast<std::int32_t>(values[index]);
    }
    return ToFmiStatus(impl, impl->runtime.SetInteger(valueReferences, nValueReferences, temp.data(), nValues));
}

fmi3Status fmi3SetUInt64(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3UInt64 values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || values == nullptr) {
        return fmi3Fatal;
    }
    if (!ValidateValueCounts(impl, valueReferences, nValueReferences, nValues)) {
        return fmi3Error;
    }
    std::vector<std::int32_t> temp(nValues);
    for (size_t index = 0; index < nValues; ++index) {
        temp[index] = static_cast<std::int32_t>(values[index]);
    }
    return ToFmiStatus(impl, impl->runtime.SetInteger(valueReferences, nValueReferences, temp.data(), nValues));
}

fmi3Status fmi3SetBoolean(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Boolean values[],
    size_t nValues) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || values == nullptr) {
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
    const auto status = impl->runtime.DoStep(currentCommunicationPoint, communicationStepSize);
    if (!status) {
        return ToFmiStatus(impl, status);
    }
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
    return fmi3OK;
}

fmi3Status fmi3GetFMUState(fmi3Instance instance, fmi3FMUState* FMUState) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || FMUState == nullptr) {
        return fmi3Fatal;
    }
    *FMUState = nullptr;
    return Unsupported(impl, "FMU state snapshots are not supported");
}

fmi3Status fmi3SetFMUState(fmi3Instance instance, fmi3FMUState) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    return Unsupported(impl, "FMU state snapshots are not supported");
}

fmi3Status fmi3FreeFMUState(fmi3Instance instance, fmi3FMUState* FMUState) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || FMUState == nullptr) {
        return fmi3Fatal;
    }
    *FMUState = nullptr;
    return fmi3OK;
}

fmi3Status fmi3SerializedFMUStateSize(fmi3Instance instance, fmi3FMUState, size_t* size) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || size == nullptr) {
        return fmi3Fatal;
    }
    *size = 0;
    return Unsupported(impl, "FMU state serialization is not supported");
}

fmi3Status fmi3SerializeFMUState(fmi3Instance instance, fmi3FMUState, fmi3Byte[], size_t) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr) {
        return fmi3Fatal;
    }
    return Unsupported(impl, "FMU state serialization is not supported");
}

fmi3Status fmi3DeserializeFMUState(fmi3Instance instance, const fmi3Byte[], size_t, fmi3FMUState* FMUState) {
    Fmi3Instance* impl = AsInstance(instance);
    if (impl == nullptr || FMUState == nullptr) {
        return fmi3Fatal;
    }
    *FMUState = nullptr;
    return Unsupported(impl, "FMU state serialization is not supported");
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
FMI3_Export fmi3Status fmi3CompletedIntegratorStep(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3EnterConfigurationMode(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3EnterContinuousTimeMode(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3EnterStepMode(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3EvaluateDiscreteStates(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3ExitConfigurationMode(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetBinary(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetClock(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetContinuousStateDerivatives(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetContinuousStates(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetEventIndicators(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetInt8(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetInt16(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetInt64(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetIntervalDecimal(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetIntervalFraction(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetNominalsOfContinuousStates(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetNumberOfContinuousStates(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetNumberOfEventIndicators(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetNumberOfVariableDependencies(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetOutputDerivatives(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetShiftDecimal(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetShiftFraction(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetUInt8(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetUInt16(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3GetVariableDependencies(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetBinary(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetClock(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetContinuousStates(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetInt8(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetInt16(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetInt64(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetIntervalDecimal(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetIntervalFraction(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetShiftDecimal(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetShiftFraction(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetTime(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetUInt8(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3SetUInt16(...) { return fmi3Error; }
FMI3_Export fmi3Status fmi3UpdateDiscreteStates(...) { return fmi3Error; }

}  // extern "C"
