local HttpClientStub = {}
HttpClientStub.__index = HttpClientStub

function HttpClientStub.new(responses)
    return setmetatable({
        responses = responses or {},
        calls = {}
    }, HttpClientStub)
end

function HttpClientStub:request_uri(url, opts)
    table.insert(self.calls, { url = url, opts = opts })
    if #self.responses == 0 then
        return nil, "no response"
    end
    return table.remove(self.responses, 1)
end

return HttpClientStub
