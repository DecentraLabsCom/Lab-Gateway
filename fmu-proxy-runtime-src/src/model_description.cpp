#include "decentralabs_proxy/model_description.hpp"

#include <cctype>
#include <cstdlib>
#include <filesystem>
#include <fstream>
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

std::string Trim(const std::string_view text) {
    std::size_t start = 0;
    std::size_t end = text.size();
    while (start < end && std::isspace(static_cast<unsigned char>(text[start]))) {
        ++start;
    }
    while (end > start && std::isspace(static_cast<unsigned char>(text[end - 1]))) {
        --end;
    }
    return std::string(text.substr(start, end - start));
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

std::optional<ScalarValue> ParseScalarValue(const ScalarType type, const std::string& text) {
    if (text.empty()) {
        return std::nullopt;
    }
    try {
        switch (type) {
            case ScalarType::kReal:
                return ScalarValue(std::stod(text));
            case ScalarType::kInteger:
            case ScalarType::kEnumeration:
                return ScalarValue(static_cast<std::int32_t>(std::stoi(text)));
            case ScalarType::kBoolean:
                return ScalarValue(text == "true" || text == "1");
            case ScalarType::kString:
                return ScalarValue(text);
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

std::optional<ScalarValue> ParseArrayValue(const ScalarType type, const std::string& text) {
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
                IntegerArray values;
                values.reserve(tokens.size());
                for (const auto& token : tokens) {
                    values.push_back(static_cast<std::int32_t>(std::stoi(token)));
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
    if (tag_name == "Enumeration") {
        return ScalarType::kEnumeration;
    }
    return ScalarType::kReal;
}

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
        if (auto it = attributes.find("unit"); it != attributes.end()) {
            info.unit = it->second;
        }
        if (auto it = attributes.find("start"); it != attributes.end()) {
            info.start_value = ParseScalarValue(info.type, it->second);
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
        if (!info.dimensions.empty()) {
            if (auto it = attributes.find("start"); it != attributes.end()) {
                info.start_value = ParseArrayValue(info.type, it->second);
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

    const char* type_names[] = {"Real", "Integer", "Boolean", "String", "Enumeration"};
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
            info.start_value = ParseScalarValue(info.type, start_it->second);
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
    }
    return "Real";
}

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
    if (auto it = root_attributes.find("guid"); it != root_attributes.end()) {
        model.guid = it->second;
    } else if (auto it = root_attributes.find("instantiationToken"); it != root_attributes.end()) {
        model.guid = it->second;
    }

    model.supports_co_simulation = xml.find("<CoSimulation") != std::string::npos;

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
