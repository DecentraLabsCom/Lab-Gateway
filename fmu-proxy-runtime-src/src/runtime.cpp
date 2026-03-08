#include "decentralabs_proxy/runtime.hpp"

#include <cctype>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <utility>

namespace decentralabs::proxy {

namespace {

std::string PercentDecode(const std::string_view text) {
    std::string output;
    output.reserve(text.size());
    for (std::size_t index = 0; index < text.size(); ++index) {
        if (text[index] == '%' && index + 2 < text.size()) {
            const std::string hex = std::string(text.substr(index + 1, 2));
            char* end = nullptr;
            const long value = std::strtol(hex.c_str(), &end, 16);
            if (end != nullptr && *end == '\0') {
                output.push_back(static_cast<char>(value));
                index += 2;
                continue;
            }
        }
        output.push_back(text[index] == '+' ? ' ' : text[index]);
    }
    return output;
}

std::optional<ScalarValue> ConvertJsonValue(const JsonValue& value, const ScalarType type) {
    if (value.IsArray()) {
        const JsonArray* items = value.AsArray();
        if (items == nullptr) {
            return std::nullopt;
        }
        switch (type) {
            case ScalarType::kReal: {
                RealArray values;
                values.reserve(items->size());
                for (const auto& item : *items) {
                    if (!item.IsNumber()) {
                        return std::nullopt;
                    }
                    values.push_back(item.AsNumber());
                }
                return ScalarValue(std::move(values));
            }
            case ScalarType::kInteger:
            case ScalarType::kEnumeration: {
                IntegerArray values;
                values.reserve(items->size());
                for (const auto& item : *items) {
                    if (!item.IsNumber()) {
                        return std::nullopt;
                    }
                    values.push_back(static_cast<std::int32_t>(std::llround(item.AsNumber())));
                }
                return ScalarValue(std::move(values));
            }
            case ScalarType::kBoolean: {
                BooleanArray values;
                values.reserve(items->size());
                for (const auto& item : *items) {
                    if (item.IsBool()) {
                        values.push_back(item.AsBool());
                    } else if (item.IsNumber()) {
                        values.push_back(item.AsNumber() != 0.0);
                    } else {
                        return std::nullopt;
                    }
                }
                return ScalarValue(std::move(values));
            }
            case ScalarType::kString: {
                StringArray values;
                values.reserve(items->size());
                for (const auto& item : *items) {
                    if (!item.IsString()) {
                        return std::nullopt;
                    }
                    values.push_back(item.AsString());
                }
                return ScalarValue(std::move(values));
            }
        }
    }
    switch (type) {
        case ScalarType::kReal:
            if (value.IsNumber()) {
                return ScalarValue(value.AsNumber());
            }
            break;
        case ScalarType::kInteger:
        case ScalarType::kEnumeration:
            if (value.IsNumber()) {
                return ScalarValue(static_cast<std::int32_t>(std::llround(value.AsNumber())));
            }
            break;
        case ScalarType::kBoolean:
            if (value.IsBool()) {
                return ScalarValue(value.AsBool());
            }
            if (value.IsNumber()) {
                return ScalarValue(value.AsNumber() != 0.0);
            }
            break;
        case ScalarType::kString:
            if (value.IsString()) {
                return ScalarValue(value.AsString());
            }
            break;
    }
    return std::nullopt;
}

std::optional<std::int32_t> ScalarValueToInt32(const ScalarValue& value) {
    if (const auto* integer = std::get_if<std::int32_t>(&value)) {
        return *integer;
    }
    if (const auto* real = std::get_if<double>(&value)) {
        return static_cast<std::int32_t>(std::llround(*real));
    }
    return std::nullopt;
}

template <typename TArray>
JsonArray ToJsonArrayFromPrimitiveArray(const TArray& values) {
    JsonArray result;
    result.reserve(values.size());
    for (const auto& value : values) {
        result.emplace_back(value);
    }
    return result;
}

}  // namespace

ProxyRuntime::ProxyRuntime(TransportFactory transport_factory)
    : transport_factory_(std::move(transport_factory)) {
    if (!transport_factory_) {
        transport_factory_ = []() { return CreateDefaultGatewayTransport(); };
    }
}

void ProxyRuntime::SetLogger(LogSink logger) {
    logger_ = std::move(logger);
}

void ProxyRuntime::SetError(const std::string& message) {
    last_error_ = message;
    if (logger_) {
        logger_("error", message);
    }
}

OperationResult ProxyRuntime::Transition(const SessionState next) {
    if (!CanTransition(state_, next)) {
        return OperationResult::Failure(
            "STATE_ERROR",
            "Invalid state transition from " + std::string(ToString(state_)) + " to " + ToString(next));
    }
    state_ = next;
    return OperationResult::Success();
}

std::string ProxyRuntime::DecodeFileUri(const std::string& resource_location) {
    std::string path = resource_location;
    constexpr std::string_view prefix = "file://";
    if (path.rfind(prefix.data(), 0) == 0) {
        path = PercentDecode(std::string_view(path).substr(prefix.size()));
        if (path.size() >= 3 && path[0] == '/' && std::isalpha(static_cast<unsigned char>(path[1])) && path[2] == ':') {
            path.erase(path.begin());
        }
    }
    return path;
}

void ProxyRuntime::SeedCacheFromModelDefaults() {
    cached_values_.clear();
    for (const auto& variable : model_.variables) {
        if (variable.start_value.has_value()) {
            cached_values_[variable.value_reference] = *variable.start_value;
            continue;
        }
        const std::size_t flat_size = ResolveVariableFlatSize(variable);
        if (flat_size > 1) {
            switch (variable.type) {
                case ScalarType::kReal:
                    cached_values_[variable.value_reference] = RealArray(flat_size, 0.0);
                    break;
                case ScalarType::kInteger:
                case ScalarType::kEnumeration:
                    cached_values_[variable.value_reference] = IntegerArray(flat_size, 0);
                    break;
                case ScalarType::kBoolean:
                    cached_values_[variable.value_reference] = BooleanArray(flat_size, false);
                    break;
                case ScalarType::kString:
                    cached_values_[variable.value_reference] = StringArray(flat_size, std::string());
                    break;
            }
            continue;
        }
        switch (variable.type) {
            case ScalarType::kReal:
                cached_values_[variable.value_reference] = 0.0;
                break;
            case ScalarType::kInteger:
            case ScalarType::kEnumeration:
                cached_values_[variable.value_reference] = static_cast<std::int32_t>(0);
                break;
            case ScalarType::kBoolean:
                cached_values_[variable.value_reference] = false;
                break;
            case ScalarType::kString:
                cached_values_[variable.value_reference] = std::string();
                break;
        }
    }
}

std::optional<std::int32_t> ProxyRuntime::ResolveDimensionExtent(const DimensionInfo& dimension) const {
    if (dimension.start.has_value()) {
        return dimension.start;
    }
    if (dimension.value_reference.has_value()) {
        const ScalarValue* cached = GetCachedValue(*dimension.value_reference);
        if (cached != nullptr) {
            return ScalarValueToInt32(*cached);
        }
        const VariableInfo* variable = FindVariableByValueReference(model_, *dimension.value_reference);
        if (variable != nullptr && variable->start_value.has_value()) {
            return ScalarValueToInt32(*variable->start_value);
        }
    }
    if (!dimension.variable_name.empty()) {
        const VariableInfo* variable = FindVariableByName(model_, dimension.variable_name);
        if (variable != nullptr && variable->start_value.has_value()) {
            return ScalarValueToInt32(*variable->start_value);
        }
    }
    return std::nullopt;
}

std::size_t ProxyRuntime::ResolveVariableFlatSize(const VariableInfo& variable) const {
    if (variable.dimensions.empty()) {
        return 1;
    }
    std::size_t size = 1;
    for (const auto& dimension : variable.dimensions) {
        const auto extent = ResolveDimensionExtent(dimension);
        if (!extent.has_value() || *extent < 0) {
            return 0;
        }
        size *= static_cast<std::size_t>(*extent);
    }
    return size;
}

std::size_t ProxyRuntime::ExpectedValueCount(const std::uint32_t* value_references, const std::size_t count) const {
    if (value_references == nullptr) {
        return 0;
    }
    std::size_t expected = 0;
    for (std::size_t index = 0; index < count; ++index) {
        const VariableInfo* variable = FindVariableByValueReference(model_, value_references[index]);
        if (variable == nullptr) {
            return 0;
        }
        const std::size_t flat_size = ResolveVariableFlatSize(*variable);
        if (flat_size == 0) {
            return 0;
        }
        expected += flat_size;
    }
    return expected;
}

OperationResult ProxyRuntime::Configure(const std::string& instance_name, const std::string& resource_location) {
    const std::string resource_path_text = DecodeFileUri(resource_location);
    if (resource_path_text.empty()) {
        return OperationResult::Failure("CONFIG_INVALID", "FMU resource location is empty");
    }

    const std::filesystem::path resource_path(resource_path_text);
    const std::filesystem::path config_path = resource_path / "config.json";
    std::filesystem::path model_path = resource_path / "modelDescription.xml";
    if (!std::filesystem::exists(model_path)) {
        std::filesystem::path probe = resource_path;
        for (int depth = 0; depth < 3; ++depth) {
            const std::filesystem::path candidate = probe / "modelDescription.xml";
            if (std::filesystem::exists(candidate)) {
                model_path = candidate;
                break;
            }
            if (!probe.has_parent_path()) {
                break;
            }
            probe = probe.parent_path();
        }
    }

    auto config = LoadRuntimeConfigFromFile(config_path.string());
    if (!config) {
        return config.status;
    }
    auto model = LoadModelDescriptionFromFile(model_path.string());
    if (!model) {
        return model.status;
    }
    if (!model.value.supports_co_simulation) {
        return OperationResult::Failure(
            "MODEL_DESCRIPTION_UNSUPPORTED",
            "The proxy runtime currently supports only Co-Simulation FMUs");
    }

    instance_name_ = instance_name;
    config_ = std::move(config.value);
    model_ = std::move(model.value);
    experiment_.start_time = model_.default_start_time.value_or(0.0);
    experiment_.stop_time = model_.default_stop_time.value_or(10.0);
    experiment_.step_size = model_.default_step_size.value_or(0.01);
    current_time_ = experiment_.start_time;
    gateway_client_ = std::make_unique<GatewayClient>(transport_factory_());
    SeedCacheFromModelDefaults();
    pending_inputs_.clear();
    string_cache_.clear();
    last_error_.clear();

    return Transition(SessionState::kInstantiated);
}

OperationResult ProxyRuntime::SetupExperiment(const double start_time, const double stop_time, const double step_size) {
    experiment_.start_time = start_time;
    experiment_.stop_time = stop_time;
    experiment_.step_size = step_size;
    current_time_ = start_time;
    return OperationResult::Success();
}

OperationResult ProxyRuntime::EnterInitializationMode() {
    if (gateway_client_ == nullptr) {
        return OperationResult::Failure("RUNTIME_NOT_CONFIGURED", "Runtime is not configured");
    }
    auto status = Transition(SessionState::kSocketConnecting);
    if (!status) {
        return status;
    }
    status = gateway_client_->CreateSession(config_);
    if (!status) {
        state_ = SessionState::kError;
        SetError(status.message);
        return status;
    }
    status = Transition(SessionState::kSocketReady);
    if (!status) {
        return status;
    }
    return Transition(SessionState::kSessionCreated);
}

OperationResult ProxyRuntime::ExitInitializationMode() {
    if (gateway_client_ == nullptr) {
        return OperationResult::Failure("RUNTIME_NOT_CONFIGURED", "Runtime is not configured");
    }
    if (state_ != SessionState::kSessionCreated) {
        return OperationResult::Failure("STATE_ERROR", "Runtime is not in session_created state");
    }

    const auto status = gateway_client_->Initialize(config_, experiment_, pending_inputs_);
    if (!status) {
        state_ = SessionState::kError;
        SetError(status.message);
        return status;
    }
    pending_inputs_.clear();
    current_time_ = experiment_.start_time;
    return Transition(SessionState::kInitialized);
}

OperationResult ProxyRuntime::ApplyOutputSnapshot(const OutputSnapshot& snapshot) {
    current_time_ = snapshot.sim_time;
    for (const auto& [name, json_value] : snapshot.values) {
        const VariableInfo* variable = FindVariableByName(model_, name);
        if (variable == nullptr) {
            continue;
        }
        const auto converted = ConvertJsonValue(json_value, variable->type);
        if (!converted.has_value()) {
            continue;
        }
        cached_values_[variable->value_reference] = *converted;
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::DoStep(const double, const double step_size) {
    if (gateway_client_ == nullptr) {
        return OperationResult::Failure("RUNTIME_NOT_CONFIGURED", "Runtime is not configured");
    }
    if (state_ != SessionState::kInitialized && state_ != SessionState::kRunning) {
        return OperationResult::Failure("STATE_ERROR", "Runtime is not initialized");
    }
    if (!pending_inputs_.empty()) {
        const auto set_status = gateway_client_->SetInputs(pending_inputs_);
        if (!set_status) {
            state_ = SessionState::kError;
            SetError(set_status.message);
            return set_status;
        }
        pending_inputs_.clear();
    }

    const auto snapshot = gateway_client_->Step(step_size);
    if (!snapshot) {
        state_ = SessionState::kError;
        SetError(snapshot.status.message);
        return snapshot.status;
    }
    auto status = ApplyOutputSnapshot(snapshot.value);
    if (!status) {
        return status;
    }
    if (state_ == SessionState::kInitialized) {
        status = Transition(SessionState::kRunning);
        if (!status) {
            return status;
        }
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::Terminate() {
    if (gateway_client_ == nullptr) {
        return OperationResult::Success();
    }
    const auto status = gateway_client_->Terminate();
    if (!status) {
        SetError(status.message);
        return status;
    }
    state_ = SessionState::kTerminated;
    return OperationResult::Success();
}

OperationResult ProxyRuntime::Reset() {
    if (gateway_client_ != nullptr && gateway_client_->IsConnected()) {
        const auto reset_status = gateway_client_->Reset();
        if (!reset_status) {
            state_ = SessionState::kError;
            SetError(reset_status.message);
            return reset_status;
        }
    }
    SeedCacheFromModelDefaults();
    pending_inputs_.clear();
    current_time_ = experiment_.start_time;
    state_ = SessionState::kInstantiated;
    return OperationResult::Success();
}

OperationResult ProxyRuntime::SetValue(const VariableInfo& variable, ScalarValue value) {
    cached_values_[variable.value_reference] = value;
    pending_inputs_[variable.name] = std::move(value);
    return OperationResult::Success();
}

const ScalarValue* ProxyRuntime::GetCachedValue(const std::uint32_t value_reference) const {
    const auto it = cached_values_.find(value_reference);
    if (it == cached_values_.end()) {
        return nullptr;
    }
    return &it->second;
}

template <typename T>
OperationResult ProxyRuntime::SetNumericValues(const std::uint32_t* value_references,
                                               const std::size_t count,
                                               const T* values,
                                               const std::size_t value_count,
                                               const ScalarType expected_type) {
    if (value_references == nullptr || values == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "Set values received null buffers");
    }
    const std::size_t expected_count = value_count == 0 ? count : value_count;
    if (ExpectedValueCount(value_references, count) != expected_count) {
        return OperationResult::Failure("INVALID_ARGUMENT", "Set values buffer length does not match referenced FMI variables");
    }
    std::size_t offset = 0;
    for (std::size_t index = 0; index < count; ++index) {
        const VariableInfo* variable = FindVariableByValueReference(model_, value_references[index]);
        if (variable == nullptr) {
            return OperationResult::Failure("UNKNOWN_VALUE_REFERENCE", "Unknown value reference");
        }
        if (variable->type != expected_type &&
            !(expected_type == ScalarType::kInteger && variable->type == ScalarType::kEnumeration)) {
            return OperationResult::Failure("TYPE_MISMATCH", "Variable type does not match setter");
        }
        const std::size_t flat_size = ResolveVariableFlatSize(*variable);
        if (flat_size == 0 || offset + flat_size > expected_count) {
            return OperationResult::Failure("INVALID_ARGUMENT", "Set values buffer is too short for referenced FMI variables");
        }
        if (flat_size == 1) {
            SetValue(*variable, static_cast<T>(values[offset]));
        } else if (expected_type == ScalarType::kReal) {
            RealArray buffer;
            buffer.reserve(flat_size);
            for (std::size_t element = 0; element < flat_size; ++element) {
                buffer.push_back(static_cast<double>(values[offset + element]));
            }
            SetValue(*variable, std::move(buffer));
        } else {
            IntegerArray buffer;
            buffer.reserve(flat_size);
            for (std::size_t element = 0; element < flat_size; ++element) {
                buffer.push_back(static_cast<std::int32_t>(values[offset + element]));
            }
            SetValue(*variable, std::move(buffer));
        }
        offset += flat_size;
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::SetReal(const std::uint32_t* value_references,
                                      const std::size_t count,
                                      const double* values,
                                      const std::size_t value_count) {
    return SetNumericValues(value_references, count, values, value_count, ScalarType::kReal);
}

OperationResult ProxyRuntime::SetInteger(const std::uint32_t* value_references,
                                         const std::size_t count,
                                         const std::int32_t* values,
                                         const std::size_t value_count) {
    return SetNumericValues(value_references, count, values, value_count, ScalarType::kInteger);
}

OperationResult ProxyRuntime::SetBoolean(const std::uint32_t* value_references,
                                         const std::size_t count,
                                         const bool* values,
                                         const std::size_t value_count) {
    if (value_references == nullptr || values == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "SetBoolean received null buffers");
    }
    const std::size_t expected_count = value_count == 0 ? count : value_count;
    if (ExpectedValueCount(value_references, count) != expected_count) {
        return OperationResult::Failure("INVALID_ARGUMENT", "SetBoolean buffer length does not match referenced FMI variables");
    }
    std::size_t offset = 0;
    for (std::size_t index = 0; index < count; ++index) {
        const VariableInfo* variable = FindVariableByValueReference(model_, value_references[index]);
        if (variable == nullptr) {
            return OperationResult::Failure("UNKNOWN_VALUE_REFERENCE", "Unknown value reference");
        }
        if (variable->type != ScalarType::kBoolean) {
            return OperationResult::Failure("TYPE_MISMATCH", "Variable type does not match SetBoolean");
        }
        const std::size_t flat_size = ResolveVariableFlatSize(*variable);
        if (flat_size == 0 || offset + flat_size > expected_count) {
            return OperationResult::Failure("INVALID_ARGUMENT", "SetBoolean buffer length does not match referenced FMI variables");
        }
        if (flat_size == 1) {
            SetValue(*variable, values[offset]);
        } else {
            BooleanArray buffer;
            buffer.reserve(flat_size);
            for (std::size_t element = 0; element < flat_size; ++element) {
                buffer.push_back(values[offset + element]);
            }
            SetValue(*variable, std::move(buffer));
        }
        offset += flat_size;
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::SetString(const std::uint32_t* value_references,
                                        const std::size_t count,
                                        const char* const* values,
                                        const std::size_t value_count) {
    if (value_references == nullptr || values == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "SetString received null buffers");
    }
    const std::size_t expected_count = value_count == 0 ? count : value_count;
    if (ExpectedValueCount(value_references, count) != expected_count) {
        return OperationResult::Failure("INVALID_ARGUMENT", "SetString buffer length does not match referenced FMI variables");
    }
    std::size_t offset = 0;
    for (std::size_t index = 0; index < count; ++index) {
        const VariableInfo* variable = FindVariableByValueReference(model_, value_references[index]);
        if (variable == nullptr) {
            return OperationResult::Failure("UNKNOWN_VALUE_REFERENCE", "Unknown value reference");
        }
        if (variable->type != ScalarType::kString) {
            return OperationResult::Failure("TYPE_MISMATCH", "Variable type does not match SetString");
        }
        const std::size_t flat_size = ResolveVariableFlatSize(*variable);
        if (flat_size == 0 || offset + flat_size > expected_count) {
            return OperationResult::Failure("INVALID_ARGUMENT", "SetString buffer length does not match referenced FMI variables");
        }
        if (flat_size == 1) {
            SetValue(*variable, std::string(values[offset] ? values[offset] : ""));
        } else {
            StringArray buffer;
            buffer.reserve(flat_size);
            for (std::size_t element = 0; element < flat_size; ++element) {
                buffer.emplace_back(values[offset + element] ? values[offset + element] : "");
            }
            SetValue(*variable, std::move(buffer));
        }
        offset += flat_size;
    }
    return OperationResult::Success();
}

template <typename T>
OperationResult ProxyRuntime::GetNumericValues(const std::uint32_t* value_references,
                                               const std::size_t count,
                                               T* values,
                                               const std::size_t value_count,
                                               const ScalarType expected_type) const {
    if (value_references == nullptr || values == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "Get values received null buffers");
    }
    const std::size_t expected_count = value_count == 0 ? count : value_count;
    if (ExpectedValueCount(value_references, count) != expected_count) {
        return OperationResult::Failure("INVALID_ARGUMENT", "Get values buffer length does not match referenced FMI variables");
    }
    std::size_t offset = 0;
    for (std::size_t index = 0; index < count; ++index) {
        const VariableInfo* variable = FindVariableByValueReference(model_, value_references[index]);
        if (variable == nullptr) {
            return OperationResult::Failure("UNKNOWN_VALUE_REFERENCE", "Unknown value reference");
        }
        if (variable->type != expected_type &&
            !(expected_type == ScalarType::kInteger && variable->type == ScalarType::kEnumeration)) {
            return OperationResult::Failure("TYPE_MISMATCH", "Variable type does not match getter");
        }
        const ScalarValue* cached = GetCachedValue(value_references[index]);
        if (cached == nullptr) {
            return OperationResult::Failure("VALUE_UNAVAILABLE", "Value is not cached");
        }
        const std::size_t flat_size = ResolveVariableFlatSize(*variable);
        if (flat_size == 0 || offset + flat_size > expected_count) {
            return OperationResult::Failure("INVALID_ARGUMENT", "Get values buffer length does not match referenced FMI variables");
        }
        if (flat_size == 1) {
            if (const auto* typed = std::get_if<T>(cached)) {
                values[offset] = *typed;
            } else {
                return OperationResult::Failure("TYPE_MISMATCH", "Cached value type does not match getter");
            }
        } else if (expected_type == ScalarType::kReal) {
            const auto* typed = std::get_if<RealArray>(cached);
            if (typed == nullptr || typed->size() != flat_size) {
                return OperationResult::Failure("TYPE_MISMATCH", "Cached array value type does not match getter");
            }
            for (std::size_t element = 0; element < flat_size; ++element) {
                values[offset + element] = static_cast<T>((*typed)[element]);
            }
        } else {
            const auto* typed = std::get_if<IntegerArray>(cached);
            if (typed == nullptr || typed->size() != flat_size) {
                return OperationResult::Failure("TYPE_MISMATCH", "Cached array value type does not match getter");
            }
            for (std::size_t element = 0; element < flat_size; ++element) {
                values[offset + element] = static_cast<T>((*typed)[element]);
            }
        }
        offset += flat_size;
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::GetReal(const std::uint32_t* value_references,
                                      const std::size_t count,
                                      double* values,
                                      const std::size_t value_count) const {
    return GetNumericValues(value_references, count, values, value_count, ScalarType::kReal);
}

OperationResult ProxyRuntime::GetInteger(const std::uint32_t* value_references,
                                         const std::size_t count,
                                         std::int32_t* values,
                                         const std::size_t value_count) const {
    return GetNumericValues(value_references, count, values, value_count, ScalarType::kInteger);
}

OperationResult ProxyRuntime::GetUnsignedInteger(const std::uint32_t* value_references,
                                                 const std::size_t count,
                                                 std::uint64_t* values,
                                                 const std::size_t value_count) const {
    if (value_references == nullptr || values == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetUnsignedInteger received null buffers");
    }
    const std::size_t expected_count = value_count == 0 ? count : value_count;
    std::vector<std::int32_t> temp(expected_count);
    const auto status = GetInteger(value_references, count, temp.data(), expected_count);
    if (!status) {
        return status;
    }
    for (std::size_t index = 0; index < expected_count; ++index) {
        if (temp[index] < 0) {
            return OperationResult::Failure("TYPE_MISMATCH", "Cached integer value cannot be represented as UInt64");
        }
        values[index] = static_cast<std::uint64_t>(temp[index]);
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::GetBoolean(const std::uint32_t* value_references,
                                         const std::size_t count,
                                         bool* values,
                                         const std::size_t value_count) const {
    if (value_references == nullptr || values == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetBoolean received null buffers");
    }
    const std::size_t expected_count = value_count == 0 ? count : value_count;
    if (ExpectedValueCount(value_references, count) != expected_count) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetBoolean buffer length does not match referenced FMI variables");
    }
    std::size_t offset = 0;
    for (std::size_t index = 0; index < count; ++index) {
        const VariableInfo* variable = FindVariableByValueReference(model_, value_references[index]);
        if (variable == nullptr) {
            return OperationResult::Failure("UNKNOWN_VALUE_REFERENCE", "Unknown value reference");
        }
        if (variable->type != ScalarType::kBoolean) {
            return OperationResult::Failure("TYPE_MISMATCH", "Variable type does not match GetBoolean");
        }
        const ScalarValue* cached = GetCachedValue(value_references[index]);
        if (cached == nullptr) {
            return OperationResult::Failure("VALUE_UNAVAILABLE", "Value is not cached");
        }
        const std::size_t flat_size = ResolveVariableFlatSize(*variable);
        if (flat_size == 0 || offset + flat_size > expected_count) {
            return OperationResult::Failure("INVALID_ARGUMENT", "GetBoolean buffer length does not match referenced FMI variables");
        }
        if (flat_size == 1) {
            const auto* typed = std::get_if<bool>(cached);
            if (typed == nullptr) {
                return OperationResult::Failure("TYPE_MISMATCH", "Cached value type does not match GetBoolean");
            }
            values[offset] = *typed;
        } else {
            const auto* typed = std::get_if<BooleanArray>(cached);
            if (typed == nullptr || typed->size() != flat_size) {
                return OperationResult::Failure("TYPE_MISMATCH", "Cached array value type does not match GetBoolean");
            }
            for (std::size_t element = 0; element < flat_size; ++element) {
                values[offset + element] = (*typed)[element];
            }
        }
        offset += flat_size;
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::GetString(const std::uint32_t* value_references,
                                        const std::size_t count,
                                        const char** values,
                                        const std::size_t value_count) {
    if (value_references == nullptr || values == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetString received null buffers");
    }
    string_cache_.clear();
    const std::size_t expected_count = value_count == 0 ? count : value_count;
    if (ExpectedValueCount(value_references, count) != expected_count) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetString buffer length does not match referenced FMI variables");
    }
    string_cache_.reserve(expected_count);
    std::size_t offset = 0;
    for (std::size_t index = 0; index < count; ++index) {
        const VariableInfo* variable = FindVariableByValueReference(model_, value_references[index]);
        if (variable == nullptr) {
            return OperationResult::Failure("UNKNOWN_VALUE_REFERENCE", "Unknown value reference");
        }
        if (variable->type != ScalarType::kString) {
            return OperationResult::Failure("TYPE_MISMATCH", "Variable type does not match GetString");
        }
        const ScalarValue* cached = GetCachedValue(value_references[index]);
        if (cached == nullptr) {
            return OperationResult::Failure("VALUE_UNAVAILABLE", "Value is not cached");
        }
        const std::size_t flat_size = ResolveVariableFlatSize(*variable);
        if (flat_size == 0 || offset + flat_size > expected_count) {
            return OperationResult::Failure("INVALID_ARGUMENT", "GetString buffer length does not match referenced FMI variables");
        }
        if (flat_size == 1) {
            const auto* text = std::get_if<std::string>(cached);
            if (text == nullptr) {
                return OperationResult::Failure("TYPE_MISMATCH", "Cached value type does not match GetString");
            }
            string_cache_.push_back(*text);
            values[offset] = string_cache_.back().c_str();
            ++offset;
        } else {
            const auto* text = std::get_if<StringArray>(cached);
            if (text == nullptr || text->size() != flat_size) {
                return OperationResult::Failure("TYPE_MISMATCH", "Cached array value type does not match GetString");
            }
            for (const auto& item : *text) {
                string_cache_.push_back(item);
                values[offset] = string_cache_.back().c_str();
                ++offset;
            }
        }
    }
    return OperationResult::Success();
}

const RuntimeConfig& ProxyRuntime::Config() const {
    return config_;
}

const ModelDescription& ProxyRuntime::Model() const {
    return model_;
}

SessionState ProxyRuntime::State() const {
    return state_;
}

double ProxyRuntime::CurrentTime() const {
    return current_time_;
}

const std::string& ProxyRuntime::LastError() const {
    return last_error_;
}

}  // namespace decentralabs::proxy
