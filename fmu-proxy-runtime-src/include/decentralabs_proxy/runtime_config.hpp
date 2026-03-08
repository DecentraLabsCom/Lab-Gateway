#pragma once

#include <optional>
#include <string>
#include <vector>

#include "decentralabs_proxy/operation_result.hpp"

namespace decentralabs::proxy {

enum class TimeMode {
    kSimTime,
    kRealtime,
};

struct RuntimeConfig {
    std::string fmi_version = "2.0.3";
    std::string gateway_ws_url;
    std::string lab_id;
    std::string reservation_key;
    std::string session_ticket;
    std::optional<long long> ticket_expires_at;
    std::string protocol_version = "1.0";
    TimeMode time_mode = TimeMode::kSimTime;
};

std::vector<std::string> MissingRequiredConfigFields(const RuntimeConfig& config);
bool HasRequiredConfig(const RuntimeConfig& config);
const char* ToString(TimeMode mode);
ValueResult<RuntimeConfig> ParseRuntimeConfigJson(const std::string& text);
ValueResult<RuntimeConfig> LoadRuntimeConfigFromFile(const std::string& path);

}  // namespace decentralabs::proxy
