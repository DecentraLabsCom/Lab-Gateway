#include "decentralabs_proxy/runtime_config.hpp"

#include <utility>

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

}  // namespace decentralabs::proxy
