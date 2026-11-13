#include "decentralabs_proxy/scalar_value_codec.hpp"

#include <cstdint>
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

std::optional<BinaryValue> DecodeBase64Impl(const std::string& text) {
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

std::optional<BinaryValue> DecodeBase64(const std::string& text) {
    return DecodeBase64Impl(text);
}

}  // namespace decentralabs::proxy::scalar_value_codec
