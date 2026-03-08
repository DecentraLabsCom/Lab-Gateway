#ifndef FMI2_FUNCTION_TYPES_H_
#define FMI2_FUNCTION_TYPES_H_

#include <stdarg.h>
#include <stddef.h>

#include "fmi2TypesPlatform.h"

typedef void (*fmi2CallbackLogger)(fmi2ComponentEnvironment componentEnvironment,
                                   fmi2String instanceName,
                                   fmi2Status status,
                                   fmi2String category,
                                   fmi2String message,
                                   ...);

typedef void* (*fmi2CallbackAllocateMemory)(size_t nobj, size_t size);
typedef void (*fmi2CallbackFreeMemory)(void* obj);
typedef void (*fmi2StepFinished)(fmi2ComponentEnvironment componentEnvironment, fmi2Status status);

typedef struct {
    fmi2CallbackLogger logger;
    fmi2CallbackAllocateMemory allocateMemory;
    fmi2CallbackFreeMemory freeMemory;
    fmi2StepFinished stepFinished;
    fmi2ComponentEnvironment componentEnvironment;
} fmi2CallbackFunctions;

#endif  // FMI2_FUNCTION_TYPES_H_
