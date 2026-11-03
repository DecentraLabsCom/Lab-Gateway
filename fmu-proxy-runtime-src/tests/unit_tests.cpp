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
#include "fmi2/fmi2Functions.h"
#include "fmi3/fmi3Functions.h"

static_assert(sizeof(fmi3Boolean) == sizeof(bool));
static_assert(sizeof(fmi3Clock) == sizeof(bool));

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

    // Opaque checkpoint fixture sealed by FMU-Executor. Timestamp values must
    // survive the proxy JSON round trip exactly so Executor's signature check
    // receives the original token fields.
    const auto checkpoint = ParseJson(
        R"({"checkpointId":"0123456789abcdef0123456789abcdef","createdAt":1793736591.253394,"expiresAt":1793822991.253394,"format":"decentralabs-fmi-state-v1","scope":"f570a9dc38098cefc29a015b51298db88e7533ecd31745b6ca9a76291d8fbdf3","signature":"c2a2caaad4fcbc3d2d135c573cd47adb9a417ccea8e364ec262cec84e446b684"})");
    CHECK(checkpoint);
    const auto checkpoint_round_trip = ParseJson(SerializeJson(checkpoint.value));
    CHECK(checkpoint_round_trip);
    CHECK(JsonNumber(*checkpoint.value.AsObject(), "createdAt")
          == JsonNumber(*checkpoint_round_trip.value.AsObject(), "createdAt"));
    CHECK(JsonNumber(*checkpoint.value.AsObject(), "expiresAt")
          == JsonNumber(*checkpoint_round_trip.value.AsObject(), "expiresAt"));
    CHECK(JsonString(*checkpoint.value.AsObject(), "signature")
          == JsonString(*checkpoint_round_trip.value.AsObject(), "signature"));

    const auto malformed = ParseJson(R"({"missing": 1} trailing)");
    CHECK(!malformed);
    CHECK(malformed.status.code == "JSON_PARSE_ERROR");
    CHECK(JsonString(object, "not-present", "fallback") == "fallback");
}

void TestFmi2SerializedStatePreservesModelExchangeMode() {
    const JsonObject checkpoint = {
        {"simulation", JsonValue(JsonObject{{"externalSolver", JsonValue(JsonObject{{"mode", JsonValue("event")}})}})},
    };
    const std::string checkpoint_json = SerializeJson(JsonValue(checkpoint));
    const std::string serialized_token = SerializeJson(JsonValue(JsonObject{
        {"checkpoint", JsonValue(checkpoint_json)},
        {"mode", JsonValue(2)},
    }));

    char instance_placeholder = 0;
    fmi2FMUstate state = nullptr;
    CHECK(fmi2DeSerializeFMUstate(
        &instance_placeholder,
        reinterpret_cast<const fmi2Byte*>(serialized_token.data()),
        serialized_token.size(),
        &state) == fmi2OK);
    CHECK(state != nullptr);

    size_t serialized_size = 0;
    CHECK(fmi2SerializedFMUstateSize(&instance_placeholder, state, &serialized_size) == fmi2OK);
    std::vector<fmi2Byte> roundtrip(serialized_size);
    CHECK(fmi2SerializeFMUstate(&instance_placeholder, state, roundtrip.data(), roundtrip.size()) == fmi2OK);
    CHECK(std::string(reinterpret_cast<const char*>(roundtrip.data()), roundtrip.size()) == serialized_token);
    CHECK(fmi2FreeFMUstate(&instance_placeholder, &state) == fmi2OK);
    CHECK(state == nullptr);
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
    CHECK(SupportedClientMessages().size() == 15);
    CHECK(SupportedServerMessages().size() == 11);

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
            <Binary name="blob" valueReference="12" causality="output"><Start value="61"/></Binary>
            <String name="labels" valueReference="14" causality="output">
              <Dimension start="2"/><Start value="north"/><Start value="south"/>
            </String>
            <Binary name="payloads" valueReference="15" causality="output">
              <Dimension start="2"/><Start value="0102"/><Start value="0304"/>
            </Binary>
            <Clock name="clock" valueReference="13" causality="output" start="true"/>
          </ModelVariables>
        </fmiModelDescription>
    )xml");
    CHECK(fmi3);
    CHECK(fmi3.value.fmi_version == "3.0");
    CHECK(fmi3.value.guid == "token-1");
    CHECK(fmi3.value.variables.size() == 6);
    CHECK(FindVariableByName(fmi3.value, "wide")->declared_type == "UInt64");
    CHECK(std::get<std::uint64_t>(*FindVariableByName(fmi3.value, "wide")->start_value) == UINT64_MAX);
    CHECK(std::get<BinaryValue>(*FindVariableByName(fmi3.value, "blob")->start_value) == BinaryValue{0x61});
    CHECK(std::get<StringArray>(*FindVariableByName(fmi3.value, "labels")->start_value) == StringArray({"north", "south"}));
    CHECK(std::get<BinaryArray>(*FindVariableByName(fmi3.value, "payloads")->start_value) == BinaryArray({BinaryValue{0x01, 0x02}, BinaryValue{0x03, 0x04}}));
    CHECK(std::get<bool>(*FindVariableByName(fmi3.value, "clock")->start_value));

    const auto fmi2_model_exchange = ParseModelDescriptionXml(R"xml(
        <fmiModelDescription fmiVersion="2.0" modelName="BouncingBall" guid="ball-guid">
          <ModelExchange modelIdentifier="bouncing_ball"/>
          <ModelVariables>
            <ScalarVariable name="height" valueReference="10" causality="local" variability="continuous">
              <Real start="1.0"/>
            </ScalarVariable>
            <ScalarVariable name="der_height" valueReference="20" causality="local" variability="continuous">
              <Real derivative="1"/>
            </ScalarVariable>
          </ModelVariables>
          <ModelStructure><Derivatives><Unknown index="2"/></Derivatives></ModelStructure>
        </fmiModelDescription>
    )xml");
    CHECK(fmi2_model_exchange);
    const VariableInfo* fmi2_derivative = FindVariableByName(fmi2_model_exchange.value, "der_height");
    CHECK(fmi2_derivative != nullptr);
    CHECK(fmi2_derivative->derivative_reference == std::uint32_t{1});
    CHECK(fmi2_model_exchange.value.continuous_state_derivative_references == std::vector<std::uint32_t>{20});
    CHECK(fmi2_model_exchange.value.continuous_state_value_references == std::vector<std::uint32_t>{10});

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
        {"blob", ScalarValue(BinaryValue{0x01, 0x02})},
    };
    std::map<std::string, ScalarValue> initial_parameters = {
        {"wide", ScalarValue(std::uint64_t{18446744073709551615ULL})},
    };
    CHECK_OK(client.Initialize(config, experiment, initial_inputs, initial_parameters));
    const auto initialize_request = ParseJson(scripted->SentPayloads().back());
    CHECK(initialize_request);
    const JsonObject& initialize_object = *initialize_request.value.AsObject();
    const JsonObject& options = *FindObjectValue(initialize_object, "options")->AsObject();
    CHECK(JsonString(options, "timeMode") == "simtime");
    const JsonObject& encoded_parameters = *FindObjectValue(initialize_object, "parameters")->AsObject();
    CHECK(JsonString(encoded_parameters, "wide") == "18446744073709551615");
    const JsonObject& encoded_inputs = *FindObjectValue(options, "inputs")->AsObject();
    CHECK(JsonString(encoded_inputs, "blob") == "AQI=");

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-3","state":"initialized"})");
    ExperimentConfig unbounded_experiment{1.0, std::nullopt, 0.5};
    CHECK_OK(client.Initialize(config, unbounded_experiment, {}, {}));
    const auto unbounded_request = ParseJson(scripted->SentPayloads().back());
    CHECK(unbounded_request);
    const JsonObject& unbounded_options = *FindObjectValue(
        *unbounded_request.value.AsObject(), "options")->AsObject();
    CHECK(FindObjectValue(unbounded_options, "stopTime") == nullptr);

    scripted->QueueResponse(R"({"type":"sim.inputs.updated","requestId":"req-4"})");
    CHECK_OK(client.SetInputs({{"temperature", ScalarValue(21.0)}}));
    scripted->QueueResponse(
        R"({"type":"sim.outputs","requestId":"req-5","simTime":1.5,"values":{"temperature":21.5,"counter":12}})");
    const auto step = client.Step(0.5);
    CHECK(step);
    CHECK_NEAR(step.value.sim_time, 1.5, 1e-12);
    CHECK_NEAR(JsonNumber(step.value.values, "temperature"), 21.5, 1e-12);
    CHECK(JsonNumber(step.value.values, "counter") == 12.0);

    scripted->QueueResponse(R"({"type":"sim.outputs","requestId":"req-6","simTime":1.75,"values":{"temperature":22.0}})");
    const auto outputs = client.GetOutputs({"temperature"});
    CHECK(outputs);
    CHECK_NEAR(outputs.value.sim_time, 1.75, 1e-12);

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-7","state":"reset"})");
    CHECK_OK(client.Reset());
    scripted->QueueResponse(R"({"type":"session.closed","requestId":"req-8","reason":"done"})");
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
            <ScalarVariable name="time" valueReference="0" causality="independent"><Real/></ScalarVariable>
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
    CHECK(runtime.Model().variables.size() == 6);
    CHECK(runtime.Config().time_mode == TimeMode::kRealtime);
    CHECK_NEAR(runtime.CurrentTime(), 0.0, 1e-12);

    const std::uint32_t input_reference = 1;
    const double input_value = 2.5;
    CHECK_OK(runtime.SetReal(&input_reference, 1, &input_value));
    CHECK_OK(runtime.SetupExperiment(0.0, 0.25, 0.25));

    scripted->QueueResponse(R"({"type":"session.created","requestId":"req-1","sessionId":"runtime-session"})");
    CHECK_OK(runtime.EnterInitializationMode());
    CHECK(runtime.State() == SessionState::kSessionCreated);
    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-2","state":"initialized"})");
    scripted->QueueResponse(
        R"({"type":"sim.outputs","requestId":"req-3","simTime":0.0,"values":{"output":0.0,"counter":0,"label":"initial","enabled":false}})");
    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-4","state":"initialized"})");
    CHECK_OK(runtime.ExitInitializationMode());
    CHECK(runtime.State() == SessionState::kInitialized);

    const std::uint32_t wrong_type_reference = 2;
    const std::int32_t wrong_type_value = 7;
    CHECK(runtime.SetInteger(&wrong_type_reference, 1, &wrong_type_value).code == "TYPE_MISMATCH");

    const double stepped_input_value = 3.5;
    CHECK_OK(runtime.SetReal(&input_reference, 1, &stepped_input_value));

    scripted->QueueResponse(
        R"({"type":"sim.samples","requestId":"req-5","simTime":0.25,"finished":true,"samples":[{"time":0.25,"outputs":{"output":4.25,"counter":12,"label":"ready","enabled":true}}]})");
    CHECK_OK(runtime.DoStep(0.0, 0.25));
    CHECK(runtime.State() == SessionState::kRunning);
    CHECK_NEAR(runtime.CurrentTime(), 0.25, 1e-12);
    CHECK(runtime.SimulationFinished());
    const std::uint32_t time_reference = 0;
    double time_value = -1.0;
    CHECK_OK(runtime.GetReal(&time_reference, 1, &time_value));
    CHECK_NEAR(time_value, 0.25, 1e-12);

    const std::size_t sent_payload_count = scripted->SentPayloads().size();
    const double one_ulp_step = std::nextafter(0.25, 1.0) - 0.25;
    const OperationResult no_advance = runtime.DoStep(0.25, one_ulp_step);
    CHECK(!no_advance);
    CHECK(no_advance.code == "NO_ADVANCE");
    CHECK(scripted->SentPayloads().size() == sent_payload_count);

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

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-6","state":"reset"})");
    CHECK_OK(runtime.Reset());
    CHECK(runtime.State() == SessionState::kInstantiated);
    CHECK_NEAR(runtime.CurrentTime(), 0.0, 1e-12);
    output_value = 123.0;
    CHECK_OK(runtime.GetReal(&output_reference, 1, &output_value));
    CHECK_NEAR(output_value, 0.0, 1e-12);

    double reset_input_value = 0.0;
    CHECK_OK(runtime.GetReal(&input_reference, 1, &reset_input_value));
    CHECK_NEAR(reset_input_value, 1.0, 1e-12);
    CHECK_OK(runtime.EnterInitializationMode());
    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-7","state":"initialized"})");
    scripted->QueueResponse(
        R"({"type":"sim.outputs","requestId":"req-8","simTime":0.0,"values":{"output":1.0,"counter":0,"label":"initial","enabled":false}})");
    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-9","state":"initialized"})");
    CHECK_OK(runtime.ExitInitializationMode());
    const auto reinitialize_request = ParseJson(scripted->SentPayloads()[6]);
    CHECK(reinitialize_request);
    const JsonObject& reinitialize_object = *reinitialize_request.value.AsObject();
    CHECK(JsonString(reinitialize_object, "type") == "sim.initialize");
    const JsonObject& reinitialize_options = *FindObjectValue(reinitialize_object, "options")->AsObject();
    CHECK(FindObjectValue(reinitialize_options, "inputs") == nullptr);

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-10","state":"initialized","_sourceFmuTerminated":true})");
    CHECK_OK(runtime.Terminate());
    CHECK(runtime.State() == SessionState::kTerminated);
    const auto terminate_request = ParseJson(scripted->SentPayloads().back());
    CHECK(terminate_request);
    CHECK(JsonString(*terminate_request.value.AsObject(), "type") == "sim.terminateFMU");
}

void TestInitializationGetsEvaluateAndRefreshOutputs() {
    TemporaryDirectory directory;
    WriteFile(directory.path / "config.json",
              R"({"gatewayWsUrl":"wss://gateway.example/fmu","labId":"lab-1","reservationKey":"reservation-1","sessionTicket":"ticket-1"})");
    WriteFile(directory.path / "modelDescription.xml", R"xml(
        <fmiModelDescription fmiVersion="2.0" modelName="InitializationModel" guid="initialization-guid">
          <CoSimulation/>
          <ModelVariables>
            <ScalarVariable name="input" valueReference="1" causality="input"><Real start="1.0"/></ScalarVariable>
            <ScalarVariable name="output" valueReference="2" causality="output"><Real start="0.0"/></ScalarVariable>
          </ModelVariables>
        </fmiModelDescription>
    )xml");

    ScriptedTransport* scripted = nullptr;
    ProxyRuntime runtime([&]() {
        auto transport = std::make_unique<ScriptedTransport>();
        scripted = transport.get();
        return transport;
    });
    CHECK_OK(runtime.Configure("initialization-instance", directory.path.string()));
    const std::uint32_t input_reference = 1;
    const std::uint32_t output_reference = 2;
    double input_value = 2.5;
    CHECK_OK(runtime.SetReal(&input_reference, 1, &input_value));
    scripted->QueueResponse(R"({"type":"session.created","requestId":"req-1","sessionId":"initialization-session"})");
    CHECK_OK(runtime.EnterInitializationMode());

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-2","state":"initialized"})");
    scripted->QueueResponse(R"({"type":"sim.outputs","requestId":"req-3","simTime":0.0,"values":{"output":2.5}})");
    double output_value = 0.0;
    CHECK_OK(runtime.GetReal(&output_reference, 1, &output_value));
    CHECK_NEAR(output_value, 2.5, 1e-12);

    input_value = 3.5;
    CHECK_OK(runtime.SetReal(&input_reference, 1, &input_value));
    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-4","state":"reset"})");
    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-5","state":"initialized"})");
    scripted->QueueResponse(R"({"type":"sim.outputs","requestId":"req-6","simTime":0.0,"values":{"output":3.5}})");
    CHECK_OK(runtime.GetReal(&output_reference, 1, &output_value));
    CHECK_NEAR(output_value, 3.5, 1e-12);

    const std::size_t requests_before_exit = scripted->SentPayloads().size();
    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-7","state":"initialized"})");
    CHECK_OK(runtime.ExitInitializationMode());
    CHECK(runtime.State() == SessionState::kInitialized);
    CHECK(scripted->SentPayloads().size() == requests_before_exit + 1);

    const auto initial_request = ParseJson(scripted->SentPayloads()[1]);
    CHECK(initial_request);
    const JsonObject& initial_object = *initial_request.value.AsObject();
    const JsonObject& initial_options = *FindObjectValue(initial_object, "options")->AsObject();
    const JsonObject& initial_inputs = *FindObjectValue(initial_options, "inputs")->AsObject();
    CHECK(JsonNumber(initial_inputs, "input") == 2.5);

    const auto refreshed_request = ParseJson(scripted->SentPayloads()[4]);
    CHECK(refreshed_request);
    const JsonObject& refreshed_object = *refreshed_request.value.AsObject();
    const JsonObject& refreshed_options = *FindObjectValue(refreshed_object, "options")->AsObject();
    const JsonObject& refreshed_inputs = *FindObjectValue(refreshed_options, "inputs")->AsObject();
    CHECK(JsonNumber(refreshed_inputs, "input") == 3.5);
}

void TestModelExchangeInitializationReadsAndExactStateWritesAreOrderIndependent() {
    TemporaryDirectory directory;
    WriteFile(directory.path / "config.json",
              R"({"gatewayWsUrl":"wss://gateway.example/fmu","labId":"lab-1","reservationKey":"reservation-1","sessionTicket":"ticket-1"})");
    WriteFile(directory.path / "modelDescription.xml", R"xml(
        <fmiModelDescription fmiVersion="3.0" modelName="InitializationME" instantiationToken="initialization-me-token">
          <ModelExchange modelIdentifier="initialization_me"/>
          <ModelVariables>
            <Float64 name="x" valueReference="1" causality="local" variability="continuous" initial="exact" start="0.25"/>
            <Float64 name="der_x" valueReference="2" causality="local" variability="continuous" derivative="1"/>
          </ModelVariables>
          <ModelStructure><ContinuousStateDerivative valueReference="2"/></ModelStructure>
        </fmiModelDescription>
    )xml");

    ScriptedTransport* scripted = nullptr;
    ProxyRuntime runtime([&]() {
        auto transport = std::make_unique<ScriptedTransport>();
        scripted = transport.get();
        return transport;
    });
    CHECK_OK(runtime.Configure("initialization-me-instance", directory.path.string()));
    CHECK_OK(runtime.SetModelExchangeMode(true));
    CHECK_OK(runtime.SetupExperiment(0.0, 2.0, 0.1));
    scripted->QueueResponse(R"({"type":"session.created","requestId":"req-1","sessionId":"initialization-me-session"})");
    CHECK_OK(runtime.EnterInitializationMode());

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-2","state":"initialized"})");
    scripted->QueueResponse(R"({"type":"sim.modelExchangeResult","requestId":"req-3","result":{"values":[0.25]}})");
    const auto states = runtime.ModelExchangeCall("getContinuousStates");
    CHECK(states);
    CHECK_NEAR((*FindObjectValue(states.value, "values")->AsArray())[0].AsNumber(), 0.25, 1e-12);

    scripted->QueueResponse(R"({"type":"sim.modelExchangeResult","requestId":"req-4","result":{"values":[0.4794]}})");
    const auto derivatives = runtime.ModelExchangeCall("getContinuousStateDerivatives");
    CHECK(derivatives);
    const JsonArray* derivative_values = FindObjectValue(derivatives.value, "values")->AsArray();
    CHECK(derivative_values != nullptr && derivative_values->size() == 1);
    CHECK_NEAR((*derivative_values)[0].AsNumber(), 0.4794, 1e-12);

    scripted->QueueResponse(R"({"type":"sim.modelExchangeResult","requestId":"req-5","result":{"values":[0.4794]}})");
    double derivative_value = 0.0;
    const std::uint32_t derivative_reference = 2;
    CHECK_OK(runtime.GetReal(&derivative_reference, 1, &derivative_value));
    CHECK_NEAR(derivative_value, 0.4794, 1e-12);

    scripted->QueueResponse(R"({"type":"sim.modelExchangeResult","requestId":"req-6","result":{"values":[1.0]}})");
    const auto nominals = runtime.ModelExchangeCall("getNominalsOfContinuousStates");
    CHECK(nominals);
    CHECK_NEAR((*FindObjectValue(nominals.value, "values")->AsArray())[0].AsNumber(), 1.0, 1e-12);

    const std::uint32_t state_reference = 1;
    const double state_value = 0.75;
    scripted->QueueResponse(R"({"type":"sim.modelExchangeResult","requestId":"req-7","result":{"values":[0.75]}})");
    CHECK_OK(runtime.SetReal(&state_reference, 1, &state_value));

    scripted->QueueResponse(R"({"type":"sim.modelExchangeResult","requestId":"req-8","result":{"mode":"event"}})");
    CHECK_OK(runtime.ExitInitializationMode());
    CHECK(runtime.State() == SessionState::kInitialized);

    const auto messages = scripted->SentPayloads();
    CHECK(messages.size() == 8);
    const auto initial_request = ParseJson(messages[1]);
    CHECK(initial_request);
    CHECK(JsonString(*initial_request.value.AsObject(), "type") == "sim.initialize");
    const auto first_read = ParseJson(messages[2]);
    CHECK(first_read);
    CHECK(JsonString(*first_read.value.AsObject(), "operation") == "getContinuousStates");
    const auto second_read = ParseJson(messages[3]);
    CHECK(second_read);
    CHECK(JsonString(*second_read.value.AsObject(), "operation") == "getContinuousStateDerivatives");
    const auto state_write = ParseJson(messages[6]);
    CHECK(state_write);
    CHECK(JsonString(*state_write.value.AsObject(), "operation") == "setValues");
}

void TestFmi3ExactAndApproxStatesCanBeSetWhileInstantiated() {
    for (const std::string initial : {"exact", "approx"}) {
        TemporaryDirectory directory;
        WriteFile(directory.path / "config.json",
                  R"({"gatewayWsUrl":"wss://gateway.example/fmu","labId":"lab-1","reservationKey":"reservation-1","sessionTicket":"ticket-1"})");
        WriteFile(directory.path / "modelDescription.xml", "<fmiModelDescription fmiVersion=\"3.0\" modelName=\"InitialState\" instantiationToken=\"initial-state-token\">"
                  "<ModelExchange modelIdentifier=\"initial_state\"/>"
                  "<ModelVariables><Float64 name=\"x\" valueReference=\"1\" causality=\"local\" variability=\"continuous\" initial=\"" + initial + "\" start=\"0.25\"/>"
                  "<Float64 name=\"der_x\" valueReference=\"2\" causality=\"local\" variability=\"continuous\" derivative=\"1\"/></ModelVariables>"
                  "<ModelStructure><ContinuousStateDerivative valueReference=\"2\"/></ModelStructure></fmiModelDescription>");

        ScriptedTransport* scripted = nullptr;
        ProxyRuntime runtime([&]() {
            auto transport = std::make_unique<ScriptedTransport>();
            scripted = transport.get();
            return transport;
        });
        CHECK_OK(runtime.Configure("initial-state-instance", directory.path.string()));
        CHECK_OK(runtime.SetModelExchangeMode(true));
        CHECK_OK(runtime.SetupExperiment(0.0, 1.0, 0.1));
        const std::uint32_t state_reference = 1;
        const double state_value = 0.8;
        CHECK_OK(runtime.SetReal(&state_reference, 1, &state_value));
        scripted->QueueResponse(R"({"type":"session.created","requestId":"req-1","sessionId":"initial-state-session"})");
        CHECK_OK(runtime.EnterInitializationMode());
        scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-2","state":"initialized"})");
        scripted->QueueResponse(R"({"type":"sim.modelExchangeResult","requestId":"req-3","result":{"mode":"event"}})");
        CHECK_OK(runtime.ExitInitializationMode());

        const auto initialize_request = ParseJson(scripted->SentPayloads()[1]);
        CHECK(initialize_request);
        const JsonObject& parameters = *FindObjectValue(*initialize_request.value.AsObject(), "parameters")->AsObject();
        CHECK_NEAR(JsonNumber(parameters, "x"), 0.8, 1e-12);
    }
}

void TestFmi2ExactStateCanBeSetDuringInitializationAfterARead() {
    TemporaryDirectory directory;
    WriteFile(directory.path / "config.json",
              R"({"gatewayWsUrl":"wss://gateway.example/fmu","labId":"lab-1","reservationKey":"reservation-1","sessionTicket":"ticket-1"})");
    WriteFile(directory.path / "modelDescription.xml", R"xml(
        <fmiModelDescription fmiVersion="2.0" modelName="Fmi2InitialState" guid="fmi2-initial-state">
          <ModelExchange modelIdentifier="fmi2_initial_state"/>
          <ModelVariables>
            <ScalarVariable name="h" valueReference="1" causality="local" variability="continuous" initial="exact"><Real start="1.0"/></ScalarVariable>
            <ScalarVariable name="der_h" valueReference="2" causality="local" variability="continuous"><Real derivative="1" start="0.0"/></ScalarVariable>
          </ModelVariables>
          <ModelStructure><Derivatives><Unknown index="2"/></Derivatives></ModelStructure>
        </fmiModelDescription>
    )xml");

    ScriptedTransport* scripted = nullptr;
    ProxyRuntime runtime([&]() {
        auto transport = std::make_unique<ScriptedTransport>();
        scripted = transport.get();
        return transport;
    });
    CHECK_OK(runtime.Configure("fmi2-initial-state-instance", directory.path.string()));
    CHECK_OK(runtime.SetModelExchangeMode(true));
    CHECK_OK(runtime.SetupExperiment(0.0, 2.0, 0.1));
    scripted->QueueResponse(R"({"type":"session.created","requestId":"req-1","sessionId":"fmi2-initial-state-session"})");
    CHECK_OK(runtime.EnterInitializationMode());

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-2","state":"initialized"})");
    scripted->QueueResponse(R"({"type":"sim.modelExchangeResult","requestId":"req-3","result":{"values":[1.0]}})");
    double current_state = 0.0;
    const std::uint32_t state_reference = 1;
    CHECK_OK(runtime.GetReal(&state_reference, 1, &current_state));
    CHECK_NEAR(current_state, 1.0, 1e-12);

    const double new_state = 0.8;
    scripted->QueueResponse(R"({"type":"sim.modelExchangeResult","requestId":"req-4","result":{"values":[0.8]}})");
    CHECK_OK(runtime.SetReal(&state_reference, 1, &new_state));
    const auto write_request = ParseJson(scripted->SentPayloads().back());
    CHECK(write_request);
    CHECK(JsonString(*write_request.value.AsObject(), "operation") == "setValues");
}

void TestModelExchangeStateCanBeCapturedAndRestoredDuringInitialization() {
    TemporaryDirectory directory;
    WriteFile(directory.path / "config.json",
              R"({"gatewayWsUrl":"wss://gateway.example/fmu","labId":"lab-1","reservationKey":"reservation-1","sessionTicket":"ticket-1"})");
    WriteFile(directory.path / "modelDescription.xml", R"xml(
        <fmiModelDescription fmiVersion="3.0" modelName="StatefulME" instantiationToken="stateful-me-token">
          <ModelExchange modelIdentifier="stateful_me" canGetAndSetFMUState="true" canSerializeFMUState="true"/>
          <ModelVariables>
            <Float64 name="x" valueReference="1" causality="local" variability="continuous" initial="exact" start="0.25"/>
            <Float64 name="der_x" valueReference="2" causality="local" variability="continuous" derivative="1"/>
          </ModelVariables>
          <ModelStructure><ContinuousStateDerivative valueReference="2"/></ModelStructure>
        </fmiModelDescription>
    )xml");

    ScriptedTransport* scripted = nullptr;
    ProxyRuntime runtime([&]() {
        auto transport = std::make_unique<ScriptedTransport>();
        scripted = transport.get();
        return transport;
    });
    CHECK_OK(runtime.Configure("stateful-me-instance", directory.path.string()));
    CHECK_OK(runtime.SetModelExchangeMode(true));
    CHECK_OK(runtime.SetupExperiment(0.0, 1.0, 0.1));
    scripted->QueueResponse(R"({"type":"session.created","requestId":"req-1","sessionId":"stateful-me-session"})");
    CHECK_OK(runtime.EnterInitializationMode());

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-2","state":"initialized"})");
    scripted->QueueResponse(R"({"type":"sim.fmuState","requestId":"req-3","checkpoint":{"opaque":"state"}})");
    std::string serialized_state;
    CHECK_OK(runtime.CaptureFmuState(serialized_state));
    const auto parsed_state = ParseJson(serialized_state);
    CHECK(parsed_state);
    CHECK(JsonBool(*parsed_state.value.AsObject(), "initializationMode"));

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-4","simTime":0.0,"outputs":{},"_restoredModelExchangeMode":"initialization"})");
    CHECK_OK(runtime.RestoreFmuState(serialized_state));
    CHECK(runtime.State() == SessionState::kSessionCreated);

    scripted->QueueResponse(R"({"type":"sim.modelExchangeResult","requestId":"req-5","result":{"mode":"event"}})");
    CHECK_OK(runtime.ExitInitializationMode());
    CHECK(runtime.State() == SessionState::kInitialized);
}

void TestCoSimulationStateCanBeCapturedDuringInitialization() {
    TemporaryDirectory directory;
    WriteFile(directory.path / "config.json",
              R"({"gatewayWsUrl":"wss://gateway.example/fmu","labId":"lab-1","reservationKey":"reservation-1","sessionTicket":"ticket-1"})");
    WriteFile(directory.path / "modelDescription.xml", R"xml(
        <fmiModelDescription fmiVersion="2.0" modelName="StatefulCS" guid="stateful-cs-guid">
          <CoSimulation modelIdentifier="stateful_cs" canGetAndSetFMUstate="true" canSerializeFMUstate="true"/>
          <ModelVariables>
            <ScalarVariable name="input" valueReference="1" causality="input" variability="continuous"><Real start="0"/></ScalarVariable>
            <ScalarVariable name="output" valueReference="2" causality="output" variability="continuous"><Real start="0"/></ScalarVariable>
          </ModelVariables>
        </fmiModelDescription>
    )xml");

    ScriptedTransport* scripted = nullptr;
    ProxyRuntime runtime([&]() {
        auto transport = std::make_unique<ScriptedTransport>();
        scripted = transport.get();
        return transport;
    });
    CHECK_OK(runtime.Configure("stateful-cs-instance", directory.path.string()));
    CHECK_OK(runtime.SetupExperiment(0.0, 1.0, 0.1));
    scripted->QueueResponse(R"({"type":"session.created","requestId":"req-1","sessionId":"stateful-cs-session"})");
    CHECK_OK(runtime.EnterInitializationMode());

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-2","state":"initialized"})");
    scripted->QueueResponse(R"({"type":"sim.fmuState","requestId":"req-3","checkpoint":{"opaque":"state"}})");
    std::string serialized_state;
    CHECK_OK(runtime.CaptureFmuState(serialized_state));
    const auto parsed_state = ParseJson(serialized_state);
    CHECK(parsed_state);
    CHECK(JsonBool(*parsed_state.value.AsObject(), "initializationMode"));

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-4","simTime":0.0,"outputs":{},"_restoredInitializationMode":true})");
    CHECK_OK(runtime.RestoreFmuState(serialized_state));
    CHECK(runtime.State() == SessionState::kSessionCreated);
    scripted->QueueResponse(R"({"type":"sim.outputs","requestId":"req-5","simTime":0.0,"values":{"output":0.0}})");
    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-6","state":"initialized"})");
    CHECK_OK(runtime.ExitInitializationMode());
    CHECK(runtime.State() == SessionState::kInitialized);
}

void TestInstantiatedConfigurationCheckpointStaysLocal() {
    TemporaryDirectory directory;
    WriteFile(directory.path / "config.json",
              R"({"gatewayWsUrl":"wss://gateway.example/fmu","labId":"lab-1","reservationKey":"reservation-1","sessionTicket":"ticket-1","fmiVersion":"3.0"})");
    WriteFile(directory.path / "modelDescription.xml", R"xml(
        <fmiModelDescription fmiVersion="3.0" modelName="ConfigState" instantiationToken="config-state-token">
          <CoSimulation/>
          <ModelVariables>
            <Boolean name="mode" valueReference="1" causality="structuralParameter" variability="tunable" start="true"/>
          </ModelVariables>
        </fmiModelDescription>
    )xml");

    ProxyRuntime runtime;
    CHECK_OK(runtime.Configure("config-state-instance", directory.path.string()));
    CHECK_OK(runtime.EnterConfigurationMode());
    std::string state;
    CHECK_OK(runtime.CaptureFmuState(state));
    const auto parsed = ParseJson(state);
    CHECK(parsed);
    CHECK(!JsonBool(*parsed.value.AsObject(), "remote"));
    CHECK(JsonBool(*parsed.value.AsObject(), "configurationMode"));

    const bool disabled = false;
    const std::uint32_t reference = 1;
    CHECK_OK(runtime.SetBoolean(&reference, 1, &disabled));
    CHECK_OK(runtime.RestoreFmuState(state));
    bool restored_value = false;
    CHECK_OK(runtime.GetBoolean(&reference, 1, &restored_value));
    CHECK(restored_value);
    const bool still_writable = false;
    CHECK_OK(runtime.SetBoolean(&reference, 1, &still_writable));
}

void TestInstantiatedCheckpointResetsAStartedRemoteSession() {
    TemporaryDirectory directory;
    WriteFile(directory.path / "config.json",
              R"({"gatewayWsUrl":"wss://gateway.example/fmu","labId":"lab-1","reservationKey":"reservation-1","sessionTicket":"ticket-1"})");
    WriteFile(directory.path / "modelDescription.xml", R"xml(
        <fmiModelDescription fmiVersion="2.0" modelName="StatefulCS" guid="stateful-cs-guid">
          <CoSimulation canGetAndSetFMUstate="true" canSerializeFMUstate="true"/>
          <ModelVariables>
            <ScalarVariable name="output" valueReference="1" causality="output" variability="continuous"><Real start="0"/></ScalarVariable>
          </ModelVariables>
        </fmiModelDescription>
    )xml");

    ScriptedTransport* scripted = nullptr;
    ProxyRuntime runtime([&]() {
        auto transport = std::make_unique<ScriptedTransport>();
        scripted = transport.get();
        return transport;
    });
    CHECK_OK(runtime.Configure("local-state-reset-instance", directory.path.string()));
    std::string instantiated_state;
    CHECK_OK(runtime.CaptureFmuState(instantiated_state));
    scripted->QueueResponse(R"({"type":"session.created","requestId":"req-1","sessionId":"local-state-reset-session"})");
    CHECK_OK(runtime.EnterInitializationMode());

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-2","state":"initialized"})");
    scripted->QueueResponse(R"({"type":"sim.outputs","requestId":"req-3","simTime":0.0,"values":{"output":0.0}})");
    double output = -1.0;
    const std::uint32_t output_reference = 1;
    CHECK_OK(runtime.GetReal(&output_reference, 1, &output));
    CHECK_NEAR(output, 0.0, 1e-12);

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-4","state":"loaded","simTime":0.0})");
    CHECK_OK(runtime.RestoreFmuState(instantiated_state));
    CHECK(runtime.State() == SessionState::kInstantiated);
    const auto reset_request = ParseJson(scripted->SentPayloads().back());
    CHECK(reset_request);
    CHECK(JsonString(*reset_request.value.AsObject(), "type") == "sim.reset");
}

void TestRemoteCheckpointCaptureAndRestoreAroundTerminate() {
    TemporaryDirectory directory;
    WriteFile(directory.path / "config.json",
              R"({"gatewayWsUrl":"wss://gateway.example/fmu","labId":"lab-1","reservationKey":"reservation-1","sessionTicket":"ticket-1"})");
    WriteFile(directory.path / "modelDescription.xml", R"xml(
        <fmiModelDescription fmiVersion="2.0" modelName="StatefulCS" guid="stateful-cs-guid">
          <CoSimulation canGetAndSetFMUstate="true" canSerializeFMUstate="true"/>
          <ModelVariables>
            <ScalarVariable name="input" valueReference="1" causality="input" variability="continuous"><Real start="0"/></ScalarVariable>
          </ModelVariables>
        </fmiModelDescription>
    )xml");

    ScriptedTransport* scripted = nullptr;
    ProxyRuntime runtime([&]() {
        auto transport = std::make_unique<ScriptedTransport>();
        scripted = transport.get();
        return transport;
    });
    CHECK_OK(runtime.Configure("terminated-state-instance", directory.path.string()));
    CHECK_OK(runtime.SetupExperiment(0.0, 1.0, 0.1));
    scripted->QueueResponse(R"({"type":"session.created","requestId":"req-1","sessionId":"terminated-state-session"})");
    CHECK_OK(runtime.EnterInitializationMode());

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-2","state":"initialized"})");
    scripted->QueueResponse(R"({"type":"sim.fmuState","requestId":"req-3","checkpoint":{"opaque":"before-terminate"}})");
    std::string before_terminate;
    CHECK_OK(runtime.CaptureFmuState(before_terminate));

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-4","state":"initialized","_sourceFmuTerminated":true})");
    CHECK_OK(runtime.Terminate());
    scripted->QueueResponse(R"({"type":"sim.fmuState","requestId":"req-5","checkpoint":{"opaque":"after-terminate"}})");
    std::string after_terminate;
    CHECK_OK(runtime.CaptureFmuState(after_terminate));
    const auto terminated_state = ParseJson(after_terminate);
    CHECK(terminated_state);
    CHECK(JsonBool(*terminated_state.value.AsObject(), "sourceFmuTerminated"));

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-6","simTime":0.0,"outputs":{},"_restoredInitializationMode":true,"_deferredInitializationExit":true,"_sourceFmuTerminated":false})");
    CHECK_OK(runtime.RestoreFmuState(before_terminate));
    CHECK(runtime.State() == SessionState::kSessionCreated);

    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-7","simTime":0.0,"outputs":{},"_restoredInitializationMode":true,"_deferredInitializationExit":true,"_sourceFmuTerminated":true})");
    CHECK_OK(runtime.RestoreFmuState(after_terminate));
    CHECK(runtime.State() == SessionState::kTerminated);

    scripted->QueueResponse(R"({"type":"session.closed","requestId":"req-8","reason":"test complete"})");
    CHECK_OK(runtime.Close());

    const auto requests = scripted->SentPayloads();
    CHECK(requests.size() == 8);
    const auto terminate_request = ParseJson(requests[3]);
    CHECK(terminate_request);
    CHECK(JsonString(*terminate_request.value.AsObject(), "type") == "sim.terminateFMU");
    const auto restore_request = ParseJson(requests[6]);
    CHECK(restore_request);
    CHECK(JsonString(*restore_request.value.AsObject(), "type") == "sim.restoreFMUState");
    const auto close_request = ParseJson(requests[7]);
    CHECK(close_request);
    CHECK(JsonString(*close_request.value.AsObject(), "type") == "session.terminate");
}

void TestUpdateDiscreteStatesWritesInputsAndRefreshesOutputs() {
    TemporaryDirectory directory;
    WriteFile(directory.path / "config.json",
              R"({"gatewayWsUrl":"wss://gateway.example/fmu","labId":"lab-1","reservationKey":"reservation-1","sessionTicket":"ticket-1"})");
    WriteFile(directory.path / "modelDescription.xml", R"xml(
        <fmiModelDescription fmiVersion="3.0" modelName="EventModel" instantiationToken="event-guid">
          <CoSimulation hasEventMode="true"/>
          <ModelVariables>
            <Float64 name="input" valueReference="1" causality="input" start="0.0"/>
            <Float64 name="output" valueReference="2" causality="output" start="0.0"/>
          </ModelVariables>
        </fmiModelDescription>
    )xml");

    ScriptedTransport* scripted = nullptr;
    ProxyRuntime runtime([&]() {
        auto transport = std::make_unique<ScriptedTransport>();
        scripted = transport.get();
        return transport;
    });
    CHECK_OK(runtime.Configure("event-instance", directory.path.string()));
    CHECK_OK(runtime.SetupExperiment(0.0, 1.0, 0.1));
    scripted->QueueResponse(R"({"type":"session.created","requestId":"req-1","sessionId":"event-session"})");
    CHECK_OK(runtime.EnterInitializationMode());
    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-2","state":"initialized"})");
    scripted->QueueResponse(R"({"type":"sim.outputs","requestId":"req-3","simTime":0.0,"values":{"output":0.0}})");
    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-4","state":"initialized"})");
    CHECK_OK(runtime.ExitInitializationMode());

    const std::uint32_t input_reference = 1;
    const double input_value = 4.0;
    CHECK_OK(runtime.SetReal(&input_reference, 1, &input_value));
    scripted->QueueResponse(R"({"type":"sim.inputs.updated","requestId":"req-5"})");
    scripted->QueueResponse(R"({"type":"sim.outputs","requestId":"req-6","simTime":0.0,"values":{"output":4.0},"nextEventTimeDefined":false})");
    bool terminate = false;
    bool next_event_time_defined = true;
    double next_event_time = -1.0;
    CHECK_OK(runtime.UpdateDiscreteStates(&terminate, &next_event_time_defined, &next_event_time));
    CHECK(!terminate);
    CHECK(!next_event_time_defined);
    CHECK_NEAR(next_event_time, 0.0, 1e-12);

    double output_value = 0.0;
    const std::uint32_t output_reference = 2;
    CHECK_OK(runtime.GetReal(&output_reference, 1, &output_value));
    CHECK_NEAR(output_value, 4.0, 1e-12);
    const auto input_update = ParseJson(scripted->SentPayloads()[4]);
    CHECK(input_update);
    CHECK(JsonString(*input_update.value.AsObject(), "type") == "sim.setInputs");
    const JsonObject& sent_values = *FindObjectValue(*input_update.value.AsObject(), "values")->AsObject();
    CHECK_NEAR(JsonNumber(sent_values, "input"), 4.0, 1e-12);
}

void TestUndefinedStopTimeDoesNotUseDefaultExperimentAsALimit() {
    TemporaryDirectory directory;
    WriteFile(directory.path / "config.json",
              R"({"gatewayWsUrl":"wss://gateway.example/fmu","labId":"lab-1","reservationKey":"reservation-1","sessionTicket":"ticket-1","timeMode":"simtime"})");
    WriteFile(directory.path / "modelDescription.xml", R"xml(
        <fmiModelDescription fmiVersion="2.0" modelName="UnboundedModel" guid="unbounded-guid">
          <CoSimulation/>
          <DefaultExperiment startTime="0.0" stopTime="0.5" stepSize="0.25"/>
          <ModelVariables>
            <ScalarVariable name="output" valueReference="1" causality="output"><Real start="0.0"/></ScalarVariable>
          </ModelVariables>
        </fmiModelDescription>
    )xml");

    ScriptedTransport* scripted = nullptr;
    ProxyRuntime runtime([&]() {
        auto transport = std::make_unique<ScriptedTransport>();
        scripted = transport.get();
        return transport;
    });
    CHECK_OK(runtime.Configure("unbounded-instance", directory.path.string()));
    CHECK_OK(runtime.SetupExperiment(0.0, std::nullopt, 0.25));
    scripted->QueueResponse(R"({"type":"session.created","requestId":"req-1","sessionId":"unbounded-session"})");
    CHECK_OK(runtime.EnterInitializationMode());
    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-2","state":"initialized"})");
    scripted->QueueResponse(R"({"type":"sim.outputs","requestId":"req-3","simTime":0.0,"values":{"output":0.0}})");
    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-4","state":"initialized"})");
    CHECK_OK(runtime.ExitInitializationMode());
    const auto sent_payloads = scripted->SentPayloads();
    CHECK(sent_payloads.size() >= 2);
    const auto initialize_request = ParseJson(sent_payloads[1]);
    CHECK(initialize_request);
    const JsonObject& options = *FindObjectValue(*initialize_request.value.AsObject(), "options")->AsObject();
    CHECK(FindObjectValue(options, "stopTime") == nullptr);

    scripted->QueueResponse(R"({"type":"sim.samples","requestId":"req-5","simTime":0.75,"samples":[{"time":0.75,"outputs":{"output":1.0}}]})");
    CHECK_OK(runtime.DoStep(0.0, 0.75));
    CHECK_NEAR(runtime.CurrentTime(), 0.75, 1e-12);
    CHECK(!runtime.SimulationFinished());
}

void TestFmi3TunableBooleanCanBeReconfiguredDuringCoSimulation() {
    TemporaryDirectory directory;
    WriteFile(directory.path / "config.json",
              R"({"gatewayWsUrl":"wss://gateway.example/fmu","labId":"lab-1","reservationKey":"reservation-1","sessionTicket":"ticket-1","timeMode":"simtime","fmiVersion":"3.0"})");
    WriteFile(directory.path / "modelDescription.xml", R"xml(
        <fmiModelDescription fmiVersion="3.0" modelName="DaeProxy" instantiationToken="dae-token">
          <CoSimulation hasEventMode="false"/>
          <ModelVariables>
            <Boolean name="dae" valueReference="1" causality="structuralParameter" variability="tunable" start="false"/>
          </ModelVariables>
        </fmiModelDescription>
    )xml");

    ScriptedTransport* scripted = nullptr;
    ProxyRuntime runtime([&]() {
        auto transport = std::make_unique<ScriptedTransport>();
        scripted = transport.get();
        return transport;
    });
    CHECK_OK(runtime.Configure("dae-instance", directory.path.string()));
    const std::uint32_t dae_reference = 1;
    const bool enabled = true;
    CHECK_OK(runtime.EnterConfigurationMode());
    CHECK_OK(runtime.SetBoolean(&dae_reference, 1, &enabled));
    CHECK_OK(runtime.ExitConfigurationMode());

    scripted->QueueResponse(R"({"type":"session.created","requestId":"req-1","sessionId":"dae-session"})");
    CHECK_OK(runtime.EnterInitializationMode());
    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-2","state":"initialized"})");
    scripted->QueueResponse(R"({"type":"sim.outputs","requestId":"req-3","simTime":0.0,"values":{}})");
    scripted->QueueResponse(R"({"type":"sim.state","requestId":"req-4","state":"initialized"})");
    CHECK_OK(runtime.ExitInitializationMode());
    const auto sent_payloads = scripted->SentPayloads();
    CHECK(sent_payloads.size() >= 2);
    const auto initialize_request = ParseJson(sent_payloads[1]);
    CHECK(initialize_request);
    const JsonObject& parameters = *FindObjectValue(*initialize_request.value.AsObject(), "parameters")->AsObject();
    CHECK(JsonBool(parameters, "dae"));

    const bool disabled = false;
    CHECK_OK(runtime.EnterConfigurationMode());
    CHECK_OK(runtime.SetBoolean(&dae_reference, 1, &disabled));
    scripted->QueueResponse(R"({"type":"sim.reconfigured","requestId":"req-5","simTime":0.0})");
    CHECK_OK(runtime.ExitConfigurationMode());
    const auto reconfiguration_request = ParseJson(scripted->SentPayloads().back());
    CHECK(reconfiguration_request);
    const JsonObject& reconfiguration = *reconfiguration_request.value.AsObject();
    CHECK(JsonString(reconfiguration, "type") == "sim.reconfigure");
    CHECK(JsonBool(*FindObjectValue(reconfiguration, "values")->AsObject(), "dae") == false);
    CHECK(runtime.State() == SessionState::kInitialized);
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
    failures += RunTest("FMI 2 serialized state preserves Model Exchange mode", TestFmi2SerializedStatePreservesModelExchangeMode);
    failures += RunTest("runtime config parsing", TestRuntimeConfigParsing);
    failures += RunTest("protocol and session state", TestProtocolAndSessionState);
    failures += RunTest("model description parsing", TestModelDescriptionParsing);
    failures += RunTest("transport implementations", TestTransportImplementations);
    failures += RunTest("gateway client protocol", TestGatewayClientProtocol);
    failures += RunTest("proxy runtime lifecycle", TestProxyRuntimeLifecycle);
    failures += RunTest("initialization reads evaluate and refresh outputs", TestInitializationGetsEvaluateAndRefreshOutputs);
    failures += RunTest("Model Exchange initialization reads and exact state writes", TestModelExchangeInitializationReadsAndExactStateWritesAreOrderIndependent);
    failures += RunTest("FMI 3 exact and approximate states can be set while instantiated", TestFmi3ExactAndApproxStatesCanBeSetWhileInstantiated);
    failures += RunTest("FMI 2 exact state can be set during initialization after a read", TestFmi2ExactStateCanBeSetDuringInitializationAfterARead);
    failures += RunTest("Model Exchange state can be captured and restored during initialization", TestModelExchangeStateCanBeCapturedAndRestoredDuringInitialization);
    failures += RunTest("Co-Simulation state can be captured during initialization", TestCoSimulationStateCanBeCapturedDuringInitialization);
    failures += RunTest("instantiated Configuration Mode checkpoint stays local", TestInstantiatedConfigurationCheckpointStaysLocal);
    failures += RunTest("instantiated checkpoint resets an active remote session", TestInstantiatedCheckpointResetsAStartedRemoteSession);
    failures += RunTest("remote state checkpoint survives Terminate", TestRemoteCheckpointCaptureAndRestoreAroundTerminate);
    failures += RunTest("discrete-state updates write inputs and refresh outputs", TestUpdateDiscreteStatesWritesInputsAndRefreshesOutputs);
    failures += RunTest("undefined stop time", TestUndefinedStopTimeDoesNotUseDefaultExperimentAsALimit);
    failures += RunTest("FMI 3 runtime reconfiguration", TestFmi3TunableBooleanCanBeReconfiguredDuringCoSimulation);
    return failures == 0 ? 0 : 1;
}
