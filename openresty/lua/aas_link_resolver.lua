-- ============================================================================
-- aas_link_resolver.lua — Resolve AAS shell ID overrides via fmu-runner
-- ============================================================================
-- When a provider links an FMU to an externally-managed AAS shell (via
-- POST /aas-admin/fmu/{accessKey}/aas-link), the Gateway stores the mapping
-- and can transparently redirect /aas/shells/<conventional-id> to the linked
-- external AAS shell ID — so Marketplace consumers need no changes.
--
-- Resolution is done via an internal subrequest to fmu-runner's
-- /aas-admin/resolve-aas-id endpoint, with results cached in a shared dict.
-- ============================================================================

local cjson = require("cjson.safe")

local _M = {}

local CACHE_TTL = 60          -- seconds to cache resolved IDs (overrides + misses)

--- Base64url-decode a string (RFC 4648 §5, no padding).
local function b64url_decode(s)
    local padded = s:gsub("-", "+"):gsub("_", "/")
    local pad = (4 - #padded % 4) % 4
    padded = padded .. string.rep("=", pad)
    return ngx.decode_base64(padded)
end

--- Base64url-encode a string (RFC 4648 §5, no padding).
local function b64url_encode(s)
    local b = ngx.encode_base64(s)
    return b:gsub("+", "-"):gsub("/", "_"):gsub("=", "")
end

--- Resolve a conventional AAS shell ID to the actual target ID.
-- Performs an internal subrequest to fmu-runner with shared-dict caching.
-- @param shell_id  The decoded shell ID string (e.g. "urn:decentralabs:lab:42")
-- @return target_id, is_override
function _M.resolve(shell_id)
    if not shell_id or shell_id == "" then return shell_id, false end

    local config = ngx.shared and ngx.shared.config
    local fmu_runner_enabled = config and config:get("fmu_runner_enabled")
    if fmu_runner_enabled == 0 or fmu_runner_enabled == false or fmu_runner_enabled == "0" then
        return shell_id, false
    end

    local cache = ngx.shared.aas_link_cache

    -- Positive cache hit (override exists)
    local cached_target = cache:get("t:" .. shell_id)
    if cached_target then
        return cached_target, true
    end
    -- Negative cache hit (no override)
    if cache:get("n:" .. shell_id) then
        return shell_id, false
    end

    -- Internal subrequest to fmu-runner
    local res = ngx.location.capture(
        "/internal/aas-resolve",
        { method = ngx.HTTP_GET, args = "shellId=" .. ngx.escape_uri(shell_id) }
    )

    if res.status ~= 200 then
        -- fmu-runner unreachable or error — pass through without caching
        ngx.log(ngx.WARN, "aas_link_resolver: resolve subrequest returned " .. res.status .. " for " .. shell_id)
        return shell_id, false
    end

    local data, err = cjson.decode(res.body)
    if not data then
        ngx.log(ngx.WARN, "aas_link_resolver: bad JSON from resolve endpoint: ", err)
        return shell_id, false
    end

    local target = data.targetId or shell_id
    local is_override = data.override == true

    if is_override and target ~= "" then
        cache:set("t:" .. shell_id, target, CACHE_TTL)
        return target, true
    end

    cache:set("n:" .. shell_id, true, CACHE_TTL)
    return shell_id, false
end

--- Rewrite the current request URI if the shell ID has an AAS link override.
-- Call this from rewrite_by_lua_block in the /aas/ location.
-- Handles /aas/shells/{encoded-id}[/...] paths.
function _M.rewrite_if_linked()
    local uri = ngx.var.uri
    -- Match /aas/shells/{encoded-id} with optional trailing path
    local encoded_id, rest = uri:match("^/aas/shells/([^/?]+)(.*)")
    if not encoded_id then return end

    local decoded = b64url_decode(encoded_id)
    if not decoded then return end

    local target_id, is_override = _M.resolve(decoded)
    if not is_override then return end

    -- Re-encode the target ID and rewrite the URI
    local new_encoded = b64url_encode(target_id)
    ngx.req.set_uri("/aas/shells/" .. new_encoded .. (rest or ""), false)
end

return _M