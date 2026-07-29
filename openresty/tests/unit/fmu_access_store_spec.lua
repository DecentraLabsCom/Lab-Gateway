local runner = require "tests.helpers.runner"
local store_module = require "modules.fmu_access_store"

local TEST_SESSION_ID = "session-store-spec-1234"
local function fake_cipher_factory()
    return {
        encrypt = function(_, _, _, plaintext, _, aad)
            return plaintext:reverse() .. "|" .. aad
        end,
        get_aead_tag = function()
            return "tag"
        end,
        decrypt = function(_, _, _, ciphertext, _, aad)
            local plaintext, stored_aad = ciphertext:match("^(.*)|([^|]*)$")
            if stored_aad ~= aad then
                return nil, "bad aad"
            end
            return plaintext:reverse()
        end,
    }
end

local function new_store()
    return store_module.new({
        path = "/tmp",
        key = string.rep("k", 32),
        cipher_factory = fake_cipher_factory,
        random_bytes = function()
            return string.rep("i", 12)
        end,
        base64_encode = function(value)
            return value
        end,
        base64_decode = function(value)
            return value
        end,
    })
end

runner.describe("FMU durable access store", function()
    runner.it("persists encrypted session state and reloads it in a new store instance", function()
        local first_store = new_store()
        local second_store = new_store()
        first_store:remove(TEST_SESSION_ID)

        runner.assert.truthy(first_store:save(TEST_SESSION_ID, "technical-jwt", 500, 100))
        local token, exp, err = second_store:load(TEST_SESSION_ID, 100)

        runner.assert.equals(nil, err)
        runner.assert.equals("technical-jwt", token)
        runner.assert.equals(500, exp)

        local file = io.open("/tmp/fmu-access-" .. TEST_SESSION_ID .. ".state", "r")
        runner.assert.truthy(file)
        local contents = file:read("*all")
        file:close()
        runner.assert.equals(false, contents:find("technical-jwt", 1, true) ~= nil)
        first_store:remove(TEST_SESSION_ID)
    end)

    runner.it("does not return expired state", function()
        local store = new_store()
        store:remove(TEST_SESSION_ID)
        runner.assert.truthy(store:save(TEST_SESSION_ID, "technical-jwt", 100, 99))

        local token, exp, err = store:load(TEST_SESSION_ID, 100)

        runner.assert.equals(nil, err)
        runner.assert.equals(nil, token)
        runner.assert.equals(nil, exp)
        runner.assert.equals(nil, io.open("/tmp/fmu-access-" .. TEST_SESSION_ID .. ".state", "r"))
    end)
end)

return runner
