#include "decentralabs_proxy/protocol.hpp"

#include <algorithm>

namespace decentralabs::proxy {

namespace {

const std::vector<std::string_view> kClientMessages = {
    kSessionCreate,
    kSessionPing,
    kModelDescribe,
    kSimInitialize,
    kSimSetInputs,
    kSimStep,
    kSimGetOutputs,
    kSessionTerminate,
};

const std::vector<std::string_view> kServerMessages = {
    kSessionCreated,
    kSessionPong,
    kModelDescription,
    kSimState,
    kSimOutputs,
    kSessionClosed,
    kError,
};

bool Contains(const std::vector<std::string_view>& haystack, const std::string_view needle) {
    return std::find(haystack.begin(), haystack.end(), needle) != haystack.end();
}

}  // namespace

const std::vector<std::string_view>& SupportedClientMessages() {
    return kClientMessages;
}

const std::vector<std::string_view>& SupportedServerMessages() {
    return kServerMessages;
}

bool IsSupportedClientMessage(const std::string_view type) {
    return Contains(kClientMessages, type);
}

bool IsSupportedServerMessage(const std::string_view type) {
    return Contains(kServerMessages, type);
}

}  // namespace decentralabs::proxy
