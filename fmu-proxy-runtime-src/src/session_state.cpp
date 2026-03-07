#include "decentralabs_proxy/session_state.hpp"

namespace decentralabs::proxy {

bool CanTransition(const SessionState from, const SessionState to) {
    if (from == SessionState::kError || from == SessionState::kTerminated) {
        return false;
    }
    if (from == to) {
        return true;
    }

    switch (from) {
        case SessionState::kUnconfigured:
            return to == SessionState::kInstantiated;
        case SessionState::kInstantiated:
            return to == SessionState::kSocketConnecting || to == SessionState::kTerminated;
        case SessionState::kSocketConnecting:
            return to == SessionState::kSocketReady || to == SessionState::kError;
        case SessionState::kSocketReady:
            return to == SessionState::kSessionCreated || to == SessionState::kError;
        case SessionState::kSessionCreated:
            return to == SessionState::kInitialized || to == SessionState::kError;
        case SessionState::kInitialized:
            return to == SessionState::kRunning || to == SessionState::kPaused || to == SessionState::kTerminated;
        case SessionState::kRunning:
            return to == SessionState::kPaused || to == SessionState::kTerminated || to == SessionState::kError;
        case SessionState::kPaused:
            return to == SessionState::kRunning || to == SessionState::kTerminated || to == SessionState::kError;
        case SessionState::kTerminated:
        case SessionState::kError:
            return false;
    }

    return false;
}

const char* ToString(const SessionState state) {
    switch (state) {
        case SessionState::kUnconfigured:
            return "unconfigured";
        case SessionState::kInstantiated:
            return "instantiated";
        case SessionState::kSocketConnecting:
            return "socket_connecting";
        case SessionState::kSocketReady:
            return "socket_ready";
        case SessionState::kSessionCreated:
            return "session_created";
        case SessionState::kInitialized:
            return "initialized";
        case SessionState::kRunning:
            return "running";
        case SessionState::kPaused:
            return "paused";
        case SessionState::kTerminated:
            return "terminated";
        case SessionState::kError:
            return "error";
    }

    return "unknown";
}

}  // namespace decentralabs::proxy
