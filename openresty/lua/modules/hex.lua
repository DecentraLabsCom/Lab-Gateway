local _M = {}

function _M.encode(value)
    if type(value) ~= "string" then
        return nil
    end
    return (value:gsub(".", function(byte)
        return string.format("%02x", string.byte(byte))
    end))
end

return _M
