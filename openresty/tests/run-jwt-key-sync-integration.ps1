#!/usr/bin/env pwsh
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OpenrestyDir = Split-Path -Parent $ScriptDir
$ProjectRoot = Split-Path -Parent $OpenrestyDir

$TempRoot = Join-Path $ProjectRoot ".tmp-jwt-key-sync-test"
$NetworkName = "lgw-key-sync-test-net"
$KeyServerContainer = "lgw-key-sync-keysrv"
$LiteContainer = "lgw-key-sync-lite"

function Cleanup {
    docker rm -f $LiteContainer 2>$null | Out-Null
    docker rm -f $KeyServerContainer 2>$null | Out-Null
    docker network rm $NetworkName 2>$null | Out-Null
    if (Test-Path $TempRoot) {
        Remove-Item -Recurse -Force $TempRoot
    }
}

try {
    docker version | Out-Null

    Write-Host "Building OpenResty image..." -ForegroundColor Yellow
    docker compose -f (Join-Path $ProjectRoot "docker-compose.yml") build openresty | Out-Null

    New-Item -ItemType Directory -Force -Path (Join-Path $TempRoot "keysrv/.well-known") | Out-Null
    New-Item -ItemType Directory -Force -Path (Join-Path $TempRoot "lite-certs") | Out-Null

    Copy-Item -Force (Join-Path $ProjectRoot "certs/fullchain.pem") (Join-Path $TempRoot "lite-certs/fullchain.pem")
    Copy-Item -Force (Join-Path $ProjectRoot "certs/privkey.pem") (Join-Path $TempRoot "lite-certs/privkey.pem")
    Copy-Item -Force (Join-Path $ProjectRoot "certs/public_key.pem") (Join-Path $TempRoot "keysrv/.well-known/public-key.pem")

    $TempRootDocker = $TempRoot -replace "\\", "/"
    $ProjectRootDocker = $ProjectRoot -replace "\\", "/"

    # Prepare a deliberately wrong key in lite-certs to verify replacement.
    docker run --rm `
        -v "${TempRootDocker}/lite-certs:/w" `
        labgateway-openresty:latest `
        sh -c "openssl genrsa -out /w/alt_private.pem 2048 >/dev/null 2>&1 && openssl rsa -in /w/alt_private.pem -pubout -out /w/public_key.pem >/dev/null 2>&1 && rm -f /w/alt_private.pem" | Out-Null

    $beforeHash = (Get-FileHash (Join-Path $TempRoot "lite-certs/public_key.pem") -Algorithm SHA256).Hash

    docker network create $NetworkName | Out-Null
    docker run -d --name $KeyServerContainer --network $NetworkName `
        -v "${TempRootDocker}/keysrv:/srv:ro" `
        python:3.12-alpine `
        sh -c "cd /srv && python -m http.server 8000" | Out-Null

    docker run -d --name $LiteContainer --network $NetworkName `
        --add-host blockchain-services:127.0.0.1 `
        --add-host guacamole:127.0.0.1 `
        --add-host guacd:127.0.0.1 `
        --add-host mysql:127.0.0.1 `
        --add-host ops-worker:127.0.0.1 `
        -e GUAC_ADMIN_USER=admin `
        -e GUAC_ADMIN_PASS=TestPass_12345 `
        -e SERVER_NAME=lite.local `
        -e HTTPS_PORT=443 `
        -e HTTP_PORT=80 `
        -e ISSUER=http://lgw-key-sync-keysrv:8000/auth `
        -v "${TempRootDocker}/lite-certs:/etc/ssl/private" `
        -v "${ProjectRootDocker}/openresty/nginx.conf:/usr/local/openresty/nginx/conf/nginx.conf:ro" `
        -v "${ProjectRootDocker}/openresty/lab_access.conf:/etc/openresty/lab_access.conf:ro" `
        -v "${ProjectRootDocker}/openresty/lua:/etc/openresty/lua:ro" `
        -v "${ProjectRootDocker}/web:/var/www/html:ro" `
        labgateway-openresty:latest | Out-Null

    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        $logs = cmd /c "docker logs $LiteContainer 2>&1"
        if ($logs -match "JWT public key ready for external issuer mode") {
            $ready = $true
            break
        }
        Start-Sleep -Seconds 1
    }

    if (-not $ready) {
        throw "Lite container did not report JWT key sync readiness."
    }

    $expectedHash = (Get-FileHash (Join-Path $TempRoot "keysrv/.well-known/public-key.pem") -Algorithm SHA256).Hash
    $afterHash = (Get-FileHash (Join-Path $TempRoot "lite-certs/public_key.pem") -Algorithm SHA256).Hash

    if ($beforeHash -eq $expectedHash) {
        throw "Precondition failed: lite key must start different from issuer key."
    }
    if ($afterHash -ne $expectedHash) {
        throw "Lite key was not synchronized from issuer key."
    }

    Write-Host "JWT key sync integration test passed." -ForegroundColor Green
    Write-Host "before=$beforeHash"
    Write-Host "after=$afterHash"
    Write-Host "expected=$expectedHash"
}
finally {
    Cleanup
}
