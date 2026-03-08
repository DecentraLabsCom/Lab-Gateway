#pragma once

#include <memory>
#include <string>
#include <vector>

#include "decentralabs_proxy/operation_result.hpp"

namespace decentralabs::proxy {

class GatewayTransport {
public:
    virtual ~GatewayTransport() = default;

    virtual OperationResult Connect(const std::string& url) = 0;
    virtual OperationResult SendText(const std::string& payload) = 0;
    virtual ValueResult<std::string> ReceiveText() = 0;
    virtual void Close() = 0;
    virtual bool IsConnected() const = 0;
};

class StubWssTransport final : public GatewayTransport {
public:
    OperationResult Connect(const std::string& url) override;
    OperationResult SendText(const std::string& payload) override;
    ValueResult<std::string> ReceiveText() override;
    void Close() override;
    bool IsConnected() const override;

private:
    std::string url_;
    bool connected_ = false;
};

class ScriptedTransport final : public GatewayTransport {
public:
    void QueueResponse(std::string payload);
    const std::vector<std::string>& SentPayloads() const;

    OperationResult Connect(const std::string& url) override;
    OperationResult SendText(const std::string& payload) override;
    ValueResult<std::string> ReceiveText() override;
    void Close() override;
    bool IsConnected() const override;

private:
    std::vector<std::string> queued_responses_;
    std::vector<std::string> sent_payloads_;
    std::string url_;
    bool connected_ = false;
};

std::unique_ptr<GatewayTransport> CreateDefaultGatewayTransport();

}  // namespace decentralabs::proxy
