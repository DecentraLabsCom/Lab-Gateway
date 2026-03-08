#include "decentralabs_proxy/gateway_client.hpp"

#include <type_traits>
#include <utility>

#include "decentralabs_proxy/protocol.hpp"

namespace decentralabs::proxy {

namespace {

JsonValue ToJsonValuePrimitive(double value) { return JsonValue(value); }
JsonValue ToJsonValuePrimitive(std::int32_t value) { return JsonValue(static_cast<int>(value)); }
JsonValue ToJsonValuePrimitive(bool value) { return JsonValue(value); }
JsonValue ToJsonValuePrimitive(const std::string& value) { return JsonValue(value); }

template <typename T>
JsonValue ToJsonValueArray(const std::vector<T>& values) {
    JsonArray items;
    items.reserve(values.size());
    for (const auto& item : values) {
        items.emplace_back(ToJsonValuePrimitive(item));
    }
    return JsonValue(std::move(items));
}

JsonValue ToJsonValue(const ScalarValue& value) {
    return std::visit(
        [](const auto& typed) -> JsonValue {
            using ValueType = std::decay_t<decltype(typed)>;
            if constexpr (std::is_same_v<ValueType, RealArray> ||
                          std::is_same_v<ValueType, IntegerArray> ||
                          std::is_same_v<ValueType, StringArray>) {
                return ToJsonValueArray(typed);
            } else if constexpr (std::is_same_v<ValueType, BooleanArray>) {
                JsonArray items;
                items.reserve(typed.size());
                for (bool item : typed) {
                    items.emplace_back(JsonValue(item));
                }
                return JsonValue(std::move(items));
            } else {
                return ToJsonValuePrimitive(typed);
            }
        },
        value);
}

JsonObject ToJsonObject(const std::map<std::string, ScalarValue>& values) {
    JsonObject json_values;
    for (const auto& [name, value] : values) {
        json_values.emplace(name, ToJsonValue(value));
    }
    return json_values;
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
    return OperationResult::Success();
}

OperationResult GatewayClient::Initialize(const RuntimeConfig& config,
                                          const ExperimentConfig& experiment,
                                          const std::map<std::string, ScalarValue>& initial_inputs) {
    JsonObject options = {
        {"timeMode", JsonValue(std::string(ToString(config.time_mode)))},
        {"startTime", JsonValue(experiment.start_time)},
        {"stopTime", JsonValue(experiment.stop_time)},
        {"stepSize", JsonValue(experiment.step_size)},
    };
    if (!initial_inputs.empty()) {
        options.emplace("inputs", JsonValue(ToJsonObject(initial_inputs)));
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
        {"values", JsonValue(ToJsonObject(values))},
    };

    const auto response = SendRequest(request);
    if (!response) {
        return response.status;
    }
    return EnsureResponseType(response.value, kSimInputsUpdated);
}

ValueResult<OutputSnapshot> GatewayClient::Step(const double delta_t) {
    JsonObject request = {
        {"type", JsonValue(std::string(kSimStep))},
        {"requestId", JsonValue(NextRequestId())},
        {"sessionId", JsonValue(session_id_)},
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
    if (const JsonValue* values = FindObjectValue(response.value, "values")) {
        if (const JsonObject* object = values->AsObject()) {
            snapshot.values = *object;
        }
    }
    return ValueResult<OutputSnapshot>::Success(std::move(snapshot));
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

OperationResult GatewayClient::Reset() {
    JsonObject request = {
        {"type", JsonValue(std::string(kSimReset))},
        {"requestId", JsonValue(NextRequestId())},
        {"sessionId", JsonValue(session_id_)},
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
