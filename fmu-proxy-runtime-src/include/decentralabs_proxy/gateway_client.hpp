#pragma once

#include <cstddef>
#include <chrono>
#include <cstdint>
#include <deque>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "decentralabs_proxy/json.hpp"
#include "decentralabs_proxy/model_description.hpp"
#include "decentralabs_proxy/operation_result.hpp"
#include "decentralabs_proxy/runtime_config.hpp"
#include "decentralabs_proxy/transport.hpp"

namespace decentralabs::proxy {

struct ExperimentConfig {
    double start_time = 0.0;
    std::optional<double> stop_time;
    double step_size = 0.01;
};

struct OutputSnapshot {
    double sim_time = 0.0;
    JsonObject values;
    bool early_return = false;
    bool event_handling_needed = false;
    bool terminate_simulation = false;
    bool finished = false;
    bool next_event_time_defined = false;
    std::optional<double> next_event_time;
};

class GatewayClient {
public:
    explicit GatewayClient(std::unique_ptr<GatewayTransport> transport);

    OperationResult CreateSession(const RuntimeConfig& config);
    OperationResult Initialize(const RuntimeConfig& config,
                               const ExperimentConfig& experiment,
                               const std::map<std::string, ScalarValue>& initial_inputs,
                               const std::map<std::string, ScalarValue>& initial_parameters,
                               bool early_return_allowed = false,
                               bool model_exchange = false,
                               bool defer_initialization_exit = false);
    OperationResult ExitInitializationMode();
    ValueResult<JsonObject> ModelExchangeCall(const std::string& operation,
                                              const JsonObject& arguments = {});
    OperationResult Reconfigure(const std::map<std::string, ScalarValue>& values);
    OperationResult SetInputs(const std::map<std::string, ScalarValue>& values,
                              bool* terminate_simulation = nullptr);
    ValueResult<OutputSnapshot> Step(double delta_t);
    ValueResult<OutputSnapshot> Step(double current_time, double delta_t);
    ValueResult<OutputSnapshot> Advance(
        double current_time,
        double delta_t,
        const std::map<std::string, ScalarValue>& input_values);
    ValueResult<OutputSnapshot> GetOutputs(const std::vector<std::string>& variables);
    ValueResult<JsonObject> CaptureFmuState();
    ValueResult<OutputSnapshot> RestoreFmuState(
        const JsonObject& checkpoint,
        const std::vector<std::string>& variables);
    OperationResult Reset();
    OperationResult Terminate();

    const std::string& SessionId() const;
    bool IsConnected() const;

private:
    ValueResult<JsonObject> SendRequest(const JsonObject& request);
    OperationResult EnsureConnected(const std::string& url);
    OperationResult WaitForRequestCapacity(bool has_input_update,
                                           std::chrono::milliseconds& total_wait,
                                           std::chrono::milliseconds max_wait);
    std::string NextRequestId();

    std::unique_ptr<GatewayTransport> transport_;
    std::uint64_t request_counter_ = 0;
    std::string gateway_url_;
    std::string session_id_;
    std::size_t max_input_updates_per_window_ = 0;
    std::chrono::milliseconds input_update_window_{0};
    double max_output_hz_ = 0.0;
    std::deque<std::chrono::steady_clock::time_point> input_update_times_;
    std::chrono::steady_clock::time_point last_output_advance_{};
};

}  // namespace decentralabs::proxy
