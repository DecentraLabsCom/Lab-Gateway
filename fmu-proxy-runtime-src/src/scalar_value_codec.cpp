#include "decentralabs_proxy/scalar_value_codec.hpp"

#include <cmath>
#include <limits>
#include <string>
#include <type_traits>
#include <utility>

namespace decentralabs::proxy::scalar_value_codec {

namespace {

std::string EncodeBase64(const BinaryValue& data) {
    static constexpr char kAlphabet[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    std::string encoded;
    encoded.reserve(((data.size() + 2) / 3) * 4);
    std::size_t index = 0;
    while (index + 3 <= data.size()) {
        const std::uint32_t chunk =
            (static_cast<std::uint32_t>(data[index]) << 16U) |
            (static_cast<std::uint32_t>(data[index + 1]) << 8U) |
            static_cast<std::uint32_t>(data[index + 2]);
        encoded.push_back(kAlphabet[(chunk >> 18U) & 0x3FU]);
        encoded.push_back(kAlphabet[(chunk >> 12U) & 0x3FU]);
        encoded.push_back(kAlphabet[(chunk >> 6U) & 0x3FU]);
        encoded.push_back(kAlphabet[chunk & 0x3FU]);
        index += 3;
    }

    const std::size_t remaining = data.size() - index;
    if (remaining == 1U) {
        const std::uint32_t chunk = static_cast<std::uint32_t>(data[index]) << 16U;
        encoded.push_back(kAlphabet[(chunk >> 18U) & 0x3FU]);
        encoded.push_back(kAlphabet[(chunk >> 12U) & 0x3FU]);
        encoded.push_back('=');
        encoded.push_back('=');
    } else if (remaining == 2U) {
        const std::uint32_t chunk =
            (static_cast<std::uint32_t>(data[index]) << 16U) |
            (static_cast<std::uint32_t>(data[index + 1]) << 8U);
        encoded.push_back(kAlphabet[(chunk >> 18U) & 0x3FU]);
        encoded.push_back(kAlphabet[(chunk >> 12U) & 0x3FU]);
        encoded.push_back(kAlphabet[(chunk >> 6U) & 0x3FU]);
        encoded.push_back('=');
    }
    return encoded;
}

std::optional<BinaryValue> DecodeBase64(const std::string& text) {
    static const std::int8_t kTable[256] = {
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,
        -1,-1,-1,-1,-1,-1,-1,-1,-1,-1,-1,62,-1,-1,-1,63,52,53,54,55,56,57,58,59,60,61,-1,-1,-1,-2,-1,-1,
        -1,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,-1,-1,-1,-1,-1,
        -1,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,-1,-1,-1,-1,
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
        const std::int8_t a = kTable[static_cast<unsigned char>(text[index])];
        const std::int8_t b = kTable[static_cast<unsigned char>(text[index + 1])];
        const std::int8_t c = text[index + 2] == '=' ? -2 : kTable[static_cast<unsigned char>(text[index + 2])];
        const std::int8_t d = text[index + 3] == '=' ? -2 : kTable[static_cast<unsigned char>(text[index + 3])];
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

template <typename T>
JsonValue EncodePrimitive(const T& value) {
    return JsonValue(value);
}

JsonValue EncodePrimitive(std::int64_t value) { return JsonValue(std::to_string(value)); }
JsonValue EncodePrimitive(std::uint64_t value) { return JsonValue(std::to_string(value)); }

template <typename T>
JsonValue EncodeArray(const std::vector<T>& values) {
    JsonArray items;
    items.reserve(values.size());
    for (const auto& item : values) {
        items.emplace_back(EncodePrimitive(item));
    }
    return JsonValue(std::move(items));
}

}  // namespace

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

JsonValue EncodeJsonValue(const ScalarValue& value) {
    return std::visit(
        [](const auto& typed) -> JsonValue {
            using ValueType = std::decay_t<decltype(typed)>;
            if constexpr (std::is_same_v<ValueType, RealArray> ||
                          std::is_same_v<ValueType, IntegerArray> ||
                          std::is_same_v<ValueType, UnsignedIntegerArray> ||
                          std::is_same_v<ValueType, StringArray>) {
                return EncodeArray(typed);
            } else if constexpr (std::is_same_v<ValueType, BinaryValue>) {
                return JsonValue(EncodeBase64(typed));
            } else if constexpr (std::is_same_v<ValueType, BinaryArray>) {
                JsonArray items;
                items.reserve(typed.size());
                for (const auto& item : typed) {
                    items.emplace_back(EncodeBase64(item));
                }
                return JsonValue(std::move(items));
            } else if constexpr (std::is_same_v<ValueType, BooleanArray>) {
                JsonArray items;
                items.reserve(typed.size());
                for (const bool item : typed) {
                    items.emplace_back(item);
                }
                return JsonValue(std::move(items));
            } else {
                return EncodePrimitive(typed);
            }
        },
        value);
}

JsonObject EncodeJsonObject(const std::map<std::string, ScalarValue>& values) {
    JsonObject json_values;
    for (const auto& [name, value] : values) {
        json_values.emplace(name, EncodeJsonValue(value));
    }
    return json_values;
}

// codeql[cpp/poorly-documented-function]
std::optional<ScalarValue> DecodeJsonValue(const JsonValue& value, const VariableInfo& variable) {
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
                    const auto decoded = DecodeBase64(item.AsString());
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

}  // namespace decentralabs::proxy::scalar_value_codec
