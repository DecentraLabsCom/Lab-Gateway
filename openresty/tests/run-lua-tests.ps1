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
FROM openresty/openresty:alpine

# Install luarocks and cjson
RUN apk add --no-cache luarocks5.1 && \
    luarocks-5.1 install lua-cjson

WORKDIR /app
"@

$DockerfilePath = Join-Path $ProjectRoot "openresty" "Dockerfile.test"
$TestDockerfile | Out-File -FilePath $DockerfilePath -Encoding utf8 -NoNewline

try {
    Write-Host "Building test container..." -ForegroundColor Yellow
    
    docker build -t openresty-lua-tests -f $DockerfilePath (Join-Path $ProjectRoot "openresty") 2>&1 | ForEach-Object {
        if ($_ -match "error" -or $_ -match "Error") {
            Write-Host $_ -ForegroundColor Red
        } elseif ($VerbosePreference -eq "Continue") {
            Write-Host $_
        }
    }

    Write-Host "Running tests..." -ForegroundColor Yellow
    Write-Host ""

    $openrestyPath = Join-Path $ProjectRoot "openresty"
    
    # Run tests in container
    $result = docker run --rm `
        -v "${openrestyPath}:/app:ro" `
        -w /app `
        openresty-lua-tests `
        luajit tests/run.lua 2>&1

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
