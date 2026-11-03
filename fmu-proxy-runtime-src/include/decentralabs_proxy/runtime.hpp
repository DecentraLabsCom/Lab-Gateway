#pragma once

#include <cstdint>
#include <chrono>
#include <functional>
#include <map>
#include <memory>
#include <optional>
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
    OperationResult SetModelExchangeMode(bool enabled);
    bool IsModelExchangeMode() const;
    ValueResult<JsonObject> ModelExchangeCall(const std::string& operation,
                                              const JsonObject& arguments = {});
    OperationResult EnterModelExchangeEventMode();
    OperationResult EnterModelExchangeContinuousTimeMode();
    OperationResult SetupExperiment(double start_time, std::optional<double> stop_time, double step_size);
    OperationResult EnterInitializationMode();
    OperationResult ExitInitializationMode();
    OperationResult EnterConfigurationMode();
    OperationResult ExitConfigurationMode();
    OperationResult UpdateDiscreteStates(bool* terminate_simulation = nullptr,
                                         bool* next_event_time_defined = nullptr,
                                         double* next_event_time = nullptr,
                                         bool* discrete_states_need_update = nullptr,
                                         bool* nominals_changed = nullptr,
                                         bool* continuous_states_changed = nullptr);
    bool HasStructuralParameters() const;
    bool HasTunableStructuralParameters() const;
    void SetEarlyReturnAllowed(bool allowed);
    OperationResult DoStep(double current_time, double step_size);
    OperationResult Terminate();
    OperationResult Reset();
    OperationResult CaptureFmuState(std::string& serialized_state);
    OperationResult RestoreFmuState(const std::string& serialized_state);

    OperationResult SetReal(const std::uint32_t* value_references, std::size_t count, const double* values, std::optional<std::size_t> value_count = std::nullopt);
    OperationResult SetInteger(const std::uint32_t* value_references, std::size_t count, const std::int32_t* values, std::optional<std::size_t> value_count = std::nullopt);
    OperationResult SetSignedInteger(const std::uint32_t* value_references, std::size_t count, const std::int64_t* values, std::optional<std::size_t> value_count = std::nullopt);
    OperationResult SetUnsignedInteger(const std::uint32_t* value_references, std::size_t count, const std::uint64_t* values, std::optional<std::size_t> value_count = std::nullopt);
    OperationResult SetBoolean(const std::uint32_t* value_references, std::size_t count, const bool* values, std::optional<std::size_t> value_count = std::nullopt);
    OperationResult SetString(const std::uint32_t* value_references, std::size_t count, const char* const* values, std::optional<std::size_t> value_count = std::nullopt);
    OperationResult SetBinary(const std::uint32_t* value_references, std::size_t count, const std::size_t* value_sizes, const std::uint8_t* const* values, std::optional<std::size_t> value_count = std::nullopt);
    OperationResult SetClock(const std::uint32_t* value_references, std::size_t count, const bool* values);

    OperationResult GetReal(const std::uint32_t* value_references, std::size_t count, double* values, std::optional<std::size_t> value_count = std::nullopt);
    OperationResult GetInteger(const std::uint32_t* value_references, std::size_t count, std::int32_t* values, std::optional<std::size_t> value_count = std::nullopt);
    OperationResult GetSignedInteger(const std::uint32_t* value_references, std::size_t count, std::int64_t* values, std::optional<std::size_t> value_count = std::nullopt);
    OperationResult GetUnsignedInteger(const std::uint32_t* value_references, std::size_t count, std::uint64_t* values, std::optional<std::size_t> value_count = std::nullopt);
    OperationResult GetBoolean(const std::uint32_t* value_references, std::size_t count, bool* values, std::optional<std::size_t> value_count = std::nullopt);
    OperationResult GetString(const std::uint32_t* value_references, std::size_t count, const char** values, std::optional<std::size_t> value_count = std::nullopt);
    OperationResult GetBinary(const std::uint32_t* value_references, std::size_t count, std::size_t* value_sizes, const std::uint8_t** values, std::optional<std::size_t> value_count = std::nullopt);
    OperationResult GetClock(const std::uint32_t* value_references, std::size_t count, bool* values);
    std::size_t ExpectedValueCount(const std::uint32_t* value_references, std::size_t count) const;
    bool TryExpectedValueCount(const std::uint32_t* value_references,
                               std::size_t count,
                               std::size_t* expected_value_count) const;

    const RuntimeConfig& Config() const;
    const ModelDescription& Model() const;
    std::size_t NumberOfContinuousStates() const;
    std::size_t NumberOfEventIndicators() const;
    SessionState State() const;
    double CurrentTime() const;
    bool LastStepEarlyReturn() const;
    bool LastStepEventHandlingNeeded() const;
    bool LastStepTerminated() const;
    bool SimulationFinished() const;
    const std::string& LastError() const;

private:
    OperationResult Transition(SessionState next);
    OperationResult SetValue(const VariableInfo& variable, ScalarValue value);
    const ScalarValue* GetCachedValue(std::uint32_t value_reference) const;
    OperationResult ApplyOutputSnapshot(const OutputSnapshot& snapshot);
    OperationResult EvaluateInitialization();
    OperationResult EvaluateInitializationForValues(const std::uint32_t* value_references,
                                                    std::size_t count,
                                                    std::optional<std::size_t> value_count);
    void InvalidateArraysForStructuralParameter(const VariableInfo& variable, bool initialization_configuration);
    void SeedCacheFromModelDefaults();
    std::size_t ResolveVariableFlatSize(const VariableInfo& variable) const;
    bool TryResolveVariableFlatSize(const VariableInfo& variable, std::size_t* flat_size) const;
    std::optional<std::int32_t> ResolveDimensionExtent(const DimensionInfo& dimension) const;
    void SetError(const std::string& message);
    static std::string DecodeFileUri(const std::string& resource_location);
    std::string ModelExchangeValueType(const VariableInfo& variable) const;
    OperationResult RefreshModelExchangeValues(const std::uint32_t* value_references,
                                               std::size_t count,
                                               ScalarType expected_type,
                                               std::optional<std::size_t> value_count);
    OperationResult SetModelExchangeValue(const VariableInfo& variable, const ScalarValue& value);

    template <typename T>
    OperationResult SetNumericValues(const std::uint32_t* value_references,
                                     std::size_t count,
                                     const T* values,
                                     std::optional<std::size_t> value_count,
                                     ScalarType expected_type);

    template <typename T>
    OperationResult GetNumericValues(const std::uint32_t* value_references,
                                     std::size_t count,
                                     T* values,
                                     std::optional<std::size_t> value_count,
                                     ScalarType expected_type);

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
    bool early_return_allowed_ = false;
    bool model_exchange_mode_ = false;
    bool model_exchange_external_solver_active_ = false;
    std::string model_exchange_remote_mode_ = "instantiated";
    bool initialization_mode_entered_ = false;
    bool configuration_mode_ = false;
    bool configuration_mode_initialization_ = false;
    bool last_step_early_return_ = false;
    bool last_step_event_handling_needed_ = false;
    bool last_step_terminated_ = false;
    bool simulation_finished_ = false;
    std::chrono::steady_clock::time_point realtime_wall_origin_{};
    double realtime_sim_origin_ = 0.0;
    bool realtime_clock_started_ = false;
    bool initialization_evaluated_ = false;
    bool initialization_evaluation_dirty_ = false;
    std::map<std::uint32_t, ScalarValue> cached_values_;
    std::map<std::string, ScalarValue> initial_inputs_;
    std::map<std::string, ScalarValue> pending_inputs_;
    std::map<std::string, ScalarValue> reconfiguration_values_;
    std::vector<std::string> string_cache_;
    std::vector<BinaryValue> binary_cache_;
};

}  // namespace decentralabs::proxy
