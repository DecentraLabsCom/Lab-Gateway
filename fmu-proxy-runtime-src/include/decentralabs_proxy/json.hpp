#pragma once

#include <map>
#include <string>
#include <string_view>
#include <variant>
#include <vector>

#include "decentralabs_proxy/operation_result.hpp"

namespace decentralabs::proxy {

class JsonValue;

using JsonObject = std::map<std::string, JsonValue>;
using JsonArray = std::vector<JsonValue>;

class JsonValue {
public:
    using Variant = std::variant<std::nullptr_t, bool, double, std::string, JsonObject, JsonArray>;

    JsonValue();
    JsonValue(std::nullptr_t);
    JsonValue(bool value);
    JsonValue(double value);
    JsonValue(int value);
    JsonValue(std::string value);
    JsonValue(const char* value);
    JsonValue(JsonObject value);
    JsonValue(JsonArray value);

    bool IsNull() const;
    bool IsBool() const;
    bool IsNumber() const;
    bool IsString() const;
    bool IsObject() const;
    bool IsArray() const;

    bool AsBool(bool fallback = false) const;
    double AsNumber(double fallback = 0.0) const;
    std::string AsString(std::string_view fallback = "") const;

    const JsonObject* AsObject() const;
    JsonObject* AsObject();

    const JsonArray* AsArray() const;
    JsonArray* AsArray();

    const Variant& Raw() const;

private:
    Variant value_;
};

ValueResult<JsonValue> ParseJson(std::string_view text);
std::string SerializeJson(const JsonValue& value);

const JsonValue* FindObjectValue(const JsonObject& object, std::string_view key);
std::string JsonString(const JsonObject& object, std::string_view key, std::string_view fallback = "");
double JsonNumber(const JsonObject& object, std::string_view key, double fallback = 0.0);
bool JsonBool(const JsonObject& object, std::string_view key, bool fallback = false);

}  // namespace decentralabs::proxy
