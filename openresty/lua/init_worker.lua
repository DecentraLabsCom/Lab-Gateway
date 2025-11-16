-- ============================================================================
-- init_worker.lua - Worker Initialization Phase (init_worker_by_lua)
-- ============================================================================
-- Delegates timer orchestration to a dedicated session guard module so we can
-- reuse the logic across OpenResty and unit tests.
-- ============================================================================
local SessionGuard = require "modules.session_guard"

local guard = SessionGuard.new()
guard:start()

