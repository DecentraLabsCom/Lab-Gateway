#include "decentralabs_proxy/gateway_client.hpp"

#include <chrono>
#include <cmath>
#include <thread>
#include <utility>

#include "decentralabs_proxy/protocol.hpp"
#include "decentralabs_proxy/scalar_value_codec.hpp"

namespace decentralabs::proxy {

namespace {

double PositiveIntegerCapability(const JsonObject* object, const char* key, double maximum) {
    if (object == nullptr) {
        return 0.0;
    }
    const JsonValue* value = FindObjectValue(*object, key);
    if (value == nullptr || !value->IsNumber()) {
        return 0.0;
    }
    const double number = value->AsNumber();
    if (!std::isfinite(number) || number < 1.0 || number > maximum || std::floor(number) != number) {
        return 0.0;
    }
    return number;
}

ValueResult<JsonObject> ParseResponseObject(const std::string& payload) {
    const auto parsed = ParseJson(payload);
    if (!parsed) {
        return ValueResult<JsonObject>::Failure(parsed.status.code, parsed.status.message);
    }
    const JsonObject* object = parsed.value.AsObject();
    if (object == nullptr) {
        return ValueResult<JsonObject>::Failure(
            "GATEWAY_PROTOCOL_ERROR",
            "Gateway reply is not a JSON object");
    }
    return ValueResult<JsonObject>::Success(*object);
}

OperationResult EnsureResponseType(const JsonObject& response, const std::string_view expected_type) {
    const std::string response_type = JsonString(response, "type");
    if (response_type == expected_type) {
        return OperationResult::Success();
    }
    if (response_type == std::string(kError)) {
        return OperationResult::Failure(
            JsonString(response, "code", "GATEWAY_ERROR"),
            JsonString(response, "message", "Gateway returned an error"));
    }
    return OperationResult::Failure(
        "GATEWAY_PROTOCOL_ERROR",
        "Unexpected gateway response type: " + response_type);
}

}  // namespace

GatewayClient::GatewayClient(std::unique_ptr<GatewayTransport> transport)
    : transport_(std::move(transport)) {}

OperationResult GatewayClient::EnsureConnected(const std::string& url) {
    if (transport_ == nullptr) {
        return OperationResult::Failure("TRANSPORT_NOT_CONFIGURED", "Gateway transport is not configured");
    }
    if (transport_->IsConnected()) {
        return OperationResult::Success();
    }
    gateway_url_ = url;
    return transport_->Connect(url);
}

std::string GatewayClient::NextRequestId() {
    ++request_counter_;
    return "req-" + std::to_string(request_counter_);
}

ValueResult<JsonObject> GatewayClient::SendRequest(const JsonObject& request) {
    if (transport_ == nullptr || !transport_->IsConnected()) {
        return ValueResult<JsonObject>::Failure(
            "TRANSPORT_NOT_CONNECTED",
            "Gateway transport is not connected");
    }

    const std::string expected_request_id = JsonString(request, "requestId");
    const auto send_status = transport_->SendText(SerializeJson(JsonValue(request)));
    if (!send_status) {
        return ValueResult<JsonObject>::Failure(send_status.code, send_status.message);
    }

    for (int attempt = 0; attempt < 32; ++attempt) {
        const auto reply = transport_->ReceiveText();
        if (!reply) {
            return ValueResult<JsonObject>::Failure(reply.status.code, reply.status.message);
        }

        const auto response = ParseResponseObject(reply.value);
        if (!response) {
            return response;
        }

        const std::string response_request_id = JsonString(response.value, "requestId");
        if (expected_request_id.empty() || response_request_id == expected_request_id) {
            return response;
        }

        const std::string response_type = JsonString(response.value, "type");
        if (response_type == std::string(kSessionClosed)) {
            return ValueResult<JsonObject>::Failure(
                "GATEWAY_SESSION_CLOSED",
                JsonString(response.value, "reason", "Gateway session closed"));
        }
    }

    return ValueResult<JsonObject>::Failure(
        "GATEWAY_PROTOCOL_ERROR",
        "Timed out waiting for a matching gateway response");
}

OperationResult GatewayClient::CreateSession(const RuntimeConfig& config) {
    const auto connect_status = EnsureConnected(config.gateway_ws_url);
    if (!connect_status) {
        return connect_status;
    }

    JsonObject request = {
        {"type", JsonValue(std::string(kSessionCreate))},
        {"requestId", JsonValue(NextRequestId())},
        {"labId", JsonValue(config.lab_id)},
        {"reservationKey", JsonValue(config.reservation_key)},
        {"sessionTicket", JsonValue(config.session_ticket)},
        {"client", JsonValue(JsonObject{
            {"name", JsonValue("decentralabs-proxy-runtime")},
            {"version", JsonValue("0.1.0")},
        })},
    };

    const auto response = SendRequest(request);
    if (!response) {
        return response.status;
    }
    const auto type_status = EnsureResponseType(response.value, kSessionCreated);
    if (!type_status) {
        return type_status;
    }
    session_id_ = JsonString(response.value, "sessionId");
    if (session_id_.empty()) {
        return OperationResult::Failure("GATEWAY_PROTOCOL_ERROR", "Gateway did not return a sessionId");
    }

    const JsonValue* capabilities_value = FindObjectValue(response.value, "capabilities");
    const JsonObject* capabilities = capabilities_value != nullptr ? capabilities_value->AsObject() : nullptr;
    const JsonValue* input_quota_value = capabilities != nullptr
        ? FindObjectValue(*capabilities, "inputUpdateQuota")
        : nullptr;
    const JsonObject* input_quota = input_quota_value != nullptr ? input_quota_value->AsObject() : nullptr;
    const double input_update_limit = PositiveIntegerCapability(input_quota, "maxUpdatesPerWindow", 10000.0);
    const double input_update_window_ms = PositiveIntegerCapability(input_quota, "windowMs", 3600000.0);
    const double output_hz = PositiveIntegerCapability(capabilities, "maxOutputHz", 1000.0);
    max_input_updates_per_window_ = input_update_limit > 0.0
        ? static_cast<std::size_t>(input_update_limit)
        : 0;
    input_update_window_ = input_update_window_ms > 0.0
        ? std::chrono::milliseconds(static_cast<std::int64_t>(input_update_window_ms))
        : std::chrono::milliseconds::zero();
    max_output_hz_ = output_hz;
    return OperationResult::Success();
}

OperationResult GatewayClient::WaitForRequestCapacity(
    const bool has_input_update,
    std::chrono::milliseconds& total_wait,
    const std::chrono::milliseconds max_wait) {
    using Clock = std::chrono::steady_clock;
    while (true) {
        const auto now = Clock::now();
        auto wait_duration = Clock::duration::zero();
        std::string wait_code = "OUTPUT_READ_RATE_LIMITED";

        if (max_output_hz_ > 0.0 && last_output_advance_ != Clock::time_point{}) {
            const auto minimum_interval = std::chrono::duration_cast<Clock::duration>(
                std::chrono::duration<double>(1.0 / max_output_hz_));
            const auto output_wait = last_output_advance_ + minimum_interval - now;
            if (output_wait > wait_duration) {
                wait_duration = output_wait;
            }
        }

        if (has_input_update && max_input_updates_per_window_ > 0 && input_update_window_.count() > 0) {
            while (!input_update_times_.empty()
                   && input_update_times_.front() + input_update_window_ <= now) {
                input_update_times_.pop_front();
            }
            if (input_update_times_.size() >= max_input_updates_per_window_) {
                const auto input_wait = input_update_times_.front() + input_update_window_ - now;
                if (input_wait >= wait_duration) {
                    wait_duration = input_wait;
                    wait_code = "INPUT_UPDATE_RATE_LIMIT";
                }
            }
        }

        if (wait_duration <= Clock::duration::zero()) {
            return OperationResult::Success();
        }

        const auto wait_ms = std::chrono::ceil<std::chrono::milliseconds>(wait_duration)
            + std::chrono::milliseconds(1);
        if (total_wait + wait_ms > max_wait) {
            return OperationResult::Failure(
                wait_code,
                "The provider's advertised FMU request quota exceeds the proxy's bounded wait");
        }
        std::this_thread::sleep_for(wait_ms);
        total_wait += wait_ms;
    }
}

OperationResult GatewayClient::Initialize(const RuntimeConfig& config,
                                          const ExperimentConfig& experiment,
                                          const std::map<std::string, ScalarValue>& initial_inputs,
                                          const bool early_return_allowed) {
    JsonObject options = {
        {"timeMode", JsonValue(std::string(ToString(config.time_mode)))},
        {"startTime", JsonValue(experiment.start_time)},
        {"stopTime", JsonValue(experiment.stop_time)},
        {"stepSize", JsonValue(experiment.step_size)},
        {"earlyReturnAllowed", JsonValue(early_return_allowed)},
        {"playbackSpeed", JsonValue(config.playback_speed)},
    };
    if (!initial_inputs.empty()) {
        options.emplace("inputs", JsonValue(scalar_value_codec::EncodeJsonObject(initial_inputs)));
    }

    JsonObject request = {
        {"type", JsonValue(std::string(kSimInitialize))},
        {"requestId", JsonValue(NextRequestId())},
        {"sessionId", JsonValue(session_id_)},
        {"options", JsonValue(std::move(options))},
    };

    const auto response = SendRequest(request);
    if (!response) {
        return response.status;
    }
    return EnsureResponseType(response.value, kSimState);
}

OperationResult GatewayClient::SetInputs(const std::map<std::string, ScalarValue>& values) {
    if (values.empty()) {
        return OperationResult::Success();
    }

    JsonObject request = {
        {"type", JsonValue(std::string(kSimSetInputs))},
        {"requestId", JsonValue(NextRequestId())},
        {"sessionId", JsonValue(session_id_)},
        {"values", JsonValue(scalar_value_codec::EncodeJsonObject(values))},
    };

    const auto response = SendRequest(request);
    if (!response) {
        return response.status;
    }
    return EnsureResponseType(response.value, kSimInputsUpdated);
}

ValueResult<OutputSnapshot> GatewayClient::Step(const double delta_t) {
    return Step(0.0, delta_t);
}

ValueResult<OutputSnapshot> GatewayClient::Step(const double current_time, const double delta_t) {
    JsonObject request = {
        {"type", JsonValue(std::string(kSimStep))},
        {"requestId", JsonValue(NextRequestId())},
        {"sessionId", JsonValue(session_id_)},
        {"currentCommunicationPoint", JsonValue(current_time)},
        {"deltaT", JsonValue(delta_t)},
    };

    const auto response = SendRequest(request);
    if (!response) {
        return ValueResult<OutputSnapshot>::Failure(response.status.code, response.status.message);
    }
    const auto type_status = EnsureResponseType(response.value, kSimOutputs);
    if (!type_status) {
        return ValueResult<OutputSnapshot>::Failure(type_status.code, type_status.message);
    }

    OutputSnapshot snapshot;
    snapshot.sim_time = JsonNumber(response.value, "simTime", 0.0);
    snapshot.early_return = JsonBool(response.value, "earlyReturn");
    snapshot.event_handling_needed = JsonBool(response.value, "eventHandlingNeeded");
    snapshot.terminate_simulation = JsonBool(response.value, "terminateSimulation");
    snapshot.finished = JsonBool(response.value, "finished");
    if (const JsonValue* values = FindObjectValue(response.value, "values")) {
        if (const JsonObject* object = values->AsObject()) {
            snapshot.values = *object;
        }
    }
    return ValueResult<OutputSnapshot>::Success(std::move(snapshot));
}

ValueResult<OutputSnapshot> GatewayClient::Advance(
    const double current_time,
    const double delta_t,
    const std::map<std::string, ScalarValue>& input_values) {
    constexpr int kMaxRetryAttempts = 8;
    constexpr auto kMaxRetryWait = std::chrono::seconds(30);
    auto total_retry_wait = std::chrono::milliseconds::zero();

    for (int attempt = 0; attempt < kMaxRetryAttempts; ++attempt) {
        const auto capacity_status = WaitForRequestCapacity(
            !input_values.empty(),
            total_retry_wait,
            std::chrono::duration_cast<std::chrono::milliseconds>(kMaxRetryWait));
        if (!capacity_status) {
            return ValueResult<OutputSnapshot>::Failure(capacity_status.code, capacity_status.message);
        }

        JsonObject request = {
            {"type", JsonValue(std::string(kSimAdvance))},
            {"requestId", JsonValue(NextRequestId())},
            {"sessionId", JsonValue(session_id_)},
            {"currentCommunicationPoint", JsonValue(current_time)},
            {"targetTime", JsonValue(current_time + delta_t)},
            {"stepSize", JsonValue(delta_t)},
            {"maxSamples", JsonValue(1)},
        };
        if (!input_values.empty()) {
            request.emplace("inputValues", JsonValue(scalar_value_codec::EncodeJsonObject(input_values)));
        }

        const auto response = SendRequest(request);
        if (!response) {
            return ValueResult<OutputSnapshot>::Failure(response.status.code, response.status.message);
        }

        const std::string response_type = JsonString(response.value, "type");
        const std::string error_code = JsonString(response.value, "code");
        const bool retryable_pre_execution_code = error_code == "INPUT_UPDATE_RATE_LIMIT"
            || error_code == "OUTPUT_READ_RATE_LIMITED";
        const bool safe_to_retry = response_type == "error"
            && JsonBool(response.value, "retryable")
            && retryable_pre_execution_code;
        const double retry_after_ms = JsonNumber(response.value, "retryAfterMs", 0.0);
        const double remaining_retry_budget_ms =
            std::chrono::duration<double, std::milli>(kMaxRetryWait - total_retry_wait).count();
        if (safe_to_retry && std::isfinite(retry_after_ms) && retry_after_ms > 0.0
            && retry_after_ms <= remaining_retry_budget_ms) {
            const auto retry_delay = std::chrono::milliseconds(
                static_cast<std::int64_t>(std::ceil(retry_after_ms)));
            if (attempt + 1 < kMaxRetryAttempts && retry_delay.count() > 0
                && total_retry_wait + retry_delay <= kMaxRetryWait) {
                std::this_thread::sleep_for(retry_delay);
                total_retry_wait += retry_delay;
                continue;
            }
        }

        const auto type_status = EnsureResponseType(response.value, kSimSamples);
        if (!type_status) {
            return ValueResult<OutputSnapshot>::Failure(type_status.code, type_status.message);
        }

        const JsonValue* samples_value = FindObjectValue(response.value, "samples");
        const JsonArray* samples = samples_value != nullptr ? samples_value->AsArray() : nullptr;
        if (samples == nullptr || samples->empty() || samples->back().AsObject() == nullptr) {
            return ValueResult<OutputSnapshot>::Failure(
                "GATEWAY_PROTOCOL_ERROR",
                "Gateway advance reply did not contain an output sample");
        }

        const JsonObject& sample = *samples->back().AsObject();
        OutputSnapshot snapshot;
        snapshot.sim_time = JsonNumber(sample, "time", JsonNumber(response.value, "simTime", 0.0));
        const double time_tolerance = std::max(1e-12, std::abs(current_time + delta_t) * 1e-12);
        if (!std::isfinite(snapshot.sim_time)
            || snapshot.sim_time < current_time - time_tolerance
            || snapshot.sim_time > current_time + delta_t + time_tolerance) {
            return ValueResult<OutputSnapshot>::Failure(
                "GATEWAY_PROTOCOL_ERROR",
                "Gateway advance returned a sample outside the requested interval");
        }
        snapshot.early_return = JsonBool(sample, "earlyReturn");
        snapshot.event_handling_needed = JsonBool(sample, "eventHandlingNeeded");
        snapshot.terminate_simulation = JsonBool(sample, "terminateSimulation");
        snapshot.finished = JsonBool(sample, "finished", JsonBool(response.value, "finished"));
        const JsonValue* values = FindObjectValue(sample, "outputs");
        if (values == nullptr || values->AsObject() == nullptr) {
            return ValueResult<OutputSnapshot>::Failure(
                "GATEWAY_PROTOCOL_ERROR",
                "Gateway advance sample did not contain an output object");
        }
        snapshot.values = *values->AsObject();
        const auto completed_at = std::chrono::steady_clock::now();
        last_output_advance_ = completed_at;
        if (!input_values.empty()) {
            input_update_times_.push_back(completed_at);
        }
        return ValueResult<OutputSnapshot>::Success(std::move(snapshot));
    }

    return ValueResult<OutputSnapshot>::Failure(
        "ADVANCE_RETRY_LIMIT",
        "Gateway advance exceeded its bounded retry limit");
}

ValueResult<OutputSnapshot> GatewayClient::GetOutputs(const std::vector<std::string>& variables) {
    JsonArray names;
    for (const auto& variable : variables) {
        names.emplace_back(variable);
    }

    JsonObject request = {
        {"type", JsonValue(std::string(kSimGetOutputs))},
        {"requestId", JsonValue(NextRequestId())},
        {"sessionId", JsonValue(session_id_)},
        {"variables", JsonValue(std::move(names))},
    };

    const auto response = SendRequest(request);
    if (!response) {
        return ValueResult<OutputSnapshot>::Failure(response.status.code, response.status.message);
    }
    const auto type_status = EnsureResponseType(response.value, kSimOutputs);
    if (!type_status) {
        return ValueResult<OutputSnapshot>::Failure(type_status.code, type_status.message);
    }

    OutputSnapshot snapshot;
    snapshot.sim_time = JsonNumber(response.value, "simTime", 0.0);
    if (const JsonValue* values = FindObjectValue(response.value, "values")) {
        if (const JsonObject* object = values->AsObject()) {
            snapshot.values = *object;
        }
    }
    return ValueResult<OutputSnapshot>::Success(std::move(snapshot));
}

ValueResult<JsonObject> GatewayClient::CaptureFmuState() {
    JsonObject request = {
        {"type", JsonValue(std::string(kSimCaptureFmuState))},
        {"requestId", JsonValue(NextRequestId())},
        {"sessionId", JsonValue(session_id_)},
    };
    const auto response = SendRequest(request);
    if (!response) {
        return ValueResult<JsonObject>::Failure(response.status.code, response.status.message);
    }
    const auto type_status = EnsureResponseType(response.value, kSimFmuState);
    if (!type_status) {
        return ValueResult<JsonObject>::Failure(type_status.code, type_status.message);
    }
    const JsonValue* checkpoint = FindObjectValue(response.value, "checkpoint");
    const JsonObject* checkpoint_object = checkpoint == nullptr ? nullptr : checkpoint->AsObject();
    if (checkpoint_object == nullptr) {
        return ValueResult<JsonObject>::Failure("GATEWAY_PROTOCOL_ERROR", "Gateway did not return an FMU state checkpoint");
    }
    return ValueResult<JsonObject>::Success({{"checkpoint", JsonValue(*checkpoint_object)}});
}

ValueResult<OutputSnapshot> GatewayClient::RestoreFmuState(
    const JsonObject& checkpoint,
    const std::vector<std::string>& variables) {
    JsonArray variable_names;
    variable_names.reserve(variables.size());
    for (const auto& variable : variables) {
        variable_names.emplace_back(variable);
    }
    JsonObject request = {
        {"type", JsonValue(std::string(kSimRestoreFmuState))},
        {"requestId", JsonValue(NextRequestId())},
        {"sessionId", JsonValue(session_id_)},
        {"checkpoint", JsonValue(checkpoint)},
        {"variables", JsonValue(std::move(variable_names))},
    };
    const auto response = SendRequest(request);
    if (!response) {
        return ValueResult<OutputSnapshot>::Failure(response.status.code, response.status.message);
    }
    const auto type_status = EnsureResponseType(response.value, kSimState);
    if (!type_status) {
        return ValueResult<OutputSnapshot>::Failure(type_status.code, type_status.message);
    }
    const JsonValue* simulation_time = FindObjectValue(response.value, "simTime");
    if (simulation_time == nullptr || !simulation_time->IsNumber()) {
        return ValueResult<OutputSnapshot>::Failure("GATEWAY_PROTOCOL_ERROR", "Gateway did not return the restored FMU time");
    }
    OutputSnapshot snapshot;
    snapshot.sim_time = simulation_time->AsNumber();
    const JsonValue* outputs = FindObjectValue(response.value, "outputs");
    if (outputs != nullptr && outputs->AsObject() != nullptr) {
        snapshot.values = *outputs->AsObject();
    }
    return ValueResult<OutputSnapshot>::Success(std::move(snapshot));
}

OperationResult GatewayClient::Reset() {
    JsonObject request = {
        {"type", JsonValue(std::string(kSimReset))},
        {"requestId", JsonValue(NextRequestId())},
        {"sessionId", JsonValue(session_id_)},
        {"deferInitialization", JsonValue(true)},
    };

    const auto response = SendRequest(request);
    if (!response) {
        return response.status;
    }
    return EnsureResponseType(response.value, kSimState);
}

OperationResult GatewayClient::Terminate() {
    if (transport_ == nullptr || !transport_->IsConnected()) {
        return OperationResult::Success();
    }

    JsonObject request = {
        {"type", JsonValue(std::string(kSessionTerminate))},
        {"requestId", JsonValue(NextRequestId())},
        {"sessionId", JsonValue(session_id_)},
    };

    const auto response = SendRequest(request);
    transport_->Close();
    session_id_.clear();
    if (!response) {
        return response.status;
    }
    return EnsureResponseType(response.value, kSessionClosed);
}

const std::string& GatewayClient::SessionId() const {
    return session_id_;
}

bool GatewayClient::IsConnected() const {
    return transport_ != nullptr && transport_->IsConnected();
}

}  // namespace decentralabs::proxy
