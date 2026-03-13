#include "decentralabs_proxy/transport.hpp"

#if defined(__linux__) || defined(__APPLE__)

#include <algorithm>
#include <array>
#include <cctype>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <fcntl.h>
#include <limits>
#include <map>
#include <memory>
#include <stdexcept>
#include <string>
#include <string_view>
#include <vector>

#include <arpa/inet.h>
#include <netdb.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>

#include <openssl/err.h>
#include <openssl/evp.h>
#include <openssl/rand.h>
#include <openssl/sha.h>
#include <openssl/ssl.h>

namespace decentralabs::proxy {
namespace {

struct ParsedGatewayUrl {
    std::string scheme;
    std::string host;
    std::string path;
    std::uint16_t port = 0;
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

std::string TrimTrailingWhitespace(std::string value) {
    while (!value.empty() && std::isspace(static_cast<unsigned char>(value.back()))) {
        value.pop_back();
    }
    return value;
}

std::string FormatSystemError(const int error_code) {
    std::string message = TrimTrailingWhitespace(std::strerror(error_code));
    if (message.empty()) {
        message = "system error " + std::to_string(error_code);
    } else {
        message += " (" + std::to_string(error_code) + ")";
    }
    return message;
}

std::string FormatOpenSslError() {
    std::string message;
    for (;;) {
        const unsigned long error_code = ERR_get_error();
        if (error_code == 0) {
            break;
        }
        char buffer[256] = {};
        ERR_error_string_n(error_code, buffer, sizeof(buffer));
        if (!message.empty()) {
            message += " | ";
        }
        message += TrimTrailingWhitespace(buffer);
    }
    if (message.empty()) {
        message = "OpenSSL error";
    }
    return message;
}

std::string FormatSslError(SSL* ssl, const int ssl_result) {
    const int ssl_error = SSL_get_error(ssl, ssl_result);
    switch (ssl_error) {
        case SSL_ERROR_ZERO_RETURN:
            return "TLS peer closed the connection";
        case SSL_ERROR_SYSCALL:
            if (errno != 0) {
                return "TLS socket error: " + FormatSystemError(errno);
            }
            return "TLS socket error";
        case SSL_ERROR_SSL:
            return FormatOpenSslError();
        default:
            return "OpenSSL error " + std::to_string(ssl_error) + ": " + FormatOpenSslError();
    }
}

bool SetNonBlocking(const int socket_fd, const bool enabled) {
    const int flags = fcntl(socket_fd, F_GETFL, 0);
    if (flags < 0) {
        return false;
    }
    const int next_flags = enabled ? (flags | O_NONBLOCK) : (flags & ~O_NONBLOCK);
    return fcntl(socket_fd, F_SETFL, next_flags) == 0;
}

std::string Base64Encode(const unsigned char* data, const std::size_t length) {
    const int encoded_length = 4 * static_cast<int>((length + 2) / 3);
    std::string encoded(static_cast<std::size_t>(encoded_length), '\0');
    const int written = EVP_EncodeBlock(
        reinterpret_cast<unsigned char*>(encoded.data()),
        data,
        static_cast<int>(length));
    if (written < 0) {
        return {};
    }
    encoded.resize(static_cast<std::size_t>(written));
    return encoded;
}

std::string ComputeWebSocketAccept(const std::string& key) {
    constexpr const char* kWebSocketGuid = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";
    const std::string source = key + kWebSocketGuid;
    unsigned char digest[SHA_DIGEST_LENGTH] = {};
    SHA1(
        reinterpret_cast<const unsigned char*>(source.data()),
        source.size(),
        digest);
    return Base64Encode(digest, sizeof(digest));
}

bool ContainsCaseInsensitiveToken(const std::string& haystack, const std::string& token) {
    std::string normalized = ToLowerCopy(haystack);
    const std::string normalized_token = ToLowerCopy(token);
    std::size_t offset = 0;
    while (offset < normalized.size()) {
        std::size_t comma = normalized.find(',', offset);
        std::string_view part(
            normalized.data() + offset,
            (comma == std::string::npos ? normalized.size() : comma) - offset);
        while (!part.empty() && std::isspace(static_cast<unsigned char>(part.front()))) {
            part.remove_prefix(1);
        }
        while (!part.empty() && std::isspace(static_cast<unsigned char>(part.back()))) {
            part.remove_suffix(1);
        }
        if (part == normalized_token) {
            return true;
        }
        if (comma == std::string::npos) {
            break;
        }
        offset = comma + 1;
    }
    return false;
}

std::string FormatHostHeader(const ParsedGatewayUrl& parsed) {
    const bool is_ipv6 = parsed.host.find(':') != std::string::npos;
    std::string host = is_ipv6 ? ("[" + parsed.host + "]") : parsed.host;
    const bool is_default_port = (parsed.secure && parsed.port == 443) || (!parsed.secure && parsed.port == 80);
    if (!is_default_port) {
        host += ":" + std::to_string(parsed.port);
    }
    return host;
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
        parsed.port = 443;
    } else if (parsed.scheme == "ws") {
        parsed.secure = false;
        parsed.port = 80;
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
                if (port_value > std::numeric_limits<std::uint16_t>::max()) {
                    throw std::out_of_range("port");
                }
                parsed.port = static_cast<std::uint16_t>(port_value);
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
                if (port_value > std::numeric_limits<std::uint16_t>::max()) {
                    throw std::out_of_range("port");
                }
                parsed.port = static_cast<std::uint16_t>(port_value);
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

class OpenSslWssTransport final : public GatewayTransport {
public:
    OperationResult Connect(const std::string& url) override {
        Close();

        const auto parsed = ParseGatewayUrl(url);
        if (!parsed) {
            return parsed.status;
        }

        if (OPENSSL_init_ssl(0, nullptr) != 1) {
            return OperationResult::Failure(
                "TRANSPORT_CONNECT_FAILED",
                "Failed to initialize OpenSSL");
        }

        const auto socket_status = ConnectSocket(parsed.value);
        if (!socket_status) {
            Close();
            return socket_status;
        }

        if (parsed.value.secure) {
            const auto tls_status = EstablishTls(parsed.value);
            if (!tls_status) {
                Close();
                return tls_status;
            }
        }

        const auto handshake_status = PerformWebSocketHandshake(parsed.value);
        if (!handshake_status) {
            Close();
            return handshake_status;
        }

        url_ = url;
        connected_ = true;
        close_sent_ = false;
        return OperationResult::Success();
    }

    OperationResult SendText(const std::string& payload) override {
        if (!connected_ || socket_fd_ < 0) {
            return OperationResult::Failure(
                "TRANSPORT_NOT_CONNECTED",
                "Gateway transport is not connected");
        }
        return SendFrame(0x1, payload, true);
    }

    ValueResult<std::string> ReceiveText() override {
        if (!connected_ || socket_fd_ < 0) {
            return ValueResult<std::string>::Failure(
                "TRANSPORT_NOT_CONNECTED",
                "Gateway transport is not connected");
        }

        std::string message;
        bool fragmented_text = false;
        for (;;) {
            const auto header = ReadExact(2);
            if (!header) {
                connected_ = false;
                Close();
                return ValueResult<std::string>::Failure(header.status.code, header.status.message);
            }

            const unsigned char first = static_cast<unsigned char>(header.value[0]);
            const unsigned char second = static_cast<unsigned char>(header.value[1]);
            const bool fin = (first & 0x80U) != 0;
            const unsigned char opcode = first & 0x0FU;
            const bool masked = (second & 0x80U) != 0;
            std::uint64_t payload_length = static_cast<std::uint64_t>(second & 0x7FU);

            if (masked) {
                connected_ = false;
                Close();
                return ValueResult<std::string>::Failure(
                    "TRANSPORT_PROTOCOL_ERROR",
                    "Gateway websocket returned a masked server frame");
            }

            if (payload_length == 126U) {
                const auto extended = ReadExact(2);
                if (!extended) {
                    connected_ = false;
                    Close();
                    return ValueResult<std::string>::Failure(extended.status.code, extended.status.message);
                }
                payload_length =
                    (static_cast<std::uint64_t>(static_cast<unsigned char>(extended.value[0])) << 8U)
                    | static_cast<std::uint64_t>(static_cast<unsigned char>(extended.value[1]));
            } else if (payload_length == 127U) {
                const auto extended = ReadExact(8);
                if (!extended) {
                    connected_ = false;
                    Close();
                    return ValueResult<std::string>::Failure(extended.status.code, extended.status.message);
                }
                payload_length = 0;
                for (const unsigned char ch : extended.value) {
                    payload_length = (payload_length << 8U) | static_cast<std::uint64_t>(ch);
                }
            }

            if (payload_length > static_cast<std::uint64_t>(std::numeric_limits<std::size_t>::max())) {
                connected_ = false;
                Close();
                return ValueResult<std::string>::Failure(
                    "TRANSPORT_PROTOCOL_ERROR",
                    "Gateway websocket frame is too large");
            }

            const auto payload = ReadExact(static_cast<std::size_t>(payload_length));
            if (!payload) {
                connected_ = false;
                Close();
                return ValueResult<std::string>::Failure(payload.status.code, payload.status.message);
            }

            if (opcode == 0x8U) {
                close_sent_ = true;
                connected_ = false;
                Close();
                return ValueResult<std::string>::Failure(
                    "TRANSPORT_CLOSED",
                    "Gateway closed websocket");
            }

            if (opcode == 0x9U) {
                const auto pong_status = SendFrame(0xAU, payload.value, true);
                if (!pong_status) {
                    connected_ = false;
                    Close();
                    return ValueResult<std::string>::Failure(pong_status.code, pong_status.message);
                }
                continue;
            }

            if (opcode == 0xAU) {
                continue;
            }

            if (opcode == 0x2U) {
                connected_ = false;
                Close();
                return ValueResult<std::string>::Failure(
                    "TRANSPORT_PROTOCOL_ERROR",
                    "Gateway websocket returned a binary frame");
            }

            if (opcode == 0x1U) {
                message.append(payload.value);
                fragmented_text = !fin;
                if (fin) {
                    return ValueResult<std::string>::Success(std::move(message));
                }
                continue;
            }

            if (opcode == 0x0U) {
                if (!fragmented_text) {
                    connected_ = false;
                    Close();
                    return ValueResult<std::string>::Failure(
                        "TRANSPORT_PROTOCOL_ERROR",
                        "Gateway websocket returned an unexpected continuation frame");
                }
                message.append(payload.value);
                if (fin) {
                    return ValueResult<std::string>::Success(std::move(message));
                }
                continue;
            }

            connected_ = false;
            Close();
            return ValueResult<std::string>::Failure(
                "TRANSPORT_PROTOCOL_ERROR",
                "Gateway websocket returned an unsupported opcode");
        }
    }

    void Close() override {
        if (socket_fd_ >= 0 && connected_ && !close_sent_) {
            SendFrame(0x8U, std::string(), true);
        }

        connected_ = false;
        close_sent_ = false;
        pending_bytes_.clear();

        if (ssl_ != nullptr) {
            SSL_shutdown(ssl_);
            SSL_free(ssl_);
            ssl_ = nullptr;
        }
        if (ssl_context_ != nullptr) {
            SSL_CTX_free(ssl_context_);
            ssl_context_ = nullptr;
        }
        if (socket_fd_ >= 0) {
            close(socket_fd_);
            socket_fd_ = -1;
        }
        url_.clear();
    }

    bool IsConnected() const override {
        return connected_;
    }

private:
    OperationResult ConnectSocket(const ParsedGatewayUrl& parsed) {
        addrinfo hints{};
        hints.ai_family = AF_UNSPEC;
        hints.ai_socktype = SOCK_STREAM;

        addrinfo* addresses = nullptr;
        const std::string port_text = std::to_string(parsed.port);
        const int lookup_status = getaddrinfo(parsed.host.c_str(), port_text.c_str(), &hints, &addresses);
        if (lookup_status != 0) {
            return OperationResult::Failure(
                "TRANSPORT_CONNECT_FAILED",
                "DNS resolution failed for gateway host: " + std::string(gai_strerror(lookup_status)));
        }

        std::unique_ptr<addrinfo, decltype(&freeaddrinfo)> address_guard(addresses, &freeaddrinfo);
        OperationResult last_error = OperationResult::Failure(
            "TRANSPORT_CONNECT_FAILED",
            "Failed to connect to the gateway host");

        for (addrinfo* entry = addresses; entry != nullptr; entry = entry->ai_next) {
            const int candidate_socket = socket(entry->ai_family, entry->ai_socktype, entry->ai_protocol);
            if (candidate_socket < 0) {
                last_error = OperationResult::Failure(
                    "TRANSPORT_CONNECT_FAILED",
                    "Failed to open gateway socket: " + FormatSystemError(errno));
                continue;
            }

            socket_fd_ = candidate_socket;
            if (!SetNonBlocking(socket_fd_, true)) {
                last_error = OperationResult::Failure(
                    "TRANSPORT_CONNECT_FAILED",
                    "Failed to configure non-blocking gateway socket: " + FormatSystemError(errno));
                close(socket_fd_);
                socket_fd_ = -1;
                continue;
            }

            const int connect_result = connect(socket_fd_, entry->ai_addr, entry->ai_addrlen);
            if (connect_result == 0) {
                return OperationResult::Success();
            }
            if (connect_result < 0 && errno == EINPROGRESS) {
                const auto wait_status = WaitForSocket(true, 10000);
                if (!wait_status) {
                    last_error = wait_status;
                    close(socket_fd_);
                    socket_fd_ = -1;
                    continue;
                }

                int socket_error = 0;
                socklen_t socket_error_length = sizeof(socket_error);
                if (getsockopt(socket_fd_, SOL_SOCKET, SO_ERROR, &socket_error, &socket_error_length) != 0) {
                    last_error = OperationResult::Failure(
                        "TRANSPORT_CONNECT_FAILED",
                        "Failed to inspect gateway socket state: " + FormatSystemError(errno));
                    close(socket_fd_);
                    socket_fd_ = -1;
                    continue;
                }
                if (socket_error == 0) {
                    return OperationResult::Success();
                }
                last_error = OperationResult::Failure(
                    "TRANSPORT_CONNECT_FAILED",
                    "Failed to connect to gateway socket: " + FormatSystemError(socket_error));
                close(socket_fd_);
                socket_fd_ = -1;
                continue;
            }

            last_error = OperationResult::Failure(
                "TRANSPORT_CONNECT_FAILED",
                "Failed to connect to gateway socket: " + FormatSystemError(errno));
            close(socket_fd_);
            socket_fd_ = -1;
        }

        return last_error;
    }

    OperationResult EstablishTls(const ParsedGatewayUrl& parsed) {
        ssl_context_ = SSL_CTX_new(TLS_client_method());
        if (ssl_context_ == nullptr) {
            return OperationResult::Failure(
                "TRANSPORT_CONNECT_FAILED",
                "Failed to create OpenSSL context: " + FormatOpenSslError());
        }

        if (parsed.allow_insecure_tls) {
            SSL_CTX_set_verify(ssl_context_, SSL_VERIFY_NONE, nullptr);
        } else {
            SSL_CTX_set_verify(ssl_context_, SSL_VERIFY_PEER, nullptr);
            if (SSL_CTX_set_default_verify_paths(ssl_context_) != 1) {
                return OperationResult::Failure(
                    "TRANSPORT_CONNECT_FAILED",
                    "Failed to load default TLS trust store: " + FormatOpenSslError());
            }
        }

        ssl_ = SSL_new(ssl_context_);
        if (ssl_ == nullptr) {
            return OperationResult::Failure(
                "TRANSPORT_CONNECT_FAILED",
                "Failed to create OpenSSL session: " + FormatOpenSslError());
        }

        if (SSL_set_fd(ssl_, socket_fd_) != 1) {
            return OperationResult::Failure(
                "TRANSPORT_CONNECT_FAILED",
                "Failed to bind TLS session to gateway socket: " + FormatOpenSslError());
        }
        if (SSL_set_tlsext_host_name(ssl_, parsed.host.c_str()) != 1) {
            return OperationResult::Failure(
                "TRANSPORT_CONNECT_FAILED",
                "Failed to configure TLS SNI for gateway host: " + FormatOpenSslError());
        }
        SSL_set_connect_state(ssl_);

        for (;;) {
            const int result = SSL_connect(ssl_);
            if (result == 1) {
                return OperationResult::Success();
            }

            const int ssl_error = SSL_get_error(ssl_, result);
            if (ssl_error == SSL_ERROR_WANT_READ) {
                const auto wait_status = WaitForSocket(false, 15000);
                if (!wait_status) {
                    return wait_status;
                }
                continue;
            }
            if (ssl_error == SSL_ERROR_WANT_WRITE) {
                const auto wait_status = WaitForSocket(true, 15000);
                if (!wait_status) {
                    return wait_status;
                }
                continue;
            }
            return OperationResult::Failure(
                "TRANSPORT_CONNECT_FAILED",
                "TLS handshake with gateway failed: " + FormatSslError(ssl_, result));
        }
    }

    OperationResult PerformWebSocketHandshake(const ParsedGatewayUrl& parsed) {
        unsigned char random_bytes[16] = {};
        if (RAND_bytes(random_bytes, sizeof(random_bytes)) != 1) {
            return OperationResult::Failure(
                "TRANSPORT_CONNECT_FAILED",
                "Failed to generate websocket nonce: " + FormatOpenSslError());
        }

        const std::string websocket_key = Base64Encode(random_bytes, sizeof(random_bytes));
        if (websocket_key.empty()) {
            return OperationResult::Failure(
                "TRANSPORT_CONNECT_FAILED",
                "Failed to encode websocket nonce");
        }

        std::string request;
        request.reserve(512);
        request += "GET " + parsed.path + " HTTP/1.1\r\n";
        request += "Host: " + FormatHostHeader(parsed) + "\r\n";
        request += "Upgrade: websocket\r\n";
        request += "Connection: Upgrade\r\n";
        request += "Sec-WebSocket-Version: 13\r\n";
        request += "Sec-WebSocket-Key: " + websocket_key + "\r\n";
        request += "User-Agent: DecentraLabsProxyRuntime/0.1\r\n";
        request += "\r\n";

        const auto write_status = WriteAll(request.data(), request.size());
        if (!write_status) {
            return OperationResult::Failure("TRANSPORT_CONNECT_FAILED", write_status.message);
        }

        const auto headers = ReadHttpHeaders();
        if (!headers) {
            return OperationResult::Failure(headers.status.code, headers.status.message);
        }

        const std::string& response = headers.value;
        const std::size_t first_line_end = response.find("\r\n");
        if (first_line_end == std::string::npos) {
            return OperationResult::Failure(
                "TRANSPORT_CONNECT_FAILED",
                "Gateway websocket handshake returned an invalid HTTP response");
        }
        const std::string status_line = response.substr(0, first_line_end);
        if (status_line.find(" 101 ") == std::string::npos) {
            return OperationResult::Failure(
                "TRANSPORT_CONNECT_FAILED",
                "Gateway websocket handshake was rejected: " + status_line);
        }

        std::map<std::string, std::string> header_map;
        std::size_t line_start = first_line_end + 2;
        while (line_start < response.size()) {
            const std::size_t line_end = response.find("\r\n", line_start);
            if (line_end == std::string::npos || line_end == line_start) {
                break;
            }
            const std::string line = response.substr(line_start, line_end - line_start);
            const std::size_t colon = line.find(':');
            if (colon != std::string::npos) {
                std::string name = ToLowerCopy(line.substr(0, colon));
                std::string value = line.substr(colon + 1);
                while (!value.empty() && std::isspace(static_cast<unsigned char>(value.front()))) {
                    value.erase(value.begin());
                }
                header_map[std::move(name)] = TrimTrailingWhitespace(std::move(value));
            }
            line_start = line_end + 2;
        }

        const auto upgrade_it = header_map.find("upgrade");
        if (upgrade_it == header_map.end() || ToLowerCopy(upgrade_it->second) != "websocket") {
            return OperationResult::Failure(
                "TRANSPORT_CONNECT_FAILED",
                "Gateway websocket handshake response is missing Upgrade: websocket");
        }

        const auto connection_it = header_map.find("connection");
        if (connection_it == header_map.end() || !ContainsCaseInsensitiveToken(connection_it->second, "upgrade")) {
            return OperationResult::Failure(
                "TRANSPORT_CONNECT_FAILED",
                "Gateway websocket handshake response is missing Connection: Upgrade");
        }

        const auto accept_it = header_map.find("sec-websocket-accept");
        if (accept_it == header_map.end() || accept_it->second != ComputeWebSocketAccept(websocket_key)) {
            return OperationResult::Failure(
                "TRANSPORT_CONNECT_FAILED",
                "Gateway websocket handshake returned an unexpected Sec-WebSocket-Accept value");
        }

        return OperationResult::Success();
    }

    OperationResult WaitForSocket(const bool write, const int timeout_ms) const {
        if (socket_fd_ < 0) {
            return OperationResult::Failure(
                "TRANSPORT_WAIT_FAILED",
                "Gateway socket is not open");
        }

        fd_set read_set;
        fd_set write_set;
        FD_ZERO(&read_set);
        FD_ZERO(&write_set);
        if (write) {
            FD_SET(socket_fd_, &write_set);
        } else {
            FD_SET(socket_fd_, &read_set);
        }

        timeval timeout{};
        timeout.tv_sec = timeout_ms / 1000;
        timeout.tv_usec = static_cast<suseconds_t>((timeout_ms % 1000) * 1000);
        const int ready = select(socket_fd_ + 1, &read_set, &write_set, nullptr, &timeout);
        if (ready > 0) {
            return OperationResult::Success();
        }
        if (ready == 0) {
            return OperationResult::Failure(
                "TRANSPORT_WAIT_TIMEOUT",
                "Timed out waiting for the gateway socket to become ready");
        }
        return OperationResult::Failure(
            "TRANSPORT_WAIT_FAILED",
            "Failed while waiting for the gateway socket to become ready: " + FormatSystemError(errno));
    }

    OperationResult WriteAll(const char* data, const std::size_t length) {
        std::size_t offset = 0;
        while (offset < length) {
            if (ssl_ != nullptr) {
                size_t written = 0;
                const int result = SSL_write_ex(ssl_, data + offset, length - offset, &written);
                if (result == 1) {
                    offset += written;
                    continue;
                }

                const int ssl_error = SSL_get_error(ssl_, result);
                if (ssl_error == SSL_ERROR_WANT_READ) {
                    const auto wait_status = WaitForSocket(false, 15000);
                    if (!wait_status) {
                        return wait_status;
                    }
                    continue;
                }
                if (ssl_error == SSL_ERROR_WANT_WRITE) {
                    const auto wait_status = WaitForSocket(true, 15000);
                    if (!wait_status) {
                        return wait_status;
                    }
                    continue;
                }
                return OperationResult::Failure(
                    "TRANSPORT_SEND_FAILED",
                    "Failed to write to TLS gateway socket: " + FormatSslError(ssl_, result));
            }

            const auto wait_status = WaitForSocket(true, 15000);
            if (!wait_status) {
                return wait_status;
            }
            const ssize_t written = send(socket_fd_, data + offset, length - offset, 0);
            if (written < 0) {
                if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) {
                    continue;
                }
                return OperationResult::Failure(
                    "TRANSPORT_SEND_FAILED",
                    "Failed to write to gateway socket: " + FormatSystemError(errno));
            }
            offset += static_cast<std::size_t>(written);
        }
        return OperationResult::Success();
    }

    ValueResult<std::string> ReadChunk() {
        std::array<char, 4096> buffer{};
        if (ssl_ != nullptr) {
            for (;;) {
                size_t bytes_read = 0;
                const int result = SSL_read_ex(ssl_, buffer.data(), buffer.size(), &bytes_read);
                if (result == 1) {
                    return ValueResult<std::string>::Success(std::string(buffer.data(), bytes_read));
                }

                const int ssl_error = SSL_get_error(ssl_, result);
                if (ssl_error == SSL_ERROR_WANT_READ) {
                    const auto wait_status = WaitForSocket(false, 15000);
                    if (!wait_status) {
                        return ValueResult<std::string>::Failure(wait_status.code, wait_status.message);
                    }
                    continue;
                }
                if (ssl_error == SSL_ERROR_WANT_WRITE) {
                    const auto wait_status = WaitForSocket(true, 15000);
                    if (!wait_status) {
                        return ValueResult<std::string>::Failure(wait_status.code, wait_status.message);
                    }
                    continue;
                }
                return ValueResult<std::string>::Failure(
                    "TRANSPORT_RECEIVE_FAILED",
                    "Failed to read from TLS gateway socket: " + FormatSslError(ssl_, result));
            }
        }

        for (;;) {
            const auto wait_status = WaitForSocket(false, 15000);
            if (!wait_status) {
                return ValueResult<std::string>::Failure(wait_status.code, wait_status.message);
            }
            const ssize_t bytes_read = recv(socket_fd_, buffer.data(), buffer.size(), 0);
            if (bytes_read == 0) {
                return ValueResult<std::string>::Failure(
                    "TRANSPORT_CLOSED",
                    "Gateway closed websocket");
            }
            if (bytes_read < 0) {
                if (errno == EINTR || errno == EAGAIN || errno == EWOULDBLOCK) {
                    continue;
                }
                return ValueResult<std::string>::Failure(
                    "TRANSPORT_RECEIVE_FAILED",
                    "Failed to read from gateway socket: " + FormatSystemError(errno));
            }
            return ValueResult<std::string>::Success(std::string(buffer.data(), static_cast<std::size_t>(bytes_read)));
        }
    }

    ValueResult<std::string> ReadHttpHeaders() {
        std::string response;
        response.reserve(2048);
        for (;;) {
            const auto chunk = ReadChunk();
            if (!chunk) {
                return chunk;
            }
            response.append(chunk.value);
            const std::size_t header_end = response.find("\r\n\r\n");
            if (header_end != std::string::npos) {
                const std::size_t extra_offset = header_end + 4;
                if (extra_offset < response.size()) {
                    pending_bytes_.insert(pending_bytes_.end(), response.begin() + extra_offset, response.end());
                    response.erase(extra_offset);
                }
                return ValueResult<std::string>::Success(std::move(response));
            }
            if (response.size() > 16384) {
                return ValueResult<std::string>::Failure(
                    "TRANSPORT_CONNECT_FAILED",
                    "Gateway websocket handshake headers are too large");
            }
        }
    }

    ValueResult<std::string> ReadExact(const std::size_t length) {
        std::string payload;
        payload.reserve(length);
        if (!pending_bytes_.empty()) {
            const std::size_t take = std::min(length, pending_bytes_.size());
            payload.append(pending_bytes_.begin(), pending_bytes_.begin() + take);
            pending_bytes_.erase(pending_bytes_.begin(), pending_bytes_.begin() + take);
        }

        while (payload.size() < length) {
            const auto chunk = ReadChunk();
            if (!chunk) {
                return chunk;
            }
            const std::size_t remaining = length - payload.size();
            if (chunk.value.size() <= remaining) {
                payload.append(chunk.value);
            } else {
                payload.append(chunk.value.data(), remaining);
                pending_bytes_.insert(pending_bytes_.end(), chunk.value.begin() + remaining, chunk.value.end());
            }
        }
        return ValueResult<std::string>::Success(std::move(payload));
    }

    OperationResult SendFrame(const unsigned char opcode, const std::string& payload, const bool mask) {
        std::string frame;
        frame.reserve(payload.size() + 14);
        frame.push_back(static_cast<char>(0x80U | (opcode & 0x0FU)));

        const std::size_t payload_length = payload.size();
        const unsigned char mask_bit = mask ? 0x80U : 0x00U;
        if (payload_length <= 125U) {
            frame.push_back(static_cast<char>(mask_bit | static_cast<unsigned char>(payload_length)));
        } else if (payload_length <= 0xFFFFU) {
            frame.push_back(static_cast<char>(mask_bit | 126U));
            frame.push_back(static_cast<char>((payload_length >> 8U) & 0xFFU));
            frame.push_back(static_cast<char>(payload_length & 0xFFU));
        } else {
            frame.push_back(static_cast<char>(mask_bit | 127U));
            for (int shift = 56; shift >= 0; shift -= 8) {
                frame.push_back(static_cast<char>((static_cast<std::uint64_t>(payload_length) >> shift) & 0xFFU));
            }
        }

        std::array<unsigned char, 4> masking_key{};
        if (mask) {
            if (RAND_bytes(masking_key.data(), static_cast<int>(masking_key.size())) != 1) {
                return OperationResult::Failure(
                    "TRANSPORT_SEND_FAILED",
                    "Failed to generate websocket masking key: " + FormatOpenSslError());
            }
            frame.append(
                reinterpret_cast<const char*>(masking_key.data()),
                reinterpret_cast<const char*>(masking_key.data()) + masking_key.size());
        }

        frame.append(payload);
        if (mask) {
            const std::size_t payload_offset = frame.size() - payload_length;
            for (std::size_t index = 0; index < payload_length; ++index) {
                frame[payload_offset + index] = static_cast<char>(
                    static_cast<unsigned char>(frame[payload_offset + index]) ^ masking_key[index % masking_key.size()]);
            }
        }

        return WriteAll(frame.data(), frame.size());
    }

    int socket_fd_ = -1;
    SSL_CTX* ssl_context_ = nullptr;
    SSL* ssl_ = nullptr;
    std::vector<char> pending_bytes_;
    std::string url_;
    bool connected_ = false;
    bool close_sent_ = false;
};

}  // namespace

std::unique_ptr<GatewayTransport> CreatePosixGatewayTransport() {
    return std::make_unique<OpenSslWssTransport>();
}

}  // namespace decentralabs::proxy

#endif
