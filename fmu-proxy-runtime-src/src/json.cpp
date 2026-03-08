#include "decentralabs_proxy/json.hpp"

#include <cctype>
#include <cstdlib>
#include <iomanip>
#include <sstream>
#include <stdexcept>

namespace decentralabs::proxy {

JsonValue::JsonValue() : value_(nullptr) {}
JsonValue::JsonValue(std::nullptr_t) : value_(nullptr) {}
JsonValue::JsonValue(const bool value) : value_(value) {}
JsonValue::JsonValue(const double value) : value_(value) {}
JsonValue::JsonValue(const int value) : value_(static_cast<double>(value)) {}
JsonValue::JsonValue(std::string value) : value_(std::move(value)) {}
JsonValue::JsonValue(const char* value) : value_(std::string(value ? value : "")) {}
JsonValue::JsonValue(JsonObject value) : value_(std::move(value)) {}
JsonValue::JsonValue(JsonArray value) : value_(std::move(value)) {}

bool JsonValue::IsNull() const {
    return std::holds_alternative<std::nullptr_t>(value_);
}

bool JsonValue::IsBool() const {
    return std::holds_alternative<bool>(value_);
}

bool JsonValue::IsNumber() const {
    return std::holds_alternative<double>(value_);
}

bool JsonValue::IsString() const {
    return std::holds_alternative<std::string>(value_);
}

bool JsonValue::IsObject() const {
    return std::holds_alternative<JsonObject>(value_);
}

bool JsonValue::IsArray() const {
    return std::holds_alternative<JsonArray>(value_);
}

bool JsonValue::AsBool(const bool fallback) const {
    if (const auto* value = std::get_if<bool>(&value_)) {
        return *value;
    }
    return fallback;
}

double JsonValue::AsNumber(const double fallback) const {
    if (const auto* value = std::get_if<double>(&value_)) {
        return *value;
    }
    return fallback;
}

std::string JsonValue::AsString(const std::string_view fallback) const {
    if (const auto* value = std::get_if<std::string>(&value_)) {
        return *value;
    }
    return std::string(fallback);
}

const JsonObject* JsonValue::AsObject() const {
    return std::get_if<JsonObject>(&value_);
}

JsonObject* JsonValue::AsObject() {
    return std::get_if<JsonObject>(&value_);
}

const JsonArray* JsonValue::AsArray() const {
    return std::get_if<JsonArray>(&value_);
}

JsonArray* JsonValue::AsArray() {
    return std::get_if<JsonArray>(&value_);
}

const JsonValue::Variant& JsonValue::Raw() const {
    return value_;
}

namespace {

std::string EscapeJsonString(const std::string_view text) {
    std::ostringstream out;
    for (const unsigned char ch : text) {
        switch (ch) {
            case '\"':
                out << "\\\"";
                break;
            case '\\':
                out << "\\\\";
                break;
            case '\b':
                out << "\\b";
                break;
            case '\f':
                out << "\\f";
                break;
            case '\n':
                out << "\\n";
                break;
            case '\r':
                out << "\\r";
                break;
            case '\t':
                out << "\\t";
                break;
            default:
                if (ch < 0x20) {
                    out << "\\u" << std::hex << std::setw(4) << std::setfill('0') << static_cast<int>(ch);
                } else {
                    out << static_cast<char>(ch);
                }
                break;
        }
    }
    return out.str();
}

class Parser {
public:
    explicit Parser(const std::string_view input) : input_(input) {}

    ValueResult<JsonValue> Parse() {
        auto value = ParseValue();
        if (!value) {
            return value;
        }
        SkipWhitespace();
        if (offset_ != input_.size()) {
            return ValueResult<JsonValue>::Failure("JSON_PARSE_ERROR", "Unexpected trailing characters in JSON payload");
        }
        return value;
    }

private:
    ValueResult<JsonValue> ParseValue() {
        SkipWhitespace();
        if (offset_ >= input_.size()) {
            return ValueResult<JsonValue>::Failure("JSON_PARSE_ERROR", "Unexpected end of JSON payload");
        }

        switch (input_[offset_]) {
            case '{':
                return ParseObject();
            case '[':
                return ParseArray();
            case '"':
                return ParseString();
            case 't':
            case 'f':
                return ParseBoolean();
            case 'n':
                return ParseNull();
            default:
                if (input_[offset_] == '-' || std::isdigit(static_cast<unsigned char>(input_[offset_]))) {
                    return ParseNumber();
                }
                return ValueResult<JsonValue>::Failure("JSON_PARSE_ERROR", "Unexpected token in JSON payload");
        }
    }

    ValueResult<JsonValue> ParseObject() {
        JsonObject object;
        ++offset_;
        SkipWhitespace();
        if (TryConsume('}')) {
            return ValueResult<JsonValue>::Success(JsonValue(std::move(object)));
        }

        for (;;) {
            auto key_value = ParseString();
            if (!key_value) {
                return key_value;
            }
            const std::string key = key_value.value.AsString();
            SkipWhitespace();
            if (!TryConsume(':')) {
                return ValueResult<JsonValue>::Failure("JSON_PARSE_ERROR", "Expected ':' in JSON object");
            }
            auto value = ParseValue();
            if (!value) {
                return value;
            }
            object.emplace(key, std::move(value.value));
            SkipWhitespace();
            if (TryConsume('}')) {
                break;
            }
            if (!TryConsume(',')) {
                return ValueResult<JsonValue>::Failure("JSON_PARSE_ERROR", "Expected ',' in JSON object");
            }
        }

        return ValueResult<JsonValue>::Success(JsonValue(std::move(object)));
    }

    ValueResult<JsonValue> ParseArray() {
        JsonArray array;
        ++offset_;
        SkipWhitespace();
        if (TryConsume(']')) {
            return ValueResult<JsonValue>::Success(JsonValue(std::move(array)));
        }

        for (;;) {
            auto value = ParseValue();
            if (!value) {
                return value;
            }
            array.emplace_back(std::move(value.value));
            SkipWhitespace();
            if (TryConsume(']')) {
                break;
            }
            if (!TryConsume(',')) {
                return ValueResult<JsonValue>::Failure("JSON_PARSE_ERROR", "Expected ',' in JSON array");
            }
        }

        return ValueResult<JsonValue>::Success(JsonValue(std::move(array)));
    }

    ValueResult<JsonValue> ParseString() {
        if (!TryConsume('"')) {
            return ValueResult<JsonValue>::Failure("JSON_PARSE_ERROR", "Expected string value");
        }

        std::string out;
        while (offset_ < input_.size()) {
            const char ch = input_[offset_++];
            if (ch == '"') {
                return ValueResult<JsonValue>::Success(JsonValue(std::move(out)));
            }
            if (ch != '\\') {
                out.push_back(ch);
                continue;
            }
            if (offset_ >= input_.size()) {
                return ValueResult<JsonValue>::Failure("JSON_PARSE_ERROR", "Invalid escape sequence in JSON string");
            }
            const char escape = input_[offset_++];
            switch (escape) {
                case '"':
                case '\\':
                case '/':
                    out.push_back(escape);
                    break;
                case 'b':
                    out.push_back('\b');
                    break;
                case 'f':
                    out.push_back('\f');
                    break;
                case 'n':
                    out.push_back('\n');
                    break;
                case 'r':
                    out.push_back('\r');
                    break;
                case 't':
                    out.push_back('\t');
                    break;
                case 'u':
                    if (offset_ + 4 > input_.size()) {
                        return ValueResult<JsonValue>::Failure("JSON_PARSE_ERROR", "Invalid unicode escape in JSON string");
                    }
                    out.push_back('?');
                    offset_ += 4;
                    break;
                default:
                    return ValueResult<JsonValue>::Failure("JSON_PARSE_ERROR", "Unsupported escape sequence in JSON string");
            }
        }

        return ValueResult<JsonValue>::Failure("JSON_PARSE_ERROR", "Unterminated JSON string");
    }

    ValueResult<JsonValue> ParseBoolean() {
        if (input_.substr(offset_, 4) == "true") {
            offset_ += 4;
            return ValueResult<JsonValue>::Success(JsonValue(true));
        }
        if (input_.substr(offset_, 5) == "false") {
            offset_ += 5;
            return ValueResult<JsonValue>::Success(JsonValue(false));
        }
        return ValueResult<JsonValue>::Failure("JSON_PARSE_ERROR", "Invalid boolean in JSON payload");
    }

    ValueResult<JsonValue> ParseNull() {
        if (input_.substr(offset_, 4) == "null") {
            offset_ += 4;
            return ValueResult<JsonValue>::Success(JsonValue(nullptr));
        }
        return ValueResult<JsonValue>::Failure("JSON_PARSE_ERROR", "Invalid null in JSON payload");
    }

    ValueResult<JsonValue> ParseNumber() {
        const std::size_t start = offset_;
        if (input_[offset_] == '-') {
            ++offset_;
        }
        while (offset_ < input_.size() && std::isdigit(static_cast<unsigned char>(input_[offset_]))) {
            ++offset_;
        }
        if (offset_ < input_.size() && input_[offset_] == '.') {
            ++offset_;
            while (offset_ < input_.size() && std::isdigit(static_cast<unsigned char>(input_[offset_]))) {
                ++offset_;
            }
        }
        if (offset_ < input_.size() && (input_[offset_] == 'e' || input_[offset_] == 'E')) {
            ++offset_;
            if (offset_ < input_.size() && (input_[offset_] == '+' || input_[offset_] == '-')) {
                ++offset_;
            }
            while (offset_ < input_.size() && std::isdigit(static_cast<unsigned char>(input_[offset_]))) {
                ++offset_;
            }
        }

        const std::string text(input_.substr(start, offset_ - start));
        char* end = nullptr;
        const double value = std::strtod(text.c_str(), &end);
        if (end == nullptr || *end != '\0') {
            return ValueResult<JsonValue>::Failure("JSON_PARSE_ERROR", "Invalid number in JSON payload");
        }
        return ValueResult<JsonValue>::Success(JsonValue(value));
    }

    void SkipWhitespace() {
        while (offset_ < input_.size() && std::isspace(static_cast<unsigned char>(input_[offset_]))) {
            ++offset_;
        }
    }

    bool TryConsume(const char expected) {
        SkipWhitespace();
        if (offset_ < input_.size() && input_[offset_] == expected) {
            ++offset_;
            return true;
        }
        return false;
    }

    std::string_view input_;
    std::size_t offset_ = 0;
};

void SerializeValue(const JsonValue& value, std::ostringstream& out) {
    if (value.IsNull()) {
        out << "null";
        return;
    }
    if (value.IsBool()) {
        out << (value.AsBool() ? "true" : "false");
        return;
    }
    if (value.IsNumber()) {
        out << std::setprecision(15) << value.AsNumber();
        return;
    }
    if (value.IsString()) {
        out << '"' << EscapeJsonString(value.AsString()) << '"';
        return;
    }
    if (const auto* object = value.AsObject()) {
        out << '{';
        bool first = true;
        for (const auto& [key, nested] : *object) {
            if (!first) {
                out << ',';
            }
            first = false;
            out << '"' << EscapeJsonString(key) << "\":";
            SerializeValue(nested, out);
        }
        out << '}';
        return;
    }
    if (const auto* array = value.AsArray()) {
        out << '[';
        for (std::size_t index = 0; index < array->size(); ++index) {
            if (index > 0) {
                out << ',';
            }
            SerializeValue((*array)[index], out);
        }
        out << ']';
    }
}

}  // namespace

ValueResult<JsonValue> ParseJson(const std::string_view text) {
    return Parser(text).Parse();
}

std::string SerializeJson(const JsonValue& value) {
    std::ostringstream out;
    SerializeValue(value, out);
    return out.str();
}

const JsonValue* FindObjectValue(const JsonObject& object, const std::string_view key) {
    const auto it = object.find(std::string(key));
    if (it == object.end()) {
        return nullptr;
    }
    return &it->second;
}

std::string JsonString(const JsonObject& object, const std::string_view key, const std::string_view fallback) {
    const JsonValue* value = FindObjectValue(object, key);
    if (value == nullptr) {
        return std::string(fallback);
    }
    return value->AsString(fallback);
}

double JsonNumber(const JsonObject& object, const std::string_view key, const double fallback) {
    const JsonValue* value = FindObjectValue(object, key);
    if (value == nullptr) {
        return fallback;
    }
    return value->AsNumber(fallback);
}

bool JsonBool(const JsonObject& object, const std::string_view key, const bool fallback) {
    const JsonValue* value = FindObjectValue(object, key);
    if (value == nullptr) {
        return fallback;
    }
    return value->AsBool(fallback);
}

}  // namespace decentralabs::proxy
