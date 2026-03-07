#pragma once

namespace decentralabs::proxy {

enum class SessionState {
    kUnconfigured,
    kInstantiated,
    kSocketConnecting,
    kSocketReady,
    kSessionCreated,
    kInitialized,
    kRunning,
    kPaused,
    kTerminated,
    kError,
};

bool CanTransition(SessionState from, SessionState to);
const char* ToString(SessionState state);

}  // namespace decentralabs::proxy
