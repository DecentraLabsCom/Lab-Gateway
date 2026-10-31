#pragma once

#include <cstdint>
#include <map>
#include <optional>
#include <string_view>

#include "decentralabs_proxy/json.hpp"
#include "decentralabs_proxy/model_description.hpp"

namespace decentralabs::proxy::scalar_value_codec {

struct IntegerBounds {
    std::int64_t min;
    std::uint64_t max;
    bool unsigned_only;
};

IntegerBounds BoundsForDeclaredType(std::string_view declared_type);

bool TryNormalizeIntegerValue(const VariableInfo& variable, std::int64_t raw_value, ScalarValue* output);
bool TryNormalizeIntegerValue(const VariableInfo& variable, std::uint64_t raw_value, ScalarValue* output);

JsonValue EncodeJsonValue(const ScalarValue& value);
JsonObject EncodeJsonObject(const std::map<std::string, ScalarValue>& values);
// Decodes the JSON representation using the FMI scalar type declared by the model.
std::optional<ScalarValue> DecodeJsonValue(const JsonValue& value, const VariableInfo& variable);

}  // namespace decentralabs::proxy::scalar_value_codec
