#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run OpenResty Lua unit tests using Docker.

.DESCRIPTION
    This script runs the Lua unit tests for the OpenResty modules using a Docker container
    with LuaJIT and the required dependencies (cjson).

.EXAMPLE
    .\run-lua-tests.ps1

.EXAMPLE
    .\run-lua-tests.ps1 -Verbose
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $ScriptDir)

Write-Host "=================================================="
Write-Host "OpenResty Lua Unit Tests"
Write-Host "=================================================="
Write-Host ""

# Check if Docker is available
try {
    docker version | Out-Null
} catch {
    Write-Host "Error: Docker is not available. Please install Docker." -ForegroundColor Red
    exit 1
}

# Create a temporary Dockerfile for testing
$TestDockerfile = @"
FROM openresty/openresty:1.31.1.1-1-alpine-fat

# Match the production Lua/OpenSSL runtime used by openresty/Dockerfile.
ENV TREE=/usr/local
ENV LUA_PATH="`$TREE/share/lua/5.1/?.lua;`$TREE/share/lua/5.1/?/init.lua;;"
ENV LUA_CPATH="`$TREE/lib/lua/5.1/?.so;;"
RUN apk add --no-cache build-base openssl openssl-dev git luarocks && \
    luarocks --tree=`$TREE install lua-cjson && \
    luarocks --tree=`$TREE install lua-resty-openssl

WORKDIR /app
"@

$DockerfilePath = Join-Path (Join-Path $ProjectRoot "openresty") "Dockerfile.test"
$TestDockerfile | Out-File -FilePath $DockerfilePath -Encoding utf8 -NoNewline

try {
    Write-Host "Building test container..." -ForegroundColor Yellow
    
    $openrestyRoot = Join-Path $ProjectRoot "openresty"
    $buildCmd = "docker build -t openresty-lua-tests -f `"$DockerfilePath`" `"$openrestyRoot`""
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $buildOutput = cmd /c "$buildCmd 2>&1"
    $ErrorActionPreference = $previousErrorAction
    $buildOutput | ForEach-Object {
        if ($_ -match "error" -or $_ -match "Error") {
            Write-Host $_ -ForegroundColor Red
        } elseif ($VerbosePreference -eq "Continue") {
            Write-Host $_
        }
    }
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    Write-Host "Running tests..." -ForegroundColor Yellow
    Write-Host ""

    $repoPath = $ProjectRoot
    $repoPathDocker = $repoPath -replace "\\", "/"

    # Run tests in container
    $runCmd = "docker run --rm -v `"${repoPathDocker}:/workspace:ro`" -w /workspace openresty-lua-tests luajit openresty/tests/run.lua"
    $previousErrorAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $result = cmd /c "$runCmd 2>&1"
    $ErrorActionPreference = $previousErrorAction

    $exitCode = $LASTEXITCODE

    # Output results
    $result | ForEach-Object {
        if ($_ -match "FAIL") {
            Write-Host $_ -ForegroundColor Red
        } elseif ($_ -match "passed") {
            Write-Host $_ -ForegroundColor Green
        } else {
            Write-Host $_
        }
    }

    Write-Host ""
    if ($exitCode -eq 0) {
        Write-Host 'All tests passed!' -ForegroundColor Green
    } else {
        Write-Host 'Some tests failed!' -ForegroundColor Red
    }

    exit $exitCode

} finally {
    # Cleanup
    if (Test-Path $DockerfilePath) {
        Remove-Item $DockerfilePath -Force
    }
}
