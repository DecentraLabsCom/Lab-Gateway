#ifndef FMI2_TYPES_PLATFORM_H_
#define FMI2_TYPES_PLATFORM_H_

#define fmi2TypesPlatform "default"
#define fmi2True 1
#define fmi2False 0

typedef void* fmi2Component;
typedef void* fmi2ComponentEnvironment;
typedef void* fmi2FMUstate;
typedef const char* fmi2String;
typedef double fmi2Real;
typedef int fmi2Integer;
typedef int fmi2Boolean;
typedef unsigned int fmi2ValueReference;
typedef unsigned char fmi2Byte;

typedef enum {
    fmi2OK,
    fmi2Warning,
    fmi2Discard,
    fmi2Error,
    fmi2Fatal,
    fmi2Pending,
} fmi2Status;

typedef enum {
    fmi2ModelExchange,
    fmi2CoSimulation,
} fmi2Type;

typedef enum {
    fmi2DoStepStatus,
    fmi2PendingStatus,
    fmi2LastSuccessfulTime,
    fmi2Terminated,
} fmi2StatusKind;

#endif  // FMI2_TYPES_PLATFORM_H_
