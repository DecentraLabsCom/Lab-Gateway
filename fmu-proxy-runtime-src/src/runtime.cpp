#include "decentralabs_proxy/runtime.hpp"

#include <cctype>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <limits>
#include <type_traits>
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

std::optional<BinaryValue> DecodeBase64(const std::string& text) {
    static const int8_t kTable[256] = {
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,62,-1,-1,-1,63,52,53,54,55,56,57,58,59,60,61,-1,-1,-1,-2,-1,-1,
        -1,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,-1,-1,-1,-1,-1,
        -1,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1
    };
    if (text.empty()) {
        return BinaryValue{};
    }
    if (text.size() % 4 != 0) {
        return std::nullopt;
    }
    BinaryValue output;
    output.reserve((text.size() / 4) * 3);
    for (std::size_t index = 0; index < text.size(); index += 4) {
        const int8_t a = kTable[static_cast<unsigned char>(text[index])];
        const int8_t b = kTable[static_cast<unsigned char>(text[index + 1])];
        const int8_t c = text[index + 2] == '=' ? -2 : kTable[static_cast<unsigned char>(text[index + 2])];
        const int8_t d = text[index + 3] == '=' ? -2 : kTable[static_cast<unsigned char>(text[index + 3])];
        if (a < 0 || b < 0 || c == -1 || d == -1) {
            return std::nullopt;
        }
        const std::uint32_t triple =
            (static_cast<std::uint32_t>(a) << 18U) |
            (static_cast<std::uint32_t>(b) << 12U) |
            (static_cast<std::uint32_t>(c < 0 ? 0 : c) << 6U) |
            static_cast<std::uint32_t>(d < 0 ? 0 : d);
        output.push_back(static_cast<std::uint8_t>((triple >> 16U) & 0xFFU));
        if (c != -2) {
            output.push_back(static_cast<std::uint8_t>((triple >> 8U) & 0xFFU));
        }
        if (d != -2) {
            output.push_back(static_cast<std::uint8_t>(triple & 0xFFU));
        }
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
    return {};
}

std::optional<std::int64_t> ParseSignedIntegerJsonValue(const JsonValue& value) {
    try {
        if (value.IsString()) {
            return static_cast<std::int64_t>(std::stoll(value.AsString()));
        }
        if (value.IsNumber()) {
            const double number = value.AsNumber();
            if (!std::isfinite(number) || std::trunc(number) != number) {
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

std::optional<std::uint64_t> ParseUnsignedIntegerJsonValue(const JsonValue& value) {
    try {
        if (value.IsString()) {
            return static_cast<std::uint64_t>(std::stoull(value.AsString()));
        }
        if (value.IsNumber()) {
            const double number = value.AsNumber();
            if (!std::isfinite(number) || std::trunc(number) != number || number < 0.0) {
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

template <typename T>
bool TryNormalizeIntegerValue(const VariableInfo& variable, const T raw_value, ScalarValue* output) {
    if (output == nullptr) {
        return false;
    }

    const auto bounds = BoundsForDeclaredType(variable.declared_type);
    if (bounds.unsigned_only) {
        std::uint64_t value = 0;
        if constexpr (std::is_unsigned_v<T>) {
            value = static_cast<std::uint64_t>(raw_value);
        } else {
            const auto signed_value = static_cast<std::int64_t>(raw_value);
            if (signed_value < 0) {
                return false;
            }
            value = static_cast<std::uint64_t>(signed_value);
        }
        if (value > bounds.max) {
            return false;
        }
        *output = value;
        return true;
    }

    if constexpr (std::is_unsigned_v<T>) {
        const auto value = static_cast<std::uint64_t>(raw_value);
        if (value > bounds.max || value > static_cast<std::uint64_t>(std::numeric_limits<std::int64_t>::max())) {
            return false;
        }
        *output = static_cast<std::int64_t>(value);
        return true;
    }

    const auto value = static_cast<std::int64_t>(raw_value);
    if (value < bounds.min) {
        return false;
    }
    if (value >= 0 && static_cast<std::uint64_t>(value) > bounds.max) {
        return false;
    }
    *output = value;
    return true;
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
        if constexpr (std::is_unsigned_v<T>) {
            if (*unsigned_value > static_cast<std::uint64_t>(std::numeric_limits<T>::max())) {
                return false;
            }
            *output = static_cast<T>(*unsigned_value);
            return true;
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
    }

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
            case ScalarType::kEnumeration: {
                const auto bounds = BoundsForDeclaredType(variable.declared_type);
                if (bounds.unsigned_only) {
                    UnsignedIntegerArray values;
                    values.reserve(items->size());
                    for (const auto& item : *items) {
                        const auto parsed = ParseUnsignedIntegerJsonValue(item);
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
                values.reserve(items->size());
                for (const auto& item : *items) {
                    const auto parsed = ParseSignedIntegerJsonValue(item);
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
            case ScalarType::kBinary: {
                BinaryArray values;
                values.reserve(items->size());
                for (const auto& item : *items) {
                    if (!item.IsString()) {
                        return std::nullopt;
                    }
                    const auto decoded = DecodeBase64(item.AsString());
                    if (!decoded.has_value()) {
                        return std::nullopt;
                    }
                    values.push_back(*decoded);
                }
                return ScalarValue(std::move(values));
            }
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
                const auto bounds = BoundsForDeclaredType(variable.declared_type);
                ScalarValue normalized;
                if (bounds.unsigned_only) {
                    const auto parsed = ParseUnsignedIntegerJsonValue(value);
                    if (parsed.has_value() && TryNormalizeIntegerValue(variable, *parsed, &normalized)) {
                        return normalized;
                    }
                } else {
                    const auto parsed = ParseSignedIntegerJsonValue(value);
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
                const auto decoded = DecodeBase64(value.AsString());
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
        const auto converted = ConvertJsonValue(json_value, *variable);
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
            if (expected_type == ScalarType::kReal) {
                SetValue(*variable, static_cast<double>(values[offset]));
            } else {
                ScalarValue normalized;
                if (!TryNormalizeIntegerValue(*variable, values[offset], &normalized)) {
                    return OperationResult::Failure("TYPE_MISMATCH", "Integer value is outside the supported range for the FMI variable");
                }
                SetValue(*variable, normalized);
            }
        } else if (expected_type == ScalarType::kReal) {
            RealArray buffer;
            buffer.reserve(flat_size);
            for (std::size_t element = 0; element < flat_size; ++element) {
                buffer.push_back(static_cast<double>(values[offset + element]));
            }
            SetValue(*variable, std::move(buffer));
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
                SetValue(*variable, std::move(buffer));
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
                SetValue(*variable, std::move(buffer));
            }
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

OperationResult ProxyRuntime::SetSignedInteger(const std::uint32_t* value_references,
                                               const std::size_t count,
                                               const std::int64_t* values,
                                               const std::size_t value_count) {
    return SetNumericValues(value_references, count, values, value_count, ScalarType::kInteger);
}

OperationResult ProxyRuntime::SetUnsignedInteger(const std::uint32_t* value_references,
                                                 const std::size_t count,
                                                 const std::uint64_t* values,
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

OperationResult ProxyRuntime::SetBinary(const std::uint32_t* value_references,
                                        const std::size_t count,
                                        const std::size_t* value_sizes,
                                        const std::uint8_t* const* values,
                                        const std::size_t value_count) {
    if (value_references == nullptr || value_sizes == nullptr || values == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "SetBinary received null buffers");
    }
    const std::size_t expected_count = value_count == 0 ? count : value_count;
    if (ExpectedValueCount(value_references, count) != expected_count) {
        return OperationResult::Failure("INVALID_ARGUMENT", "SetBinary buffer length does not match referenced FMI variables");
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
        const std::size_t flat_size = ResolveVariableFlatSize(*variable);
        if (flat_size == 0 || offset + flat_size > expected_count) {
            return OperationResult::Failure("INVALID_ARGUMENT", "SetBinary buffer length does not match referenced FMI variables");
        }
        if (flat_size == 1) {
            const auto* data = values[offset];
            SetValue(*variable, BinaryValue(data, data + value_sizes[offset]));
        } else {
            BinaryArray buffer;
            buffer.reserve(flat_size);
            for (std::size_t element = 0; element < flat_size; ++element) {
                const auto* data = values[offset + element];
                buffer.emplace_back(data, data + value_sizes[offset + element]);
            }
            SetValue(*variable, std::move(buffer));
        }
        offset += flat_size;
    }
    return OperationResult::Success();
}

OperationResult ProxyRuntime::SetClock(const std::uint32_t* value_references,
                                       const std::size_t count,
                                       const bool* values) {
    if (value_references == nullptr || values == nullptr) {
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
        SetValue(*variable, values[index]);
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
                                      const std::size_t value_count) const {
    return GetNumericValues(value_references, count, values, value_count, ScalarType::kReal);
}

OperationResult ProxyRuntime::GetInteger(const std::uint32_t* value_references,
                                         const std::size_t count,
                                         std::int32_t* values,
                                         const std::size_t value_count) const {
    return GetNumericValues(value_references, count, values, value_count, ScalarType::kInteger);
}

OperationResult ProxyRuntime::GetSignedInteger(const std::uint32_t* value_references,
                                               const std::size_t count,
                                               std::int64_t* values,
                                               const std::size_t value_count) const {
    return GetNumericValues(value_references, count, values, value_count, ScalarType::kInteger);
}

OperationResult ProxyRuntime::GetUnsignedInteger(const std::uint32_t* value_references,
                                                 const std::size_t count,
                                                 std::uint64_t* values,
                                                 const std::size_t value_count) const {
    return GetNumericValues(value_references, count, values, value_count, ScalarType::kInteger);
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

OperationResult ProxyRuntime::GetBinary(const std::uint32_t* value_references,
                                        const std::size_t count,
                                        std::size_t* value_sizes,
                                        const std::uint8_t** values,
                                        const std::size_t value_count) {
    if (value_references == nullptr || value_sizes == nullptr || values == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetBinary received null buffers");
    }
    string_cache_.clear();
    const std::size_t expected_count = value_count == 0 ? count : value_count;
    if (ExpectedValueCount(value_references, count) != expected_count) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetBinary buffer length does not match referenced FMI variables");
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
        const std::size_t flat_size = ResolveVariableFlatSize(*variable);
        if (flat_size == 0 || offset + flat_size > expected_count) {
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
                                       bool* values) const {
    if (value_references == nullptr || values == nullptr) {
        return OperationResult::Failure("INVALID_ARGUMENT", "GetClock received null buffers");
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
