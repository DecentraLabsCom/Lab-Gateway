local cjson = require "cjson.safe"
local cipher = require "resty.openssl.cipher"
local rand = require "resty.openssl.rand"

local _M = {}

local FORMAT_PREFIX = "v1"
local CIPHER_NAME = "aes-256-gcm"
local IV_LENGTH = 12
local SESSION_ID_PATTERN = "^[A-Za-z0-9_-]+$"
local MIN_SESSION_ID_LENGTH = 16
local MAX_SESSION_ID_LENGTH = 512
local MAX_RECORD_BYTES = 128 * 1024

local function current_ngx()
    return _G.ngx
end

local function default_base64_encode(value)
    return current_ngx().encode_base64(value)
end

local function default_base64_decode(value)
    return current_ngx().decode_base64(value)
end

local function decode_key(value, decode)
    if type(value) ~= "string" or value == "" or value:upper() == "CHANGE_ME" then
        return nil, "ACCESS_CODE_ENCRYPTION_KEY is not configured"
    end
    local normalized = value:gsub("-", "+"):gsub("_", "/")
    normalized = normalized .. string.rep("=", (4 - #normalized % 4) % 4)
    local decoded = decode(normalized)
    if type(decoded) ~= "string" or #decoded ~= 32 then
        return nil, "ACCESS_CODE_ENCRYPTION_KEY must contain exactly 32 bytes"
    end
    return decoded
end

local function valid_session_id(session_id)
    return type(session_id) == "string"
        and #session_id >= MIN_SESSION_ID_LENGTH
        and #session_id <= MAX_SESSION_ID_LENGTH
        and session_id:match(SESSION_ID_PATTERN) ~= nil
end

local function path_for(path, session_id)
    return path .. "/fmu-access-" .. session_id .. ".state"
end

local function missing_file_error(err)
    local message = tostring(err or "")
    return message:find("No such file", 1, true) ~= nil
        or message:find("cannot find", 1, true) ~= nil
end

local function encrypt_record(self, session_id, record)
    local plaintext, encode_err = cjson.encode(record)
    if not plaintext then
        return nil, encode_err or "Unable to serialize FMU access state"
    end
    local iv, rand_err = self.random_bytes(IV_LENGTH, true)
    if not iv then
        return nil, rand_err or "Unable to generate FMU access state IV"
    end
    local instance, cipher_err = self.cipher_factory(CIPHER_NAME)
    if not instance then
        return nil, cipher_err or "Unable to initialize FMU access state cipher"
    end
    local ciphertext, encrypt_err = instance:encrypt(self.key, iv, plaintext, false, session_id)
    if not ciphertext then
        return nil, encrypt_err or "Unable to encrypt FMU access state"
    end
    local tag, tag_err = instance:get_aead_tag()
    if not tag then
        return nil, tag_err or "Unable to authenticate FMU access state"
    end
    return table.concat({
        FORMAT_PREFIX,
        self.base64_encode(iv),
        self.base64_encode(ciphertext),
        self.base64_encode(tag),
    }, ".")
end

local function decrypt_record(self, session_id, value)
    local version, encoded_iv, encoded_ciphertext, encoded_tag = value:match("^([^%.]+)%.([^%.]+)%.([^%.]+)%.([^%.]+)$")
    if version ~= FORMAT_PREFIX or not encoded_iv or not encoded_ciphertext or not encoded_tag then
        return nil, "Invalid FMU access state format"
    end
    local iv = self.base64_decode(encoded_iv)
    local ciphertext = self.base64_decode(encoded_ciphertext)
    local tag = self.base64_decode(encoded_tag)
    if type(iv) ~= "string" or #iv ~= IV_LENGTH or type(ciphertext) ~= "string" or type(tag) ~= "string" then
        return nil, "Invalid FMU access state encoding"
    end
    local instance, cipher_err = self.cipher_factory(CIPHER_NAME)
    if not instance then
        return nil, cipher_err or "Unable to initialize FMU access state cipher"
    end
    local plaintext, decrypt_err = instance:decrypt(self.key, iv, ciphertext, false, session_id, tag)
    if not plaintext then
        return nil, decrypt_err or "Unable to decrypt FMU access state"
    end
    local record, decode_err = cjson.decode(plaintext)
    if type(record) ~= "table" or type(record.sessionId) ~= "string"
        or record.sessionId ~= session_id or type(record.token) ~= "string"
        or record.token == "" or type(record.exp) ~= "number" then
        return nil, decode_err or "Invalid FMU access state payload"
    end
    return record
end

function _M.new(options)
    options = options or {}
    local base64_encode = options.base64_encode or default_base64_encode
    local base64_decode = options.base64_decode or default_base64_decode
    local configured_key = options.key
    local key, key_err = configured_key, nil
    local path = options.path or os.getenv("FMU_ACCESS_STATE_PATH") or "/var/lib/openresty/fmu-access"
    local store = {
        path = path:gsub("/+$", ""),
        key = key,
        key_err = key_err,
        cipher_factory = options.cipher_factory or function(name)
            return cipher.new(name)
        end,
        random_bytes = options.random_bytes or function(length)
            return rand.bytes(length, true)
        end,
        base64_encode = base64_encode,
        base64_decode = base64_decode,
    }

    function store:available()
        if not self.key and not self.key_err then
            self.key, self.key_err = decode_key(os.getenv("ACCESS_CODE_ENCRYPTION_KEY"), self.base64_decode)
        end
        return self.key ~= nil and self.path ~= ""
    end

    function store:save(session_id, token, exp, now)
        if not valid_session_id(session_id) then
            return false, "Invalid FMU session identifier"
        end
        if type(token) ~= "string" or token == "" or type(exp) ~= "number" or exp <= (now or 0) then
            return false, "Invalid FMU access state"
        end
        if not self:available() then
            return false, self.key_err or "FMU access state path is unavailable"
        end
        local serialized, encrypt_err = encrypt_record(self, session_id, {
            sessionId = session_id,
            token = token,
            exp = math.floor(exp),
        })
        if not serialized then
            return false, encrypt_err
        end
        local target = path_for(self.path, session_id)
        local temporary = target .. ".tmp"
        local file, open_err = io.open(temporary, "wb")
        if not file then
            return false, open_err or "Unable to open FMU access state"
        end
        local ok, write_err = file:write(serialized)
        local flush_ok, flush_err = file:flush()
        local close_ok, close_err = file:close()
        if not ok or not flush_ok or not close_ok then
            os.remove(temporary)
            return false, write_err or flush_err or close_err or "Unable to write FMU access state"
        end
        local renamed, rename_err = os.rename(temporary, target)
        if not renamed then
            os.remove(temporary)
            return false, rename_err or "Unable to commit FMU access state"
        end
        return true
    end

    function store:load(session_id, now)
        if not valid_session_id(session_id) then
            return nil, nil, "Invalid FMU session identifier"
        end
        if not self:available() then
            return nil, nil, self.key_err or "FMU access state path is unavailable"
        end
        local file, open_err = io.open(path_for(self.path, session_id), "rb")
        if not file then
            if missing_file_error(open_err) then
                return nil, nil
            end
            return nil, nil, open_err or "Unable to read FMU access state"
        end
        local value = file:read(MAX_RECORD_BYTES + 1)
        file:close()
        if not value or #value > MAX_RECORD_BYTES then
            return nil, nil, "Invalid FMU access state size"
        end
        local record, decrypt_err = decrypt_record(self, session_id, value)
        if not record then
            return nil, nil, decrypt_err
        end
        if record.exp <= (now or 0) then
            self:remove(session_id)
            return nil, nil
        end
        return record.token, record.exp
    end

    function store:remove(session_id)
        if not valid_session_id(session_id) then
            return false, "Invalid FMU session identifier"
        end
        local removed, remove_err = os.remove(path_for(self.path, session_id))
        if removed or missing_file_error(remove_err) then
            return true
        end
        return false, remove_err or "Unable to remove FMU access state"
    end

    function store:path_for(session_id)
        return path_for(self.path, session_id)
    end

    return store
end

_M.default = _M.new()

return _M
