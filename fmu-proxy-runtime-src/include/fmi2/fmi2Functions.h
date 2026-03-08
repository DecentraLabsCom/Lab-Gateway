#ifndef FMI2_FUNCTIONS_H_
#define FMI2_FUNCTIONS_H_

#include "fmi2FunctionTypes.h"

#if defined(_WIN32) || defined(__CYGWIN__)
#define FMI2_Export __declspec(dllexport)
#else
#define FMI2_Export __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

FMI2_Export const char* fmi2GetTypesPlatform(void);
FMI2_Export const char* fmi2GetVersion(void);
FMI2_Export fmi2Component fmi2Instantiate(fmi2String instanceName,
                                          fmi2Type fmuType,
                                          fmi2String fmuGUID,
                                          fmi2String fmuResourceLocation,
                                          const fmi2CallbackFunctions* functions,
                                          fmi2Boolean visible,
                                          fmi2Boolean loggingOn);
FMI2_Export void fmi2FreeInstance(fmi2Component c);
FMI2_Export fmi2Status fmi2SetupExperiment(fmi2Component c,
                                           fmi2Boolean toleranceDefined,
                                           fmi2Real tolerance,
                                           fmi2Real startTime,
                                           fmi2Boolean stopTimeDefined,
                                           fmi2Real stopTime);
FMI2_Export fmi2Status fmi2EnterInitializationMode(fmi2Component c);
FMI2_Export fmi2Status fmi2ExitInitializationMode(fmi2Component c);
FMI2_Export fmi2Status fmi2Terminate(fmi2Component c);
FMI2_Export fmi2Status fmi2Reset(fmi2Component c);
FMI2_Export fmi2Status fmi2SetDebugLogging(fmi2Component c,
                                           fmi2Boolean loggingOn,
                                           size_t nCategories,
                                           const fmi2String categories[]);
FMI2_Export fmi2Status fmi2SetReal(fmi2Component c,
                                   const fmi2ValueReference vr[],
                                   size_t nvr,
                                   const fmi2Real value[]);
FMI2_Export fmi2Status fmi2SetInteger(fmi2Component c,
                                      const fmi2ValueReference vr[],
                                      size_t nvr,
                                      const fmi2Integer value[]);
FMI2_Export fmi2Status fmi2SetBoolean(fmi2Component c,
                                      const fmi2ValueReference vr[],
                                      size_t nvr,
                                      const fmi2Boolean value[]);
FMI2_Export fmi2Status fmi2SetString(fmi2Component c,
                                     const fmi2ValueReference vr[],
                                     size_t nvr,
                                     const fmi2String value[]);
FMI2_Export fmi2Status fmi2GetFMUstate(fmi2Component c, fmi2FMUstate* FMUstate);
FMI2_Export fmi2Status fmi2SetFMUstate(fmi2Component c, fmi2FMUstate FMUstate);
FMI2_Export fmi2Status fmi2FreeFMUstate(fmi2Component c, fmi2FMUstate* FMUstate);
FMI2_Export fmi2Status fmi2SerializedFMUstateSize(fmi2Component c,
                                                  fmi2FMUstate FMUstate,
                                                  size_t* size);
FMI2_Export fmi2Status fmi2SerializeFMUstate(fmi2Component c,
                                             fmi2FMUstate FMUstate,
                                             fmi2Byte serializedState[],
                                             size_t size);
FMI2_Export fmi2Status fmi2DeSerializeFMUstate(fmi2Component c,
                                               const fmi2Byte serializedState[],
                                               size_t size,
                                               fmi2FMUstate* FMUstate);
FMI2_Export fmi2Status fmi2GetDirectionalDerivative(fmi2Component c,
                                                    const fmi2ValueReference vUnknown_ref[],
                                                    size_t nUnknown,
                                                    const fmi2ValueReference vKnown_ref[],
                                                    size_t nKnown,
                                                    const fmi2Real dvKnown[],
                                                    fmi2Real dvUnknown[]);
FMI2_Export fmi2Status fmi2GetReal(fmi2Component c,
                                   const fmi2ValueReference vr[],
                                   size_t nvr,
                                   fmi2Real value[]);
FMI2_Export fmi2Status fmi2GetInteger(fmi2Component c,
                                      const fmi2ValueReference vr[],
                                      size_t nvr,
                                      fmi2Integer value[]);
FMI2_Export fmi2Status fmi2GetBoolean(fmi2Component c,
                                      const fmi2ValueReference vr[],
                                      size_t nvr,
                                      fmi2Boolean value[]);
FMI2_Export fmi2Status fmi2GetString(fmi2Component c,
                                     const fmi2ValueReference vr[],
                                     size_t nvr,
                                     fmi2String value[]);
FMI2_Export fmi2Status fmi2DoStep(fmi2Component c,
                                  fmi2Real currentCommunicationPoint,
                                  fmi2Real communicationStepSize,
                                  fmi2Boolean noSetFMUStatePriorToCurrentPoint);
FMI2_Export fmi2Status fmi2CancelStep(fmi2Component c);
FMI2_Export fmi2Status fmi2GetStatus(fmi2Component c, const fmi2StatusKind s, fmi2Status* value);
FMI2_Export fmi2Status fmi2GetRealStatus(fmi2Component c, const fmi2StatusKind s, fmi2Real* value);
FMI2_Export fmi2Status fmi2GetIntegerStatus(fmi2Component c, const fmi2StatusKind s, fmi2Integer* value);
FMI2_Export fmi2Status fmi2GetBooleanStatus(fmi2Component c, const fmi2StatusKind s, fmi2Boolean* value);
FMI2_Export fmi2Status fmi2GetStringStatus(fmi2Component c, const fmi2StatusKind s, fmi2String* value);
FMI2_Export fmi2Status fmi2SetRealInputDerivatives(fmi2Component c,
                                                   const fmi2ValueReference vr[],
                                                   size_t nvr,
                                                   const fmi2Integer order[],
                                                   const fmi2Real value[]);
FMI2_Export fmi2Status fmi2GetRealOutputDerivatives(fmi2Component c,
                                                    const fmi2ValueReference vr[],
                                                    size_t nvr,
                                                    const fmi2Integer order[],
                                                    fmi2Real value[]);

#ifdef __cplusplus
}
#endif

#endif  // FMI2_FUNCTIONS_H_
