local _M = {}

local function same_value(left, right)
    return left ~= nil and tostring(left) == tostring(right)
end

local function rollback(ngx, cache, state)
    for index = #state, 1, -1 do
        local mapping = state[index]
        if mapping.created and same_value(cache:get(mapping.key), mapping.value) then
            local deleted = cache:delete(mapping.key)
            if deleted == false then
                ngx.log(ngx.WARN, "Unable to roll back access mapping " .. mapping.key)
            end
        end
    end
end

function _M.persist(ngx, cache, mappings)
    if not cache then
        return nil, "access mapping cache unavailable"
    end

    local state = {}
    for _, mapping in ipairs(mappings or {}) do
        if type(mapping.key) ~= "string" or mapping.key == ""
            or mapping.value == nil or mapping.value == "" then
            rollback(ngx, cache, state)
            return nil, "access mapping is incomplete"
        end

        local existing = cache:get(mapping.key)
        if existing ~= nil then
            if not same_value(existing, mapping.value) then
                rollback(ngx, cache, state)
                return nil, "access mapping belongs to another session"
            end
            state[#state + 1] = {
                key = mapping.key,
                value = mapping.value,
                created = false
            }
        else
            local stored, store_error = cache:set(mapping.key, mapping.value, mapping.ttl)
            if not stored then
                rollback(ngx, cache, state)
                return nil, store_error or "access mapping could not be stored"
            end
            state[#state + 1] = {
                key = mapping.key,
                value = mapping.value,
                created = true
            }
        end
    end

    return state
end

function _M.rollback(ngx, cache, state)
    if state then
        rollback(ngx, cache, state)
    end
end

return _M
