local cjson = require "cjson.safe"

local config = ngx.shared.config
local marketplace_url = config and config:get("marketplace_url") or ""
marketplace_url = marketplace_url:gsub("/+$", "")

ngx.header["Content-Type"] = "application/javascript; charset=utf-8"
ngx.header["Cache-Control"] = "no-store"

local marketplace_literal = cjson.encode(marketplace_url)
if not marketplace_literal or not marketplace_url:match("^https?://") then
    ngx.say("void 0;")
    return
end

ngx.print([[
(function () {
    "use strict";

    const expiresAt = new URLSearchParams(window.location.search).get("dlabs_session_exp");
    if (!expiresAt || !/^\d+(?:\.\d+)?$/.test(expiresAt)) {
        return;
    }

    const expiresAtMs = Number(expiresAt) * 1000;
    if (!Number.isFinite(expiresAtMs)) {
        return;
    }

    const marketplaceUrl = ]] .. marketplace_literal .. [[;
    const returnToMarketplace = function () {
        const remainingMs = expiresAtMs - Date.now();
        if (remainingMs <= 0) {
            window.location.replace(marketplaceUrl);
            return;
        }
        window.setTimeout(returnToMarketplace, Math.min(remainingMs, 2147483647));
    };

    returnToMarketplace();
})();
]])
