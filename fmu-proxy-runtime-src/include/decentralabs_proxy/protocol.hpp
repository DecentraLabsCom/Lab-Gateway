#pragma once

#include <string_view>
#include <vector>

namespace decentralabs::proxy {

inline constexpr std::string_view kSessionCreate = "session.create";
inline constexpr std::string_view kSessionPing = "session.ping";
inline constexpr std::string_view kModelDescribe = "model.describe";
inline constexpr std::string_view kSimInitialize = "sim.initialize";
inline constexpr std::string_view kSimSetInputs = "sim.setInputs";
inline constexpr std::string_view kSimStep = "sim.step";
inline constexpr std::string_view kSimGetOutputs = "sim.getOutputs";
inline constexpr std::string_view kSimReset = "sim.reset";
inline constexpr std::string_view kSessionTerminate = "session.terminate";

inline constexpr std::string_view kSessionCreated = "session.created";
inline constexpr std::string_view kSessionPong = "session.pong";
inline constexpr std::string_view kModelDescription = "model.description";
inline constexpr std::string_view kSimState = "sim.state";
inline constexpr std::string_view kSimOutputs = "sim.outputs";
inline constexpr std::string_view kSimInputsUpdated = "sim.inputs.updated";
inline constexpr std::string_view kSessionClosed = "session.closed";
inline constexpr std::string_view kError = "error";

const std::vector<std::string_view>& SupportedClientMessages();
const std::vector<std::string_view>& SupportedServerMessages();
bool IsSupportedClientMessage(std::string_view type);
bool IsSupportedServerMessage(std::string_view type);

}  // namespace decentralabs::proxy
