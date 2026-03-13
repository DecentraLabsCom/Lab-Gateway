#ifndef FMI3_FUNCTIONS_H_
#define FMI3_FUNCTIONS_H_

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
#define FMI3_Export __declspec(dllexport)
#else
#define FMI3_Export __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef void* fmi3Instance;
typedef void* fmi3InstanceEnvironment;
typedef void* fmi3FMUState;
typedef uint32_t fmi3ValueReference;
typedef float fmi3Float32;
typedef double fmi3Float64;
typedef int8_t fmi3Int8;
typedef uint8_t fmi3UInt8;
typedef int16_t fmi3Int16;
typedef uint16_t fmi3UInt16;
typedef int32_t fmi3Int32;
typedef uint32_t fmi3UInt32;
typedef int64_t fmi3Int64;
typedef uint64_t fmi3UInt64;
typedef int fmi3Boolean;
typedef const char* fmi3String;
typedef uint8_t fmi3Byte;
typedef const fmi3Byte* fmi3Binary;
typedef fmi3Boolean fmi3Clock;

enum {
    fmi3False = 0,
    fmi3True = 1,
};

typedef int fmi3Status;
enum {
    fmi3OK = 0,
    fmi3Warning = 1,
    fmi3Discard = 2,
    fmi3Error = 3,
    fmi3Fatal = 4,
};

typedef void (*fmi3LogMessageCallback)(
    fmi3InstanceEnvironment,
    fmi3Status,
    fmi3String,
    fmi3String);

typedef void (*fmi3IntermediateUpdateCallback)(
    fmi3InstanceEnvironment,
    fmi3Float64,
    fmi3Boolean,
    fmi3Boolean,
    fmi3Boolean,
    fmi3Boolean,
    fmi3Boolean*,
    fmi3Float64*);

FMI3_Export const char* fmi3GetVersion(void);
FMI3_Export fmi3Status fmi3SetDebugLogging(
    fmi3Instance instance,
    fmi3Boolean loggingOn,
    size_t nCategories,
    const fmi3String categories[]);

FMI3_Export fmi3Instance fmi3InstantiateCoSimulation(
    fmi3String instanceName,
    fmi3String instantiationToken,
    fmi3String resourcePath,
    fmi3Boolean visible,
    fmi3Boolean loggingOn,
    fmi3Boolean eventModeUsed,
    fmi3Boolean earlyReturnAllowed,
    const fmi3ValueReference requiredIntermediateVariables[],
    size_t nRequiredIntermediateVariables,
    fmi3InstanceEnvironment instanceEnvironment,
    fmi3LogMessageCallback logMessage,
    fmi3IntermediateUpdateCallback intermediateUpdate);

FMI3_Export fmi3Instance fmi3InstantiateModelExchange(
    fmi3String instanceName,
    fmi3String instantiationToken,
    fmi3String resourcePath,
    fmi3Boolean visible,
    fmi3Boolean loggingOn,
    fmi3InstanceEnvironment instanceEnvironment,
    fmi3LogMessageCallback logMessage);

FMI3_Export void fmi3FreeInstance(fmi3Instance instance);
FMI3_Export fmi3Status fmi3EnterInitializationMode(
    fmi3Instance instance,
    fmi3Boolean toleranceDefined,
    fmi3Float64 tolerance,
    fmi3Float64 startTime,
    fmi3Boolean stopTimeDefined,
    fmi3Float64 stopTime);
FMI3_Export fmi3Status fmi3ExitInitializationMode(fmi3Instance instance);
FMI3_Export fmi3Status fmi3EnterEventMode(fmi3Instance instance);
FMI3_Export fmi3Status fmi3Terminate(fmi3Instance instance);
FMI3_Export fmi3Status fmi3Reset(fmi3Instance instance);

FMI3_Export fmi3Status fmi3GetFloat32(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Float32 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3GetFloat64(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Float64 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3GetInt32(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Int32 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3GetInt8(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Int8 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3GetInt16(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Int16 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3GetInt64(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Int64 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3GetUInt32(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3UInt32 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3GetUInt8(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3UInt8 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3GetUInt16(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3UInt16 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3GetUInt64(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3UInt64 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3GetBoolean(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Boolean values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3GetString(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3String values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3GetBinary(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    size_t valueSizes[],
    fmi3Binary values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3GetClock(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    fmi3Clock values[]);

FMI3_Export fmi3Status fmi3SetFloat32(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Float32 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3SetFloat64(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Float64 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3SetInt32(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Int32 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3SetInt8(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Int8 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3SetInt16(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Int16 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3SetInt64(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Int64 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3SetUInt32(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3UInt32 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3SetUInt8(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3UInt8 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3SetUInt16(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3UInt16 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3SetUInt64(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3UInt64 values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3SetBoolean(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Boolean values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3SetString(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3String values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3SetBinary(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const size_t valueSizes[],
    const fmi3Binary values[],
    size_t nValues);
FMI3_Export fmi3Status fmi3SetClock(
    fmi3Instance instance,
    const fmi3ValueReference valueReferences[],
    size_t nValueReferences,
    const fmi3Clock values[]);

FMI3_Export fmi3Status fmi3DoStep(
    fmi3Instance instance,
    fmi3Float64 currentCommunicationPoint,
    fmi3Float64 communicationStepSize,
    fmi3Boolean noSetFMUStatePriorToCurrentPoint,
    fmi3Boolean* eventHandlingNeeded,
    fmi3Boolean* terminateSimulation,
    fmi3Boolean* earlyReturn,
    fmi3Float64* lastSuccessfulTime);

FMI3_Export fmi3Status fmi3GetFMUState(fmi3Instance instance, fmi3FMUState* FMUState);
FMI3_Export fmi3Status fmi3SetFMUState(fmi3Instance instance, fmi3FMUState FMUState);
FMI3_Export fmi3Status fmi3FreeFMUState(fmi3Instance instance, fmi3FMUState* FMUState);
FMI3_Export fmi3Status fmi3SerializedFMUStateSize(fmi3Instance instance, fmi3FMUState FMUState, size_t* size);
FMI3_Export fmi3Status fmi3SerializeFMUState(fmi3Instance instance, fmi3FMUState FMUState, fmi3Byte serializedState[], size_t size);
FMI3_Export fmi3Status fmi3DeserializeFMUState(fmi3Instance instance, const fmi3Byte serializedState[], size_t size, fmi3FMUState* FMUState);
FMI3_Export fmi3Status fmi3GetDirectionalDerivative(
    fmi3Instance instance,
    const fmi3ValueReference unknowns[],
    size_t nUnknowns,
    const fmi3ValueReference knowns[],
    size_t nKnowns,
    const fmi3Float64 seed[],
    size_t nSeed,
    fmi3Float64 sensitivity[],
    size_t nSensitivity);
FMI3_Export fmi3Status fmi3GetAdjointDerivative(
    fmi3Instance instance,
    const fmi3ValueReference unknowns[],
    size_t nUnknowns,
    const fmi3ValueReference knowns[],
    size_t nKnowns,
    const fmi3Float64 seed[],
    size_t nSeed,
    fmi3Float64 sensitivity[],
    size_t nSensitivity);

#ifdef __cplusplus
}
#endif

#endif  // FMI3_FUNCTIONS_H_
