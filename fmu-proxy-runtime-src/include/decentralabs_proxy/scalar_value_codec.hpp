#pragma once

#include <cstdint>
#include <map>
#include <optional>
#include <string>

#include "decentralabs_proxy/json.hpp"
#include "decentralabs_proxy/model_description.hpp"

namespace decentralabs::proxy::scalar_value_codec {

std::optional<BinaryValue> DecodeBase64(const std::string& text);

JsonValue EncodeJsonValue(const ScalarValue& value);
JsonObject EncodeJsonObject(const std::map<std::string, ScalarValue>& values);

}  // namespace decentralabs::proxy::scalar_value_codec
