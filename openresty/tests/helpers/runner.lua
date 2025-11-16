local Runner = {
    suites = {},
    current = nil
}

function Runner.describe(name, fn)
    local suite = { name = name, tests = {} }
    table.insert(Runner.suites, suite)
    local previous = Runner.current
    Runner.current = suite
    fn()
    Runner.current = previous
end

local function add_test(name, fn)
    local suite = Runner.current
    if not suite then
        suite = { name = "default", tests = {} }
        table.insert(Runner.suites, suite)
    end
    table.insert(suite.tests, { name = name, fn = fn })
end

function Runner.it(name, fn)
    add_test(name, fn)
end

local Assertions = {}

function Assertions.equals(expected, actual, message)
    if expected ~= actual then
        error((message or "Values differ") ..
            string.format("\nExpected: %s\nActual: %s", tostring(expected), tostring(actual)))
    end
end

function Assertions.truthy(value, message)
    if not value then
        error(message or "Expected value to be truthy")
    end
end

function Assertions.contains(haystack, needle, message)
    for _, entry in ipairs(haystack) do
        if entry == needle then
            return
        end
    end
    error(message or ("Expected list to contain: " .. tostring(needle)))
end

Runner.assert = Assertions

function Runner.run()
    local passed = 0
    local failed = 0
    for _, suite in ipairs(Runner.suites) do
        for _, test in ipairs(suite.tests) do
            local ok, err = xpcall(test.fn, debug.traceback)
            if ok then
                passed = passed + 1
            else
                failed = failed + 1
                io.stderr:write(string.format("❌ %s > %s\n%s\n", suite.name, test.name, err))
            end
        end
    end

    print(string.format("Executed %d tests: %d passed, %d failed", passed + failed, passed, failed))
    return failed == 0
end

return Runner
