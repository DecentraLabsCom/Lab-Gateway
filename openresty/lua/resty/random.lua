local ffi = require "ffi"

ffi.cdef [[
    int RAND_bytes(unsigned char *buf, int num);
]]

local crypto = ffi.load("crypto")
local _M = {}

function _M.bytes(length, _strong)
    if type(length) ~= "number"
        or length < 1
        or length ~= math.floor(length)
        or length > 1024 * 1024 then
        return nil
    end

    local buffer = ffi.new("unsigned char[?]", length)
    if crypto.RAND_bytes(buffer, length) ~= 1 then
        return nil
    end
    return ffi.string(buffer, length)
end

return _M
