#include "decentralabs_proxy/model_description.hpp"

#include <cctype>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <limits>
#include <regex>
#include <set>
#include <sstream>
#include <utility>

namespace decentralabs::proxy {

namespace {

std::string ReadFileText(const std::string& path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        return {};
    }
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return buffer.str();
}

std::string DecodeXmlEntities(std::string text) {
    const std::pair<std::string_view, std::string_view> replacements[] = {
        {"&quot;", "\""},
        {"&apos;", "'"},
        {"&lt;", "<"},
        {"&gt;", ">"},
        {"&amp;", "&"},
    };
    for (const auto& [from, to] : replacements) {
        std::size_t position = 0;
        while ((position = text.find(from, position)) != std::string::npos) {
            text.replace(position, from.size(), to);
            position += to.size();
        }
    }
    return text;
}

std::map<std::string, std::string> ParseAttributes(const std::string_view fragment) {
    std::map<std::string, std::string> attributes;
    const std::regex pattern(R"attr(([A-Za-z_:][A-Za-z0-9_.:-]*)\s*=\s*"([^"]*)")attr");
    const std::string text(fragment);
    for (std::sregex_iterator it(text.begin(), text.end(), pattern), end; it != end; ++it) {
        attributes.emplace((*it)[1].str(), DecodeXmlEntities((*it)[2].str()));
    }
    return attributes;
}

std::optional<double> OptionalDouble(const std::map<std::string, std::string>& attributes, const std::string& key) {
    const auto it = attributes.find(key);
    if (it == attributes.end() || it->second.empty()) {
        return std::nullopt;
    }
    try {
        return std::stod(it->second);
    } catch (...) {
        return std::nullopt;
    }
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

    std::string compact;
    compact.reserve(text.size());
    for (const unsigned char ch : text) {
        if (!std::isspace(ch)) {
            compact.push_back(static_cast<char>(ch));
        }
    }
    if (compact.empty()) {
        return BinaryValue{};
    }
    if (compact.size() % 4 != 0) {
        return std::nullopt;
    }

    BinaryValue output;
    output.reserve((compact.size() / 4) * 3);
    for (std::size_t index = 0; index < compact.size(); index += 4) {
        const int8_t a = kTable[static_cast<unsigned char>(compact[index])];
        const int8_t b = kTable[static_cast<unsigned char>(compact[index + 1])];
        const int8_t c = compact[index + 2] == '=' ? -2 : kTable[static_cast<unsigned char>(compact[index + 2])];
        const int8_t d = compact[index + 3] == '=' ? -2 : kTable[static_cast<unsigned char>(compact[index + 3])];
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

std::optional<BinaryValue> DecodeHexBinary(const std::string& text) {
    std::string compact;
    compact.reserve(text.size());
    for (const unsigned char ch : text) {
        if (!std::isspace(ch)) {
            compact.push_back(static_cast<char>(ch));
        }
    }
    if (compact.size() % 2 != 0) {
        return std::nullopt;
    }
    const auto digit = [](const unsigned char ch) -> int {
        if (ch >= '0' && ch <= '9') return ch - '0';
        if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
        if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
        return -1;
    };
    BinaryValue output;
    output.reserve(compact.size() / 2);
    for (std::size_t index = 0; index < compact.size(); index += 2) {
        const int high = digit(static_cast<unsigned char>(compact[index]));
        const int low = digit(static_cast<unsigned char>(compact[index + 1]));
        if (high < 0 || low < 0) {
            return std::nullopt;
        }
        output.push_back(static_cast<std::uint8_t>((high << 4) | low));
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

std::optional<ScalarValue> ParseIntegerToken(const std::string_view declared_type, const std::string& text) {
    const auto bounds = BoundsForDeclaredType(declared_type);
    try {
        if (bounds.unsigned_only) {
            const auto parsed = std::stoull(text);
            if (parsed > bounds.max) {
                return std::nullopt;
            }
            return ScalarValue(static_cast<std::uint64_t>(parsed));
        }

        const auto parsed = std::stoll(text);
        if (parsed < bounds.min) {
            return std::nullopt;
        }
        if (parsed >= 0 && static_cast<std::uint64_t>(parsed) > bounds.max) {
            return std::nullopt;
        }
        return ScalarValue(static_cast<std::int64_t>(parsed));
    } catch (...) {
        return std::nullopt;
    }
}

std::optional<ScalarValue> ParseScalarValue(const std::string_view declared_type, const ScalarType type, const std::string& text) {
    if (text.empty()) {
        return std::nullopt;
    }
    try {
        switch (type) {
            case ScalarType::kReal:
                return ScalarValue(std::stod(text));
            case ScalarType::kInteger:
            case ScalarType::kEnumeration:
                if (const auto parsed = ParseIntegerToken(declared_type, text)) {
                    return *parsed;
                }
                return std::nullopt;
            case ScalarType::kBoolean:
                return ScalarValue(text == "true" || text == "1");
            case ScalarType::kString:
                return ScalarValue(text);
            case ScalarType::kBinary: {
                const auto decoded = DecodeBase64(text);
                if (!decoded.has_value()) {
                    return std::nullopt;
                }
                return ScalarValue(*decoded);
            }
            case ScalarType::kClock:
                return ScalarValue(text == "true" || text == "1");
        }
    } catch (...) {
        return std::nullopt;
    }
    return std::nullopt;
}

std::vector<std::string> SplitWhitespaceTokens(const std::string& text) {
    std::vector<std::string> tokens;
    std::istringstream stream(text);
    std::string token;
    while (stream >> token) {
        tokens.push_back(token);
    }
    return tokens;
}

std::optional<ScalarValue> ParseArrayValue(const std::string_view declared_type, const ScalarType type, const std::string& text) {
    const auto tokens = SplitWhitespaceTokens(text);
    if (tokens.empty()) {
        return std::nullopt;
    }
    try {
        switch (type) {
            case ScalarType::kReal: {
                RealArray values;
                values.reserve(tokens.size());
                for (const auto& token : tokens) {
                    values.push_back(std::stod(token));
                }
                return ScalarValue(std::move(values));
            }
            case ScalarType::kInteger:
            case ScalarType::kEnumeration: {
                const auto bounds = BoundsForDeclaredType(declared_type);
                if (bounds.unsigned_only) {
                    UnsignedIntegerArray values;
                    values.reserve(tokens.size());
                    for (const auto& token : tokens) {
                        const auto parsed = ParseIntegerToken(declared_type, token);
                        const auto* integer = parsed ? std::get_if<std::uint64_t>(&*parsed) : nullptr;
                        if (integer == nullptr) {
                            return std::nullopt;
                        }
                        values.push_back(*integer);
                    }
                    return ScalarValue(std::move(values));
                }

                IntegerArray values;
                values.reserve(tokens.size());
                for (const auto& token : tokens) {
                    const auto parsed = ParseIntegerToken(declared_type, token);
                    const auto* integer = parsed ? std::get_if<std::int64_t>(&*parsed) : nullptr;
                    if (integer == nullptr) {
                        return std::nullopt;
                    }
                    values.push_back(*integer);
                }
                return ScalarValue(std::move(values));
            }
            case ScalarType::kBoolean: {
                BooleanArray values;
                values.reserve(tokens.size());
                for (const auto& token : tokens) {
                    values.push_back(token == "true" || token == "1");
                }
                return ScalarValue(std::move(values));
            }
            case ScalarType::kString:
                return ScalarValue(StringArray(tokens.begin(), tokens.end()));
            case ScalarType::kBinary: {
                BinaryArray values;
                values.reserve(tokens.size());
                for (const auto& token : tokens) {
                    const auto decoded = DecodeBase64(token);
                    if (!decoded.has_value()) {
                        return std::nullopt;
                    }
                    values.push_back(*decoded);
                }
                return ScalarValue(std::move(values));
            }
            case ScalarType::kClock: {
                BooleanArray values;
                values.reserve(tokens.size());
                for (const auto& token : tokens) {
                    values.push_back(token == "true" || token == "1");
                }
                return ScalarValue(std::move(values));
            }
        }
    } catch (...) {
        return std::nullopt;
    }
    return std::nullopt;
}

ScalarType ParseScalarType(const std::string_view tag_name) {
    if (tag_name == "Integer" || tag_name == "Int8" || tag_name == "UInt8" || tag_name == "Int16" ||
        tag_name == "UInt16" || tag_name == "Int32" || tag_name == "UInt32" || tag_name == "Int64" ||
        tag_name == "UInt64") {
        return ScalarType::kInteger;
    }
    if (tag_name == "Boolean") {
        return ScalarType::kBoolean;
    }
    if (tag_name == "String") {
        return ScalarType::kString;
    }
    if (tag_name == "Binary") {
        return ScalarType::kBinary;
    }
    if (tag_name == "Clock") {
        return ScalarType::kClock;
    }
    if (tag_name == "Enumeration") {
        return ScalarType::kEnumeration;
    }
    return ScalarType::kReal;
}

/** Parse one ScalarVariable XML block into the runtime variable model. */
// codeql[cpp/poorly-documented-function]
bool ParseVariableBlock(const std::string& block, VariableInfo* output) {
    if (block.rfind("<ScalarVariable", 0) != 0) {
        const std::size_t open_end = block.find('>');
        if (open_end == std::string::npos) {
            return false;
        }
        std::size_t tag_name_end = 1;
        while (tag_name_end < block.size() && !std::isspace(static_cast<unsigned char>(block[tag_name_end])) &&
               block[tag_name_end] != '/' && block[tag_name_end] != '>') {
            ++tag_name_end;
        }
        const std::string tag_name = block.substr(1, tag_name_end - 1);
        const auto attributes = ParseAttributes(block.substr(0, open_end + 1));
        auto name_it = attributes.find("name");
        auto vr_it = attributes.find("valueReference");
        if (name_it == attributes.end() || vr_it == attributes.end()) {
            return false;
        }

        VariableInfo info;
        info.name = name_it->second;
        info.value_reference = static_cast<std::uint32_t>(std::stoul(vr_it->second));
        info.type = ParseScalarType(tag_name);
        info.declared_type = tag_name;
        if (auto it = attributes.find("causality"); it != attributes.end()) {
            info.causality = it->second;
        }
        if (auto it = attributes.find("variability"); it != attributes.end()) {
            info.variability = it->second;
        }
        if (auto it = attributes.find("initial"); it != attributes.end()) {
            info.initial = it->second;
        }
        if (auto it = attributes.find("reinit"); it != attributes.end()) {
            if (it->second == "true") {
                info.reinit = true;
            } else if (it->second == "false") {
                info.reinit = false;
            } else {
                return false;
            }
        }
        if (auto it = attributes.find("derivative"); it != attributes.end()) {
            try {
                const auto raw_reference = std::stoull(it->second);
                if (raw_reference > std::numeric_limits<std::uint32_t>::max()) return false;
                info.derivative_reference = static_cast<std::uint32_t>(raw_reference);
            } catch (...) {
                return false;
            }
        }
        if (auto it = attributes.find("unit"); it != attributes.end()) {
            info.unit = it->second;
        }
        if (auto it = attributes.find("start"); it != attributes.end()) {
            info.start_value = ParseScalarValue(info.declared_type, info.type, it->second);
        }
        const std::regex dimension_pattern(R"tag(<Dimension\b([^>]*)/?>)tag");
        for (std::sregex_iterator it(block.begin(), block.end(), dimension_pattern), end; it != end; ++it) {
            DimensionInfo dimension;
            const auto dimension_attributes = ParseAttributes((*it)[0].str());
            if (auto attr = dimension_attributes.find("valueReference"); attr != dimension_attributes.end()) {
                dimension.value_reference = static_cast<std::uint32_t>(std::stoul(attr->second));
            }
            if (auto attr = dimension_attributes.find("start"); attr != dimension_attributes.end()) {
                dimension.start = static_cast<std::int32_t>(std::stoi(attr->second));
            }
            info.dimensions.emplace_back(std::move(dimension));
        }
        if (info.type == ScalarType::kString || info.type == ScalarType::kBinary) {
            std::vector<std::string> starts;
            const std::regex start_pattern(R"tag(<Start\b([^>]*)/?>)tag");
            for (std::sregex_iterator it(block.begin(), block.end(), start_pattern), end; it != end; ++it) {
                const auto start_attributes = ParseAttributes((*it)[0].str());
                const auto value = start_attributes.find("value");
                starts.push_back(value == start_attributes.end() ? std::string() : value->second);
            }
            if (!starts.empty()) {
                const bool is_array = !info.dimensions.empty() || starts.size() > 1;
                if (info.type == ScalarType::kString) {
                    if (is_array) {
                        info.start_value = ScalarValue(StringArray(starts.begin(), starts.end()));
                    } else {
                        info.start_value = ScalarValue(starts.front());
                    }
                } else {
                    BinaryArray values;
                    values.reserve(starts.size());
                    bool valid = true;
                    for (const auto& start : starts) {
                        auto decoded = DecodeHexBinary(start);
                        if (!decoded.has_value()) {
                            valid = false;
                            break;
                        }
                        values.push_back(std::move(*decoded));
                    }
                    if (valid) {
                        if (is_array) {
                            info.start_value = ScalarValue(std::move(values));
                        } else {
                            info.start_value = ScalarValue(std::move(values.front()));
                        }
                    }
                }
            }
        } else if (!info.dimensions.empty()) {
            if (auto it = attributes.find("start"); it != attributes.end()) {
                info.start_value = ParseArrayValue(info.declared_type, info.type, it->second);
            }
        }
        *output = std::move(info);
        return true;
    }

    const std::size_t open_end = block.find('>');
    if (open_end == std::string::npos) {
        return false;
    }
    const auto scalar_attributes = ParseAttributes(block.substr(0, open_end + 1));
    auto name_it = scalar_attributes.find("name");
    auto vr_it = scalar_attributes.find("valueReference");
    if (name_it == scalar_attributes.end() || vr_it == scalar_attributes.end()) {
        return false;
    }

    VariableInfo info;
    info.name = name_it->second;
    info.value_reference = static_cast<std::uint32_t>(std::stoul(vr_it->second));
    if (auto it = scalar_attributes.find("causality"); it != scalar_attributes.end()) {
        info.causality = it->second;
    }
    if (auto it = scalar_attributes.find("variability"); it != scalar_attributes.end()) {
        info.variability = it->second;
    }
    if (auto it = scalar_attributes.find("initial"); it != scalar_attributes.end()) {
        info.initial = it->second;
    }
    if (auto it = scalar_attributes.find("derivative"); it != scalar_attributes.end()) {
        try {
            const auto raw_reference = std::stoull(it->second);
            if (raw_reference > std::numeric_limits<std::uint32_t>::max()) return false;
            info.derivative_reference = static_cast<std::uint32_t>(raw_reference);
        } catch (...) {
            return false;
        }
    }

    const char* type_names[] = {"Real", "Integer", "Boolean", "String", "Enumeration", "Binary", "Clock"};
    for (const char* type_name : type_names) {
        const std::string needle = std::string("<") + type_name;
        const std::size_t type_start = block.find(needle);
        if (type_start == std::string::npos) {
            continue;
        }
        const std::size_t type_end = block.find('>', type_start);
        if (type_end == std::string::npos) {
            return false;
        }
        info.type = ParseScalarType(type_name);
        const auto type_attributes = ParseAttributes(block.substr(type_start, type_end - type_start + 1));
        info.declared_type = type_name;
        if (auto unit_it = type_attributes.find("unit"); unit_it != type_attributes.end()) {
            info.unit = unit_it->second;
        }
        if (auto start_it = type_attributes.find("start"); start_it != type_attributes.end()) {
            info.start_value = ParseScalarValue(info.declared_type, info.type, start_it->second);
        }
        *output = std::move(info);
        return true;
    }

    *output = std::move(info);
    return true;
}

}  // namespace

const VariableInfo* FindVariableByName(const ModelDescription& model, const std::string& name) {
    const auto it = model.by_name.find(name);
    if (it == model.by_name.end()) {
        return nullptr;
    }
    return &model.variables[it->second];
}

const VariableInfo* FindVariableByValueReference(const ModelDescription& model, const std::uint32_t value_reference) {
    const auto it = model.by_value_reference.find(value_reference);
    if (it == model.by_value_reference.end()) {
        return nullptr;
    }
    return &model.variables[it->second];
}

const char* ToString(const ScalarType type) {
    switch (type) {
        case ScalarType::kReal:
            return "Real";
        case ScalarType::kInteger:
            return "Integer";
        case ScalarType::kBoolean:
            return "Boolean";
        case ScalarType::kString:
            return "String";
        case ScalarType::kEnumeration:
            return "Enumeration";
        case ScalarType::kBinary:
            return "Binary";
        case ScalarType::kClock:
            return "Clock";
    }
    return "Real";
}

/** Parse FMI model-description XML without relying on a general-purpose XML DOM. */
// codeql[cpp/poorly-documented-function]
ValueResult<ModelDescription> ParseModelDescriptionXml(const std::string& xml) {
    ModelDescription model;

    const std::size_t root_start = xml.find("<fmiModelDescription");
    if (root_start == std::string::npos) {
        return ValueResult<ModelDescription>::Failure(
            "MODEL_DESCRIPTION_INVALID",
            "Missing <fmiModelDescription> root element");
    }
    const std::size_t root_end = xml.find('>', root_start);
    if (root_end == std::string::npos) {
        return ValueResult<ModelDescription>::Failure(
            "MODEL_DESCRIPTION_INVALID",
            "Invalid <fmiModelDescription> root element");
    }
    const auto root_attributes = ParseAttributes(xml.substr(root_start, root_end - root_start + 1));
    if (auto it = root_attributes.find("fmiVersion"); it != root_attributes.end()) {
        model.fmi_version = it->second;
    }
    if (auto it = root_attributes.find("modelName"); it != root_attributes.end()) {
        model.model_name = it->second;
    }
    if (auto guid_it = root_attributes.find("guid"); guid_it != root_attributes.end()) {
        model.guid = guid_it->second;
    } else if (auto token_it = root_attributes.find("instantiationToken"); token_it != root_attributes.end()) {
        model.guid = token_it->second;
    }

    model.supports_co_simulation = xml.find("<CoSimulation") != std::string::npos;
    model.supports_model_exchange = xml.find("<ModelExchange") != std::string::npos;
    if (auto count = root_attributes.find("numberOfEventIndicators"); count != root_attributes.end()) {
        try {
            const auto parsed = std::stoull(count->second);
            if (parsed <= std::numeric_limits<std::size_t>::max()) {
                model.number_of_event_indicators = static_cast<std::size_t>(parsed);
            }
        } catch (...) {
            return ValueResult<ModelDescription>::Failure(
                "MODEL_DESCRIPTION_INVALID",
                "Invalid numberOfEventIndicators attribute");
        }
    }

    const std::size_t default_start = xml.find("<DefaultExperiment");
    if (default_start != std::string::npos) {
        const std::size_t default_end = xml.find('>', default_start);
        if (default_end != std::string::npos) {
            const auto default_attributes = ParseAttributes(xml.substr(default_start, default_end - default_start + 1));
            model.default_start_time = OptionalDouble(default_attributes, "startTime");
            model.default_stop_time = OptionalDouble(default_attributes, "stopTime");
            model.default_step_size = OptionalDouble(default_attributes, "stepSize");
        }
    }

    std::size_t cursor = 0;
    while ((cursor = xml.find("<ScalarVariable", cursor)) != std::string::npos) {
        const std::size_t close = xml.find("</ScalarVariable>", cursor);
        if (close == std::string::npos) {
            return ValueResult<ModelDescription>::Failure(
                "MODEL_DESCRIPTION_INVALID",
                "Unterminated <ScalarVariable> element");
        }
        const std::size_t block_end = close + std::string("</ScalarVariable>").size();
        VariableInfo variable;
        if (!ParseVariableBlock(xml.substr(cursor, block_end - cursor), &variable)) {
            return ValueResult<ModelDescription>::Failure(
                "MODEL_DESCRIPTION_INVALID",
                "Unable to parse ScalarVariable entry");
        }
        model.by_value_reference.emplace(variable.value_reference, model.variables.size());
        model.by_name.emplace(variable.name, model.variables.size());
        model.variables.emplace_back(std::move(variable));
        cursor = block_end;
    }

    if (model.variables.empty()) {
        const std::size_t model_variables_start = xml.find("<ModelVariables");
        if (model_variables_start != std::string::npos) {
            const std::size_t model_variables_open_end = xml.find('>', model_variables_start);
            const std::size_t model_variables_end = xml.find("</ModelVariables>", model_variables_start);
            if (model_variables_open_end != std::string::npos && model_variables_end != std::string::npos) {
                const std::string model_variables_xml = xml.substr(
                    model_variables_open_end + 1,
                    model_variables_end - model_variables_open_end - 1);
                const std::set<std::string> supported_tags = {
                    "Float32", "Float64", "Int8", "UInt8", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64",
                    "Boolean", "String", "Binary", "Clock",
                };
                std::size_t variable_cursor = 0;
                while ((variable_cursor = model_variables_xml.find('<', variable_cursor)) != std::string::npos) {
                    if (variable_cursor + 1 >= model_variables_xml.size() || model_variables_xml[variable_cursor + 1] == '/') {
                        ++variable_cursor;
                        continue;
                    }
                    std::size_t tag_name_end = variable_cursor + 1;
                    while (tag_name_end < model_variables_xml.size() &&
                           !std::isspace(static_cast<unsigned char>(model_variables_xml[tag_name_end])) &&
                           model_variables_xml[tag_name_end] != '/' &&
                           model_variables_xml[tag_name_end] != '>') {
                        ++tag_name_end;
                    }
                    const std::string tag_name = model_variables_xml.substr(variable_cursor + 1, tag_name_end - variable_cursor - 1);
                    if (supported_tags.find(tag_name) == supported_tags.end()) {
                        variable_cursor = tag_name_end;
                        continue;
                    }
                    const std::size_t open_end = model_variables_xml.find('>', tag_name_end);
                    if (open_end == std::string::npos) {
                        return ValueResult<ModelDescription>::Failure(
                            "MODEL_DESCRIPTION_INVALID",
                            "Unable to parse FMI 3 variable element");
                    }
                    std::size_t block_end = open_end + 1;
                    if (!(open_end > variable_cursor && model_variables_xml[open_end - 1] == '/')) {
                        const std::string close_tag = "</" + tag_name + ">";
                        const std::size_t close = model_variables_xml.find(close_tag, open_end + 1);
                        if (close == std::string::npos) {
                            return ValueResult<ModelDescription>::Failure(
                                "MODEL_DESCRIPTION_INVALID",
                                "Unterminated FMI 3 variable element");
                        }
                        block_end = close + close_tag.size();
                    }
                    VariableInfo variable;
                    if (!ParseVariableBlock(model_variables_xml.substr(variable_cursor, block_end - variable_cursor), &variable)) {
                        return ValueResult<ModelDescription>::Failure(
                            "MODEL_DESCRIPTION_INVALID",
                            "Unable to parse FMI 3 variable entry");
                    }
                    model.by_value_reference.emplace(variable.value_reference, model.variables.size());
                    model.by_name.emplace(variable.name, model.variables.size());
                    model.variables.emplace_back(std::move(variable));
                    variable_cursor = block_end;
                }
            }
        }
    }

    auto parse_reference = [](const std::string& text) -> std::optional<std::uint32_t> {
        try {
            const unsigned long long value = std::stoull(text);
            if (value <= std::numeric_limits<std::uint32_t>::max()) {
                return static_cast<std::uint32_t>(value);
            }
        } catch (...) {
        }
        return std::nullopt;
    };
    auto reference_from_fmi2_index = [&model](const std::string& text) -> std::optional<std::uint32_t> {
        try {
            const unsigned long long index = std::stoull(text);
            if (index > 0 && index <= model.variables.size()) {
                return model.variables[static_cast<std::size_t>(index - 1)].value_reference;
            }
        } catch (...) {
        }
        return std::nullopt;
    };
    auto parse_fmi3_structure_list = [&](const std::string& element_name,
                                         const std::string& destination_name) -> bool {
        std::vector<std::uint32_t>* destination = destination_name == "derivatives"
            ? &model.continuous_state_derivative_references
            : &model.event_indicator_references;
        const std::string opening = "<" + element_name;
        std::size_t structure_start = xml.find("<ModelStructure");
        if (structure_start == std::string::npos) {
            return true;
        }
        const std::size_t structure_end = xml.find("</ModelStructure>", structure_start);
        if (structure_end == std::string::npos) {
            return true;
        }
        std::size_t position = structure_start;
        while ((position = xml.find(opening, position)) != std::string::npos && position < structure_end) {
            const std::size_t boundary = position + opening.size();
            if (boundary < xml.size() && !std::isspace(static_cast<unsigned char>(xml[boundary]))
                && xml[boundary] != '>' && xml[boundary] != '/') {
                position = boundary;
                continue;
            }
            const std::size_t element_end = xml.find('>', position);
            if (element_end == std::string::npos || element_end > structure_end) {
                return false;
            }
            const auto attributes = ParseAttributes(xml.substr(position, element_end - position + 1));
            const auto raw_reference = attributes.find("valueReference");
            const auto reference = raw_reference == attributes.end()
                ? std::nullopt
                : parse_reference(raw_reference->second);
            if (!reference.has_value() || model.by_value_reference.find(*reference) == model.by_value_reference.end()) {
                return false;
            }
            destination->push_back(*reference);
            position = element_end + 1;
        }
        return true;
    };
    auto parse_fmi2_unknown_group = [&](const std::string& group_name,
                                        std::vector<std::uint32_t>* destination) -> bool {
        const std::string opening = "<" + group_name;
        const std::size_t group_start = xml.find(opening);
        if (group_start == std::string::npos) {
            return true;
        }
        const std::size_t group_open_end = xml.find('>', group_start);
        const std::size_t group_end = xml.find("</" + group_name + ">", group_start);
        if (group_open_end == std::string::npos || group_end == std::string::npos) {
            return false;
        }
        std::size_t position = group_open_end + 1;
        while ((position = xml.find("<Unknown", position)) != std::string::npos && position < group_end) {
            const std::size_t element_end = xml.find('>', position);
            if (element_end == std::string::npos || element_end > group_end) {
                return false;
            }
            const auto attributes = ParseAttributes(xml.substr(position, element_end - position + 1));
            const auto raw_index = attributes.find("index");
            const auto reference = raw_index == attributes.end()
                ? std::nullopt
                : reference_from_fmi2_index(raw_index->second);
            if (!reference.has_value()) {
                return false;
            }
            destination->push_back(*reference);
            position = element_end + 1;
        }
        return true;
    };

    if (model.fmi_version.rfind("3", 0) == 0) {
        if (!parse_fmi3_structure_list("ContinuousStateDerivative", "derivatives")
            || !parse_fmi3_structure_list("EventIndicator", "eventIndicators")) {
            return ValueResult<ModelDescription>::Failure(
                "MODEL_DESCRIPTION_INVALID",
                "Invalid FMI 3 ModelStructure state or event indicator reference");
        }
    } else {
        if (!parse_fmi2_unknown_group("Derivatives", &model.continuous_state_derivative_references)) {
            return ValueResult<ModelDescription>::Failure(
                "MODEL_DESCRIPTION_INVALID",
                "Invalid FMI 2 ModelStructure derivative reference");
        }
    }

    if (model.supports_model_exchange) {
        for (const std::uint32_t derivative_reference : model.continuous_state_derivative_references) {
            const VariableInfo* derivative_variable = FindVariableByValueReference(model, derivative_reference);
            if (derivative_variable == nullptr || !derivative_variable->derivative_reference.has_value()) {
                return ValueResult<ModelDescription>::Failure(
                    "MODEL_DESCRIPTION_INVALID",
                    "Model Exchange derivative is missing its state-variable mapping");
            }
            const auto state_reference = model.fmi_version.rfind("3", 0) == 0
                ? derivative_variable->derivative_reference
                : reference_from_fmi2_index(std::to_string(*derivative_variable->derivative_reference));
            if (!state_reference.has_value() || FindVariableByValueReference(model, *state_reference) == nullptr) {
                return ValueResult<ModelDescription>::Failure(
                    "MODEL_DESCRIPTION_INVALID",
                    "Model Exchange derivative references an unknown state variable");
            }
            model.continuous_state_value_references.push_back(*state_reference);
        }
    }

    auto variable_extent = [&model](const VariableInfo& variable) -> std::optional<std::size_t> {
        const auto scalar_extent = [](const ScalarValue& value) -> std::optional<std::size_t> {
            if (const auto* signed_value = std::get_if<std::int64_t>(&value)) {
                if (*signed_value >= 0) return static_cast<std::size_t>(*signed_value);
            } else if (const auto* unsigned_value = std::get_if<std::uint64_t>(&value)) {
                if (*unsigned_value <= std::numeric_limits<std::size_t>::max()) return static_cast<std::size_t>(*unsigned_value);
            } else if (const auto* real_value = std::get_if<double>(&value)) {
                if (std::isfinite(*real_value) && *real_value >= 0.0 && std::floor(*real_value) == *real_value
                    && *real_value <= static_cast<double>(std::numeric_limits<std::size_t>::max())) {
                    return static_cast<std::size_t>(*real_value);
                }
            }
            return std::nullopt;
        };
        std::size_t size = 1;
        for (const auto& dimension : variable.dimensions) {
            std::optional<std::size_t> extent;
            if (dimension.start.has_value() && *dimension.start >= 0) {
                extent = static_cast<std::size_t>(*dimension.start);
            } else if (dimension.value_reference.has_value()) {
                const VariableInfo* dimension_variable = FindVariableByValueReference(model, *dimension.value_reference);
                if (dimension_variable != nullptr && dimension_variable->start_value.has_value()) {
                    extent = scalar_extent(*dimension_variable->start_value);
                }
            }
            if (!extent.has_value() || (*extent != 0 && size > std::numeric_limits<std::size_t>::max() / *extent)) {
                return std::nullopt;
            }
            size *= *extent;
        }
        return size;
    };
    for (const std::uint32_t reference : model.continuous_state_derivative_references) {
        const VariableInfo* variable = FindVariableByValueReference(model, reference);
        const auto size = variable == nullptr ? std::nullopt : variable_extent(*variable);
        if (!size.has_value() || *size > std::numeric_limits<std::size_t>::max() - model.number_of_continuous_states) {
            return ValueResult<ModelDescription>::Failure(
                "MODEL_DESCRIPTION_INVALID",
                "Unable to resolve FMI continuous-state dimensions");
        }
        model.number_of_continuous_states += *size;
    }
    if (!model.event_indicator_references.empty()) {
        model.number_of_event_indicators = 0;
        for (const std::uint32_t reference : model.event_indicator_references) {
            const VariableInfo* variable = FindVariableByValueReference(model, reference);
            const auto size = variable == nullptr ? std::nullopt : variable_extent(*variable);
            if (!size.has_value() || *size > std::numeric_limits<std::size_t>::max() - model.number_of_event_indicators) {
                return ValueResult<ModelDescription>::Failure(
                    "MODEL_DESCRIPTION_INVALID",
                    "Unable to resolve FMI event-indicator dimensions");
            }
            model.number_of_event_indicators += *size;
        }
    }

    return ValueResult<ModelDescription>::Success(std::move(model));
}

ValueResult<ModelDescription> LoadModelDescriptionFromFile(const std::string& path) {
    std::string xml = ReadFileText(path);
    if (xml.empty()) {
        return ValueResult<ModelDescription>::Failure(
            "MODEL_DESCRIPTION_IO_ERROR",
            "Unable to read modelDescription.xml from " + path);
    }
    return ParseModelDescriptionXml(xml);
}

}  // namespace decentralabs::proxy
