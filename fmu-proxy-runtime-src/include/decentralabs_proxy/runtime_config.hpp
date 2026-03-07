#pragma once

#include <string>
#include <vector>

namespace decentralabs::proxy {

enum class TimeMode {
    kSimTime,
    kRealtime,
};

struct RuntimeConfig {
    std::string gateway_ws_url;
    std::string lab_id;
    std::string reservation_key;
    std::string session_ticket;
    std::string protocol_version = "1.0";
    TimeMode time_mode = TimeMode::kSimTime;
};

std::vector<std::string> MissingRequiredConfigFields(const RuntimeConfig& config);
bool HasRequiredConfig(const RuntimeConfig& config);
const char* ToString(TimeMode mode);

}  // namespace decentralabs::proxy
