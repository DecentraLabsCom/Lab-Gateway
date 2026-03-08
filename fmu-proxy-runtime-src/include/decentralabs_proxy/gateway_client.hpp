#pragma once

#include <cstdint>
#include <map>
#include <memory>
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
    double stop_time = 1.0;
    double step_size = 0.01;
};

struct OutputSnapshot {
    double sim_time = 0.0;
    JsonObject values;
};

class GatewayClient {
public:
    explicit GatewayClient(std::unique_ptr<GatewayTransport> transport);

    OperationResult CreateSession(const RuntimeConfig& config);
    OperationResult Initialize(const RuntimeConfig& config,
                               const ExperimentConfig& experiment,
                               const std::map<std::string, ScalarValue>& initial_inputs);
    OperationResult SetInputs(const std::map<std::string, ScalarValue>& values);
    ValueResult<OutputSnapshot> Step(double delta_t);
    ValueResult<OutputSnapshot> GetOutputs(const std::vector<std::string>& variables);
    OperationResult Reset();
    OperationResult Terminate();

    const std::string& SessionId() const;
    bool IsConnected() const;

private:
    ValueResult<JsonObject> SendRequest(const JsonObject& request);
    OperationResult EnsureConnected(const std::string& url);
    std::string NextRequestId();

    std::unique_ptr<GatewayTransport> transport_;
    std::uint64_t request_counter_ = 0;
    std::string gateway_url_;
    std::string session_id_;
};

}  // namespace decentralabs::proxy
