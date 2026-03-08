#include "decentralabs_proxy/transport.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <limits>
#include <optional>
#include <stdexcept>
#include <string_view>
#include <utility>

#if defined(_WIN32)
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <winhttp.h>
#endif

namespace decentralabs::proxy {

#if defined(_WIN32)
namespace {

struct ParsedGatewayUrl {
    std::string scheme;
    std::string host;
    std::string path;
    INTERNET_PORT port = 0;
    bool secure = false;
    bool allow_insecure_tls = false;
};

std::string ToLowerCopy(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](const unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return value;
}

bool IsLoopbackHost(const std::string& host) {
    const std::string normalized = ToLowerCopy(host);
    return normalized == "localhost" || normalized == "127.0.0.1" || normalized == "::1" || normalized == "[::1]";
}

ValueResult<ParsedGatewayUrl> ParseGatewayUrl(const std::string& url) {
    const std::size_t scheme_end = url.find("://");
    if (scheme_end == std::string::npos) {
        return ValueResult<ParsedGatewayUrl>::Failure(
            "TRANSPORT_URL_INVALID",
            "Gateway URL is missing a scheme");
    }

    ParsedGatewayUrl parsed;
    parsed.scheme = ToLowerCopy(url.substr(0, scheme_end));
    if (parsed.scheme == "wss") {
        parsed.secure = true;
        parsed.port = INTERNET_DEFAULT_HTTPS_PORT;
    } else if (parsed.scheme == "ws") {
        parsed.secure = false;
        parsed.port = INTERNET_DEFAULT_HTTP_PORT;
    } else {
        return ValueResult<ParsedGatewayUrl>::Failure(
            "TRANSPORT_URL_INVALID",
            "Gateway URL must use ws:// or wss://");
    }

    const std::string_view remainder(url.data() + scheme_end + 3, url.size() - scheme_end - 3);
    const std::size_t path_start = remainder.find('/');
    const std::string authority = path_start == std::string::npos
        ? std::string(remainder)
        : std::string(remainder.substr(0, path_start));
    parsed.path = path_start == std::string::npos
        ? "/"
        : std::string(remainder.substr(path_start));

    const std::size_t fragment = parsed.path.find('#');
    if (fragment != std::string::npos) {
        parsed.path.erase(fragment);
    }
    if (authority.empty()) {
        return ValueResult<ParsedGatewayUrl>::Failure(
            "TRANSPORT_URL_INVALID",
            "Gateway URL is missing a host");
    }

    if (!authority.empty() && authority.front() == '[') {
        const std::size_t closing_bracket = authority.find(']');
        if (closing_bracket == std::string::npos) {
            return ValueResult<ParsedGatewayUrl>::Failure(
                "TRANSPORT_URL_INVALID",
                "Gateway URL contains an invalid IPv6 host");
        }
        parsed.host = authority.substr(1, closing_bracket - 1);
        if (closing_bracket + 1 < authority.size()) {
            if (authority[closing_bracket + 1] != ':') {
                return ValueResult<ParsedGatewayUrl>::Failure(
                    "TRANSPORT_URL_INVALID",
                    "Gateway URL contains an invalid host/port separator");
            }
            const std::string port_text = authority.substr(closing_bracket + 2);
            if (port_text.empty()) {
                return ValueResult<ParsedGatewayUrl>::Failure(
                    "TRANSPORT_URL_INVALID",
                    "Gateway URL port is empty");
            }
            try {
                const auto port_value = std::stoul(port_text);
                if (port_value > std::numeric_limits<INTERNET_PORT>::max()) {
                    throw std::out_of_range("port");
                }
                parsed.port = static_cast<INTERNET_PORT>(port_value);
            } catch (const std::exception&) {
                return ValueResult<ParsedGatewayUrl>::Failure(
                    "TRANSPORT_URL_INVALID",
                    "Gateway URL contains an invalid port");
            }
        }
    } else {
        const std::size_t colon = authority.rfind(':');
        if (colon != std::string::npos && authority.find(':') == colon) {
            parsed.host = authority.substr(0, colon);
            const std::string port_text = authority.substr(colon + 1);
            if (parsed.host.empty() || port_text.empty()) {
                return ValueResult<ParsedGatewayUrl>::Failure(
                    "TRANSPORT_URL_INVALID",
                    "Gateway URL contains an invalid host or port");
            }
            try {
                const auto port_value = std::stoul(port_text);
                if (port_value > std::numeric_limits<INTERNET_PORT>::max()) {
                    throw std::out_of_range("port");
                }
                parsed.port = static_cast<INTERNET_PORT>(port_value);
            } catch (const std::exception&) {
                return ValueResult<ParsedGatewayUrl>::Failure(
                    "TRANSPORT_URL_INVALID",
                    "Gateway URL contains an invalid port");
            }
        } else {
            parsed.host = authority;
        }
    }

    if (parsed.host.empty()) {
        return ValueResult<ParsedGatewayUrl>::Failure(
            "TRANSPORT_URL_INVALID",
            "Gateway URL host is empty");
    }

    parsed.allow_insecure_tls = parsed.secure && IsLoopbackHost(parsed.host);
    return ValueResult<ParsedGatewayUrl>::Success(std::move(parsed));
}

std::wstring Utf8ToWide(const std::string& text) {
    if (text.empty()) {
        return {};
    }
    const int size = MultiByteToWideChar(CP_UTF8, 0, text.c_str(), static_cast<int>(text.size()), nullptr, 0);
    if (size <= 0) {
        return {};
    }
    std::wstring wide(static_cast<std::size_t>(size), L'\0');
    const int written = MultiByteToWideChar(CP_UTF8, 0, text.c_str(), static_cast<int>(text.size()), wide.data(), size);
    if (written != size) {
        return {};
    }
    return wide;
}

std::string WideToUtf8(const std::wstring& text) {
    if (text.empty()) {
        return {};
    }
    const int size = WideCharToMultiByte(CP_UTF8, 0, text.c_str(), static_cast<int>(text.size()), nullptr, 0, nullptr, nullptr);
    if (size <= 0) {
        return {};
    }
    std::string narrow(static_cast<std::size_t>(size), '\0');
    const int written = WideCharToMultiByte(CP_UTF8, 0, text.c_str(), static_cast<int>(text.size()), narrow.data(), size, nullptr, nullptr);
    if (written != size) {
        return {};
    }
    return narrow;
}

std::string TrimTrailingWhitespace(std::string value) {
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back()))) {
        value.pop_back();
    }
    return value;
}

std::string FormatWinHttpError(const DWORD error_code) {
    std::wstring message_wide;
    wchar_t* buffer = nullptr;
    const HMODULE module = GetModuleHandleW(L"winhttp.dll");
    const DWORD flags = FORMAT_MESSAGE_ALLOCATE_BUFFER
        | FORMAT_MESSAGE_IGNORE_INSERTS
        | FORMAT_MESSAGE_FROM_SYSTEM
        | (module != nullptr ? FORMAT_MESSAGE_FROM_HMODULE : 0);
    const DWORD length = FormatMessageW(
        flags,
        module,
        error_code,
        0,
        reinterpret_cast<LPWSTR>(&buffer),
        0,
        nullptr);
    if (length != 0 && buffer != nullptr) {
        message_wide.assign(buffer, length);
        LocalFree(buffer);
    }
    std::string message = TrimTrailingWhitespace(WideToUtf8(message_wide));
    if (message.empty()) {
        message = "WinHTTP error " + std::to_string(error_code);
    } else {
        message += " (" + std::to_string(error_code) + ")";
    }
    return message;
}

template <typename T>
void CloseInternetHandle(T& handle) {
    if (handle != nullptr) {
        WinHttpCloseHandle(handle);
        handle = nullptr;
    }
}

class WinHttpWssTransport final : public GatewayTransport {
public:
    OperationResult Connect(const std::string& url) override {
        Close();

        const auto parsed = ParseGatewayUrl(url);
        if (!parsed) {
            return parsed.status;
        }

        session_ = WinHttpOpen(
            L"DecentraLabsProxyRuntime/0.1",
            WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
            WINHTTP_NO_PROXY_NAME,
            WINHTTP_NO_PROXY_BYPASS,
            0);
        if (session_ == nullptr) {
            return FailureFromLastError("TRANSPORT_CONNECT_FAILED", "Failed to open WinHTTP session");
        }

        if (!WinHttpSetTimeouts(session_, 10000, 10000, 15000, 15000)) {
            return FailureFromLastError("TRANSPORT_CONNECT_FAILED", "Failed to configure WinHTTP timeouts");
        }

        const std::wstring host = Utf8ToWide(parsed.value.host);
        const std::wstring path = Utf8ToWide(parsed.value.path);
        if (host.empty() || path.empty()) {
            return OperationResult::Failure(
                "TRANSPORT_URL_INVALID",
                "Gateway URL contains characters that could not be converted for WinHTTP");
        }

        connection_ = WinHttpConnect(session_, host.c_str(), parsed.value.port, 0);
        if (connection_ == nullptr) {
            return FailureFromLastError("TRANSPORT_CONNECT_FAILED", "Failed to connect WinHTTP session");
        }

        request_ = WinHttpOpenRequest(
            connection_,
            L"GET",
            path.c_str(),
            nullptr,
            WINHTTP_NO_REFERER,
            WINHTTP_DEFAULT_ACCEPT_TYPES,
            parsed.value.secure ? WINHTTP_FLAG_SECURE : 0);
        if (request_ == nullptr) {
            return FailureFromLastError("TRANSPORT_CONNECT_FAILED", "Failed to create WinHTTP websocket request");
        }

        if (!WinHttpSetOption(request_, WINHTTP_OPTION_UPGRADE_TO_WEB_SOCKET, nullptr, 0)) {
            return FailureFromLastError("TRANSPORT_CONNECT_FAILED", "Failed to enable websocket upgrade");
        }

        if (parsed.value.secure) {
            if (!WinHttpSetOption(
                    request_,
                    WINHTTP_OPTION_CLIENT_CERT_CONTEXT,
                    WINHTTP_NO_CLIENT_CERT_CONTEXT,
                    0)) {
                return FailureFromLastError(
                    "TRANSPORT_CONNECT_FAILED",
                    "Failed to disable client certificate selection for secure websocket request");
            }
        }

        if (parsed.value.allow_insecure_tls) {
            DWORD security_flags = SECURITY_FLAG_IGNORE_UNKNOWN_CA
                | SECURITY_FLAG_IGNORE_CERT_DATE_INVALID
                | SECURITY_FLAG_IGNORE_CERT_CN_INVALID
                | SECURITY_FLAG_IGNORE_CERT_WRONG_USAGE;
            if (!WinHttpSetOption(request_, WINHTTP_OPTION_SECURITY_FLAGS, &security_flags, sizeof(security_flags))) {
                return FailureFromLastError("TRANSPORT_CONNECT_FAILED", "Failed to relax loopback TLS validation");
            }
        }

        if (!WinHttpSendRequest(request_, WINHTTP_NO_ADDITIONAL_HEADERS, 0, WINHTTP_NO_REQUEST_DATA, 0, 0, 0)) {
            return FailureFromLastError("TRANSPORT_CONNECT_FAILED", "Failed to send websocket upgrade request");
        }
        if (!WinHttpReceiveResponse(request_, nullptr)) {
            return FailureFromLastError("TRANSPORT_CONNECT_FAILED", "Failed to receive websocket upgrade response");
        }

        websocket_ = WinHttpWebSocketCompleteUpgrade(request_, 0);
        if (websocket_ == nullptr) {
            return FailureFromLastError("TRANSPORT_CONNECT_FAILED", "Failed to complete websocket upgrade");
        }

        CloseInternetHandle(request_);
        url_ = url;
        connected_ = true;
        return OperationResult::Success();
    }

    OperationResult SendText(const std::string& payload) override {
        if (!connected_ || websocket_ == nullptr) {
            return OperationResult::Failure(
                "TRANSPORT_NOT_CONNECTED",
                "Gateway transport is not connected");
        }
        if (payload.size() > std::numeric_limits<DWORD>::max()) {
            return OperationResult::Failure(
                "TRANSPORT_PAYLOAD_TOO_LARGE",
                "Gateway websocket payload exceeds WinHTTP limits");
        }

        const DWORD status = WinHttpWebSocketSend(
            websocket_,
            WINHTTP_WEB_SOCKET_UTF8_MESSAGE_BUFFER_TYPE,
            const_cast<char*>(payload.data()),
            static_cast<DWORD>(payload.size()));
        if (status != NO_ERROR) {
            connected_ = false;
            return OperationResult::Failure(
                "TRANSPORT_SEND_FAILED",
                "Failed to send websocket message: " + FormatWinHttpError(status));
        }
        return OperationResult::Success();
    }

    ValueResult<std::string> ReceiveText() override {
        if (!connected_ || websocket_ == nullptr) {
            return ValueResult<std::string>::Failure(
                "TRANSPORT_NOT_CONNECTED",
                "Gateway transport is not connected");
        }

        std::string payload;
        std::array<char, 4096> buffer{};
        for (;;) {
            WINHTTP_WEB_SOCKET_BUFFER_TYPE buffer_type = WINHTTP_WEB_SOCKET_BINARY_MESSAGE_BUFFER_TYPE;
            DWORD bytes_read = 0;
            const DWORD status = WinHttpWebSocketReceive(
                websocket_,
                buffer.data(),
                static_cast<DWORD>(buffer.size()),
                &bytes_read,
                &buffer_type);

            if (status != NO_ERROR) {
                connected_ = false;
                return ValueResult<std::string>::Failure(
                    "TRANSPORT_RECEIVE_FAILED",
                    "Failed to receive websocket message: " + FormatWinHttpError(status));
            }

            if (buffer_type == WINHTTP_WEB_SOCKET_CLOSE_BUFFER_TYPE) {
                connected_ = false;
                USHORT close_status = WINHTTP_WEB_SOCKET_SUCCESS_CLOSE_STATUS;
                DWORD status_size = 0;
                std::array<unsigned char, 128> close_reason{};
                WinHttpWebSocketQueryCloseStatus(
                    websocket_,
                    &close_status,
                    close_reason.data(),
                    static_cast<DWORD>(close_reason.size()),
                    &status_size);
                std::string reason(
                    reinterpret_cast<const char*>(close_reason.data()),
                    reinterpret_cast<const char*>(close_reason.data()) + status_size);
                std::string message = "Gateway closed websocket";
                if (!reason.empty()) {
                    message += ": " + reason;
                } else {
                    message += " with status " + std::to_string(close_status);
                }
                return ValueResult<std::string>::Failure("TRANSPORT_CLOSED", std::move(message));
            }

            if (buffer_type != WINHTTP_WEB_SOCKET_UTF8_FRAGMENT_BUFFER_TYPE
                && buffer_type != WINHTTP_WEB_SOCKET_UTF8_MESSAGE_BUFFER_TYPE) {
                connected_ = false;
                return ValueResult<std::string>::Failure(
                    "TRANSPORT_PROTOCOL_ERROR",
                    "Gateway websocket returned a non-text frame");
            }

            payload.append(buffer.data(), buffer.data() + bytes_read);
            if (buffer_type == WINHTTP_WEB_SOCKET_UTF8_MESSAGE_BUFFER_TYPE) {
                return ValueResult<std::string>::Success(std::move(payload));
            }
        }
    }

    void Close() override {
        connected_ = false;
        if (websocket_ != nullptr) {
            WinHttpWebSocketClose(websocket_, WINHTTP_WEB_SOCKET_SUCCESS_CLOSE_STATUS, nullptr, 0);
        }
        CloseInternetHandle(websocket_);
        CloseInternetHandle(request_);
        CloseInternetHandle(connection_);
        CloseInternetHandle(session_);
        url_.clear();
    }

    bool IsConnected() const override {
        return connected_;
    }

private:
    OperationResult FailureFromLastError(const std::string& code, const std::string& prefix) {
        const DWORD error_code = GetLastError();
        const std::string message = prefix + ": " + FormatWinHttpError(error_code);
        Close();
        return OperationResult::Failure(code, message);
    }

    HINTERNET session_ = nullptr;
    HINTERNET connection_ = nullptr;
    HINTERNET request_ = nullptr;
    HINTERNET websocket_ = nullptr;
    std::string url_;
    bool connected_ = false;
};

}  // namespace
#endif

OperationResult StubWssTransport::Connect(const std::string& url) {
    url_ = url;
    connected_ = false;
    return OperationResult::Failure(
        "WSS_TRANSPORT_UNAVAILABLE",
        "No native WSS backend is compiled into this FMU proxy runtime yet");
}

OperationResult StubWssTransport::SendText(const std::string&) {
    return OperationResult::Failure(
        "WSS_TRANSPORT_UNAVAILABLE",
        "Cannot send over WSS because no transport backend is compiled");
}

ValueResult<std::string> StubWssTransport::ReceiveText() {
    return ValueResult<std::string>::Failure(
        "WSS_TRANSPORT_UNAVAILABLE",
        "Cannot receive over WSS because no transport backend is compiled");
}

void StubWssTransport::Close() {
    connected_ = false;
}

bool StubWssTransport::IsConnected() const {
    return connected_;
}

void ScriptedTransport::QueueResponse(std::string payload) {
    queued_responses_.emplace_back(std::move(payload));
}

const std::vector<std::string>& ScriptedTransport::SentPayloads() const {
    return sent_payloads_;
}

OperationResult ScriptedTransport::Connect(const std::string& url) {
    url_ = url;
    connected_ = true;
    return OperationResult::Success();
}

OperationResult ScriptedTransport::SendText(const std::string& payload) {
    if (!connected_) {
        return OperationResult::Failure("TRANSPORT_NOT_CONNECTED", "Scripted transport is not connected");
    }
    sent_payloads_.emplace_back(payload);
    return OperationResult::Success();
}

ValueResult<std::string> ScriptedTransport::ReceiveText() {
    if (!connected_) {
        return ValueResult<std::string>::Failure("TRANSPORT_NOT_CONNECTED", "Scripted transport is not connected");
    }
    if (queued_responses_.empty()) {
        return ValueResult<std::string>::Failure("TRANSPORT_NO_RESPONSE", "Scripted transport has no queued response");
    }
    std::string payload = queued_responses_.front();
    queued_responses_.erase(queued_responses_.begin());
    return ValueResult<std::string>::Success(std::move(payload));
}

void ScriptedTransport::Close() {
    connected_ = false;
}

bool ScriptedTransport::IsConnected() const {
    return connected_;
}

std::unique_ptr<GatewayTransport> CreateDefaultGatewayTransport() {
#if defined(_WIN32)
    return std::make_unique<WinHttpWssTransport>();
#else
    return std::make_unique<StubWssTransport>();
#endif
}

}  // namespace decentralabs::proxy
