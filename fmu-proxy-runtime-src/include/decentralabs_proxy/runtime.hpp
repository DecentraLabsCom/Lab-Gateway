#pragma once

#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <vector>

#include "decentralabs_proxy/gateway_client.hpp"
#include "decentralabs_proxy/model_description.hpp"
#include "decentralabs_proxy/operation_result.hpp"
#include "decentralabs_proxy/runtime_config.hpp"
#include "decentralabs_proxy/session_state.hpp"
#include "decentralabs_proxy/transport.hpp"

namespace decentralabs::proxy {

class ProxyRuntime {
public:
    using LogSink = std::function<void(const std::string&, const std::string&)>;
    using TransportFactory = std::function<std::unique_ptr<GatewayTransport>()>;

    explicit ProxyRuntime(TransportFactory transport_factory = {});

    void SetLogger(LogSink logger);

    OperationResult Configure(const std::string& instance_name, const std::string& resource_location);
    OperationResult SetupExperiment(double start_time, double stop_time, double step_size);
    OperationResult EnterInitializationMode();
    OperationResult ExitInitializationMode();
    OperationResult DoStep(double current_time, double step_size);
    OperationResult Terminate();
    OperationResult Reset();

    OperationResult SetReal(const std::uint32_t* value_references, std::size_t count, const double* values, std::size_t value_count = 0);
    OperationResult SetInteger(const std::uint32_t* value_references, std::size_t count, const std::int32_t* values, std::size_t value_count = 0);
    OperationResult SetSignedInteger(const std::uint32_t* value_references, std::size_t count, const std::int64_t* values, std::size_t value_count = 0);
    OperationResult SetUnsignedInteger(const std::uint32_t* value_references, std::size_t count, const std::uint64_t* values, std::size_t value_count = 0);
    OperationResult SetBoolean(const std::uint32_t* value_references, std::size_t count, const bool* values, std::size_t value_count = 0);
    OperationResult SetString(const std::uint32_t* value_references, std::size_t count, const char* const* values, std::size_t value_count = 0);
    OperationResult SetBinary(const std::uint32_t* value_references, std::size_t count, const std::size_t* value_sizes, const std::uint8_t* const* values, std::size_t value_count = 0);
    OperationResult SetClock(const std::uint32_t* value_references, std::size_t count, const bool* values);

    OperationResult GetReal(const std::uint32_t* value_references, std::size_t count, double* values, std::size_t value_count = 0) const;
    OperationResult GetInteger(const std::uint32_t* value_references, std::size_t count, std::int32_t* values, std::size_t value_count = 0) const;
    OperationResult GetSignedInteger(const std::uint32_t* value_references, std::size_t count, std::int64_t* values, std::size_t value_count = 0) const;
    OperationResult GetUnsignedInteger(const std::uint32_t* value_references, std::size_t count, std::uint64_t* values, std::size_t value_count = 0) const;
    OperationResult GetBoolean(const std::uint32_t* value_references, std::size_t count, bool* values, std::size_t value_count = 0) const;
    OperationResult GetString(const std::uint32_t* value_references, std::size_t count, const char** values, std::size_t value_count = 0);
    OperationResult GetBinary(const std::uint32_t* value_references, std::size_t count, std::size_t* value_sizes, const std::uint8_t** values, std::size_t value_count = 0);
    OperationResult GetClock(const std::uint32_t* value_references, std::size_t count, bool* values) const;
    std::size_t ExpectedValueCount(const std::uint32_t* value_references, std::size_t count) const;

    const RuntimeConfig& Config() const;
    const ModelDescription& Model() const;
    SessionState State() const;
    double CurrentTime() const;
    const std::string& LastError() const;

private:
    OperationResult Transition(SessionState next);
    OperationResult SetValue(const VariableInfo& variable, ScalarValue value);
    const ScalarValue* GetCachedValue(std::uint32_t value_reference) const;
    OperationResult ApplyOutputSnapshot(const OutputSnapshot& snapshot);
    void SeedCacheFromModelDefaults();
    std::size_t ResolveVariableFlatSize(const VariableInfo& variable) const;
    std::optional<std::int32_t> ResolveDimensionExtent(const DimensionInfo& dimension) const;
    void SetError(const std::string& message);
    static std::string DecodeFileUri(const std::string& resource_location);

    template <typename T>
    OperationResult SetNumericValues(const std::uint32_t* value_references,
                                     std::size_t count,
                                     const T* values,
                                     std::size_t value_count,
                                     ScalarType expected_type);

    template <typename T>
    OperationResult GetNumericValues(const std::uint32_t* value_references,
                                     std::size_t count,
                                     T* values,
                                     std::size_t value_count,
                                     ScalarType expected_type) const;

    TransportFactory transport_factory_;
    std::unique_ptr<GatewayClient> gateway_client_;
    LogSink logger_;
    RuntimeConfig config_;
    ModelDescription model_;
    ExperimentConfig experiment_;
    SessionState state_ = SessionState::kUnconfigured;
    std::string instance_name_;
    std::string last_error_;
    double current_time_ = 0.0;
    std::map<std::uint32_t, ScalarValue> cached_values_;
    std::map<std::string, ScalarValue> pending_inputs_;
    std::vector<std::string> string_cache_;
};

}  // namespace decentralabs::proxy
