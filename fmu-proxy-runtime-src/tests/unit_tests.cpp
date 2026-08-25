#include <chrono>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <functional>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <system_error>
#include <utility>
#include <variant>
#include <vector>

#include "decentralabs_proxy/gateway_client.hpp"
#include "decentralabs_proxy/json.hpp"
#include "decentralabs_proxy/model_description.hpp"
#include "decentralabs_proxy/protocol.hpp"
#include "decentralabs_proxy/runtime.hpp"
#include "decentralabs_proxy/runtime_config.hpp"
#include "decentralabs_proxy/session_state.hpp"
#include "decentralabs_proxy/transport.hpp"

namespace {

using namespace decentralabs::proxy;

class TestFailure final : public std::runtime_error {
public:
    explicit TestFailure(const std::string& message) : std::runtime_error(message) {}
};

void Check(const bool condition, const char* expression, const char* file, const int line) {
    if (!condition) {
        throw TestFailure(std::string(file) + ":" + std::to_string(line) + " CHECK(" + expression + ") failed");
    }
}

#define CHECK(condition) Check(static_cast<bool>(condition), #condition, __FILE__, __LINE__)

void CheckNear(const double actual, const double expected, const double tolerance, const char* expression,
               const char* file, const int line) {
    if (std::fabs(actual - expected) > tolerance) {
        throw TestFailure(std::string(file) + ":" + std::to_string(line) + " CHECK_NEAR(" + expression + ") failed");
    }
}

#define CHECK_NEAR(actual, expected, tolerance) CheckNear((actual), (expected), (tolerance), #actual, __FILE__, __LINE__)

void CheckStatus(const OperationResult& result, const char* expression, const char* file, const int line) {
    if (!result) {
        throw TestFailure(std::string(file) + ":" + std::to_string(line) + " " + expression + " failed: " +
                          result.code + " - " + result.message);
    }
}

#define CHECK_OK(result) CheckStatus((result), #result, __FILE__, __LINE__)

struct TemporaryDirectory final {
    std::filesystem::path path;

    TemporaryDirectory() {
        const auto stamp = std::chrono::steady_clock::now().time_since_epoch().count();
        path = std::filesystem::temp_directory_path() /
               ("decentralabs-proxy-tests-" + std::to_string(stamp));
        std::filesystem::create_directories(path);
    }

    ~TemporaryDirectory() {
        std::error_code error;
        std::filesystem::remove_all(path, error);
    }
};

void WriteFile(const std::filesystem::path& path, const std::string& contents) {
    std::ofstream file(path, std::ios::binary);
    CHECK(file.good());
    file << contents;
    CHECK(file.good());
}

RuntimeConfig TestConfig() {
    RuntimeConfig config;
    config.gateway_ws_url = "wss://gateway.example/fmu";
    config.lab_id = "lab-1";
    config.reservation_key = "reservation-1";
    config.session_ticket = "ticket-1";
    return config;
}

void TestJsonParserAndSerializer() {
    const auto parsed = ParseJson(R"({"message":"line\n\"quoted\"","enabled":true,"count":3,"items":[null,false]})");
    CHECK(parsed);
    CHECK(parsed.value.IsObject());
    const auto& object = *parsed.value.AsObject();
    CHECK(JsonString(object, "message") == "line\n\"quoted\"");
    CHECK(JsonBool(object, "enabled"));
    CHECK_NEAR(JsonNumber(object, "count"), 3.0, 1e-12);
    const JsonValue* items = FindObjectValue(object, "items");
    CHECK(items != nullptr);
    CHECK(items->IsArray());
    CHECK(items->AsArray()->size() == 2);
    CHECK((*items->AsArray())[0].IsNull());

    const std::string serialized = SerializeJson(parsed.value);
    const auto reparsed = ParseJson(serialized);
    CHECK(reparsed);
    CHECK(JsonString(*reparsed.value.AsObject(), "message") == "line\n\"quoted\"");

    const auto malformed = ParseJson(R"({"missing": 1} trailing)");
    CHECK(!malformed);
    CHECK(malformed.status.code == "JSON_PARSE_ERROR");
    CHECK(JsonString(object, "not-present", "fallback") == "fallback");
}

void TestRuntimeConfigParsing() {
    const auto parsed = ParseRuntimeConfigJson(
        R"({"fmiVersion":"3.0","gatewayWsUrl":"wss://gateway","labId":"lab","reservationKey":"res","sessionTicket":"ticket","ticketExpiresAt":1234,"protocolVersion":"2.0","timeMode":"realtime"})");
    CHECK(parsed);
    CHECK(parsed.value.fmi_version == "3.0");
    CHECK(parsed.value.gateway_ws_url == "wss://gateway");
    CHECK(parsed.value.ticket_expires_at.has_value());
    CHECK(*parsed.value.ticket_expires_at == 1234);
    CHECK(parsed.value.time_mode == TimeMode::kRealtime);
    CHECK(HasRequiredConfig(parsed.value));
    CHECK(std::string(ToString(parsed.value.time_mode)) == "realtime");

    const auto defaults = ParseRuntimeConfigJson(
        R"({"gatewayWsUrl":"wss://gateway","labId":"lab","reservationKey":"res","sessionTicket":"ticket"})");
    CHECK(defaults);
    CHECK(defaults.value.fmi_version == "2.0.3");
    CHECK(defaults.value.protocol_version == "1.0");
    CHECK(defaults.value.time_mode == TimeMode::kSimTime);

    const auto missing = ParseRuntimeConfigJson(
        R"({"gatewayWsUrl":"wss://gateway","labId":"lab","sessionTicket":"ticket"})");
    CHECK(!missing);
    CHECK(missing.status.code == "CONFIG_INVALID");
    CHECK(missing.status.message.find("reservationKey") != std::string::npos);

    const auto invalid = ParseRuntimeConfigJson("[]");
    CHECK(!invalid);
    CHECK(invalid.status.code == "CONFIG_INVALID");
    CHECK(!HasRequiredConfig(RuntimeConfig{}));
}

void TestProtocolAndSessionState() {
    CHECK(IsSupportedClientMessage(kSessionCreate));
    CHECK(IsSupportedClientMessage(kSimStep));
    CHECK(!IsSupportedClientMessage("session.unknown"));
    CHECK(IsSupportedServerMessage(kSessionCreated));
    CHECK(IsSupportedServerMessage(kError));
    CHECK(!IsSupportedServerMessage("sim.unknown"));
    CHECK(SupportedClientMessages().size() == 9);
    CHECK(SupportedServerMessages().size() == 8);

    CHECK(CanTransition(SessionState::kUnconfigured, SessionState::kInstantiated));
    CHECK(CanTransition(SessionState::kInstantiated, SessionState::kSocketConnecting));
    CHECK(CanTransition(SessionState::kSocketConnecting, SessionState::kSocketReady));
    CHECK(CanTransition(SessionState::kSocketReady, SessionState::kSessionCreated));
    CHECK(CanTransition(SessionState::kSessionCreated, SessionState::kInitialized));
    CHECK(CanTransition(SessionState::kInitialized, SessionState::kRunning));
    CHECK(CanTransition(SessionState::kRunning, SessionState::kPaused));
    CHECK(CanTransition(SessionState::kPaused, SessionState::kRunning));
    CHECK(CanTransition(SessionState::kRunning, SessionState::kTerminated));
    CHECK(CanTransition(SessionState::kError, SessionState::kInstantiated));
    CHECK(CanTransition(SessionState::kUnconfigured, SessionState::kUnconfigured));
    CHECK(!CanTransition(SessionState::kUnconfigured, SessionState::kRunning));
    CHECK(!CanTransition(SessionState::kSessionCreated, SessionState::kRunning));
    CHECK(std::string(ToString(SessionState::kSocketConnecting)) == "socket_connecting");
}

void TestModelDescriptionParsing() {
    const auto fmi2 = ParseModelDescriptionXml(R"xml(
        <fmiModelDescription fmiVersion="2.0" modelName="Thermal &amp; Plant" guid="guid-1">
          <CoSimulation modelIdentifier="thermal"/>
          <DefaultExperiment startTime="1.5" stopTime="9.0" stepSize="0.25"/>
          <ModelVariables>
            <ScalarVariable name="temperature" valueReference="1" causality="input">
              <Real start="20.5" unit="K"/>
            </ScalarVariable>
            <ScalarVariable name="counter" valueReference="2" causality="output">
              <Integer start="7"/>
            </ScalarVariable>
            <ScalarVariable name="label" valueReference="3" causality="parameter">
              <String start="A &amp; B"/>
            </ScalarVariable>
            <ScalarVariable name="enabled" valueReference="4" causality="output">
              <Boolean start="true"/>
            </ScalarVariable>
          </ModelVariables>
        </fmiModelDescription>
    )xml");
    CHECK(fmi2);
    CHECK(fmi2.value.model_name == "Thermal & Plant");
    CHECK(fmi2.value.guid == "guid-1");
    CHECK(fmi2.value.supports_co_simulation);
    CHECK_NEAR(*fmi2.value.default_start_time, 1.5, 1e-12);
    CHECK_NEAR(*fmi2.value.default_step_size, 0.25, 1e-12);
    CHECK(fmi2.value.variables.size() == 4);
    const VariableInfo* temperature = FindVariableByName(fmi2.value, "temperature");
    CHECK(temperature != nullptr);
    CHECK(temperature->type == ScalarType::kReal);
    CHECK(std::get<double>(*temperature->start_value) == 20.5);
    CHECK(FindVariableByValueReference(fmi2.value, 2)->name == "counter");
    CHECK(std::get<std::string>(*FindVariableByName(fmi2.value, "label")->start_value) == "A & B");
    CHECK(std::get<bool>(*FindVariableByName(fmi2.value, "enabled")->start_value));
    CHECK(std::string(ToString(ScalarType::kBinary)) == "Binary");

    const auto fmi3 = ParseModelDescriptionXml(R"xml(
        <fmiModelDescription fmiVersion="3.0" modelName="StateSpace" instantiationToken="token-1">
          <CoSimulation/>
          <ModelVariables>
            <Float64 name="output" valueReference="10" causality="output"/>
            <UInt64 name="wide" valueReference="11" causality="output" start="18446744073709551615"/>
            <Binary name="blob" valueReference="12" causality="output" start="YQ=="/>
            <Clock name="clock" valueReference="13" causality="output" start="true"/>
          </ModelVariables>
        </fmiModelDescription>
    )xml");
    CHECK(fmi3);
    CHECK(fmi3.value.fmi_version == "3.0");
    CHECK(fmi3.value.guid == "token-1");
    CHECK(fmi3.value.variables.size() == 4);
    CHECK(FindVariableByName(fmi3.value, "wide")->declared_type == "UInt64");
    CHECK(std::get<std::uint64_t>(*FindVariableByName(fmi3.value, "wide")->start_value) == UINT64_MAX);
    CHECK(std::get<BinaryValue>(*FindVariableByName(fmi3.value, "blob")->start_value) == BinaryValue{0x61});
    CHECK(std::get<bool>(*FindVariableByName(fmi3.value, "clock")->start_value));

    const auto invalid = ParseModelDescriptionXml("<not-a-model/>");
    CHECK(!invalid);
    CHECK(invalid.status.code == "MODEL_DESCRIPTION_INVALID");
    const auto unterminated = ParseModelDescriptionXml(
        R"(<fmiModelDescription><CoSimulation/><ScalarVariable name="x" valueReference="1">)");
    CHECK(!unterminated);
    CHECK(unterminated.status.code == "MODEL_DESCRIPTION_INVALID");
}

void TestTransportImplementations() {
    ScriptedTransport scripted;
    CHECK(!scripted.IsConnected());
    const auto disconnected_send = scripted.SendText("payload");
    CHECK(!disconnected_send);
    CHECK(disconnected_send.code == "TRANSPORT_NOT_CONNECTED");
    CHECK_OK(scripted.Connect("wss://gateway.example/path"));
    CHECK(scripted.IsConnected());
    CHECK_OK(scripted.SendText("request"));
    CHECK(scripted.SentPayloads().size() == 1);
    CHECK(scripted.SentPayloads()[0] == "request");
    const auto empty_receive = scripted.ReceiveText();
    CHECK(!empty_receive);
    CHECK(empty_receive.status.code == "TRANSPORT_NO_RESPONSE");
    scripted.QueueResponse("reply");
    const auto reply = scripted.ReceiveText();
    CHECK(reply);
    CHECK(reply.value == "reply");
    scripted.Close();
    CHECK(!scripted.IsConnected());

    StubWssTransport stub;
    const auto stub_connect = stub.Connect("wss://gateway.example/path");
    CHECK(!stub_connect);
    CHECK(stub_connect.code == "WSS_TRANSPORT_UNAVAILABLE");
}

void TestGatewayClientProtocol() {
    auto transport = std::make_unique<ScriptedTransport>();
    ScriptedTransport* scripted = transport.get();
    GatewayClient client(std::move(transport));
    RuntimeConfig config = TestConfig();

    scripted->QueueResponse(R"({"type":"session.pong","requestId":"not-req-1"})");
    scripted->QueueResponse(R"({"type":"session.created","requestId":"req-1","sessionId":"session-1"})");
    CHECK_OK(client.CreateSession(config));
    CHECK(client.SessionId() == "session-1");
    CHECK(client.IsConnected());
    CHECK(scripted->SentPayloads().size() == 1);
    const auto create_request = ParseJson(scripted->SentPayloads()[0]);
    CHECK(create_request);
    CHECK(JsonString(*create_request.value.AsObject(), "type") == "session.create");
    CHECK(JsonString(*create_request.value.AsObject(), "labId") == "lab-1");

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-2","state":"initialized"})");
    ExperimentConfig experiment{1.0, 8.0, 0.5};
    std::map<std::string, ScalarValue> initial_inputs = {
        {"wide", ScalarValue(std::uint64_t{18446744073709551615ULL})},
        {"blob", ScalarValue(BinaryValue{0x01, 0x02})},
    };
    CHECK_OK(client.Initialize(config, experiment, initial_inputs));
    const auto initialize_request = ParseJson(scripted->SentPayloads().back());
    CHECK(initialize_request);
    const JsonObject& initialize_object = *initialize_request.value.AsObject();
    const JsonObject& options = *FindObjectValue(initialize_object, "options")->AsObject();
    CHECK(JsonString(options, "timeMode") == "simtime");
    const JsonObject& encoded_inputs = *FindObjectValue(options, "inputs")->AsObject();
    CHECK(JsonString(encoded_inputs, "wide") == "18446744073709551615");
    CHECK(JsonString(encoded_inputs, "blob") == "AQI=");

    scripted->QueueResponse(R"({"type":"sim.inputs.updated","requestId":"req-3"})");
    CHECK_OK(client.SetInputs({{"temperature", ScalarValue(21.0)}}));
    scripted->QueueResponse(
        R"({"type":"sim.outputs","requestId":"req-4","simTime":1.5,"values":{"temperature":21.5,"counter":12}})");
    const auto step = client.Step(0.5);
    CHECK(step);
    CHECK_NEAR(step.value.sim_time, 1.5, 1e-12);
    CHECK_NEAR(JsonNumber(step.value.values, "temperature"), 21.5, 1e-12);
    CHECK(JsonNumber(step.value.values, "counter") == 12.0);

    scripted->QueueResponse(R"({"type":"sim.outputs","requestId":"req-5","simTime":1.75,"values":{"temperature":22.0}})");
    const auto outputs = client.GetOutputs({"temperature"});
    CHECK(outputs);
    CHECK_NEAR(outputs.value.sim_time, 1.75, 1e-12);

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-6","state":"reset"})");
    CHECK_OK(client.Reset());
    scripted->QueueResponse(R"({"type":"session.closed","requestId":"req-7","reason":"done"})");
    CHECK_OK(client.Terminate());
    CHECK(client.SessionId().empty());
    CHECK(!client.IsConnected());

    auto error_transport = std::make_unique<ScriptedTransport>();
    ScriptedTransport* error_scripted = error_transport.get();
    GatewayClient error_client(std::move(error_transport));
    error_scripted->QueueResponse(R"({"type":"error","requestId":"req-1","code":"AUTH_FAILED","message":"bad ticket"})");
    const auto error = error_client.CreateSession(config);
    CHECK(!error);
    CHECK(error.code == "AUTH_FAILED");
}

void TestProxyRuntimeLifecycle() {
    TemporaryDirectory directory;
    WriteFile(directory.path / "config.json",
              R"({"gatewayWsUrl":"wss://gateway.example/fmu","labId":"lab-1","reservationKey":"reservation-1","sessionTicket":"ticket-1","timeMode":"realtime"})");
    WriteFile(directory.path / "modelDescription.xml", R"xml(
        <fmiModelDescription fmiVersion="2.0" modelName="RuntimeModel" guid="runtime-guid">
          <CoSimulation/>
          <DefaultExperiment startTime="0.0" stopTime="10.0" stepSize="0.5"/>
          <ModelVariables>
            <ScalarVariable name="input" valueReference="1" causality="input"><Real start="1.0"/></ScalarVariable>
            <ScalarVariable name="output" valueReference="2" causality="output"><Real start="0.0"/></ScalarVariable>
            <ScalarVariable name="counter" valueReference="3" causality="output"><Integer start="0"/></ScalarVariable>
            <ScalarVariable name="label" valueReference="4" causality="output"><String start="initial"/></ScalarVariable>
            <ScalarVariable name="enabled" valueReference="5" causality="output"><Boolean start="false"/></ScalarVariable>
          </ModelVariables>
        </fmiModelDescription>
    )xml");

    ScriptedTransport* scripted = nullptr;
    ProxyRuntime runtime([&]() {
        auto transport = std::make_unique<ScriptedTransport>();
        scripted = transport.get();
        return transport;
    });

    CHECK_OK(runtime.Configure("instance-1", directory.path.string()));
    CHECK(runtime.State() == SessionState::kInstantiated);
    CHECK(runtime.Model().variables.size() == 5);
    CHECK(runtime.Config().time_mode == TimeMode::kRealtime);
    CHECK_NEAR(runtime.CurrentTime(), 0.0, 1e-12);

    const std::uint32_t input_reference = 1;
    const double input_value = 2.5;
    CHECK_OK(runtime.SetReal(&input_reference, 1, &input_value));
    CHECK_OK(runtime.SetupExperiment(0.0, 5.0, 0.25));

    scripted->QueueResponse(R"({"type":"session.created","requestId":"req-1","sessionId":"runtime-session"})");
    CHECK_OK(runtime.EnterInitializationMode());
    CHECK(runtime.State() == SessionState::kSessionCreated);
    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-2","state":"initialized"})");
    CHECK_OK(runtime.ExitInitializationMode());
    CHECK(runtime.State() == SessionState::kInitialized);

    const std::uint32_t wrong_type_reference = 2;
    const std::int32_t wrong_type_value = 7;
    CHECK(runtime.SetInteger(&wrong_type_reference, 1, &wrong_type_value).code == "TYPE_MISMATCH");

    const double stepped_input_value = 3.5;
    CHECK_OK(runtime.SetReal(&input_reference, 1, &stepped_input_value));

    scripted->QueueResponse(R"({"type":"sim.inputs.updated","requestId":"req-3"})");
    scripted->QueueResponse(
        R"({"type":"sim.outputs","requestId":"req-4","simTime":0.25,"values":{"output":4.25,"counter":12,"label":"ready","enabled":true}})");
    CHECK_OK(runtime.DoStep(0.0, 0.25));
    CHECK(runtime.State() == SessionState::kRunning);
    CHECK_NEAR(runtime.CurrentTime(), 0.25, 1e-12);

    const std::uint32_t output_reference = 2;
    double output_value = 0.0;
    CHECK_OK(runtime.GetReal(&output_reference, 1, &output_value));
    CHECK_NEAR(output_value, 4.25, 1e-12);
    const std::uint32_t counter_reference = 3;
    std::int32_t counter_value = 0;
    CHECK_OK(runtime.GetInteger(&counter_reference, 1, &counter_value));
    CHECK(counter_value == 12);
    const std::uint32_t label_reference = 4;
    const char* label = nullptr;
    CHECK_OK(runtime.GetString(&label_reference, 1, &label));
    CHECK(std::string(label) == "ready");
    const std::uint32_t enabled_reference = 5;
    bool enabled = false;
    CHECK_OK(runtime.GetBoolean(&enabled_reference, 1, &enabled));
    CHECK(enabled);

    const std::uint32_t unknown_reference = 999;
    CHECK(runtime.GetReal(&unknown_reference, 1, &output_value).code == "INVALID_ARGUMENT");

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-5","state":"reset"})");
    CHECK_OK(runtime.Reset());
    CHECK(runtime.State() == SessionState::kInstantiated);
    CHECK_NEAR(runtime.CurrentTime(), 0.0, 1e-12);
    output_value = 123.0;
    CHECK_OK(runtime.GetReal(&output_reference, 1, &output_value));
    CHECK_NEAR(output_value, 0.0, 1e-12);

    scripted->QueueResponse(R"({"type":"session.closed","requestId":"req-6","reason":"test complete"})");
    CHECK_OK(runtime.Terminate());
    CHECK(runtime.State() == SessionState::kTerminated);
}

using TestFunction = std::function<void()>;

int RunTest(const char* name, const TestFunction& test) {
    try {
        test();
        std::cout << "[PASS] " << name << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "[FAIL] " << name << ": " << error.what() << '\n';
        return 1;
    }
}

}  // namespace

int main() {
    int failures = 0;
    failures += RunTest("json parser and serializer", TestJsonParserAndSerializer);
    failures += RunTest("runtime config parsing", TestRuntimeConfigParsing);
    failures += RunTest("protocol and session state", TestProtocolAndSessionState);
    failures += RunTest("model description parsing", TestModelDescriptionParsing);
    failures += RunTest("transport implementations", TestTransportImplementations);
    failures += RunTest("gateway client protocol", TestGatewayClientProtocol);
    failures += RunTest("proxy runtime lifecycle", TestProxyRuntimeLifecycle);
    return failures == 0 ? 0 : 1;
}
