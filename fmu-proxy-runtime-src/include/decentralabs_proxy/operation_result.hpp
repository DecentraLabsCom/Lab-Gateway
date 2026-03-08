#pragma once

#include <string>
#include <utility>

namespace decentralabs::proxy {

struct OperationResult {
    bool ok = true;
    std::string code;
    std::string message;

    explicit operator bool() const {
        return ok;
    }

    static OperationResult Success() {
        return {};
    }

    static OperationResult Failure(std::string error_code, std::string error_message) {
        return OperationResult{
            false,
            std::move(error_code),
            std::move(error_message),
        };
    }
};

template <typename T>
struct ValueResult {
    OperationResult status;
    T value{};

    explicit operator bool() const {
        return static_cast<bool>(status);
    }

    static ValueResult<T> Success(T result) {
        return ValueResult<T>{
            OperationResult::Success(),
            std::move(result),
        };
    }

    static ValueResult<T> Failure(std::string error_code, std::string error_message) {
        return ValueResult<T>{
            OperationResult::Failure(std::move(error_code), std::move(error_message)),
            {},
        };
    }
};

}  // namespace decentralabs::proxy
