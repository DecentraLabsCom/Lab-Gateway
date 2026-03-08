#include "decentralabs_proxy/runtime_config.hpp"

#include <fstream>
#include <sstream>
#include <utility>

#include "decentralabs_proxy/json.hpp"

namespace decentralabs::proxy {

std::vector<std::string> MissingRequiredConfigFields(const RuntimeConfig& config) {
    std::vector<std::string> missing;
    if (config.gateway_ws_url.empty()) {
        missing.emplace_back("gatewayWsUrl");
    }
    if (config.lab_id.empty()) {
        missing.emplace_back("labId");
    }
    if (config.reservation_key.empty()) {
        missing.emplace_back("reservationKey");
    }
    if (config.session_ticket.empty()) {
        missing.emplace_back("sessionTicket");
    }
    if (config.protocol_version.empty()) {
        missing.emplace_back("protocolVersion");
    }
    return missing;
}

bool HasRequiredConfig(const RuntimeConfig& config) {
    return MissingRequiredConfigFields(config).empty();
}

const char* ToString(const TimeMode mode) {
    switch (mode) {
        case TimeMode::kSimTime:
            return "simtime";
        case TimeMode::kRealtime:
            return "realtime";
    }
    return "unknown";
}

namespace {

std::string ReadFileText(const std::string& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        return {};
    }
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return buffer.str();
}

}  // namespace

ValueResult<RuntimeConfig> ParseRuntimeConfigJson(const std::string& text) {
    const auto parsed = ParseJson(text);
    if (!parsed) {
        return ValueResult<RuntimeConfig>::Failure(parsed.status.code, parsed.status.message);
    }

    const JsonObject* root = parsed.value.AsObject();
    if (root == nullptr) {
        return ValueResult<RuntimeConfig>::Failure(
            "CONFIG_INVALID",
            "Runtime config must be a JSON object");
    }

    RuntimeConfig config;
    config.fmi_version = JsonString(*root, "fmiVersion", "2.0.3");
    config.gateway_ws_url = JsonString(*root, "gatewayWsUrl");
    config.lab_id = JsonString(*root, "labId");
    config.reservation_key = JsonString(*root, "reservationKey");
    config.session_ticket = JsonString(*root, "sessionTicket");
    config.protocol_version = JsonString(*root, "protocolVersion", "1.0");

    const JsonValue* ticket_expires = FindObjectValue(*root, "ticketExpiresAt");
    if (ticket_expires != nullptr && ticket_expires->IsNumber()) {
        config.ticket_expires_at = static_cast<long long>(ticket_expires->AsNumber());
    }

    const std::string time_mode = JsonString(*root, "timeMode", "simtime");
    config.time_mode = (time_mode == "realtime") ? TimeMode::kRealtime : TimeMode::kSimTime;

    const auto missing = MissingRequiredConfigFields(config);
    if (!missing.empty()) {
        std::string message = "Missing required config fields:";
        for (const auto& field : missing) {
            message += " " + field;
        }
        return ValueResult<RuntimeConfig>::Failure("CONFIG_INVALID", std::move(message));
    }

    return ValueResult<RuntimeConfig>::Success(std::move(config));
}

ValueResult<RuntimeConfig> LoadRuntimeConfigFromFile(const std::string& path) {
    const std::string payload = ReadFileText(path);
    if (payload.empty()) {
        return ValueResult<RuntimeConfig>::Failure(
            "CONFIG_IO_ERROR",
            "Unable to read runtime config from " + path);
    }
    return ParseRuntimeConfigJson(payload);
}

}  // namespace decentralabs::proxy
