#include "decentralabs_proxy/runtime.hpp"

#include "decentralabs_proxy/scalar_value_codec.hpp"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <limits>
#include <thread>
#include <type_traits>
#include <utility>

namespace decentralabs::proxy {

namespace {

std::string PercentDecode(const std::string_view text) {
    std::string output;
    output.reserve(text.size());
    std::size_t index = 0;
    while (index < text.size()) {
        if (text[index] == '%' && index + 2 < text.size()) {
            const std::string hex = std::string(text.substr(index + 1, 2));
            char* end = nullptr;
            const long value = std::strtol(hex.c_str(), &end, 16);
            if (end != nullptr && *end == '\0') {
                output.push_back(static_cast<char>(value));
                index += 3;
                continue;
            }
        }
        output.push_back(text[index] == '+' ? ' ' : text[index]);
        ++index;
    }
    return output;
}

struct IntegerBounds {
    std::int64_t min = std::numeric_limits<std::int64_t>::min();
    std::uint64_t max = std::numeric_limits<std::uint64_t>::max();
    bool unsigned_only = false;
};

IntegerBounds BoundsForDeclaredType(const std::string_view declared_type) {
    if (declared_type == "Int8") {
        return {std::numeric_limits<std::int8_t>::min(), static_cast<std::uint64_t>(std::numeric_limits<std::int8_t>::max()), false};
    }
    if (declared_type == "UInt8") {
        return {0, std::numeric_limits<std::uint8_t>::max(), true};
    }
    if (declared_type == "Int16") {
        return {std::numeric_limits<std::int16_t>::min(), static_cast<std::uint64_t>(std::numeric_limits<std::int16_t>::max()), false};
    }
    if (declared_type == "UInt16") {
        return {0, std::numeric_limits<std::uint16_t>::max(), true};
    }
    if (declared_type == "Int32" || declared_type == "Integer" || declared_type == "Enumeration") {
        return {std::numeric_limits<std::int32_t>::min(), static_cast<std::uint64_t>(std::numeric_limits<std::int32_t>::max()), false};
    }
    if (declared_type == "UInt32") {
        return {0, std::numeric_limits<std::uint32_t>::max(), true};
    }
    if (declared_type == "UInt64") {
        return {0, std::numeric_limits<std::uint64_t>::max(), true};
    }
    return {std::numeric_limits<std::int64_t>::min(), std::numeric_limits<std::uint64_t>::max(), false};
}

bool TryNormalizeIntegerValue(const VariableInfo& variable, const std::int64_t raw_value, ScalarValue* output) {
    if (output == nullptr) {
        return false;
    }
    const auto bounds = BoundsForDeclaredType(variable.declared_type);
    if (bounds.unsigned_only) {
        if (raw_value < 0) {
            return false;
        }
        const auto value = static_cast<std::uint64_t>(raw_value);
        if (value > bounds.max) {
            return false;
        }
        *output = value;
        return true;
    }
    if (raw_value < bounds.min || (raw_value >= 0 && static_cast<std::uint64_t>(raw_value) > bounds.max)) {
        return false;
    }
    *output = raw_value;
    return true;
}

bool TryNormalizeIntegerValue(const VariableInfo& variable, const std::uint64_t raw_value, ScalarValue* output) {
    if (output == nullptr) {
        return false;
    }
    const auto bounds = BoundsForDeclaredType(variable.declared_type);
    if (bounds.unsigned_only) {
        if (raw_value > bounds.max) {
            return false;
        }
        *output = raw_value;
        return true;
    }
    if (raw_value > bounds.max || raw_value > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
        return false;
    }
    *output = static_cast<std::int64_t>(raw_value);
    return true;
}

template <typename T>
bool TryNormalizeIntegerValue(const VariableInfo& variable, const T raw_value, ScalarValue* output) {
    if constexpr (std::is_unsigned_v<T>) {
        return TryNormalizeIntegerValue(variable, static_cast<std::uint64_t>(raw_value), output);
    } else {
        return TryNormalizeIntegerValue(variable, static_cast<std::int64_t>(raw_value), output);
    }
}

std::optional<std::int64_t> ParseSignedInteger(const JsonValue& value) {
    try {
        if (value.IsString()) {
            return static_cast<std::int64_t>(std::stoll(value.AsString()));
        }
        if (value.IsNumber()) {
            const double number = value.AsNumber();
            double integral_part = 0.0;
            const double fractional_part = std::modf(number, &integral_part);
            if (!std::isfinite(number) || std::abs(fractional_part) > std::numeric_limits<double>::epsilon()) {
                return std::nullopt;
            }
            if (number < static_cast<double>(std::numeric_limits<std::int64_t>::min()) ||
                number > static_cast<double>(std::numeric_limits<std::int64_t>::max())) {
                return std::nullopt;
            }
            return static_cast<std::int64_t>(number);
        }
    } catch (...) {
        return std::nullopt;
    }
    return std::nullopt;
}

std::optional<std::uint64_t> ParseUnsignedInteger(const JsonValue& value) {
    try {
        if (value.IsString()) {
            return static_cast<std::uint64_t>(std::stoull(value.AsString()));
        }
        if (value.IsNumber()) {
            const double number = value.AsNumber();
            double integral_part = 0.0;
            const double fractional_part = std::modf(number, &integral_part);
            if (!std::isfinite(number) || std::abs(fractional_part) > std::numeric_limits<double>::epsilon() || number < 0.0) {
                return std::nullopt;
            }
            if (number > static_cast<double>(std::numeric_limits<std::uint64_t>::max())) {
                return std::nullopt;
            }
            return static_cast<std::uint64_t>(number);
        }
    } catch (...) {
        return std::nullopt;
    }
    return std::nullopt;
}

std::optional<ScalarValue> DecodeIntegerArray(const JsonArray& items, const VariableInfo& variable) {
    if (BoundsForDeclaredType(variable.declared_type).unsigned_only) {
        UnsignedIntegerArray values;
        values.reserve(items.size());
        for (const auto& item : items) {
            const auto parsed = ParseUnsignedInteger(item);
            if (!parsed.has_value()) {
                return std::nullopt;
            }
            ScalarValue normalized;
            if (!TryNormalizeIntegerValue(variable, *parsed, &normalized)) {
                return std::nullopt;
            }
            const auto* integer = std::get_if<std::uint64_t>(&normalized);
            if (integer == nullptr) {
                return std::nullopt;
            }
            values.push_back(*integer);
        }
        return ScalarValue(std::move(values));
    }

    IntegerArray values;
    values.reserve(items.size());
    for (const auto& item : items) {
        const auto parsed = ParseSignedInteger(item);
        if (!parsed.has_value()) {
            return std::nullopt;
        }
        ScalarValue normalized;
        if (!TryNormalizeIntegerValue(variable, *parsed, &normalized)) {
            return std::nullopt;
        }
        const auto* integer = std::get_if<std::int64_t>(&normalized);
        if (integer == nullptr) {
            return std::nullopt;
        }
        values.push_back(*integer);
    }
    return ScalarValue(std::move(values));
}

// codeql[cpp/poorly-documented-function]
std::optional<ScalarValue> ConvertJsonValue(const JsonValue& value, const VariableInfo& variable) {
    if (value.IsArray()) {
        const JsonArray* items = value.AsArray();
        if (items == nullptr) {
            return std::nullopt;
        }
        switch (variable.type) {
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
            case ScalarType::kEnumeration:
                return DecodeIntegerArray(*items, variable);
            case ScalarType::kBoolean:
            case ScalarType::kClock: {
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
            case ScalarType::kBinary: {
                BinaryArray values;
                values.reserve(items->size());
                for (const auto& item : *items) {
                    if (!item.IsString()) {
                        return std::nullopt;
                    }
                    const auto decoded = scalar_value_codec::DecodeBase64(item.AsString());
                    if (!decoded.has_value()) {
                        return std::nullopt;
                    }
                    values.push_back(*decoded);
                }
                return ScalarValue(std::move(values));
            }
        }
    }

    switch (variable.type) {
        case ScalarType::kReal:
            if (value.IsNumber()) {
                return ScalarValue(value.AsNumber());
            }
            break;
        case ScalarType::kInteger:
        case ScalarType::kEnumeration:
            if (value.IsNumber() || value.IsString()) {
                ScalarValue normalized;
                if (BoundsForDeclaredType(variable.declared_type).unsigned_only) {
                    const auto parsed = ParseUnsignedInteger(value);
                    if (parsed.has_value() && TryNormalizeIntegerValue(variable, *parsed, &normalized)) {
                        return normalized;
                    }
                } else {
                    const auto parsed = ParseSignedInteger(value);
                    if (parsed.has_value() && TryNormalizeIntegerValue(variable, *parsed, &normalized)) {
                        return normalized;
                    }
                }
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
        case ScalarType::kBinary:
            if (value.IsString()) {
                const auto decoded = scalar_value_codec::DecodeBase64(value.AsString());
                if (decoded.has_value()) {
                    return ScalarValue(*decoded);
                }
            }
            break;
        case ScalarType::kClock:
            if (value.IsBool()) {
                return ScalarValue(value.AsBool());
            }
            if (value.IsNumber()) {
                return ScalarValue(value.AsNumber() != 0.0);
            }
            break;
    }
    return std::nullopt;
}

template <typename T>
bool TryCastStoredInteger(const VariableInfo& variable, const ScalarValue& stored_value, T* output) {
    if (output == nullptr) {
        return false;
    }

    const auto bounds = BoundsForDeclaredType(variable.declared_type);
    if (const auto* unsigned_value = std::get_if<std::uint64_t>(&stored_value)) {
        if (!bounds.unsigned_only || *unsigned_value > bounds.max) {
            return false;
        }
        if (*unsigned_value > static_cast<std::uint64_t>(std::numeric_limits<T>::max())) {
            return false;
        }
        *output = static_cast<T>(*unsigned_value);
        return true;
    }

    const auto* signed_value = std::get_if<std::int64_t>(&stored_value);
    if (signed_value == nullptr) {
        return false;
    }
    if (bounds.unsigned_only && *signed_value < 0) {
        return false;
    }
    if constexpr (std::is_unsigned_v<T>) {
        if (*signed_value < 0) {
            return false;
        }
        const auto value = static_cast<std::uint64_t>(*signed_value);
        if (value > bounds.max || value > static_cast<std::uint64_t>(std::numeric_limits<T>::max())) {
            return false;
        }
        *output = static_cast<T>(value);
        return true;
    } else {
        if (*signed_value < bounds.min) {
            return false;
        }
        if (*signed_value >= 0 && static_cast<std::uint64_t>(*signed_value) > bounds.max) {
            return false;
        }
        if (*signed_value < static_cast<std::int64_t>(std::numeric_limits<T>::min()) ||
            *signed_value > static_cast<std::int64_t>(std::numeric_limits<T>::max())) {
            return false;
        }
        *output = static_cast<T>(*signed_value);
        return true;
    }
}

std::optional<std::int32_t> ScalarValueToInt32(const ScalarValue& value) {
    if (const auto* integer = std::get_if<std::int64_t>(&value)) {
        if (*integer < std::numeric_limits<std::int32_t>::min() || *integer > std::numeric_limits<std::int32_t>::max()) {
            return std::nullopt;
        }
        return static_cast<std::int32_t>(*integer);
    }
    if (const auto* integer = std::get_if<std::uint64_t>(&value)) {
        if (*integer > static_cast<std::uint64_t>(std::numeric_limits<std::int32_t>::max())) {
            return std::nullopt;
        }
        return static_cast<std::int32_t>(*integer);
    }
    if (const auto* real = std::get_if<double>(&value)) {
        const auto rounded = std::llround(*real);
        if (rounded < std::numeric_limits<std::int32_t>::min() || rounded > std::numeric_limits<std::int32_t>::max()) {
            return std::nullopt;
        }
        return static_cast<std::int32_t>(rounded);
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
                    if (BoundsForDeclaredType(variable.declared_type).unsigned_only) {
                        cached_values_[variable.value_reference] = UnsignedIntegerArray(flat_size, static_cast<std::uint64_t>(0));
                    } else {
                        cached_values_[variable.value_reference] = IntegerArray(flat_size, static_cast<std::int64_t>(0));
                    }
                    break;
                case ScalarType::kBoolean:
                    cached_values_[variable.value_reference] = BooleanArray(flat_size, false);
                    break;
                case ScalarType::kString:
                    cached_values_[variable.value_reference] = StringArray(flat_size, std::string());
                    break;
                case ScalarType::kBinary:
                    cached_values_[variable.value_reference] = BinaryArray(flat_size, BinaryValue());
                    break;
                case ScalarType::kClock:
                    cached_values_[variable.value_reference] = BooleanArray(flat_size, false);
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
                if (BoundsForDeclaredType(variable.declared_type).unsigned_only) {
                    cached_values_[variable.value_reference] = static_cast<std::uint64_t>(0);
                } else {
                    cached_values_[variable.value_reference] = static_cast<std::int64_t>(0);
                }
                break;
            case ScalarType::kBoolean:
                cached_values_[variable.value_reference] = false;
                break;
            case ScalarType::kString:
                cached_values_[variable.value_reference] = std::string();
                break;
            case ScalarType::kBinary:
                cached_values_[variable.value_reference] = BinaryValue();
                break;
            case ScalarType::kClock:
                cached_values_[variable.value_reference] = false;
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
    std::size_t flat_size = 0;
    return TryResolveVariableFlatSize(variable, &flat_size) ? flat_size : 0;
}

bool ProxyRuntime::TryResolveVariableFlatSize(const VariableInfo& variable, std::size_t* flat_size) const {
    if (flat_size == nullptr) {
        return false;
    }
    if (variable.dimensions.empty()) {
        *flat_size = 1;
        return true;
    }
    std::size_t size = 1;
    for (const auto& dimension : variable.dimensions) {
        const auto extent = ResolveDimensionExtent(dimension);
        if (!extent.has_value() || *extent < 0) {
            return false;
        }
        const auto unsigned_extent = static_cast<std::size_t>(*extent);
        if (unsigned_extent != 0 && size > std::numeric_limits<std::size_t>::max() / unsigned_extent) {
            return false;
        }
        size *= unsigned_extent;
    }
    *flat_size = size;
    return true;
}

std::size_t ProxyRuntime::ExpectedValueCount(const std::uint32_t* value_references, const std::size_t count) const {
    std::size_t expected = 0;
    if (!TryExpectedValueCount(value_references, count, &expected)) {
        return 0;
    }
    return expected;
}

bool ProxyRuntime::TryExpectedValueCount(const std::uint32_t* value_references,
                                         const std::size_t count,
                                         std::size_t* expected_value_count) const {
    if (expected_value_count == nullptr || (count > 0 && value_references == nullptr)) {
        return false;
    }
    std::size_t expected = 0;
    for (std::size_t index = 0; index < count; ++index) {
        const VariableInfo* variable = FindVariableByValueReference(model_, value_references[index]);
        if (variable == nullptr) {
            return false;
        }
        std::size_t flat_size = 0;
        if (!TryResolveVariableFlatSize(*variable, &flat_size)
            || flat_size > std::numeric_limits<std::size_t>::max() - expected) {
            return false;
        }
        expected += flat_size;
    }
    *expected_value_count = expected;
    return true;
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
    if (!model.value.supports_co_simulation && !model.value.supports_model_exchange) {
        return OperationResult::Failure(
            "MODEL_DESCRIPTION_UNSUPPORTED",
            "The proxy declares no supported FMI simulation interface");
    }

    instance_name_ = instance_name;
    config_ = std::move(config.value);
    model_ = std::move(model.value);
    model_exchange_mode_ = false;
    model_exchange_external_solver_active_ = false;
    model_exchange_remote_mode_ = "instantiated";
    experiment_.start_time = model_.default_start_time.value_or(0.0);
    experiment_.stop_time = model_.default_stop_time;
    experiment_.step_size = model_.default_step_size.value_or(0.01);
    current_time_ = experiment_.start_time;
    configuration_mode_ = false;
    configuration_mode_initialization_ = false;
    last_step_early_return_ = false;
    last_step_event_handling_needed_ = false;
    last_step_terminated_ = false;
    simulation_finished_ = false;
    initialization_evaluated_ = false;
    initialization_evaluation_dirty_ = false;
    initialization_outputs_evaluated_ = false;
    gateway_client_ = std::make_unique<GatewayClient>(transport_factory_());
    SeedCacheFromModelDefaults();
    initial_inputs_.clear();
    pending_inputs_.clear();
    reconfiguration_values_.clear();
    string_cache_.clear();
    last_error_.clear();

    return Transition(SessionState::kInstantiated);
}

OperationResult ProxyRuntime::SetModelExchangeMode(const bool enabled) {
    if (state_ != SessionState::kInstantiated) {
        return OperationResult::Failure("STATE_ERROR", "FMI interface must be selected before initialization");
    }
    if (enabled && !model_.supports_model_exchange) {
        return OperationResult::Failure("MODEL_EXCHANGE_UNAVAILABLE", "The proxy does not declare Model Exchange");
    }
    if (!enabled && !model_.supports_co_simulation) {
        return OperationResult::Failure("CO_SIMULATION_UNAVAILABLE", "The proxy does not declare Co-Simulation");
    }
    model_exchange_mode_ = enabled;
    initialization_mode_entered_ = false;
    return OperationResult::Success();
}

bool ProxyRuntime::IsModelExchangeMode() const {
    return model_exchange_mode_;
}

ValueResult<JsonObject> ProxyRuntime::ModelExchangeCall(
    const std::string& operation,
    const JsonObject& arguments) {
    if (!model_exchange_mode_ || gateway_client_ == nullptr) {
        return ValueResult<JsonObject>::Failure(
            "MODEL_EXCHANGE_NOT_ACTIVE",
            "External Model Exchange execution is not active");
    }
    if (!model_exchange_external_solver_active_) {
        const bool initialization_read = operation == "getValues"
            || operation == "getContinuousStates"
            || operation == "getDerivatives"
            || operation == "getContinuousStateDerivatives"
            || operation == "getEventIndicators"
            || operation == "getNominalsOfContinuousStates";
        if (!initialization_read || state_ != SessionState::kSessionCreated || !initialization_mode_entered_) {
            return ValueResult<JsonObject>::Failure(
                "MODEL_EXCHANGE_NOT_ACTIVE",
                "External Model Exchange execution is not active");
        }
        const auto initialization_status = EvaluateInitialization();
        if (!initialization_status) {
            return ValueResult<JsonObject>::Failure(
                initialization_status.code,
                initialization_status.message);
        }
    }
    auto result = gateway_client_->ModelExchangeCall(operation, arguments);
    if (!result) {
        last_error_ = result.status.message;
        return result;
    }
    if (operation == "setTime") {
        const JsonValue* time_value = FindObjectValue(arguments, "time");
        if (time_value != nullptr && time_value->IsNumber()) {
            current_time_ = time_value->AsNumber();
        }
    } else if (operation == "exitInitializationMode" || operation == "enterEventMode") {
        model_exchange_remote_mode_ = "event";
        if (operation == "exitInitializationMode") {
            initialization_mode_entered_ = false;
            initialization_evaluated_ = true;
            initialization_evaluation_dirty_ = false;
        }
    } else if (operation == "enterContinuousTimeMode") {
        model_exchange_remote_mode_ = "continuous";
    }
    return result;
}

std::string ProxyRuntime::ModelExchangeValueType(const VariableInfo& variable) const {
    if (model_.fmi_version.rfind("2.", 0) == 0) {
        switch (variable.type) {
            case ScalarType::kReal: return "Real";
            case ScalarType::kInteger:
            case ScalarType::kEnumeration: return "Integer";
            case ScalarType::kBoolean: return "Boolean";
            case ScalarType::kString: return "String";
            case ScalarType::kBinary: return "Binary";
            case ScalarType::kClock: return "Clock";
        }
    }
    if (variable.type == ScalarType::kEnumeration) {
        return "Int64";
    }
    if (!variable.declared_type.empty()) {
        return variable.declared_type;
    }
    switch (variable.type) {
        case ScalarType::kReal: return "Float64";
        case ScalarType::kInteger: return "Int32";
        case ScalarType::kBoolean: return "Boolean";
        case ScalarType::kString: return "String";
        case ScalarType::kBinary: return "Binary";
        case ScalarType::kClock: return "Clock";
        case ScalarType::kEnumeration: return "Int64";
    }
    return {};
}

OperationResult ProxyRuntime::RefreshModelExchangeValues(
    const std::uint32_t* value_references,
    const std::size_t count,
    const ScalarType expected_type,
    const std::optional<std::size_t> value_count) {
    if (!model_exchange_external_solver_active_ || count == 0) {
        return OperationResult::Success();
    }
    if (value_references == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "Model Exchange read received null value references");
    }
    const std::size_t expected_values = value_count.value_or(count);
    std::size_t model_values = 0;
    if (!TryExpectedValueCount(value_references, count, &model_values) || model_values != expected_values) {
        return OperationResult::Failure("INVALID_ARGUMENT", "Model Exchange read size does not match the referenced variables");
    }

    std::vector<std::uint32_t> remote_references;
    remote_references.reserve(count);
    std::string value_type;
    std::size_t remote_value_count = 0;
    for (std::size_t index = 0; index < count; ++index) {
        const VariableInfo* variable = FindVariableByValueReference(model_, value_references[index]);
        if (variable == nullptr) {
            return OperationResult::Failure("UNKNOWN_VALUE_REFERENCE", "Unknown value reference");
        }
        if (variable->type != expected_type
            && !(expected_type == ScalarType::kInteger && variable->type == ScalarType::kEnumeration)) {
            return OperationResult::Failure("TYPE_MISMATCH", "Variable type does not match getter");
        }
        if (variable->causality == "independent") {
            continue;
        }
        const std::string current_type = ModelExchangeValueType(*variable);
        if (current_type.empty() || (!value_type.empty() && current_type != value_type)) {
            return OperationResult::Failure("TYPE_MISMATCH", "Model Exchange read contains incompatible FMI types");
        }
        value_type = current_type;
        const std::size_t flat_size = ResolveVariableFlatSize(*variable);
        if (flat_size > std::numeric_limits<std::size_t>::max() - remote_value_count) {
            return OperationResult::Failure("INVALID_ARGUMENT", "Model Exchange read size overflows");
        }
        remote_value_count += flat_size;
        remote_references.push_back(value_references[index]);
    }
    if (remote_references.empty()) {
        return OperationResult::Success();
    }

    JsonArray json_references;
    json_references.reserve(remote_references.size());
    for (const auto reference : remote_references) {
        json_references.emplace_back(static_cast<double>(reference));
    }
    const JsonObject arguments = {
        {"valueType", JsonValue(value_type)},
        {"valueReferences", JsonValue(std::move(json_references))},
    };
    const auto response = ModelExchangeCall("getValues", arguments);
    if (!response) {
        return response.status;
    }
    const JsonValue* raw_values = FindObjectValue(response.value, "values");
    const JsonArray* values = raw_values == nullptr ? nullptr : raw_values->AsArray();
    if (values == nullptr || values->size() != remote_value_count) {
        return OperationResult::Failure("GATEWAY_PROTOCOL_ERROR", "Gateway returned an invalid Model Exchange value count");
    }

    std::size_t offset = 0;
    for (const auto reference : remote_references) {
        const VariableInfo* variable = FindVariableByValueReference(model_, reference);
        if (variable == nullptr) {
            return OperationResult::Failure("UNKNOWN_VALUE_REFERENCE", "Unknown value reference");
        }
        const std::size_t flat_size = ResolveVariableFlatSize(*variable);
        JsonValue raw_value;
        if (flat_size == 1) {
            raw_value = (*values)[offset];
        } else {
            JsonArray items;
            items.reserve(flat_size);
            for (std::size_t element = 0; element < flat_size; ++element) {
                items.push_back((*values)[offset + element]);
            }
            raw_value = JsonValue(std::move(items));
        }
        const auto converted = ConvertJsonValue(raw_value, *variable);
        if (!converted.has_value()) {
            return OperationResult::Failure("GATEWAY_PROTOCOL_ERROR", "Gateway returned a value that does not match the FMI variable type");
        }
        cached_values_[reference] = *converted;
        offset += flat_size;
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::SetModelExchangeValue(const VariableInfo& variable, const ScalarValue& value) {
    if (!model_exchange_external_solver_active_ || gateway_client_ == nullptr) {
        return OperationResult::Failure("MODEL_EXCHANGE_NOT_ACTIVE", "External Model Exchange execution is not active");
    }
    if (model_exchange_remote_mode_ != "initialization"
        && model_exchange_remote_mode_ != "event"
        && model_exchange_remote_mode_ != "continuous") {
        return OperationResult::Failure("STATE_ERROR", "Model Exchange value writes are not allowed in the current mode");
    }
    JsonArray references{JsonValue(static_cast<double>(variable.value_reference))};
    JsonArray values;
    const JsonValue encoded = scalar_value_codec::EncodeJsonValue(value);
    if (const JsonArray* array = encoded.AsArray()) {
        values = *array;
    } else {
        values.push_back(encoded);
    }
    const JsonObject arguments = {
        {"valueType", JsonValue(ModelExchangeValueType(variable))},
        {"valueReferences", JsonValue(std::move(references))},
        {"values", JsonValue(std::move(values))},
    };
    const auto response = ModelExchangeCall("setValues", arguments);
    return response ? OperationResult::Success() : response.status;
}

OperationResult ProxyRuntime::EnterModelExchangeEventMode() {
    const auto response = ModelExchangeCall("enterEventMode");
    return response ? OperationResult::Success() : response.status;
}

OperationResult ProxyRuntime::EnterModelExchangeContinuousTimeMode() {
    const auto response = ModelExchangeCall("enterContinuousTimeMode");
    return response ? OperationResult::Success() : response.status;
}

OperationResult ProxyRuntime::SetupExperiment(
    const double start_time,
    const std::optional<double> stop_time,
    const double step_size) {
    experiment_.start_time = start_time;
    experiment_.stop_time = stop_time;
    experiment_.step_size = step_size;
    current_time_ = start_time;
    initialization_mode_entered_ = false;
    return OperationResult::Success();
}

OperationResult ProxyRuntime::EnterInitializationMode() {
    if (configuration_mode_) {
        return OperationResult::Failure("STATE_ERROR", "Exit Configuration Mode before initialization");
    }
    if (gateway_client_ == nullptr) {
        return OperationResult::Failure("RUNTIME_NOT_CONFIGURED", "Runtime is not configured");
    }
    auto status = Transition(SessionState::kSocketConnecting);
    if (!status) {
        return status;
    }
    if (gateway_client_->SessionId().empty()) {
        status = gateway_client_->CreateSession(config_);
        if (!status) {
            state_ = SessionState::kError;
            SetError(status.message);
            return status;
        }
    }
    status = Transition(SessionState::kSocketReady);
    if (!status) {
        return status;
    }
    status = Transition(SessionState::kSessionCreated);
    if (status) {
        initialization_mode_entered_ = true;
    }
    return status;
}

OperationResult ProxyRuntime::EnterConfigurationMode() {
    if (configuration_mode_) {
        return OperationResult::Failure("STATE_ERROR", "Runtime is already in Configuration Mode");
    }
    if (state_ == SessionState::kInstantiated) {
        if (!HasStructuralParameters()) {
            return OperationResult::Failure("STATE_ERROR", "The model has no structural parameters");
        }
        configuration_mode_initialization_ = true;
    } else if (state_ == SessionState::kInitialized || state_ == SessionState::kRunning) {
        if (!HasTunableStructuralParameters()) {
            return OperationResult::Failure("STATE_ERROR", "The model has no tunable structural parameters");
        }
        configuration_mode_initialization_ = false;
        reconfiguration_values_.clear();
    } else {
        return OperationResult::Failure("STATE_ERROR", "Configuration Mode is not available in the current state");
    }
    configuration_mode_ = true;
    return OperationResult::Success();
}

OperationResult ProxyRuntime::ExitConfigurationMode() {
    if (!configuration_mode_) {
        return OperationResult::Failure("STATE_ERROR", "Runtime is not in Configuration Mode");
    }
    if (!configuration_mode_initialization_ && !reconfiguration_values_.empty()) {
        if (gateway_client_ == nullptr) {
            return OperationResult::Failure("RUNTIME_NOT_CONFIGURED", "Runtime is not configured");
        }
        const auto status = gateway_client_->Reconfigure(reconfiguration_values_);
        if (!status) {
            SetError(status.message);
            return status;
        }
        std::vector<std::string> affected_output_names;
        for (const auto& [name, value] : reconfiguration_values_) {
            (void)value;
            const VariableInfo* variable = FindVariableByName(model_, name);
            if (variable != nullptr) {
                InvalidateArraysForStructuralParameter(*variable, false);
                for (const auto& candidate : model_.variables) {
                    const bool depends_on_parameter = std::any_of(
                        candidate.dimensions.begin(), candidate.dimensions.end(),
                        [variable](const DimensionInfo& dimension) {
                            return dimension.value_reference == variable->value_reference;
                        });
                    if (depends_on_parameter && candidate.causality == "output") {
                        affected_output_names.push_back(candidate.name);
                    }
                }
            }
        }
        if (!affected_output_names.empty()) {
            const auto outputs = gateway_client_->GetOutputs(affected_output_names);
            if (!outputs) {
                SetError(outputs.status.message);
                return outputs.status;
            }
            ApplyOutputSnapshot(outputs.value);
        }
    }
    configuration_mode_ = false;
    configuration_mode_initialization_ = false;
    reconfiguration_values_.clear();
    return OperationResult::Success();
}

bool ProxyRuntime::HasStructuralParameters() const {
    return std::any_of(model_.variables.begin(), model_.variables.end(), [](const VariableInfo& variable) {
        return variable.causality == "structuralParameter";
    });
}

bool ProxyRuntime::HasTunableStructuralParameters() const {
    return std::any_of(model_.variables.begin(), model_.variables.end(), [](const VariableInfo& variable) {
        return variable.causality == "structuralParameter" && variable.variability == "tunable";
    });
}

void ProxyRuntime::InvalidateArraysForStructuralParameter(
    const VariableInfo& structural_parameter,
    const bool initialization_configuration) {
    for (const auto& candidate : model_.variables) {
        const bool depends_on_parameter = std::any_of(
            candidate.dimensions.begin(), candidate.dimensions.end(),
            [&structural_parameter](const DimensionInfo& dimension) {
                return dimension.value_reference == structural_parameter.value_reference;
            });
        if (!depends_on_parameter) {
            continue;
        }
        cached_values_.erase(candidate.value_reference);
        std::size_t flat_size = 0;
        if (TryResolveVariableFlatSize(candidate, &flat_size) && flat_size == 0) {
            switch (candidate.type) {
                case ScalarType::kReal:
                    cached_values_[candidate.value_reference] = RealArray{};
                    break;
                case ScalarType::kInteger:
                case ScalarType::kEnumeration:
                    if (BoundsForDeclaredType(candidate.declared_type).unsigned_only) {
                        cached_values_[candidate.value_reference] = UnsignedIntegerArray{};
                    } else {
                        cached_values_[candidate.value_reference] = IntegerArray{};
                    }
                    break;
                case ScalarType::kBoolean:
                case ScalarType::kClock:
                    cached_values_[candidate.value_reference] = BooleanArray{};
                    break;
                case ScalarType::kString:
                    cached_values_[candidate.value_reference] = StringArray{};
                    break;
                case ScalarType::kBinary:
                    cached_values_[candidate.value_reference] = BinaryArray{};
                    break;
            }
        }
        pending_inputs_.erase(candidate.name);
        if (initialization_configuration) {
            initial_inputs_.erase(candidate.name);
        }
    }
}

OperationResult ProxyRuntime::ExitInitializationMode() {
    if (gateway_client_ == nullptr) {
        return OperationResult::Failure("RUNTIME_NOT_CONFIGURED", "Runtime is not configured");
    }
    if (state_ != SessionState::kSessionCreated) {
        return OperationResult::Failure("STATE_ERROR", "Runtime is not in session_created state");
    }

    const auto status = EvaluateInitialization();
    if (!status) {
        state_ = SessionState::kError;
        SetError(status.message);
        return status;
    }
    if (model_exchange_external_solver_active_) {
        const auto exit_status = ModelExchangeCall("exitInitializationMode");
        if (!exit_status) {
            state_ = SessionState::kError;
            SetError(exit_status.status.message);
            return exit_status.status;
        }
    } else {
        const auto exit_status = gateway_client_->ExitInitializationMode();
        if (!exit_status) {
            state_ = SessionState::kError;
            SetError(exit_status.message);
            return exit_status;
        }
    }
    pending_inputs_.clear();
    realtime_sim_origin_ = current_time_;
    realtime_wall_origin_ = std::chrono::steady_clock::now();
    realtime_clock_started_ = true;
    const auto transition = Transition(SessionState::kInitialized);
    if (transition) {
        initialization_mode_entered_ = false;
    }
    return transition;
}

OperationResult ProxyRuntime::EvaluateInitialization(const bool read_initial_outputs) {
    if (gateway_client_ == nullptr) {
        return OperationResult::Failure("RUNTIME_NOT_CONFIGURED", "Runtime is not configured");
    }
    if (state_ != SessionState::kSessionCreated) {
        return OperationResult::Failure("STATE_ERROR", "Initialization evaluation requires Initialization Mode");
    }
    if (initialization_evaluated_ && !initialization_evaluation_dirty_) {
        if (!read_initial_outputs || initialization_outputs_evaluated_ || model_exchange_mode_) {
            return OperationResult::Success();
        }
        std::vector<std::string> output_variables;
        for (const auto& variable : model_.variables) {
            if (variable.causality == "output") {
                output_variables.push_back(variable.name);
            }
        }
        const auto initial_outputs = gateway_client_->GetOutputs(output_variables);
        if (!initial_outputs) {
            return initial_outputs.status;
        }
        ApplyOutputSnapshot(initial_outputs.value);
        initialization_outputs_evaluated_ = true;
        return OperationResult::Success();
    }
    if (initialization_evaluated_) {
        const auto reset_status = gateway_client_->Reset();
        if (!reset_status) {
            return reset_status;
        }
        SeedCacheFromModelDefaults();
        initialization_outputs_evaluated_ = false;
        for (const auto& [name, value] : initial_inputs_) {
            const VariableInfo* variable = FindVariableByName(model_, name);
            if (variable != nullptr) {
                cached_values_[variable->value_reference] = value;
            }
        }
        current_time_ = experiment_.start_time;
    }

    std::map<std::string, ScalarValue> initialization_inputs;
    std::map<std::string, ScalarValue> initialization_parameters;
    for (const auto& [name, value] : initial_inputs_) {
        const VariableInfo* variable = FindVariableByName(model_, name);
        if (variable != nullptr && variable->causality == "input") {
            initialization_inputs.emplace(name, value);
        } else {
            initialization_parameters.emplace(name, value);
        }
    }

    const auto status = gateway_client_->Initialize(
        config_,
        experiment_,
        initialization_inputs,
        initialization_parameters,
        early_return_allowed_,
        model_exchange_mode_,
        true);
    if (!status) {
        return status;
    }
    model_exchange_external_solver_active_ = model_exchange_mode_;
    if (model_exchange_external_solver_active_) {
        model_exchange_remote_mode_ = "initialization";
    } else {
        model_exchange_remote_mode_ = "instantiated";
    }
    if (model_exchange_mode_) {
        initialization_evaluated_ = true;
        initialization_evaluation_dirty_ = false;
        initialization_outputs_evaluated_ = false;
        return OperationResult::Success();
    }

    initialization_evaluated_ = true;
    initialization_evaluation_dirty_ = false;
    initialization_outputs_evaluated_ = false;
    if (!read_initial_outputs) {
        return OperationResult::Success();
    }

    std::vector<std::string> output_variables;
    for (const auto& variable : model_.variables) {
        if (variable.causality == "output") {
            output_variables.push_back(variable.name);
        }
    }
    const auto initial_outputs = gateway_client_->GetOutputs(output_variables);
    if (!initial_outputs) {
        return initial_outputs.status;
    }
    ApplyOutputSnapshot(initial_outputs.value);
    initialization_evaluated_ = true;
    initialization_evaluation_dirty_ = false;
    initialization_outputs_evaluated_ = true;
    return OperationResult::Success();
}

OperationResult ProxyRuntime::EvaluateInitializationForValues(
    const std::uint32_t* value_references,
    const std::size_t count,
    const std::optional<std::size_t> value_count) {
    if (state_ != SessionState::kSessionCreated || count == 0 || value_references == nullptr) {
        return OperationResult::Success();
    }
    std::size_t expected_count = 0;
    if (!TryExpectedValueCount(value_references, count, &expected_count)
        || expected_count != value_count.value_or(count)) {
        return OperationResult::Success();
    }
    bool requests_output = false;
    for (std::size_t index = 0; index < count; ++index) {
        const VariableInfo* variable = FindVariableByValueReference(model_, value_references[index]);
        if (variable == nullptr) {
            return OperationResult::Success();
        }
        requests_output = requests_output || variable->causality == "output";
    }
    return (model_exchange_mode_ || requests_output) ? EvaluateInitialization() : OperationResult::Success();
}

void ProxyRuntime::SetEarlyReturnAllowed(const bool allowed) {
    early_return_allowed_ = allowed;
}

OperationResult ProxyRuntime::ApplyOutputSnapshot(const OutputSnapshot& snapshot) {
    current_time_ = snapshot.sim_time;
    for (const auto& [name, json_value] : snapshot.values) {
        const VariableInfo* variable = FindVariableByName(model_, name);
        if (variable == nullptr) {
            continue;
        }
        const auto converted = ConvertJsonValue(json_value, *variable);
        if (!converted.has_value()) {
            continue;
        }
        cached_values_[variable->value_reference] = *converted;
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::UpdateDiscreteStates(bool* terminate_simulation,
                                                   bool* next_event_time_defined,
                                                   double* next_event_time,
                                                   bool* discrete_states_need_update,
                                                   bool* nominals_changed,
                                                   bool* continuous_states_changed) {
    if (gateway_client_ == nullptr || !gateway_client_->IsConnected()) {
        return OperationResult::Failure("RUNTIME_NOT_CONNECTED", "Discrete-state update requires an active Gateway session");
    }
    if (state_ != SessionState::kInitialized && state_ != SessionState::kRunning) {
        return OperationResult::Failure("STATE_ERROR", "Discrete-state update requires an initialized simulation");
    }
    if (model_exchange_mode_) {
        const std::string operation = model_.fmi_version.rfind("3.", 0) == 0
            ? "updateDiscreteStates"
            : "newDiscreteStates";
        const auto response = ModelExchangeCall(operation);
        if (!response) {
            SetError(response.status.message);
            return response.status;
        }
        const JsonObject& fields = response.value;
        const bool needs_update = JsonBool(fields, "discreteStatesNeedUpdate");
        const bool terminated = JsonBool(fields, "terminateSimulation");
        const bool nominal_update = JsonBool(fields, "nominalsOfContinuousStatesChanged");
        const bool state_update = JsonBool(fields, "valuesOfContinuousStatesChanged");
        const bool next_defined = JsonBool(fields, "nextEventTimeDefined");
        const JsonValue* next_value = FindObjectValue(fields, "nextEventTime");
        if (next_defined && (next_value == nullptr || !next_value->IsNumber() || !std::isfinite(next_value->AsNumber()))) {
            return OperationResult::Failure("GATEWAY_PROTOCOL_ERROR", "Gateway omitted the next Model Exchange event time");
        }
        if (terminate_simulation != nullptr) *terminate_simulation = terminated;
        if (next_event_time_defined != nullptr) *next_event_time_defined = next_defined;
        if (next_event_time != nullptr) *next_event_time = next_defined ? next_value->AsNumber() : 0.0;
        if (discrete_states_need_update != nullptr) *discrete_states_need_update = needs_update;
        if (nominals_changed != nullptr) *nominals_changed = nominal_update;
        if (continuous_states_changed != nullptr) *continuous_states_changed = state_update;
        simulation_finished_ = terminated;
        last_step_terminated_ = terminated;
        return OperationResult::Success();
    }
    bool terminated = false;
    const auto input_status = gateway_client_->SetInputs(pending_inputs_, &terminated);
    if (!input_status) {
        SetError(input_status.message);
        return input_status;
    }
    pending_inputs_.clear();

    std::vector<std::string> output_variables;
    for (const auto& variable : model_.variables) {
        if (variable.causality == "output") {
            output_variables.push_back(variable.name);
        }
    }
    const auto outputs = gateway_client_->GetOutputs(output_variables);
    if (!outputs) {
        SetError(outputs.status.message);
        return outputs.status;
    }
    ApplyOutputSnapshot(outputs.value);
    last_step_event_handling_needed_ = false;
    last_step_terminated_ = terminated;
    simulation_finished_ = terminated;
    if (next_event_time_defined != nullptr) {
        *next_event_time_defined = outputs.value.next_event_time_defined;
    }
    if (next_event_time != nullptr) {
        *next_event_time = outputs.value.next_event_time.value_or(0.0);
    }
    if (terminate_simulation != nullptr) {
        *terminate_simulation = terminated;
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::DoStep(const double current_time, const double step_size) {
    if (model_exchange_mode_) {
        return OperationResult::Failure("MODEL_EXCHANGE_DO_STEP_UNAVAILABLE", "DoStep is not part of the Model Exchange interface");
    }
    if (gateway_client_ == nullptr) {
        return OperationResult::Failure("RUNTIME_NOT_CONFIGURED", "Runtime is not configured");
    }
    if (state_ != SessionState::kInitialized && state_ != SessionState::kRunning) {
        return OperationResult::Failure("STATE_ERROR", "Runtime is not initialized");
    }
    if (!std::isfinite(current_time) || !std::isfinite(step_size) || step_size <= 0.0) {
        return OperationResult::Failure("INVALID_STEP", "Step time and size must be finite and step size positive");
    }
    last_error_.clear();
    const double time_tolerance = std::max(1e-12, std::abs(current_time_) * 1e-12);
    if (std::abs(current_time - current_time_) > time_tolerance) {
        return OperationResult::Failure("INVALID_STEP", "Current communication point does not match simulation time");
    }
    last_step_early_return_ = false;
    last_step_event_handling_needed_ = false;
    last_step_terminated_ = false;
    // Use the last time confirmed by the Gateway as the communication point after
    // accepting an importer timestamp within FMI's floating-point comparison tolerance.
    const double effective_current_time = current_time_;
    const double requested_time = effective_current_time + step_size;
    constexpr double kMinimumExecutorAdvance = 1e-15;
    if (requested_time <= effective_current_time + kMinimumExecutorAdvance) {
        return OperationResult::Failure(
            "NO_ADVANCE",
            "Requested communication step does not advance beyond the current simulation time");
    }
    if (simulation_finished_) {
        return OperationResult::Failure("STATE_ERROR", "Simulation has finished");
    }
    const double stop_tolerance = experiment_.stop_time.has_value()
        ? std::max(1e-12, std::abs(*experiment_.stop_time) * 1e-12)
        : 0.0;
    if (!std::isfinite(requested_time)
        || (experiment_.stop_time.has_value() && requested_time > *experiment_.stop_time + stop_tolerance)) {
        return OperationResult::Failure("INVALID_STEP", "Step would advance past stopTime");
    }

    const auto snapshot = gateway_client_->Advance(effective_current_time, step_size, pending_inputs_);
    if (!snapshot) {
        if (snapshot.status.code == "INPUT_UPDATE_RATE_LIMIT"
            || snapshot.status.code == "OUTPUT_READ_RATE_LIMITED") {
            last_error_ = snapshot.status.message;
            return snapshot.status;
        }
        state_ = SessionState::kError;
        SetError(snapshot.status.message);
        return snapshot.status;
    }
    pending_inputs_.clear();
    auto status = ApplyOutputSnapshot(snapshot.value);
    if (!status) {
        return status;
    }
    last_step_early_return_ = snapshot.value.early_return;
    last_step_event_handling_needed_ = snapshot.value.event_handling_needed;
    for (const auto& variable : model_.variables) {
        if (variable.type != ScalarType::kClock || variable.causality != "output") {
            continue;
        }
        const ScalarValue* value = GetCachedValue(variable.value_reference);
        const auto* active = value == nullptr ? nullptr : std::get_if<bool>(value);
        if (active != nullptr && *active) {
            last_step_event_handling_needed_ = true;
            break;
        }
    }
    last_step_terminated_ = snapshot.value.terminate_simulation;
    simulation_finished_ = snapshot.value.finished;
    if (last_step_early_return_ && !early_return_allowed_) {
        return OperationResult::Failure("UNNEGOTIATED_EARLY_RETURN", "FMU returned early without permission");
    }
    if (state_ == SessionState::kInitialized) {
        status = Transition(SessionState::kRunning);
        if (!status) {
            return status;
        }
    }
    if (config_.time_mode == TimeMode::kRealtime && realtime_clock_started_) {
        const auto simulated_elapsed = std::chrono::duration<double>(
            (current_time_ - realtime_sim_origin_) / config_.playback_speed);
        const auto target = realtime_wall_origin_
            + std::chrono::duration_cast<std::chrono::steady_clock::duration>(simulated_elapsed);
        std::this_thread::sleep_until(target);
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
    initial_inputs_.clear();
    pending_inputs_.clear();
    current_time_ = experiment_.start_time;
    last_step_early_return_ = false;
    last_step_event_handling_needed_ = false;
    last_step_terminated_ = false;
    simulation_finished_ = false;
    configuration_mode_ = false;
    configuration_mode_initialization_ = false;
    realtime_clock_started_ = false;
    initialization_evaluated_ = false;
    initialization_evaluation_dirty_ = false;
    initialization_outputs_evaluated_ = false;
    model_exchange_external_solver_active_ = false;
    model_exchange_remote_mode_ = "instantiated";
    reconfiguration_values_.clear();
    state_ = SessionState::kInstantiated;
    return OperationResult::Success();
}

OperationResult ProxyRuntime::CaptureFmuState(std::string& serialized_state) {
    if (gateway_client_ == nullptr || !gateway_client_->IsConnected()) {
        return OperationResult::Failure("RUNTIME_NOT_CONNECTED", "FMU state capture requires an active Gateway session");
    }
    if (state_ == SessionState::kSessionCreated && initialization_mode_entered_) {
        const auto initialization_status = EvaluateInitialization(false);
        if (!initialization_status) {
            SetError(initialization_status.message);
            return initialization_status;
        }
    }
    const bool initialization_state = state_ == SessionState::kSessionCreated
        && initialization_mode_entered_ && initialization_evaluated_;
    if (state_ != SessionState::kInitialized && state_ != SessionState::kRunning && !initialization_state) {
        return OperationResult::Failure("STATE_ERROR", "FMU state capture requires an initialized simulation");
    }
    if (configuration_mode_) {
        return OperationResult::Failure("STATE_ERROR", "FMU state capture is unavailable in Configuration Mode");
    }
    const auto checkpoint = gateway_client_->CaptureFmuState();
    if (!checkpoint) {
        SetError(checkpoint.status.message);
        return checkpoint.status;
    }
    const JsonValue* remote_checkpoint_value = FindObjectValue(checkpoint.value, "checkpoint");
    const JsonObject* remote_checkpoint = remote_checkpoint_value == nullptr
        ? nullptr
        : remote_checkpoint_value->AsObject();
    if (remote_checkpoint == nullptr) {
        return OperationResult::Failure("GATEWAY_PROTOCOL_ERROR", "Gateway returned an invalid FMU checkpoint");
    }
    std::map<std::string, ScalarValue> cached_by_name;
    for (const auto& [reference, value] : cached_values_) {
        const VariableInfo* variable = FindVariableByValueReference(model_, reference);
        if (variable != nullptr) {
            cached_by_name.emplace(variable->name, value);
        }
    }
    JsonObject state = {
        {"version", JsonValue(2)},
        {"checkpoint", JsonValue(*remote_checkpoint)},
        {"currentTime", JsonValue(current_time_)},
        {"running", JsonValue(state_ == SessionState::kRunning)},
        {"simulationFinished", JsonValue(simulation_finished_)},
        {"lastStepEarlyReturn", JsonValue(last_step_early_return_)},
        {"lastStepEventHandlingNeeded", JsonValue(last_step_event_handling_needed_)},
        {"lastStepTerminated", JsonValue(last_step_terminated_)},
        {"initialInputs", JsonValue(scalar_value_codec::EncodeJsonObject(initial_inputs_))},
        {"pendingInputs", JsonValue(scalar_value_codec::EncodeJsonObject(pending_inputs_))},
        {"cachedValues", JsonValue(scalar_value_codec::EncodeJsonObject(cached_by_name))},
        {"initializationMode", JsonValue(initialization_state)},
        {"modelExchangeRemoteMode", JsonValue(model_exchange_external_solver_active_ ? model_exchange_remote_mode_ : "")},
    };
    serialized_state = SerializeJson(JsonValue(std::move(state)));
    return OperationResult::Success();
}

OperationResult ProxyRuntime::RestoreFmuState(const std::string& serialized_state) {
    if (gateway_client_ == nullptr || !gateway_client_->IsConnected()) {
        return OperationResult::Failure("RUNTIME_NOT_CONNECTED", "FMU state restore requires an active Gateway session");
    }
    if (state_ == SessionState::kSessionCreated && initialization_mode_entered_) {
        const auto initialization_status = EvaluateInitialization(false);
        if (!initialization_status) {
            SetError(initialization_status.message);
            return initialization_status;
        }
    }
    const bool initialization_state = state_ == SessionState::kSessionCreated
        && initialization_mode_entered_ && initialization_evaluated_;
    if (state_ != SessionState::kInitialized && state_ != SessionState::kRunning && !initialization_state) {
        return OperationResult::Failure("STATE_ERROR", "FMU state restore requires an initialized simulation");
    }
    const auto parsed = ParseJson(serialized_state);
    if (!parsed || parsed.value.AsObject() == nullptr) {
        return OperationResult::Failure("INVALID_FMU_STATE", "Serialized FMU state is invalid");
    }
    const JsonObject* serialized_object = parsed.value.AsObject();
    const JsonValue* version = FindObjectValue(*serialized_object, "version");
    const JsonValue* checkpoint_value = FindObjectValue(*serialized_object, "checkpoint");
    const JsonObject* checkpoint = checkpoint_value == nullptr ? nullptr : checkpoint_value->AsObject();
    const JsonValue* time_value = FindObjectValue(*serialized_object, "currentTime");
    const JsonValue* running_value = FindObjectValue(*serialized_object, "running");
    const JsonValue* finished_value = FindObjectValue(*serialized_object, "simulationFinished");
    const JsonValue* early_return_value = FindObjectValue(*serialized_object, "lastStepEarlyReturn");
    const JsonValue* event_needed_value = FindObjectValue(*serialized_object, "lastStepEventHandlingNeeded");
    const JsonValue* terminated_value = FindObjectValue(*serialized_object, "lastStepTerminated");
    const JsonValue* initialization_mode_value = FindObjectValue(*serialized_object, "initializationMode");
    const JsonValue* model_exchange_remote_mode_value = FindObjectValue(*serialized_object, "modelExchangeRemoteMode");
    if (version == nullptr || !version->IsNumber() || version->AsNumber() != 2.0
        || checkpoint == nullptr || time_value == nullptr || !time_value->IsNumber()
        || running_value == nullptr || !running_value->IsBool()
        || finished_value == nullptr || !finished_value->IsBool()
        || early_return_value == nullptr || !early_return_value->IsBool()
        || event_needed_value == nullptr || !event_needed_value->IsBool()
        || terminated_value == nullptr || !terminated_value->IsBool()) {
        return OperationResult::Failure("INVALID_FMU_STATE", "Serialized FMU state is incomplete");
    }
    if ((initialization_mode_value != nullptr && !initialization_mode_value->IsBool())
        || (model_exchange_remote_mode_value != nullptr
            && (!model_exchange_remote_mode_value->IsString()
                || (model_exchange_remote_mode_value->AsString() != ""
                    && model_exchange_remote_mode_value->AsString() != "instantiated"
                    && model_exchange_remote_mode_value->AsString() != "initialization"
                    && model_exchange_remote_mode_value->AsString() != "event"
                    && model_exchange_remote_mode_value->AsString() != "continuous")))) {
        return OperationResult::Failure("INVALID_FMU_STATE", "Serialized FMU Model Exchange phase is invalid");
    }
    const bool restore_initialization_mode =
        initialization_mode_value != nullptr && initialization_mode_value->AsBool();
    const std::string serialized_model_exchange_remote_mode =
        model_exchange_remote_mode_value == nullptr ? "" : model_exchange_remote_mode_value->AsString();
    if (restore_initialization_mode
        && ((model_exchange_mode_
             && (!model_exchange_external_solver_active_
                 || serialized_model_exchange_remote_mode != "initialization"))
            || (!model_exchange_mode_ && !serialized_model_exchange_remote_mode.empty()))) {
        return OperationResult::Failure("INVALID_FMU_STATE", "Serialized FMU state does not match the active initialization phase");
    }
    const double serialized_time = time_value->AsNumber();
    if (!std::isfinite(serialized_time)) {
        return OperationResult::Failure("INVALID_FMU_STATE", "Serialized FMU time is invalid");
    }
    auto decode_values = [this, serialized_object](const char* field,
                                                    std::map<std::string, ScalarValue>* output) {
        if (output == nullptr) {
            return false;
        }
        const JsonValue* value = FindObjectValue(*serialized_object, field);
        const JsonObject* object = value == nullptr ? nullptr : value->AsObject();
        if (object == nullptr) {
            return false;
        }
        output->clear();
        for (const auto& [name, item] : *object) {
            const VariableInfo* variable = FindVariableByName(model_, name);
            if (variable == nullptr) {
                return false;
            }
            const auto converted = ConvertJsonValue(item, *variable);
            if (!converted.has_value()) {
                return false;
            }
            output->emplace(name, *converted);
        }
        return true;
    };
    std::map<std::string, ScalarValue> initial_inputs;
    std::map<std::string, ScalarValue> pending_inputs;
    std::map<std::string, ScalarValue> cached_by_name;
    if (!decode_values("initialInputs", &initial_inputs)
        || !decode_values("pendingInputs", &pending_inputs)
        || !decode_values("cachedValues", &cached_by_name)) {
        return OperationResult::Failure("INVALID_FMU_STATE", "Serialized FMU proxy values are invalid");
    }
    std::vector<std::string> output_variables;
    output_variables.reserve(512);
    for (const auto& variable : model_.variables) {
        if (variable.causality == "output" && output_variables.size() < 512) {
            output_variables.push_back(variable.name);
        }
    }
    const auto restored = gateway_client_->RestoreFmuState(*checkpoint, output_variables);
    if (!restored) {
        SetError(restored.status.message);
        return restored.status;
    }
    const double time_tolerance = std::max(1e-12, std::abs(serialized_time) * 1e-12);
    if (!std::isfinite(restored.value.sim_time)
        || std::abs(restored.value.sim_time - serialized_time) > time_tolerance) {
        return OperationResult::Failure("INVALID_FMU_STATE", "Gateway restored a different simulation time");
    }
    current_time_ = restored.value.sim_time;
    simulation_finished_ = finished_value->AsBool();
    last_step_early_return_ = early_return_value->AsBool();
    last_step_event_handling_needed_ = event_needed_value->AsBool();
    last_step_terminated_ = terminated_value->AsBool();
    initial_inputs_ = std::move(initial_inputs);
    pending_inputs_ = std::move(pending_inputs);
    cached_values_.clear();
    SeedCacheFromModelDefaults();
    OutputSnapshot output_snapshot;
    output_snapshot.sim_time = restored.value.sim_time;
    output_snapshot.values = restored.value.values;
    ApplyOutputSnapshot(output_snapshot);
    for (const auto& [name, value] : cached_by_name) {
        const VariableInfo* variable = FindVariableByName(model_, name);
        if (variable != nullptr) {
            cached_values_[variable->value_reference] = value;
        }
    }
    if (restore_initialization_mode) {
        state_ = SessionState::kSessionCreated;
        initialization_mode_entered_ = true;
        initialization_evaluated_ = true;
        initialization_evaluation_dirty_ = false;
        initialization_outputs_evaluated_ = false;
        model_exchange_external_solver_active_ = model_exchange_mode_;
        model_exchange_remote_mode_ = model_exchange_mode_ ? "initialization" : "instantiated";
        initialization_mode_entered_ = true;
    } else {
        state_ = running_value->AsBool() ? SessionState::kRunning : SessionState::kInitialized;
        initialization_mode_entered_ = false;
        initialization_evaluated_ = true;
        initialization_evaluation_dirty_ = false;
        initialization_outputs_evaluated_ = true;
        if (model_exchange_mode_ && model_exchange_external_solver_active_
            && !serialized_model_exchange_remote_mode.empty()) {
            model_exchange_remote_mode_ = serialized_model_exchange_remote_mode;
        }
    }
    configuration_mode_ = false;
    configuration_mode_initialization_ = false;
    reconfiguration_values_.clear();
    realtime_sim_origin_ = current_time_;
    realtime_wall_origin_ = std::chrono::steady_clock::now();
    realtime_clock_started_ = true;
    return OperationResult::Success();
}

OperationResult ProxyRuntime::SetValue(const VariableInfo& variable, ScalarValue value) {
    const bool initialization_state =
        state_ == SessionState::kInstantiated || state_ == SessionState::kSessionCreated;
    const bool runtime_state = state_ == SessionState::kInitialized || state_ == SessionState::kRunning;
    const bool is_continuous_state = model_exchange_mode_
        && std::find(model_.continuous_state_value_references.begin(),
                     model_.continuous_state_value_references.end(),
                     variable.value_reference) != model_.continuous_state_value_references.end();
    const bool fmi3 = model_.fmi_version.rfind("3.", 0) == 0;
    const bool fmi2 = model_.fmi_version.rfind("2.", 0) == 0;
    const bool writable_initial_state = is_continuous_state
        && ((fmi3 && (variable.initial == "exact"
                      || (!initialization_mode_entered_ && variable.initial == "approx")))
            || (fmi2 && (variable.initial == "exact"
                         || (!initialization_mode_entered_ && variable.initial == "approx"))));
    const bool external_model_exchange_value = model_exchange_external_solver_active_
        && (initialization_state || runtime_state)
        && !configuration_mode_
        && variable.causality != "structuralParameter"
        && variable.causality != "independent";
    if (external_model_exchange_value) {
        const bool state_settable =
            (fmi2 && model_exchange_remote_mode_ == "initialization"
             && initialization_mode_entered_ && variable.initial == "exact")
            || (fmi3 && model_exchange_remote_mode_ == "initialization"
                && initialization_mode_entered_ && variable.initial == "exact")
            || (fmi3 && model_exchange_remote_mode_ == "continuous")
            || (fmi3 && model_exchange_remote_mode_ == "event" && variable.reinit == false);
        if (is_continuous_state && !state_settable) {
            return OperationResult::Failure(
                "VARIABLE_NOT_SETTABLE",
                "Continuous states cannot be set in the current FMI Model Exchange mode");
        }
        const auto status = SetModelExchangeValue(variable, value);
        if (!status) {
            SetError(status.message);
            return status;
        }
        cached_values_[variable.value_reference] = std::move(value);
        return OperationResult::Success();
    }
    const bool writable_input = variable.causality == "input"
        && (initialization_state || runtime_state)
        && !configuration_mode_;
    const bool writable_parameter = variable.causality == "parameter"
        && !configuration_mode_
        && ((initialization_state && variable.variability != "constant")
            || (runtime_state && variable.variability == "tunable"));
    const bool writable_structural_parameter = variable.causality == "structuralParameter"
        && (variable.variability == "fixed" || variable.variability == "tunable")
        && configuration_mode_
        && ((initialization_state && configuration_mode_initialization_)
            || (runtime_state && !configuration_mode_initialization_ && variable.variability == "tunable"))
        && model_.fmi_version.rfind("3.", 0) == 0;
    if (!writable_input && !writable_parameter && !writable_structural_parameter && !writable_initial_state) {
        return OperationResult::Failure(
            "VARIABLE_NOT_SETTABLE",
            "Variable is not settable in the current FMI mode");
    }
    if (simulation_finished_) {
        return OperationResult::Failure("SIMULATION_FINISHED", "Simulation has finished");
    }
    if (state_ == SessionState::kSessionCreated) {
        initialization_evaluation_dirty_ = true;
    }
    if (writable_structural_parameter) {
        const bool defines_array_dimension = std::any_of(
                model_.variables.begin(), model_.variables.end(), [&variable](const VariableInfo& candidate) {
                    return std::any_of(candidate.dimensions.begin(), candidate.dimensions.end(), [&variable](const DimensionInfo& dimension) {
                        return dimension.value_reference == variable.value_reference;
                    });
                });
        if (defines_array_dimension) {
            const auto* unsigned_value = std::get_if<std::uint64_t>(&value);
            if (variable.declared_type != "UInt64" || unsigned_value == nullptr) {
                return OperationResult::Failure("TYPE_MISMATCH", "A structural dimension must be a scalar UInt64");
            }
            if ((configuration_mode_initialization_ && *unsigned_value == 0) ||
                *unsigned_value > static_cast<std::uint64_t>(std::numeric_limits<std::int32_t>::max())) {
                return OperationResult::Failure(
                    "INVALID_DIMENSION",
                    configuration_mode_initialization_
                        ? "Initial structural array dimensions must fit a positive 32-bit extent"
                        : "Reconfigured structural array dimensions must fit a non-negative 32-bit extent");
            }
        }
    }
    if (initialization_state && !writable_structural_parameter && variable.start_value.has_value()
        && *variable.start_value == value) {
        cached_values_[variable.value_reference] = std::move(value);
        initial_inputs_.erase(variable.name);
        pending_inputs_.erase(variable.name);
        return OperationResult::Success();
    }

    const auto cached = cached_values_.find(variable.value_reference);
    if (runtime_state && variable.type != ScalarType::kClock
        && cached != cached_values_.end() && cached->second == value) {
        return OperationResult::Success();
    }
    cached_values_[variable.value_reference] = value;
    if (writable_structural_parameter && runtime_state) {
        reconfiguration_values_[variable.name] = std::move(value);
        return OperationResult::Success();
    }
    if (writable_structural_parameter) {
        InvalidateArraysForStructuralParameter(variable, true);
    }
    if (initialization_state) {
        initial_inputs_[variable.name] = value;
    }
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
                                               const std::optional<std::size_t> value_count,
                                               const ScalarType expected_type) {
    if (count > 0 && value_references == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "Set values received null buffers");
    }
    const std::size_t expected_count = value_count.value_or(count);
    std::size_t model_value_count = 0;
    if (!TryExpectedValueCount(value_references, count, &model_value_count) || model_value_count != expected_count) {
        return OperationResult::Failure("INVALID_ARGUMENT", "Set values buffer length does not match referenced FMI variables");
    }
    if (expected_count > 0 && values == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "Set values received null buffers");
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
        std::size_t flat_size = 0;
        if (!TryResolveVariableFlatSize(*variable, &flat_size) || offset + flat_size > expected_count) {
            return OperationResult::Failure("INVALID_ARGUMENT", "Set values buffer is too short for referenced FMI variables");
        }
        if (flat_size == 1) {
            if (expected_type == ScalarType::kReal) {
                const auto status = SetValue(*variable, static_cast<double>(values[offset]));
                if (!status) {
                    return status;
                }
            } else {
                ScalarValue normalized;
                if (!TryNormalizeIntegerValue(*variable, values[offset], &normalized)) {
                    return OperationResult::Failure("TYPE_MISMATCH", "Integer value is outside the supported range for the FMI variable");
                }
                const auto status = SetValue(*variable, normalized);
                if (!status) {
                    return status;
                }
            }
        } else if (expected_type == ScalarType::kReal) {
            RealArray buffer;
            buffer.reserve(flat_size);
            for (std::size_t element = 0; element < flat_size; ++element) {
                buffer.push_back(static_cast<double>(values[offset + element]));
            }
            const auto status = SetValue(*variable, std::move(buffer));
            if (!status) {
                return status;
            }
        } else {
            if (BoundsForDeclaredType(variable->declared_type).unsigned_only) {
                UnsignedIntegerArray buffer;
                buffer.reserve(flat_size);
                for (std::size_t element = 0; element < flat_size; ++element) {
                    ScalarValue normalized;
                    if (!TryNormalizeIntegerValue(*variable, values[offset + element], &normalized)) {
                        return OperationResult::Failure("TYPE_MISMATCH", "Integer value is outside the supported range for the FMI variable");
                    }
                    const auto* integer = std::get_if<std::uint64_t>(&normalized);
                    if (integer == nullptr) {
                        return OperationResult::Failure("TYPE_MISMATCH", "Integer value could not be normalized as UInt64");
                    }
                    buffer.push_back(*integer);
                }
                const auto status = SetValue(*variable, std::move(buffer));
                if (!status) {
                    return status;
                }
            } else {
                IntegerArray buffer;
                buffer.reserve(flat_size);
                for (std::size_t element = 0; element < flat_size; ++element) {
                    ScalarValue normalized;
                    if (!TryNormalizeIntegerValue(*variable, values[offset + element], &normalized)) {
                        return OperationResult::Failure("TYPE_MISMATCH", "Integer value is outside the supported range for the FMI variable");
                    }
                    const auto* integer = std::get_if<std::int64_t>(&normalized);
                    if (integer == nullptr) {
                        return OperationResult::Failure("TYPE_MISMATCH", "Integer value could not be normalized as Int64");
                    }
                    buffer.push_back(*integer);
                }
                const auto status = SetValue(*variable, std::move(buffer));
                if (!status) {
                    return status;
                }
            }
        }
        offset += flat_size;
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::SetReal(const std::uint32_t* value_references,
                                      const std::size_t count,
                                      const double* values,
                                      const std::optional<std::size_t> value_count) {
    return SetNumericValues(value_references, count, values, value_count, ScalarType::kReal);
}

OperationResult ProxyRuntime::SetInteger(const std::uint32_t* value_references,
                                         const std::size_t count,
                                         const std::int32_t* values,
                                         const std::optional<std::size_t> value_count) {
    return SetNumericValues(value_references, count, values, value_count, ScalarType::kInteger);
}

OperationResult ProxyRuntime::SetSignedInteger(const std::uint32_t* value_references,
                                               const std::size_t count,
                                               const std::int64_t* values,
                                               const std::optional<std::size_t> value_count) {
    return SetNumericValues(value_references, count, values, value_count, ScalarType::kInteger);
}

OperationResult ProxyRuntime::SetUnsignedInteger(const std::uint32_t* value_references,
                                                 const std::size_t count,
                                                 const std::uint64_t* values,
                                                 const std::optional<std::size_t> value_count) {
    return SetNumericValues(value_references, count, values, value_count, ScalarType::kInteger);
}

OperationResult ProxyRuntime::SetBoolean(const std::uint32_t* value_references,
                                         const std::size_t count,
                                         const bool* values,
                                         const std::optional<std::size_t> value_count) {
    if (count > 0 && value_references == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "SetBoolean received null buffers");
    }
    const std::size_t expected_count = value_count.value_or(count);
    std::size_t model_value_count = 0;
    if (!TryExpectedValueCount(value_references, count, &model_value_count) || model_value_count != expected_count) {
        return OperationResult::Failure("INVALID_ARGUMENT", "SetBoolean buffer length does not match referenced FMI variables");
    }
    if (expected_count > 0 && values == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "SetBoolean received null buffers");
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
        std::size_t flat_size = 0;
        if (!TryResolveVariableFlatSize(*variable, &flat_size) || offset + flat_size > expected_count) {
            return OperationResult::Failure("INVALID_ARGUMENT", "SetBoolean buffer length does not match referenced FMI variables");
        }
        if (flat_size == 1) {
            const auto status = SetValue(*variable, values[offset]);
            if (!status) {
                return status;
            }
        } else {
            BooleanArray buffer;
            buffer.reserve(flat_size);
            for (std::size_t element = 0; element < flat_size; ++element) {
                buffer.push_back(values[offset + element]);
            }
            const auto status = SetValue(*variable, std::move(buffer));
            if (!status) {
                return status;
            }
        }
        offset += flat_size;
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::SetString(const std::uint32_t* value_references,
                                        const std::size_t count,
                                        const char* const* values,
                                        const std::optional<std::size_t> value_count) {
    if (count > 0 && value_references == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "SetString received null buffers");
    }
    const std::size_t expected_count = value_count.value_or(count);
    std::size_t model_value_count = 0;
    if (!TryExpectedValueCount(value_references, count, &model_value_count) || model_value_count != expected_count) {
        return OperationResult::Failure("INVALID_ARGUMENT", "SetString buffer length does not match referenced FMI variables");
    }
    if (expected_count > 0 && values == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "SetString received null buffers");
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
        std::size_t flat_size = 0;
        if (!TryResolveVariableFlatSize(*variable, &flat_size) || offset + flat_size > expected_count) {
            return OperationResult::Failure("INVALID_ARGUMENT", "SetString buffer length does not match referenced FMI variables");
        }
        if (flat_size == 1) {
            const auto status = SetValue(*variable, std::string(values[offset] ? values[offset] : ""));
            if (!status) {
                return status;
            }
        } else {
            StringArray buffer;
            buffer.reserve(flat_size);
            for (std::size_t element = 0; element < flat_size; ++element) {
                buffer.emplace_back(values[offset + element] ? values[offset + element] : "");
            }
            const auto status = SetValue(*variable, std::move(buffer));
            if (!status) {
                return status;
            }
        }
        offset += flat_size;
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::SetBinary(const std::uint32_t* value_references,
                                        const std::size_t count,
                                        const std::size_t* value_sizes,
                                        const std::uint8_t* const* values,
                                        const std::optional<std::size_t> value_count) {
    if (count > 0 && value_references == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "SetBinary received null buffers");
    }
    const std::size_t expected_count = value_count.value_or(count);
    std::size_t model_value_count = 0;
    if (!TryExpectedValueCount(value_references, count, &model_value_count) || model_value_count != expected_count) {
        return OperationResult::Failure("INVALID_ARGUMENT", "SetBinary buffer length does not match referenced FMI variables");
    }
    if (expected_count > 0 && (value_sizes == nullptr || values == nullptr)) {
        return OperationResult::Failure("INVALID_ARGUMENT", "SetBinary received null buffers");
    }
    std::size_t offset = 0;
    for (std::size_t index = 0; index < count; ++index) {
        const VariableInfo* variable = FindVariableByValueReference(model_, value_references[index]);
        if (variable == nullptr) {
            return OperationResult::Failure("UNKNOWN_VALUE_REFERENCE", "Unknown value reference");
        }
        if (variable->type != ScalarType::kBinary) {
            return OperationResult::Failure("TYPE_MISMATCH", "Variable type does not match SetBinary");
        }
        std::size_t flat_size = 0;
        if (!TryResolveVariableFlatSize(*variable, &flat_size) || offset + flat_size > expected_count) {
            return OperationResult::Failure("INVALID_ARGUMENT", "SetBinary buffer length does not match referenced FMI variables");
        }
        if (flat_size == 1) {
            const auto* data = values[offset];
            BinaryValue binary;
            if (value_sizes[offset] > 0) {
                if (data == nullptr) {
                    return OperationResult::Failure("INVALID_ARGUMENT", "SetBinary received a null value buffer");
                }
                binary.assign(data, data + value_sizes[offset]);
            }
            const auto status = SetValue(*variable, std::move(binary));
            if (!status) {
                return status;
            }
        } else {
            BinaryArray buffer;
            buffer.reserve(flat_size);
            for (std::size_t element = 0; element < flat_size; ++element) {
                const auto* data = values[offset + element];
                BinaryValue binary;
                if (value_sizes[offset + element] > 0) {
                    if (data == nullptr) {
                        return OperationResult::Failure("INVALID_ARGUMENT", "SetBinary received a null value buffer");
                    }
                    binary.assign(data, data + value_sizes[offset + element]);
                }
                buffer.push_back(std::move(binary));
            }
            const auto status = SetValue(*variable, std::move(buffer));
            if (!status) {
                return status;
            }
        }
        offset += flat_size;
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::SetClock(const std::uint32_t* value_references,
                                       const std::size_t count,
                                       const bool* values) {
    if (count > 0 && (value_references == nullptr || values == nullptr)) {
        return OperationResult::Failure("INVALID_ARGUMENT", "SetClock received null buffers");
    }
    for (std::size_t index = 0; index < count; ++index) {
        const VariableInfo* variable = FindVariableByValueReference(model_, value_references[index]);
        if (variable == nullptr) {
            return OperationResult::Failure("UNKNOWN_VALUE_REFERENCE", "Unknown value reference");
        }
        if (variable->type != ScalarType::kClock) {
            return OperationResult::Failure("TYPE_MISMATCH", "Variable type does not match SetClock");
        }
        const auto status = SetValue(*variable, values[index]);
        if (!status) {
            return status;
        }
    }
    return OperationResult::Success();
}

template <typename T>
OperationResult ProxyRuntime::GetNumericValues(const std::uint32_t* value_references,
                                               const std::size_t count,
                                               T* values,
                                               const std::optional<std::size_t> value_count,
                                               const ScalarType expected_type) {
    if (count > 0 && value_references == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "Get values received null buffers");
    }
    const std::size_t expected_count = value_count.value_or(count);
    std::size_t model_value_count = 0;
    if (!TryExpectedValueCount(value_references, count, &model_value_count) || model_value_count != expected_count) {
        return OperationResult::Failure("INVALID_ARGUMENT", "Get values buffer length does not match referenced FMI variables");
    }
    if (expected_count > 0 && values == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "Get values received null buffers");
    }
    const auto remote_status = RefreshModelExchangeValues(value_references, count, expected_type, value_count);
    if (!remote_status) {
        return remote_status;
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
        if (expected_type == ScalarType::kReal && variable->causality == "independent") {
            const std::size_t flat_size = ResolveVariableFlatSize(*variable);
            if (flat_size != 1 || offset >= expected_count) {
                return OperationResult::Failure("INVALID_ARGUMENT", "Independent variable must be scalar");
            }
            values[offset++] = static_cast<T>(current_time_);
            continue;
        }
        const ScalarValue* cached = GetCachedValue(value_references[index]);
        if (cached == nullptr) {
            return OperationResult::Failure("VALUE_UNAVAILABLE", "Value is not cached");
        }
        std::size_t flat_size = 0;
        if (!TryResolveVariableFlatSize(*variable, &flat_size) || offset + flat_size > expected_count) {
            return OperationResult::Failure("INVALID_ARGUMENT", "Get values buffer length does not match referenced FMI variables");
        }
        if (flat_size == 1) {
            if (expected_type == ScalarType::kReal) {
                const auto* typed = std::get_if<double>(cached);
                if (typed == nullptr) {
                    return OperationResult::Failure("TYPE_MISMATCH", "Cached value type does not match getter");
                }
                values[offset] = static_cast<T>(*typed);
            } else {
                if (!TryCastStoredInteger(*variable, *cached, &values[offset])) {
                    return OperationResult::Failure("TYPE_MISMATCH", "Cached integer value does not fit the requested FMI getter");
                }
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
            if (const auto* signed_array = std::get_if<IntegerArray>(cached)) {
                if (signed_array->size() != flat_size) {
                    return OperationResult::Failure("TYPE_MISMATCH", "Cached array value type does not match getter");
                }
                for (std::size_t element = 0; element < flat_size; ++element) {
                    if (!TryCastStoredInteger(*variable, ScalarValue((*signed_array)[element]), &values[offset + element])) {
                        return OperationResult::Failure("TYPE_MISMATCH", "Cached integer array value does not fit the requested FMI getter");
                    }
                }
            } else if (const auto* unsigned_array = std::get_if<UnsignedIntegerArray>(cached)) {
                if (unsigned_array->size() != flat_size) {
                    return OperationResult::Failure("TYPE_MISMATCH", "Cached array value type does not match getter");
                }
                for (std::size_t element = 0; element < flat_size; ++element) {
                    if (!TryCastStoredInteger(*variable, ScalarValue((*unsigned_array)[element]), &values[offset + element])) {
                        return OperationResult::Failure("TYPE_MISMATCH", "Cached integer array value does not fit the requested FMI getter");
                    }
                }
            } else {
                return OperationResult::Failure("TYPE_MISMATCH", "Cached array value type does not match getter");
            }
        }
        offset += flat_size;
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::GetReal(const std::uint32_t* value_references,
                                      const std::size_t count,
                                      double* values,
                                      const std::optional<std::size_t> value_count) {
    if (count > 0 && values == nullptr) {
        return GetNumericValues(value_references, count, values, value_count, ScalarType::kReal);
    }
    const auto initialization_status = EvaluateInitializationForValues(value_references, count, value_count);
    if (!initialization_status) {
        return initialization_status;
    }
    return GetNumericValues(value_references, count, values, value_count, ScalarType::kReal);
}

OperationResult ProxyRuntime::GetInteger(const std::uint32_t* value_references,
                                         const std::size_t count,
                                         std::int32_t* values,
                                         const std::optional<std::size_t> value_count) {
    if (count > 0 && values == nullptr) {
        return GetNumericValues(value_references, count, values, value_count, ScalarType::kInteger);
    }
    const auto initialization_status = EvaluateInitializationForValues(value_references, count, value_count);
    if (!initialization_status) {
        return initialization_status;
    }
    return GetNumericValues(value_references, count, values, value_count, ScalarType::kInteger);
}

OperationResult ProxyRuntime::GetSignedInteger(const std::uint32_t* value_references,
                                               const std::size_t count,
                                               std::int64_t* values,
                                               const std::optional<std::size_t> value_count) {
    if (count > 0 && values == nullptr) {
        return GetNumericValues(value_references, count, values, value_count, ScalarType::kInteger);
    }
    const auto initialization_status = EvaluateInitializationForValues(value_references, count, value_count);
    if (!initialization_status) {
        return initialization_status;
    }
    return GetNumericValues(value_references, count, values, value_count, ScalarType::kInteger);
}

OperationResult ProxyRuntime::GetUnsignedInteger(const std::uint32_t* value_references,
                                                 const std::size_t count,
                                                 std::uint64_t* values,
                                                 const std::optional<std::size_t> value_count) {
    if (count > 0 && values == nullptr) {
        return GetNumericValues(value_references, count, values, value_count, ScalarType::kInteger);
    }
    const auto initialization_status = EvaluateInitializationForValues(value_references, count, value_count);
    if (!initialization_status) {
        return initialization_status;
    }
    return GetNumericValues(value_references, count, values, value_count, ScalarType::kInteger);
}

OperationResult ProxyRuntime::GetBoolean(const std::uint32_t* value_references,
                                         const std::size_t count,
                                         bool* values,
                                         const std::optional<std::size_t> value_count) {
    if (count > 0 && value_references == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetBoolean received null buffers");
    }
    const std::size_t expected_count = value_count.value_or(count);
    std::size_t model_value_count = 0;
    if (!TryExpectedValueCount(value_references, count, &model_value_count) || model_value_count != expected_count) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetBoolean buffer length does not match referenced FMI variables");
    }
    if (expected_count > 0 && values == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetBoolean received null buffers");
    }
    const auto initialization_status = EvaluateInitializationForValues(value_references, count, value_count);
    if (!initialization_status) {
        return initialization_status;
    }
    const auto remote_status = RefreshModelExchangeValues(value_references, count, ScalarType::kBoolean, value_count);
    if (!remote_status) {
        return remote_status;
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
        std::size_t flat_size = 0;
        if (!TryResolveVariableFlatSize(*variable, &flat_size) || offset + flat_size > expected_count) {
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
                                        const std::optional<std::size_t> value_count) {
    if (count > 0 && value_references == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetString received null buffers");
    }
    string_cache_.clear();
    const std::size_t expected_count = value_count.value_or(count);
    std::size_t model_value_count = 0;
    if (!TryExpectedValueCount(value_references, count, &model_value_count) || model_value_count != expected_count) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetString buffer length does not match referenced FMI variables");
    }
    if (expected_count > 0 && values == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetString received null buffers");
    }
    const auto initialization_status = EvaluateInitializationForValues(value_references, count, value_count);
    if (!initialization_status) {
        return initialization_status;
    }
    const auto remote_status = RefreshModelExchangeValues(value_references, count, ScalarType::kString, value_count);
    if (!remote_status) {
        return remote_status;
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
        std::size_t flat_size = 0;
        if (!TryResolveVariableFlatSize(*variable, &flat_size) || offset + flat_size > expected_count) {
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

OperationResult ProxyRuntime::GetBinary(const std::uint32_t* value_references,
                                        const std::size_t count,
                                        std::size_t* value_sizes,
                                        const std::uint8_t** values,
                                        const std::optional<std::size_t> value_count) {
    if (count > 0 && value_references == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetBinary received null buffers");
    }
    binary_cache_.clear();
    const std::size_t expected_count = value_count.value_or(count);
    std::size_t model_value_count = 0;
    if (!TryExpectedValueCount(value_references, count, &model_value_count) || model_value_count != expected_count) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetBinary buffer length does not match referenced FMI variables");
    }
    if (expected_count > 0 && (value_sizes == nullptr || values == nullptr)) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetBinary received null buffers");
    }
    const auto initialization_status = EvaluateInitializationForValues(value_references, count, value_count);
    if (!initialization_status) {
        return initialization_status;
    }
    const auto remote_status = RefreshModelExchangeValues(value_references, count, ScalarType::kBinary, value_count);
    if (!remote_status) {
        return remote_status;
    }
    std::size_t offset = 0;
    for (std::size_t index = 0; index < count; ++index) {
        const VariableInfo* variable = FindVariableByValueReference(model_, value_references[index]);
        if (variable == nullptr) {
            return OperationResult::Failure("UNKNOWN_VALUE_REFERENCE", "Unknown value reference");
        }
        if (variable->type != ScalarType::kBinary) {
            return OperationResult::Failure("TYPE_MISMATCH", "Variable type does not match GetBinary");
        }
        const ScalarValue* cached = GetCachedValue(value_references[index]);
        if (cached == nullptr) {
            return OperationResult::Failure("VALUE_UNAVAILABLE", "Value is not cached");
        }
        std::size_t flat_size = 0;
        if (!TryResolveVariableFlatSize(*variable, &flat_size) || offset + flat_size > expected_count) {
            return OperationResult::Failure("INVALID_ARGUMENT", "GetBinary buffer length does not match referenced FMI variables");
        }
        if (flat_size == 1) {
            const auto* data = std::get_if<BinaryValue>(cached);
            if (data == nullptr) {
                return OperationResult::Failure("TYPE_MISMATCH", "Cached value type does not match GetBinary");
            }
            value_sizes[offset] = data->size();
            values[offset] = data->empty() ? nullptr : data->data();
            ++offset;
        } else {
            const auto* data = std::get_if<BinaryArray>(cached);
            if (data == nullptr || data->size() != flat_size) {
                return OperationResult::Failure("TYPE_MISMATCH", "Cached array value type does not match GetBinary");
            }
            for (const auto& item : *data) {
                value_sizes[offset] = item.size();
                values[offset] = item.empty() ? nullptr : item.data();
                ++offset;
            }
        }
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::GetClock(const std::uint32_t* value_references,
                                       const std::size_t count,
                                       bool* values) {
    if (count > 0 && (value_references == nullptr || values == nullptr)) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetClock received null buffers");
    }
    const auto initialization_status = EvaluateInitializationForValues(value_references, count, count);
    if (!initialization_status) {
        return initialization_status;
    }
    const auto remote_status = RefreshModelExchangeValues(value_references, count, ScalarType::kClock, count);
    if (!remote_status) {
        return remote_status;
    }
    for (std::size_t index = 0; index < count; ++index) {
        const VariableInfo* variable = FindVariableByValueReference(model_, value_references[index]);
        if (variable == nullptr) {
            return OperationResult::Failure("UNKNOWN_VALUE_REFERENCE", "Unknown value reference");
        }
        if (variable->type != ScalarType::kClock) {
            return OperationResult::Failure("TYPE_MISMATCH", "Variable type does not match GetClock");
        }
        const ScalarValue* cached = GetCachedValue(value_references[index]);
        if (cached == nullptr) {
            return OperationResult::Failure("VALUE_UNAVAILABLE", "Value is not cached");
        }
        const auto* typed = std::get_if<bool>(cached);
        if (typed == nullptr) {
            return OperationResult::Failure("TYPE_MISMATCH", "Cached value type does not match GetClock");
        }
        values[index] = *typed;
        if (variable->causality == "output" && values[index]) {
            cached_values_[value_references[index]] = false;
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

std::size_t ProxyRuntime::NumberOfContinuousStates() const {
    if (model_.continuous_state_derivative_references.empty()) {
        return model_.number_of_continuous_states;
    }
    std::size_t count = 0;
    for (const auto reference : model_.continuous_state_derivative_references) {
        const std::size_t size = ExpectedValueCount(&reference, 1);
        if (size > std::numeric_limits<std::size_t>::max() - count) {
            return 0;
        }
        count += size;
    }
    return count;
}

std::size_t ProxyRuntime::NumberOfEventIndicators() const {
    if (model_.event_indicator_references.empty()) {
        return model_.number_of_event_indicators;
    }
    std::size_t count = 0;
    for (const auto reference : model_.event_indicator_references) {
        const std::size_t size = ExpectedValueCount(&reference, 1);
        if (size > std::numeric_limits<std::size_t>::max() - count) {
            return 0;
        }
        count += size;
    }
    return count;
}

SessionState ProxyRuntime::State() const {
    return state_;
}

double ProxyRuntime::CurrentTime() const {
    return current_time_;
}

bool ProxyRuntime::LastStepEarlyReturn() const {
    return last_step_early_return_;
}

bool ProxyRuntime::LastStepEventHandlingNeeded() const {
    return last_step_event_handling_needed_;
}

bool ProxyRuntime::LastStepTerminated() const {
    return last_step_terminated_;
}

bool ProxyRuntime::SimulationFinished() const {
    return simulation_finished_;
}

const std::string& ProxyRuntime::LastError() const {
    return last_error_;
}

}  // namespace decentralabs::proxy
