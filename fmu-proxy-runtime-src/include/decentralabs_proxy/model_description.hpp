#pragma once

#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <variant>
#include <vector>

#include "decentralabs_proxy/operation_result.hpp"

namespace decentralabs::proxy {

enum class ScalarType {
    kReal,
    kInteger,
    kBoolean,
    kString,
    kEnumeration,
};

using RealArray = std::vector<double>;
using IntegerArray = std::vector<std::int32_t>;
using BooleanArray = std::vector<bool>;
using StringArray = std::vector<std::string>;
using ScalarValue = std::variant<double, std::int32_t, bool, std::string, RealArray, IntegerArray, BooleanArray, StringArray>;

struct DimensionInfo {
    std::optional<std::uint32_t> value_reference;
    std::optional<std::int32_t> start;
    std::string variable_name;
};

struct VariableInfo {
    std::string name;
    std::uint32_t value_reference = 0;
    ScalarType type = ScalarType::kReal;
    std::string declared_type;
    std::string causality = "local";
    std::string variability = "continuous";
    std::string unit;
    std::optional<ScalarValue> start_value;
    std::vector<DimensionInfo> dimensions;
};

struct ModelDescription {
    std::string fmi_version = "2.0";
    std::string model_name = "DecentraLabsProxy";
    std::string guid;
    bool supports_co_simulation = false;
    std::optional<double> default_start_time;
    std::optional<double> default_stop_time;
    std::optional<double> default_step_size;
    std::vector<VariableInfo> variables;
    std::map<std::uint32_t, std::size_t> by_value_reference;
    std::map<std::string, std::size_t> by_name;
};

const VariableInfo* FindVariableByName(const ModelDescription& model, const std::string& name);
const VariableInfo* FindVariableByValueReference(const ModelDescription& model, std::uint32_t value_reference);
const char* ToString(ScalarType type);
ValueResult<ModelDescription> ParseModelDescriptionXml(const std::string& xml);
ValueResult<ModelDescription> LoadModelDescriptionFromFile(const std::string& path);

}  // namespace decentralabs::proxy
