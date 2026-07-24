@echo off
setlocal enabledelayedexpansion
REM =================================================================
REM DecentraLabs Gateway - Full Version Setup Script (Windows)
REM Complete blockchain-based authentication system with blockchain-services
REM =================================================================

set "ROOT_ENV_FILE=.env"
set "BLOCKCHAIN_ENV_FILE=blockchain-services\.env"
set "compose_cmd=docker compose"
set "compose_files="
set "compose_full="
set "cf_enabled=0"
set "certbot_enabled=0"
set "aas_enabled=0"
set "fmu_runner_enabled=0"
set "fmu_runner_profile=fmu-runner"
set "external_aas_url="
set "existing_mysql_root_password="
set "existing_guacamole_mysql_password="
set "existing_blockchain_mysql_password="
set "existing_ops_backend_mysql_password="
set "existing_ops_guacamole_mysql_password="
set "existing_ops_secrets_key="
set "existing_basyx_mongo_root_password="
set "existing_basyx_mongo_password="
set "existing_aas_allowed_hosts="
set "existing_aas_service_token="
echo DecentraLabs Gateway - Full Version Setup
echo ==========================================
echo.

REM Check prerequisites
echo Checking prerequisites...
docker --version >nul 2>&1
if errorlevel 1 (
    echo Docker is not installed. Please install Docker Desktop first.
    echo    Visit: https://docs.docker.com/desktop/install/windows-install/
    pause
    exit /b 1
)

docker compose version >nul 2>&1
if errorlevel 1 (
    echo Docker Compose V2 is not available.
    echo    Visit: https://docs.docker.com/compose/install/
    pause
    exit /b 1
)

git --version >nul 2>&1
if errorlevel 1 (
    echo Git is required to initialize the blockchain-services submodule.
    pause
    exit /b 1
)

echo Docker, Docker Compose, and Git are available
echo.

echo Ensuring blockchain-services submodule is present...
git submodule update --init --recursive blockchain-services
if errorlevel 1 (
    echo Failed to initialize blockchain-services submodule.
    pause
    exit /b 1
)
echo blockchain-services submodule ready.
echo.

call :ReadEnvValue "%ROOT_ENV_FILE%" "MYSQL_ROOT_PASSWORD" existing_mysql_root_password
call :ReadEnvValue "%ROOT_ENV_FILE%" "GUACAMOLE_MYSQL_PASSWORD" existing_guacamole_mysql_password
call :ReadEnvValue "%ROOT_ENV_FILE%" "BLOCKCHAIN_MYSQL_PASSWORD" existing_blockchain_mysql_password
call :ReadEnvValue "%ROOT_ENV_FILE%" "OPS_BACKEND_MYSQL_PASSWORD" existing_ops_backend_mysql_password
call :ReadEnvValue "%ROOT_ENV_FILE%" "OPS_GUACAMOLE_MYSQL_PASSWORD" existing_ops_guacamole_mysql_password
call :ReadEnvValue "%ROOT_ENV_FILE%" "OPS_SECRETS_KEY" existing_ops_secrets_key
call :ReadEnvValue "%ROOT_ENV_FILE%" "BASYX_MONGO_ROOT_PASSWORD" existing_basyx_mongo_root_password
call :ReadEnvValue "%ROOT_ENV_FILE%" "BASYX_MONGO_PASSWORD" existing_basyx_mongo_password
call :ReadEnvValue "%ROOT_ENV_FILE%" "AAS_ALLOWED_HOSTS" existing_aas_allowed_hosts
call :ReadEnvValue "%ROOT_ENV_FILE%" "AAS_SERVICE_TOKEN" existing_aas_service_token
REM Check if .env already exists
if exist "%ROOT_ENV_FILE%" (
    echo .env file already exists!
    set /p "overwrite=Do you want to overwrite it? (y/N): "
    if defined overwrite set "overwrite=!overwrite: =!"
    if /i "!overwrite!"=="y" (
        copy ".env.example" "%ROOT_ENV_FILE%" >nul
        echo Overwritten .env file from template
    ) else (
        echo Keeping existing .env file.
    )
) else (
    copy ".env.example" "%ROOT_ENV_FILE%" >nul
    echo Created .env file from template
)
echo.

if exist "%BLOCKCHAIN_ENV_FILE%" (
    echo blockchain-services\.env already exists.
) else (
    if exist "blockchain-services\.env.example" (
        copy "blockchain-services\.env.example" "%BLOCKCHAIN_ENV_FILE%" >nul
        echo Created blockchain-services\.env from template
    ) else (
        echo blockchain-services\.env.example not found. Please update the submodule.
        pause
        exit /b 1
    )
)
call :MigrateSamlEnv
if errorlevel 1 (
    echo Failed to migrate SAML configuration.
    pause
    exit /b 1
)
call :RemoveGatewayManagedBackendEnv
echo.

REM Database Passwords
echo Database Passwords
echo ===================
echo Enter database passwords (leave empty for auto-generated):
set "mysql_root_password="
set /p "mysql_root_password=MySQL root password: "

if "!mysql_root_password!"=="" (
    if not "!existing_mysql_root_password!"=="" (
        call :IsPlaceholderSecret "!existing_mysql_root_password!"
        if errorlevel 1 (
            set "mysql_root_password=!existing_mysql_root_password!"
            echo Reusing existing MySQL root password from .env
        )
    )
)
if "!mysql_root_password!"=="" (
    call :GenerateHex 16 generated_hex
    if not defined generated_hex set "generated_hex=P@ss_%RANDOM%_%TIME:~9%"
    set "mysql_root_password=R00t_!generated_hex!"
    if defined mysql_root_password set "mysql_root_password=!mysql_root_password: =!"
    echo Generated root password: !mysql_root_password!
)

REM Generate independent runtime credentials. These principals are written
REM to .env without being reused by any other schema or service.
set "guacamole_mysql_password=!existing_guacamole_mysql_password!"
set "blockchain_mysql_password=!existing_blockchain_mysql_password!"
set "ops_backend_mysql_password=!existing_ops_backend_mysql_password!"
set "ops_guacamole_mysql_password=!existing_ops_guacamole_mysql_password!"
if defined guacamole_mysql_password call :IsPlaceholderSecret "!guacamole_mysql_password!" && set "guacamole_mysql_password="
if defined blockchain_mysql_password call :IsPlaceholderSecret "!blockchain_mysql_password!" && set "blockchain_mysql_password="
if defined ops_backend_mysql_password call :IsPlaceholderSecret "!ops_backend_mysql_password!" && set "ops_backend_mysql_password="
if defined ops_guacamole_mysql_password call :IsPlaceholderSecret "!ops_guacamole_mysql_password!" && set "ops_guacamole_mysql_password="
if "!guacamole_mysql_password!"=="" call :GenerateHex 16 generated_hex & set "guacamole_mysql_password=GuacApp_!generated_hex!"
if "!blockchain_mysql_password!"=="" call :GenerateHex 16 generated_hex & set "blockchain_mysql_password=ChainApp_!generated_hex!"
if "!ops_backend_mysql_password!"=="" call :GenerateHex 16 generated_hex & set "ops_backend_mysql_password=OpsBackend_!generated_hex!"
if "!ops_guacamole_mysql_password!"=="" call :GenerateHex 16 generated_hex & set "ops_guacamole_mysql_password=OpsGuac_!generated_hex!"
set "ops_secrets_key=!existing_ops_secrets_key!"
if defined ops_secrets_key call :IsPlaceholderSecret "!ops_secrets_key!" && set "ops_secrets_key="
if "!ops_secrets_key!"=="" for /f "delims=" %%K in ('powershell -NoLogo -NoProfile -Command "[Convert]::ToBase64String((1..32 | ForEach-Object { Get-Random -Minimum 0 -Maximum 256 }) -as [byte[]]).TrimEnd('=') -replace '\+', '-' -replace '/', '_'"') do set "ops_secrets_key=%%K"

REM Bundled BaSyx/Mongo credentials are separate and alphanumeric so they are
REM safe in the Mongo URI and never reused by MySQL or application principals.
set "basyx_mongo_root_password=!existing_basyx_mongo_root_password!"
set "basyx_mongo_password=!existing_basyx_mongo_password!"
if defined basyx_mongo_root_password call :IsPlaceholderSecret "!basyx_mongo_root_password!" && set "basyx_mongo_root_password="
if defined basyx_mongo_password call :IsPlaceholderSecret "!basyx_mongo_password!" && set "basyx_mongo_password="
if "!basyx_mongo_root_password!"=="" call :GenerateHex 16 generated_hex & set "basyx_mongo_root_password=AasRoot_!generated_hex!"
if "!basyx_mongo_password!"=="" call :GenerateHex 16 generated_hex & set "basyx_mongo_password=AasApp_!generated_hex!"

call :UpdateEnv "%ROOT_ENV_FILE%" "MYSQL_ROOT_PASSWORD" "!mysql_root_password!"
call :UpdateEnv "%ROOT_ENV_FILE%" "GUACAMOLE_MYSQL_USER" "guacamole_app"
call :UpdateEnv "%ROOT_ENV_FILE%" "GUACAMOLE_MYSQL_PASSWORD" "!guacamole_mysql_password!"
call :UpdateEnv "%ROOT_ENV_FILE%" "BLOCKCHAIN_MYSQL_USER" "blockchain_app"
call :UpdateEnv "%ROOT_ENV_FILE%" "BLOCKCHAIN_MYSQL_PASSWORD" "!blockchain_mysql_password!"
call :UpdateEnv "%ROOT_ENV_FILE%" "OPS_BACKEND_MYSQL_USER" "ops_backend"
call :UpdateEnv "%ROOT_ENV_FILE%" "OPS_BACKEND_MYSQL_PASSWORD" "!ops_backend_mysql_password!"
call :UpdateEnv "%ROOT_ENV_FILE%" "OPS_GUACAMOLE_MYSQL_USER" "ops_guac"
call :UpdateEnv "%ROOT_ENV_FILE%" "OPS_GUACAMOLE_MYSQL_PASSWORD" "!ops_guacamole_mysql_password!"
call :UpdateEnv "%ROOT_ENV_FILE%" "OPS_SECRETS_KEY" "!ops_secrets_key!"
call :UpdateEnv "%ROOT_ENV_FILE%" "BASYX_MONGO_ROOT_USER" "basyx_root"
call :UpdateEnv "%ROOT_ENV_FILE%" "BASYX_MONGO_ROOT_PASSWORD" "!basyx_mongo_root_password!"
call :UpdateEnv "%ROOT_ENV_FILE%" "BASYX_MONGO_USER" "aas_app"
call :UpdateEnv "%ROOT_ENV_FILE%" "BASYX_MONGO_PASSWORD" "!basyx_mongo_password!"

echo.
echo IMPORTANT: Save these passwords securely!
echo    Root password: !mysql_root_password!
echo    Dedicated database principals: guacamole_app, blockchain_app, ops_backend, ops_guac
echo.

REM Guacamole Admin Credentials
echo.
echo Guacamole Admin Credentials
echo ============================
echo These are the credentials for the Guacamole web interface.
echo A strong admin password is required.
set "guac_admin_user="
set "guac_admin_pass="
set /p "guac_admin_user=Guacamole admin username [guacadmin]: "
set /p "guac_admin_pass=Guacamole admin password (leave empty for auto-generated): "

if "!guac_admin_user!"=="" set "guac_admin_user=guacadmin"
if "!guac_admin_pass!"=="" (
    call :GenerateHex 16 generated_hex
    if not defined generated_hex set "generated_hex=%RANDOM%_%TIME:~9%"
    set "guac_admin_pass=Guac_!generated_hex!"
    if defined guac_admin_pass set "guac_admin_pass=!guac_admin_pass: =!"
    echo Generated Guacamole admin password: !guac_admin_pass!
)
if /i "!guac_admin_pass!"=="guacadmin" (
    echo Refusing to use insecure Guacamole admin password. Set a strong value.
    exit /b 1
)
if /i "!guac_admin_pass!"=="changeme" (
    echo Refusing to use insecure Guacamole admin password. Set a strong value.
    exit /b 1
)
if /i "!guac_admin_pass!"=="change_me" (
    echo Refusing to use insecure Guacamole admin password. Set a strong value.
    exit /b 1
)
if /i "!guac_admin_pass!"=="password" (
    echo Refusing to use insecure Guacamole admin password. Set a strong value.
    exit /b 1
)
if /i "!guac_admin_pass!"=="test" (
    echo Refusing to use insecure Guacamole admin password. Set a strong value.
    exit /b 1
)

call :UpdateEnv "%ROOT_ENV_FILE%" "GUAC_ADMIN_USER" "!guac_admin_user!"
call :UpdateEnv "%ROOT_ENV_FILE%" "GUAC_ADMIN_PASS" "!guac_admin_pass!"
echo.

REM Admin Access Token
echo Admin Access Token
echo ============================
echo This token protects /wallet, /billing, /wallet-dashboard, and /billing/admin/** behind OpenResty.
set "access_token="
set /p "access_token=Admin access token (leave empty for auto-generated): "
if defined access_token set "access_token=!access_token: =!"
if "!access_token!"=="=" set "access_token="
if /i "!access_token!"=="CHANGE_ME" set "access_token="

if "!access_token!"=="" (
    call :GenerateHex 16 generated_hex
    if not defined generated_hex set "generated_hex=%RANDOM%%RANDOM%%RANDOM%"
    set "access_token=acc_!generated_hex!"
    echo Generated admin access token: !access_token!
)

call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_ACCESS_TOKEN" "!access_token!"
call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_ACCESS_TOKEN_HEADER" "X-Access-Token"
call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_ACCESS_TOKEN_COOKIE" "access_token"
call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_ACCESS_TOKEN_REQUIRED" "true"
call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_DASHBOARD_LOCAL_ONLY" "true"
echo.
echo Wallet Dashboard Access Scope
echo =============================
echo Choose how /wallet-dashboard and wallet/billing admin routes are exposed:
echo   1^) Localhost only ^(recommended^)
echo   2^) Private networks + admin access token
set "dashboard_access_scope="
set /p "dashboard_access_scope=Choose [1/2] (default: 1): "
if defined dashboard_access_scope set "dashboard_access_scope=!dashboard_access_scope: =!"
if "!dashboard_access_scope!"=="2" (
    call :UpdateEnv "%ROOT_ENV_FILE%" "SECURITY_ALLOW_PRIVATE_NETWORKS" "true"
    call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_DASHBOARD_ALLOW_PRIVATE" "true"
    call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_DASHBOARD_LOCAL_ONLY" "false"
    set "admin_allowed_cidrs="
    set /p "admin_allowed_cidrs=Allowed private CIDRs (comma-separated, leave empty for any private range): "
    if defined admin_allowed_cidrs set "admin_allowed_cidrs=!admin_allowed_cidrs: =!"
    call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_ALLOWED_CIDRS" "!admin_allowed_cidrs!"
    echo Configured wallet dashboard access for private networks protected by ADMIN_ACCESS_TOKEN.
) else (
    call :UpdateEnv "%ROOT_ENV_FILE%" "SECURITY_ALLOW_PRIVATE_NETWORKS" "false"
    call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_DASHBOARD_ALLOW_PRIVATE" "false"
    call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_DASHBOARD_LOCAL_ONLY" "true"
    call :UpdateEnv "%ROOT_ENV_FILE%" "ADMIN_ALLOWED_CIDRS" ""
    echo Configured wallet dashboard access for localhost only.
)
echo.

REM Lab Manager Access Token
echo Lab Manager Access Token
echo ========================
echo This token protects /lab-manager and /ops when accessed outside private networks.
set "lab_manager_token="
set /p "lab_manager_token=Lab Manager token (leave empty for auto-generated): "
if defined lab_manager_token set "lab_manager_token=!lab_manager_token: =!"
if "!lab_manager_token!"=="=" set "lab_manager_token="
if /i "!lab_manager_token!"=="CHANGE_ME" set "lab_manager_token="

if "!lab_manager_token!"=="" (
    call :GenerateHex 16 generated_hex
    if not defined generated_hex set "generated_hex=%RANDOM%%RANDOM%%RANDOM%"
    set "lab_manager_token=lab_!generated_hex!"
    echo Generated Lab Manager token: !lab_manager_token!
)

call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_MANAGER_TOKEN" "!lab_manager_token!"
call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_MANAGER_TOKEN_HEADER" "X-Lab-Manager-Token"
call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_MANAGER_TOKEN_COOKIE" "lab_manager_token"
call :ReadEnvValue "%ROOT_ENV_FILE%" "AUTH_ACCESS_CODE_REDEEMER_TOKEN" access_code_redeemer_token
if /i "!access_code_redeemer_token!"=="CHANGE_ME" set "access_code_redeemer_token="
if "!access_code_redeemer_token!"=="" (
    call :GenerateHex 32 generated_hex
    if not defined generated_hex set "generated_hex=%RANDOM%%RANDOM%%RANDOM%%RANDOM%"
    set "access_code_redeemer_token=acr_!generated_hex!"
    echo Generated access-code redeemer token.
)
call :UpdateEnv "%ROOT_ENV_FILE%" "AUTH_ACCESS_CODE_REDEEMER_TOKEN" "!access_code_redeemer_token!"
call :ReadEnvValue "%ROOT_ENV_FILE%" "ACCESS_CODE_ENCRYPTION_KEY" access_code_encryption_key
if /i "!access_code_encryption_key!"=="CHANGE_ME" set "access_code_encryption_key="
if "!access_code_encryption_key!"=="" (
    call :GenerateObserverSecret access_code_encryption_key
    echo Generated access-code encryption key.
)
call :UpdateEnv "%ROOT_ENV_FILE%" "ACCESS_CODE_ENCRYPTION_KEY" "!access_code_encryption_key!"
call :ReadEnvValue "%ROOT_ENV_FILE%" "SESSION_OBSERVATION_INGEST_TOKEN" session_observation_ingest_token
if /i "!session_observation_ingest_token!"=="CHANGE_ME" set "session_observation_ingest_token="
if "!session_observation_ingest_token!"=="" (
    call :GenerateHex 32 generated_hex
    if not defined generated_hex set "generated_hex=%RANDOM%%RANDOM%%RANDOM%%RANDOM%"
    set "session_observation_ingest_token=soi_!generated_hex!"
    echo Generated session-observation ingestion token.
)
call :UpdateEnv "%ROOT_ENV_FILE%" "SESSION_OBSERVATION_INGEST_TOKEN" "!session_observation_ingest_token!"
call :ReadEnvValue "%ROOT_ENV_FILE%" "OPS_INTERNAL_AUTH_TOKEN" ops_internal_auth_token
if /i "!ops_internal_auth_token!"=="CHANGE_ME" set "ops_internal_auth_token="
if "!ops_internal_auth_token!"=="" (
    call :GenerateHex 32 generated_hex
    if not defined generated_hex set "generated_hex=%RANDOM%%RANDOM%%RANDOM%%RANDOM%"
    set "ops_internal_auth_token=ops_!generated_hex!"
    echo Generated dedicated Ops Worker internal-auth token.
)
call :UpdateEnv "%ROOT_ENV_FILE%" "OPS_INTERNAL_AUTH_TOKEN" "!ops_internal_auth_token!"
call :UpdateEnv "%ROOT_ENV_FILE%" "OPS_INTERNAL_AUTH_HEADER" "X-Ops-Internal-Token"
echo.

echo Lab Manager Backend Allowlist
echo =============================
echo Optional CIDR allowlist enforced by blockchain-services for /lab-admin calls authenticated with LAB_MANAGER_TOKEN.
echo Leave empty to keep the current behavior and allow any request that already passes the existing admin network policy.
set "lab_manager_allowed_cidrs="
set /p "lab_manager_allowed_cidrs=LAB_MANAGER_ALLOWED_CIDRS [empty]: "
if defined lab_manager_allowed_cidrs set "lab_manager_allowed_cidrs=!lab_manager_allowed_cidrs: =!"
call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_MANAGER_ALLOWED_CIDRS" "!lab_manager_allowed_cidrs!"
if "!lab_manager_allowed_cidrs!"=="" (
    echo    * LAB_MANAGER_ALLOWED_CIDRS left empty ^(no extra /lab-admin CIDR allowlist^).
) else (
    echo    * LAB_MANAGER_ALLOWED_CIDRS set to: !lab_manager_allowed_cidrs!
)
echo.



REM Domain Configuration
echo Domain Configuration
echo =====================
echo Enter your domain name (or press Enter for localhost):
set /p "domain=Domain: "
if defined domain set "domain=!domain: =!"
if not defined domain set "domain=localhost"
if "!domain!"=="" set "domain=localhost"

if /i "!domain!"=="localhost" (
    echo Configuring for local development...
    call :UpdateEnv "%ROOT_ENV_FILE%" "SERVER_NAME" "localhost"
    call :UpdateEnv "%ROOT_ENV_FILE%" "HTTPS_PORT" "8443"
    call :UpdateEnv "%ROOT_ENV_FILE%" "HTTP_PORT" "8081"
    call :UpdateEnv "%ROOT_ENV_FILE%" "OPENRESTY_BIND_ADDRESS" "127.0.0.1"
    call :UpdateEnv "%ROOT_ENV_FILE%" "OPENRESTY_BIND_HTTPS_PORT" "8443"
    call :UpdateEnv "%ROOT_ENV_FILE%" "OPENRESTY_BIND_HTTP_PORT" "8081"
    set "https_port=8443"
    set "http_port=8081"
    echo    * Server: https://localhost:8443
    echo    * Using development ports ^(8443/8081^)
) else (
    echo Configuring for production...
    call :UpdateEnv "%ROOT_ENV_FILE%" "SERVER_NAME" "!domain!"
    
    echo.
    echo Deployment Mode
    echo ---------------
    echo How is the gateway exposed to the internet?
    echo   1^) Direct - Gateway has a public IP ^(ports bound directly^)
    echo   2^) Router - Behind NAT/router with port forwarding ^(e.g., router:8043 -^> host:443^)
    set /p "deploy_mode=Choose [1/2] (default: 1): "
    if defined deploy_mode set "deploy_mode=!deploy_mode: =!"
    
    if "!deploy_mode!"=="2" (
        echo Router mode selected.
        call :UpdateEnv "%ROOT_ENV_FILE%" "OPENRESTY_BIND_ADDRESS" "0.0.0.0"
        set /p "public_https=Public HTTPS port (the port clients use, e.g., 8043): "
        if defined public_https set "public_https=!public_https: =!"
        if "!public_https!"=="" set "public_https=443"
        set /p "local_https=Local HTTPS port to bind on this host (default: 443): "
        if defined local_https set "local_https=!local_https: =!"
        if "!local_https!"=="" set "local_https=443"
        set /p "public_http=Public HTTP port (default: 80): "
        if defined public_http set "public_http=!public_http: =!"
        if "!public_http!"=="" set "public_http=80"
        set /p "local_http=Local HTTP port to bind on this host (default: 80): "
        if defined local_http set "local_http=!local_http: =!"
        if "!local_http!"=="" set "local_http=80"
        call :UpdateEnv "%ROOT_ENV_FILE%" "HTTPS_PORT" "!public_https!"
        call :UpdateEnv "%ROOT_ENV_FILE%" "HTTP_PORT" "!public_http!"
        call :UpdateEnv "%ROOT_ENV_FILE%" "OPENRESTY_BIND_HTTPS_PORT" "!local_https!"
        call :UpdateEnv "%ROOT_ENV_FILE%" "OPENRESTY_BIND_HTTP_PORT" "!local_http!"
        set "https_port=!public_https!"
        set "http_port=!public_http!"
        echo    * Public URL: https://!domain!:!public_https!
        echo    * OpenResty will bind to 0.0.0.0:!local_https! and 0.0.0.0:!local_http!
    ) else (
        echo Direct mode selected.
        call :UpdateEnv "%ROOT_ENV_FILE%" "OPENRESTY_BIND_ADDRESS" "0.0.0.0"
        set /p "direct_https=HTTPS port (default: 443): "
        if defined direct_https set "direct_https=!direct_https: =!"
        if "!direct_https!"=="" set "direct_https=443"
        set /p "direct_http=HTTP port (default: 80): "
        if defined direct_http set "direct_http=!direct_http: =!"
        if "!direct_http!"=="" set "direct_http=80"
        call :UpdateEnv "%ROOT_ENV_FILE%" "HTTPS_PORT" "!direct_https!"
        call :UpdateEnv "%ROOT_ENV_FILE%" "HTTP_PORT" "!direct_http!"
        call :UpdateEnv "%ROOT_ENV_FILE%" "OPENRESTY_BIND_HTTPS_PORT" "!direct_https!"
        call :UpdateEnv "%ROOT_ENV_FILE%" "OPENRESTY_BIND_HTTP_PORT" "!direct_http!"
        set "https_port=!direct_https!"
        set "http_port=!direct_http!"
        echo    * Server: https://!domain!:!direct_https!
        echo    * Using ports ^(!direct_https!/!direct_http!^)
    )
)
echo.

echo JWT Issuer ^(Full/Lite^)
echo ======================
echo ISSUER controls which JWT issuer OpenResty accepts:
echo   - Leave empty -^> Full mode ^(this gateway handles auth + access^).
echo   - Set https://^<your-full-gateway-domain^>/auth -^> Lite mode ^(trust Full-issued JWTs^).
echo   - In Lite mode, public key sync is automatic from https://^<issuer-origin^>/.well-known/public-key.pem.
echo   - Lite mode disables local auth/billing/intents endpoints, but keeps lab/FMU access using those external JWTs.
call :ReadEnvValue "%ROOT_ENV_FILE%" "ISSUER" current_issuer
if defined current_issuer (
    echo Current ISSUER in .env: !current_issuer!
) else (
    echo Current ISSUER in .env: ^(empty^)
)
set "issuer_value="
set /p "issuer_value=ISSUER [empty->Full, https://full/auth->Lite]: "
if defined issuer_value set "issuer_value=!issuer_value: =!"
call :UpdateEnv "%ROOT_ENV_FILE%" "ISSUER" "!issuer_value!"
if "!issuer_value!"=="" (
    call :UpdateEnv "%ROOT_ENV_FILE%" "BLOCKCHAIN_SERVICES_ENABLED" "true"
    echo    * ISSUER left empty ^(Full mode^).
    echo    * Embedded blockchain-services enabled.
    call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_ADMIN_BACKEND_URL" ""
    call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_ADMIN_BACKEND_TOKEN" ""
    call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_ADMIN_BACKEND_TOKEN_HEADER" "X-Lab-Manager-Token"
    call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_ADMIN_BACKEND_ALLOW_INSECURE" "false"
    echo    * LAB_ADMIN_BACKEND_URL left empty ^(Full mode uses embedded blockchain-services^).
    call :ReadEnvValue "%ROOT_ENV_FILE%" "SESSION_OBSERVER_GATEWAY_ID" session_observer_gateway_id
    call :ReadEnvValue "%ROOT_ENV_FILE%" "SESSION_OBSERVER_SIGNING_SECRET" session_observer_signing_secret
    call :ReadEnvValue "%ROOT_ENV_FILE%" "SESSION_OBSERVER_CREDENTIALS_JSON" session_observer_credentials_json
    if not defined session_observer_gateway_id set "session_observer_gateway_id=!domain!"
    if not defined session_observer_signing_secret call :GenerateObserverSecret session_observer_signing_secret
    if not defined session_observer_credentials_json set "session_observer_credentials_json={}"
    if "!session_observer_credentials_json!"=="{}" set "session_observer_credentials_json={^"!session_observer_gateway_id!^":^"!session_observer_signing_secret!^"}"
    call :UpdateEnv "%ROOT_ENV_FILE%" "SESSION_OBSERVER_GATEWAY_ID" "!session_observer_gateway_id!"
    call :UpdateEnv "%ROOT_ENV_FILE%" "SESSION_OBSERVER_SIGNING_SECRET" "!session_observer_signing_secret!"
    call :UpdateEnv "%ROOT_ENV_FILE%" "SESSION_OBSERVER_CREDENTIALS_JSON" "!session_observer_credentials_json!"
    call :ReadEnvValue "%ROOT_ENV_FILE%" "ACCESS_CODE_REDEEMER_CREDENTIALS_JSON" access_code_redeemer_credentials_json
    if not defined access_code_redeemer_credentials_json set "access_code_redeemer_credentials_json={}"
    if "!access_code_redeemer_credentials_json!"=="{}" set "access_code_redeemer_credentials_json={^"!session_observer_gateway_id!^":^"!access_code_redeemer_token!^"}"
    call :UpdateEnv "%ROOT_ENV_FILE%" "ACCESS_CODE_REDEEMER_CREDENTIALS_JSON" "!access_code_redeemer_credentials_json!"
    call :UpdateEnv "%ROOT_ENV_FILE%" "ACCESS_AUDIT_URL" ""
    call :UpdateEnv "%ROOT_ENV_FILE%" "AUTH_SESSION_TICKET_ISSUE_URL" "http://blockchain-services:8080/auth/fmu/session-ticket/issue"
    call :UpdateEnv "%ROOT_ENV_FILE%" "AUTH_SESSION_TICKET_REDEEM_URL" "http://blockchain-services:8080/auth/fmu/session-ticket/redeem"
    echo    * Configured a dedicated signed session-observer credential for this Full gateway.
) else (
    call :UpdateEnv "%ROOT_ENV_FILE%" "BLOCKCHAIN_SERVICES_ENABLED" "false"
    echo    * ISSUER set to: !issuer_value! ^(Lite mode^).
    echo    * Embedded blockchain-services kept dormant ^(Lite mode^).
    echo.
    echo Lite /lab-admin Remote Backend
    echo ==============================
    echo Optional. Configure this only if this Lite gateway must publish/update labs on-chain from /lab-manager.
    echo Leave empty to keep /lab-admin blocked in Lite mode.
    set "lab_admin_backend_url="
    set /p "lab_admin_backend_url=LAB_ADMIN_BACKEND_URL [empty -^> blocked]: "
    if defined lab_admin_backend_url set "lab_admin_backend_url=!lab_admin_backend_url: =!"
    call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_ADMIN_BACKEND_URL" "!lab_admin_backend_url!"
    call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_ADMIN_BACKEND_TOKEN_HEADER" "X-Lab-Manager-Token"
    call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_ADMIN_BACKEND_ALLOW_INSECURE" "false"
    if "!lab_admin_backend_url!"=="" (
        call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_ADMIN_BACKEND_TOKEN" ""
        echo    * LAB_ADMIN_BACKEND_URL left empty ^(/lab-admin remains blocked in Lite mode^).
        echo    * LAB_ADMIN_BACKEND_TOKEN left empty.
    ) else (
        set "lab_admin_backend_token="
        set /p "lab_admin_backend_token=LAB_ADMIN_BACKEND_TOKEN [empty -^> configure later]: "
        if defined lab_admin_backend_token set "lab_admin_backend_token=!lab_admin_backend_token: =!"
        call :UpdateEnv "%ROOT_ENV_FILE%" "LAB_ADMIN_BACKEND_TOKEN" "!lab_admin_backend_token!"
        echo    * LAB_ADMIN_BACKEND_URL set to: !lab_admin_backend_url!
        if "!lab_admin_backend_token!"=="" (
            echo    * LAB_ADMIN_BACKEND_TOKEN left empty ^(/lab-admin remote calls will fail until it is configured^).
        ) else (
            echo    * LAB_ADMIN_BACKEND_TOKEN configured.
        )
    )
    echo    * LAB_ADMIN_BACKEND_TOKEN_HEADER set to: X-Lab-Manager-Token
    echo    * LAB_ADMIN_BACKEND_ALLOW_INSECURE set to: false
    echo.
    echo Lite Gateway Trust Bundle
    echo =========================
    echo Import the bundle created on Full with scripts\Issue-LiteTrustBundle.ps1.
    set "lite_trust_bundle="
    set /p "lite_trust_bundle=Trust bundle path: "
    if not exist "!lite_trust_bundle!" (
        echo A Full-issued trust bundle is required in Lite mode.
        exit /b 1
    )
    call :ReadEnvValue "!lite_trust_bundle!" "ISSUER" bundle_issuer
    call :ReadEnvValue "!lite_trust_bundle!" "AUTH_ACCESS_CODE_REDEEMER_TOKEN" bundle_redeemer
    call :ReadEnvValue "!lite_trust_bundle!" "ACCESS_AUDIT_URL" bundle_audit_url
    call :ReadEnvValue "!lite_trust_bundle!" "SERVER_NAME" bundle_server_name
    call :ReadEnvValue "!lite_trust_bundle!" "SESSION_OBSERVER_GATEWAY_ID" bundle_gateway_id
    call :ReadEnvValue "!lite_trust_bundle!" "SESSION_OBSERVER_SIGNING_SECRET" bundle_observer_secret
    call :ReadEnvValue "!lite_trust_bundle!" "GUACAMOLE_PROVISIONER_TOKEN" bundle_guacamole_provisioner_token
    call :ReadEnvValue "!lite_trust_bundle!" "GUACAMOLE_PROVISIONER_TOKEN_HEADER" bundle_guacamole_provisioner_token_header
    call :ReadEnvValue "!lite_trust_bundle!" "FMU_GATEWAY_ID" bundle_fmu_gateway_id
    call :ReadEnvValue "!lite_trust_bundle!" "FMU_JWT_AUDIENCE" bundle_fmu_audience
    call :ReadEnvValue "!lite_trust_bundle!" "AUTH_SESSION_TICKET_ISSUE_URL" bundle_ticket_issue_url
    call :ReadEnvValue "!lite_trust_bundle!" "AUTH_SESSION_TICKET_REDEEM_URL" bundle_ticket_redeem_url
    if not defined bundle_issuer exit /b 1
    if not defined bundle_redeemer exit /b 1
    if not defined bundle_audit_url exit /b 1
    if not defined bundle_server_name exit /b 1
    if not defined bundle_gateway_id exit /b 1
    if not defined bundle_observer_secret exit /b 1
    if not defined bundle_guacamole_provisioner_token exit /b 1
    if not defined bundle_guacamole_provisioner_token_header exit /b 1
    if not defined bundle_fmu_gateway_id exit /b 1
    if not defined bundle_fmu_audience exit /b 1
    if not defined bundle_ticket_issue_url exit /b 1
    if not defined bundle_ticket_redeem_url exit /b 1
    if /i not "!bundle_issuer!"=="!issuer_value!" (
        echo Trust bundle ISSUER does not match the configured Full issuer.
        exit /b 1
    )
    if /i not "!bundle_server_name!"=="!domain!" (
        echo Trust bundle SERVER_NAME does not match this Lite gateway.
        exit /b 1
    )
    if /i not "!bundle_gateway_id!"=="!domain!" (
        echo Trust bundle gateway ID does not match this Lite gateway.
        exit /b 1
    )
    if /i not "!bundle_fmu_gateway_id!"=="!domain!" (
        echo Trust bundle FMU gateway ID does not match this Lite gateway.
        exit /b 1
    )
    call :UpdateEnv "%ROOT_ENV_FILE%" "AUTH_ACCESS_CODE_REDEEMER_TOKEN" "!bundle_redeemer!"
    call :UpdateEnv "%ROOT_ENV_FILE%" "ACCESS_AUDIT_URL" "!bundle_audit_url!"
    call :UpdateEnv "%ROOT_ENV_FILE%" "SESSION_OBSERVER_GATEWAY_ID" "!bundle_gateway_id!"
    call :UpdateEnv "%ROOT_ENV_FILE%" "SESSION_OBSERVER_SIGNING_SECRET" "!bundle_observer_secret!"
    call :UpdateEnv "%ROOT_ENV_FILE%" "GUACAMOLE_PROVISIONER_TOKEN" "!bundle_guacamole_provisioner_token!"
    call :UpdateEnv "%ROOT_ENV_FILE%" "GUACAMOLE_PROVISIONER_TOKEN_HEADER" "!bundle_guacamole_provisioner_token_header!"
    call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_GATEWAY_ID" "!bundle_fmu_gateway_id!"
    call :UpdateEnv "%ROOT_ENV_FILE%" "AUTH_SESSION_TICKET_ISSUE_URL" "!bundle_ticket_issue_url!"
    call :UpdateEnv "%ROOT_ENV_FILE%" "AUTH_SESSION_TICKET_REDEEM_URL" "!bundle_ticket_redeem_url!"
    call :UpdateEnv "%ROOT_ENV_FILE%" "SESSION_OBSERVER_CREDENTIALS_JSON" "{}"
    echo    * Imported redeem, session-observation and Guacamole-provisioner credentials for !bundle_gateway_id!.
)
echo.

echo FMU Runner Integration
echo ======================
echo Controls whether /fmu and FMU AAS sync routes are active on this gateway.
echo When disabled, OpenResty starts without requiring the fmu-runner container and those routes return 503.
echo FMU runner is optional and disabled unless FMU_RUNNER_ENABLED is explicitly enabled.
set "current_fmu_runner_enabled="
call :ReadEnvValue "%ROOT_ENV_FILE%" "FMU_RUNNER_ENABLED" current_fmu_runner_enabled
if not defined current_fmu_runner_enabled (
    set "current_fmu_runner_enabled=false"
) else (
    if /i "!current_fmu_runner_enabled!"=="false" (
        set "current_fmu_runner_enabled=false"
    ) else if /i "!current_fmu_runner_enabled!"=="0" (
        set "current_fmu_runner_enabled=false"
    ) else if /i "!current_fmu_runner_enabled!"=="no" (
        set "current_fmu_runner_enabled=false"
    ) else (
        set "current_fmu_runner_enabled=true"
    )
)
if /i "!current_fmu_runner_enabled!"=="true" (
    set "fmu_prompt=Y/n"
) else (
    set "fmu_prompt=y/N"
)
set "enable_fmu_runner="
set /p "enable_fmu_runner=Enable FMU runner integration? [!fmu_prompt!]: "
if defined enable_fmu_runner set "enable_fmu_runner=!enable_fmu_runner: =!"
if /i "!enable_fmu_runner!"=="" (
    if /i "!current_fmu_runner_enabled!"=="true" (
        set "fmu_runner_enabled=1"
    ) else (
        set "fmu_runner_enabled=0"
    )
) else if /i "!enable_fmu_runner!"=="y" (
    set "fmu_runner_enabled=1"
) else if /i "!enable_fmu_runner!"=="yes" (
    set "fmu_runner_enabled=1"
) else if /i "!enable_fmu_runner!"=="true" (
    set "fmu_runner_enabled=1"
) else if "!enable_fmu_runner!"=="1" (
    set "fmu_runner_enabled=1"
) else (
    set "fmu_runner_enabled=0"
)
if "!fmu_runner_enabled!"=="1" (
    call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_RUNNER_ENABLED" "true"
    set "current_fmu_backend_mode="
    call :ReadEnvValue "%ROOT_ENV_FILE%" "FMU_BACKEND_MODE" current_fmu_backend_mode
    if /i "!current_fmu_backend_mode!"=="local" (
        set "current_fmu_backend_mode=local"
    ) else (
        set "current_fmu_backend_mode=station"
    )
    set "selected_fmu_backend_mode="
    set /p "selected_fmu_backend_mode=FMU execution backend [station/local] (default: !current_fmu_backend_mode!): "
    if defined selected_fmu_backend_mode set "selected_fmu_backend_mode=!selected_fmu_backend_mode: =!"
    if not defined selected_fmu_backend_mode set "selected_fmu_backend_mode=!current_fmu_backend_mode!"
    if /i "!selected_fmu_backend_mode!"=="local" (
        set "fmu_runner_profile=fmu-local-dev"
        call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_BACKEND_MODE" "local"
        call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_LOCAL_DEV_MODE" "true"
        echo    * Local FMU execution selected.
        echo    * The local FMU runner will restart automatically after a Docker or host restart.
        echo    * Full mode retrieves JWKS over the dedicated fmu_auth network; Lite mode uses the external issuer JWKS endpoint.
    ) else if /i "!selected_fmu_backend_mode!"=="station" (
        set "fmu_runner_profile=fmu-runner"
        call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_BACKEND_MODE" "station"
        call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_LOCAL_DEV_MODE" "false"
        echo    * Lab Station FMU execution selected.
        echo    * The production FMU runner will restart automatically after a Docker or host restart.
    ) else (
        echo Invalid FMU execution backend: !selected_fmu_backend_mode! ^(choose station or local^).
        exit /b 1
    )
    echo    * FMU runner enabled. /fmu routes are active.
    echo    * Compose profile: !fmu_runner_profile!.
) else (
    call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_RUNNER_ENABLED" "false"
    rem Keep the persisted selection safe when the optional integration is disabled.
    rem The local profile also hard-codes this guard, but clearing stale state
    rem keeps .env and the selected deployment mode consistent.
    call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_LOCAL_DEV_MODE" "false"
    echo    * FMU runner disabled. Startup will use '--scale fmu-runner=0'.
    echo    * No FMU runner container will be configured.
)
echo.

echo AAS Support ^(Asset Administration Shell^)
echo ==========================================
if not "!issuer_value!"=="" (
    echo Lite Gateway detected - AAS is only available on Full Gateway instances. Skipping.
    call :UpdateEnv "%ROOT_ENV_FILE%" "BASYX_AAS_URL" ""
    call :UpdateEnv "%ROOT_ENV_FILE%" "AAS_ALLOWED_HOSTS" ""
    call :UpdateEnv "%ROOT_ENV_FILE%" "AAS_SERVICE_TOKEN" ""
) else (
    echo AAS enables publishing Digital Twin descriptions ^(IDTA 02006^) for FMUs and physical labs.
    echo   1^) Bundled BaSyx  - Deploy the included BaSyx AAS Server container ^(recommended^)
    echo   2^) External server - Connect to an existing AAS server ^(BaSyx, NOVAAS, etc.^)
    echo   3^) None           - Skip AAS support
    set /p "aas_option=AAS server [1/2/3] (default: 1): "
    if defined aas_option set "aas_option=!aas_option: =!"
    if "!aas_option!"=="2" (
        echo External AAS server selected.
        set /p "external_aas_url=External AAS API base URL ^(HTTPS only, e.g. https://my-aas.example.com^): "
        if defined external_aas_url set "external_aas_url=!external_aas_url: =!"
        if "!external_aas_url!"=="" (
            echo No URL provided. AAS support disabled.
            call :UpdateEnv "%ROOT_ENV_FILE%" "BASYX_AAS_URL" ""
        ) else (
            echo    * External AAS server: !external_aas_url!
            echo    * Bundled basyx-aas-server / basyx-mongo containers will NOT be started.
            call :UpdateEnv "%ROOT_ENV_FILE%" "BASYX_AAS_URL" "!external_aas_url!"
            set "aas_allowed_hosts=!existing_aas_allowed_hosts!"
            set /p "aas_allowed_hosts=Exact allowlisted AAS hostname ^(without port^): "
            if not defined aas_allowed_hosts set "aas_allowed_hosts=!existing_aas_allowed_hosts!"
            set "aas_service_token=!existing_aas_service_token!"
            set /p "aas_service_token=Dedicated AAS service token ^(leave empty to generate^): "
            if not defined aas_service_token (
                call :GenerateHex 32 generated_hex
                set "aas_service_token=aas_!generated_hex!"
            )
            call :UpdateEnv "%ROOT_ENV_FILE%" "AAS_ALLOWED_HOSTS" "!aas_allowed_hosts!"
            call :UpdateEnv "%ROOT_ENV_FILE%" "AAS_SERVICE_TOKEN" "!aas_service_token!"
            call :UpdateEnv "%ROOT_ENV_FILE%" "AAS_SERVICE_TOKEN_HEADER" "Authorization"
        )
    ) else if "!aas_option!"=="3" (
        echo AAS support disabled.
        call :UpdateEnv "%ROOT_ENV_FILE%" "BASYX_AAS_URL" ""
        call :UpdateEnv "%ROOT_ENV_FILE%" "AAS_ALLOWED_HOSTS" ""
        call :UpdateEnv "%ROOT_ENV_FILE%" "AAS_SERVICE_TOKEN" ""
    ) else (
        echo Bundled BaSyx selected.
        call :UpdateEnv "%ROOT_ENV_FILE%" "BASYX_AAS_URL" ""
        call :UpdateEnv "%ROOT_ENV_FILE%" "AAS_ALLOWED_HOSTS" ""
        call :UpdateEnv "%ROOT_ENV_FILE%" "AAS_SERVICE_TOKEN" ""
        set "aas_enabled=1"
    )
)
echo.

echo Remote Access (Cloudflare Tunnel)
echo =================================
set "enable_cf="
set /p "enable_cf=Enable Cloudflare Tunnel to expose the gateway without opening inbound ports? (y/N): "
if defined enable_cf set "enable_cf=!enable_cf: =!"
if /i "!enable_cf!"=="y" set "cf_enabled=1"
if /i "!enable_cf!"=="yes" set "cf_enabled=1"

if "!cf_enabled!"=="1" (
    set "cf_token="
    set /p "cf_token=Cloudflare Tunnel token (leave empty to use a Quick Tunnel): "
    if defined cf_token set "cf_token=!cf_token: =!"
    if not "!cf_token!"=="" (
        call :UpdateEnv "%ROOT_ENV_FILE%" "CLOUDFLARE_TUNNEL_TOKEN" "!cf_token!"
    ) else (
        call :UpdateEnv "%ROOT_ENV_FILE%" "CLOUDFLARE_TUNNEL_TOKEN" ""
    )
    if /i "!domain!"=="localhost" (
        echo Cloudflare enabled: switching to standard ports ^(443/80^) for a cleaner public URL.
        call :UpdateEnv "%ROOT_ENV_FILE%" "HTTPS_PORT" "443"
        call :UpdateEnv "%ROOT_ENV_FILE%" "HTTP_PORT" "80"
        call :UpdateEnv "%ROOT_ENV_FILE%" "OPENRESTY_BIND_HTTPS_PORT" "443"
        call :UpdateEnv "%ROOT_ENV_FILE%" "OPENRESTY_BIND_HTTP_PORT" "80"
        set "https_port=443"
        set "http_port=80"
    )
)
set "gateway_public_origin=https://!domain!"
if not "!https_port!"=="443" set "gateway_public_origin=!gateway_public_origin!:!https_port!"
set "expected_fmu_audience=!gateway_public_origin!/fmu"
if not "!issuer_value!"=="" if /i not "!bundle_fmu_audience!"=="!expected_fmu_audience!" (
    echo Trust bundle FMU audience does not match this Lite gateway public URL ^(!expected_fmu_audience!^).
    exit /b 1
)
call :UpdateEnv "%ROOT_ENV_FILE%" "FMU_JWT_AUDIENCE" "!gateway_public_origin!/fmu"
echo    * FMU JWT audience: !expected_fmu_audience!
if "!cf_enabled!"=="1" (
    if not "!cf_token!"=="" (
        set "cf_profile=cloudflare-token"
        set "cf_service=cloudflared-token"
    ) else (
        set "cf_profile=cloudflare"
        set "cf_service=cloudflared"
    )
)
REM Build complete compose command: base + files + profile
set "compose_full=%compose_cmd% !compose_files!"
if "!cf_enabled!"=="1" set "compose_full=!compose_full! --profile !cf_profile!"
if "!fmu_runner_enabled!"=="1" set "compose_full=!compose_full! --profile !fmu_runner_profile!"
set "compose_up_args=up -d"
if "!fmu_runner_enabled!"=="0" set "compose_up_args=up -d --scale fmu-runner=0"
echo.

echo Ops Worker configuration
echo ------------------------
echo The stack mounts ops-worker/hosts.empty.json by default.
echo To use your own hosts file, set OPS_CONFIG_PATH=./ops-worker/hosts.json before running docker compose.
echo.

if not exist certs mkdir certs
if not exist blockchain-data mkdir blockchain-data
if not exist lab-content mkdir lab-content
if not exist fmu-data mkdir fmu-data
if not exist fmu-proxy-runtime mkdir fmu-proxy-runtime
if not exist fmu-proxy-runtime\binaries mkdir fmu-proxy-runtime\binaries
if not exist fmu-proxy-runtime\binaries\linux64 mkdir fmu-proxy-runtime\binaries\linux64
if not exist fmu-proxy-runtime\binaries\win64 mkdir fmu-proxy-runtime\binaries\win64
if not exist fmu-proxy-runtime\binaries\darwin64 mkdir fmu-proxy-runtime\binaries\darwin64
if not exist ops-data mkdir ops-data
if not exist ops-data\guac-revocation-spool mkdir ops-data\guac-revocation-spool
if not exist secrets mkdir secrets
if not exist certs\.gitkeep type nul > certs\.gitkeep
call :SecureEnvFile "%ROOT_ENV_FILE%"
call :SecureEnvFile "%BLOCKCHAIN_ENV_FILE%"
call :SecureSecretTree "certs"
call :SecureSecretTree "blockchain-data"
call :SecureSecretTree "ops-data"
call :SyncComposeSecrets

echo SSL Certificates
echo ================
if exist certs\fullchain.pem (
    if exist certs\privkey.pem (
        echo SSL certificates found in certs\ - they will be used.
    ) else (
        echo Found certs\fullchain.pem but privkey.pem is missing.
    )
) else (
    echo No SSL certificates in certs\ - OpenResty will auto-generate self-signed certs at startup.
    if /i not "!domain!"=="localhost" (
        echo.
        echo For production, consider adding valid certificates:
        echo   * certs\fullchain.pem ^(certificate chain^)
        echo   * certs\privkey.pem ^(private key^)
        echo Sources: Let's Encrypt ^(certbot^), your CA, or cloud provider.
    )
)
echo.

echo JWT Signing Keys
echo =================
echo blockchain-services will generate keys at runtime if missing (volume ./blockchain-data).
if exist blockchain-data\keys\private_key.pem (
    echo private_key.pem already exists in blockchain-data\keys\ ^(it will be reused^).
) else (
    echo No private_key.pem in blockchain-data\keys\; the container will create a new one at startup.
)
echo.
echo Certbot (Let's Encrypt) - optional automation
echo ============================================
set "cb_domains="
set /p "cb_domains=Domains for TLS (comma-separated, leave empty to skip ACME): "
if defined cb_domains set "cb_domains=!cb_domains: =!"
set "cb_email="
set /p "cb_email=Email for ACME (leave empty to skip ACME): "
if defined cb_email set "cb_email=!cb_email: =!"
if not "%cb_domains%"=="" if not "%cb_email%"=="" (
    call :UpdateEnv "%ROOT_ENV_FILE%" "CERTBOT_DOMAINS" "%cb_domains%"
    call :UpdateEnv "%ROOT_ENV_FILE%" "CERTBOT_EMAIL" "%cb_email%"
    echo Configured CERTBOT_DOMAINS and CERTBOT_EMAIL in .env
) else (
    echo Skipped certbot configuration ^(ACME^). Self-signed certificates will be auto-rotated in-container every ~87 days.
)
set "certbot_domains="
set "certbot_email="
call :ReadEnvValue "%ROOT_ENV_FILE%" "CERTBOT_DOMAINS" certbot_domains
call :ReadEnvValue "%ROOT_ENV_FILE%" "CERTBOT_EMAIL" certbot_email
if not "!certbot_domains!"=="" if not "!certbot_email!"=="" set "certbot_enabled=1"
if "!certbot_enabled!"=="1" set "compose_full=!compose_full! --profile certbot"
if "!aas_enabled!"=="1" set "compose_full=!compose_full! --profile aas"
echo.

echo Blockchain Services Configuration
echo ==================================
echo.
rem Provider registration enabled by default (non-interactive).
call :UpdateEnv "%BLOCKCHAIN_ENV_FILE%" "FEATURES_PROVIDERS_ENABLED" "true"
call :UpdateEnv "%BLOCKCHAIN_ENV_FILE%" "FEATURES_PROVIDERS_REGISTRATION_ENABLED" "true"
call :ReadEnvValue "%BLOCKCHAIN_ENV_FILE%" "CONTRACT_ADDRESS" contract_default
if defined contract_default (
    call :UpdateEnv "%BLOCKCHAIN_ENV_FILE%" "CONTRACT_ADDRESS" "!contract_default!"
)

call :ReadEnvValue "%BLOCKCHAIN_ENV_FILE%" "ETHEREUM_SEPOLIA_RPC_URL" sepolia_default
if not defined sepolia_default set "sepolia_default=https://ethereum-sepolia-rpc.publicnode.com,https://0xrpc.io/sep,https://ethereum-sepolia-public.nodies.app"
set /p "sepolia_rpc=Sepolia RPC URLs (comma separated) [!sepolia_default!]: "
if "!sepolia_rpc!"=="" set "sepolia_rpc=!sepolia_default!"
if not "!sepolia_rpc!"=="" (
    call :UpdateEnv "%BLOCKCHAIN_ENV_FILE%" "ETHEREUM_SEPOLIA_RPC_URL" "!sepolia_rpc!"
)

call :ReadEnvValue "%BLOCKCHAIN_ENV_FILE%" "ALLOWED_ORIGINS" origins_default
if not defined origins_default set "origins_default=https://marketplace-decentralabs.vercel.app"
set /p "allowed_origins=Allowed origins for CORS [!origins_default!]: "
if "!allowed_origins!"=="" set "allowed_origins=!origins_default!"
if not "!allowed_origins!"=="" (
    call :UpdateEnv "%BLOCKCHAIN_ENV_FILE%" "ALLOWED_ORIGINS" "!allowed_origins!"
)

call :ReadEnvValue "%BLOCKCHAIN_ENV_FILE%" "MARKETPLACE_PUBLIC_KEY_URL" mpk_default
if not defined mpk_default set "mpk_default=https://marketplace-decentralabs.vercel.app/.well-known/public-key.pem"
set /p "marketplace_pk=Marketplace public key URL [!mpk_default!]: "
if "!marketplace_pk!"=="" set "marketplace_pk=!mpk_default!"
if not "!marketplace_pk!"=="" (
    call :UpdateEnv "%BLOCKCHAIN_ENV_FILE%" "MARKETPLACE_PUBLIC_KEY_URL" "!marketplace_pk!"
)

echo.
echo Institutional Wallet Reminder
echo -----------------------------
echo Wallet creation/import is handled inside the blockchain-services web console.
echo After creating the wallet, update these variables in %BLOCKCHAIN_ENV_FILE%:
echo    * INSTITUTIONAL_WALLET_ADDRESS
echo    * INSTITUTIONAL_WALLET_PASSWORD
echo Wallet data will be persisted in the blockchain-data\ directory.
echo FMU proxy runtime binaries must be copied into fmu-proxy-runtime\binaries\^{linux64^|win64^|darwin64^} before proxy downloads will work.
echo.

echo Next Steps
echo ==========
echo 1. Review and customize %ROOT_ENV_FILE% if needed
echo 2. Ensure SSL certificates and RSA keys are present in certs\
echo 3. Review blockchain settings in %BLOCKCHAIN_ENV_FILE if needed%
echo 4. Run: !compose_full! !compose_up_args!
echo    Core services and Guacamole use automatic restart policies; the selected FMU profile does too.
if "!cf_enabled!"=="1" (
    echo 5. Cloudflare tunnel: check '!compose_full! logs !cf_service!' for the public hostname ^(or your configured tunnel token domain^).
)
if /i "!domain!"=="localhost" (
    echo Access: https://localhost:!https_port! ^(HTTP: !http_port!^)
) else (
    echo Access: https://!domain!
)
set "token_host="
if /i "!domain!"=="localhost" (
    if "!https_port!"=="443" (
        set "token_host=https://localhost"
    ) else (
        set "token_host=https://localhost:!https_port!"
    )
) else (
    if "!https_port!"=="443" (
        set "token_host=https://!domain!"
    ) else (
        set "token_host=https://!domain!:!https_port!"
    )
)
echo    * Admin dashboard: !token_host!/wallet-dashboard ^(login required^)
echo    * Lab Manager: !token_host!/lab-manager ^(login required^)
echo    * Guacamole: /guacamole/
echo    * Blockchain Services API: /auth
echo.

set /p "start_services=Do you want to start the services now? (Y/n): "
if /i "!start_services!"=="n" goto skip_start
if /i "!start_services!"=="no" goto skip_start

echo.
echo Building and starting services...
echo This may take several minutes on first run...

call !compose_full! down --remove-orphans
if errorlevel 1 goto compose_fail
call !compose_full! build --no-cache
if errorlevel 1 (
    echo.
    echo Initial docker build failed.
    echo Attempting automatic BuildKit cache recovery and one retry...
    docker builder prune -af
    if errorlevel 1 echo Warning: docker builder prune failed. Retrying anyway...
    docker buildx prune -af
    if errorlevel 1 echo Warning: docker buildx prune failed. Retrying anyway...
    call !compose_full! build --no-cache
    if errorlevel 1 goto compose_fail
)
call !compose_full! !compose_up_args!
if errorlevel 1 goto compose_fail
goto compose_success

:compose_fail
echo Failed to start services. Check the error messages above.
goto docker_start_done

:compose_success
echo.
echo Services started successfully!
if /i "!domain!"=="localhost" (
    echo Access your lab at: https://localhost:!https_port!
) else (
    echo Access your lab at: https://!domain!
)
set "token_host="
if /i "!domain!"=="localhost" (
    if "!https_port!"=="443" (
        set "token_host=https://localhost"
    ) else (
        set "token_host=https://localhost:!https_port!"
    )
) else (
    if "!https_port!"=="443" (
        set "token_host=https://!domain!"
    ) else (
        set "token_host=https://!domain!:!https_port!"
    )
)
echo    * Admin dashboard: !token_host!/wallet-dashboard ^(login required^)
echo    * Lab Manager: !token_host!/lab-manager ^(login required^)
    echo    * Guacamole: /guacamole/ ^(!guac_admin_user! / !guac_admin_pass!^)
    echo    * Blockchain Services API: /auth
    if "!cf_enabled!"=="1" (
        echo    * Cloudflare tunnel logs ^(hostname^): !compose_full! logs !cf_service!
    )
    echo.
echo To check status: !compose_full! ps
echo To view logs: !compose_full! logs -f
echo.
echo Configuration:
echo    Environment: %ROOT_ENV_FILE%
echo    Blockchain Services Config: %BLOCKCHAIN_ENV_FILE%
echo    Certificates ^& Keys: certs\
echo    Wallet data directory: blockchain-data\
echo.
echo Full version deployment complete!
echo Your blockchain-based authentication system is now running.
goto docker_start_done

:skip_start
echo Configuration complete!
echo.
echo Next steps:
echo 1. Update blockchain contract and wallet values if needed.
echo 2. Run: !compose_full! !compose_up_args!
echo 3. Access your services as listed above.
if "!cf_enabled!"=="1" (
    echo 4. Cloudflare tunnel hostname: !compose_full! logs !cf_service!
)
echo.
echo For more information, see README.md

:docker_start_done
goto end

:end
echo.
pause
goto :eof

:RemoveGatewayManagedBackendEnv
if not exist "%BLOCKCHAIN_ENV_FILE%" exit /b
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "ADMIN_ACCESS_TOKEN"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "ADMIN_ACCESS_TOKEN_HEADER"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "ADMIN_ACCESS_TOKEN_COOKIE"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "ADMIN_ACCESS_TOKEN_REQUIRED"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "ADMIN_DASHBOARD_LOCAL_ONLY"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "ADMIN_DASHBOARD_ALLOW_PRIVATE"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "SECURITY_ALLOW_PRIVATE_NETWORKS"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "ADMIN_ALLOWED_CIDRS"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "LAB_MANAGER_TOKEN"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "LAB_MANAGER_TOKEN_HEADER"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "LAB_MANAGER_TOKEN_COOKIE"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "LAB_MANAGER_ALLOWED_CIDRS"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "OPS_INTERNAL_AUTH_TOKEN"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "OPS_INTERNAL_AUTH_HEADER"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "GUACAMOLE_MYSQL_USER"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "GUACAMOLE_MYSQL_PASSWORD"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "BLOCKCHAIN_MYSQL_USER"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "BLOCKCHAIN_MYSQL_PASSWORD"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "OPS_BACKEND_MYSQL_USER"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "OPS_BACKEND_MYSQL_PASSWORD"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "OPS_GUACAMOLE_MYSQL_USER"
call :RemoveEnv "%BLOCKCHAIN_ENV_FILE%" "OPS_GUACAMOLE_MYSQL_PASSWORD"
exit /b

:MigrateSamlEnv
if not exist "%BLOCKCHAIN_ENV_FILE%" exit /b 1
if not exist "scripts\Migrate-SamlEnv.ps1" exit /b 1
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "scripts\Migrate-SamlEnv.ps1" -EnvPath "%BLOCKCHAIN_ENV_FILE%" -TemplatePath "blockchain-services\.env.example"
exit /b %errorlevel%

:RemoveEnv
set "env_file=%~1"
set "env_key=%~2"
powershell -NoLogo -NoProfile -Command "& { param($file,$key); if (-not (Test-Path -LiteralPath $file)) { return }; $pattern = '^' + [regex]::Escape($key) + '=.*$'; $content = @(Get-Content -LiteralPath $file | Where-Object { $_ -notmatch $pattern }); Set-Content -LiteralPath $file -Value $content -Encoding Ascii }" "%env_file%" "%env_key%"
exit /b

:UpdateEnv
set "env_file=%~1"
set "env_key=%~2"
set "env_value=%~3"
powershell -NoLogo -NoProfile -Command "& { param($file,$key,$value); if (-not (Test-Path -LiteralPath $file)) { New-Item -Path $file -ItemType File -Force | Out-Null }; $content = @(); if (Test-Path -LiteralPath $file) { $content = @(Get-Content -LiteralPath $file) }; $pattern = '^' + [regex]::Escape($key) + '=.*$'; $replacement = $key + '=' + $value; $updated = $false; for ($i = 0; $i -lt $content.Count; $i++) { if ($content[$i] -match $pattern) { $content[$i] = $replacement; $updated = $true } }; if (-not $updated) { $content += $replacement }; Set-Content -LiteralPath $file -Value $content -Encoding Ascii }" "%env_file%" "%env_key%" "%env_value%"
exit /b

:SyncComposeSecrets
call :WriteComposeSecret "mysql_root_password" "MYSQL_ROOT_PASSWORD"
call :WriteComposeSecret "guacamole_mysql_password" "GUACAMOLE_MYSQL_PASSWORD"
call :WriteComposeSecret "blockchain_mysql_password" "BLOCKCHAIN_MYSQL_PASSWORD"
call :WriteComposeSecret "ops_backend_mysql_password" "OPS_BACKEND_MYSQL_PASSWORD"
call :WriteComposeSecret "ops_guacamole_mysql_password" "OPS_GUACAMOLE_MYSQL_PASSWORD"
call :WriteComposeSecret "guac_admin_pass" "GUAC_ADMIN_PASS"
call :WriteComposeSecret "admin_access_token" "ADMIN_ACCESS_TOKEN"
call :WriteComposeSecret "lab_manager_token" "LAB_MANAGER_TOKEN"
call :WriteComposeSecret "ops_internal_auth_token" "OPS_INTERNAL_AUTH_TOKEN"
call :WriteComposeSecret "ops_secrets_key" "OPS_SECRETS_KEY"
call :WriteComposeSecret "auth_access_code_redeemer_token" "AUTH_ACCESS_CODE_REDEEMER_TOKEN"
call :WriteComposeSecret "session_observation_ingest_token" "SESSION_OBSERVATION_INGEST_TOKEN"
call :WriteComposeSecret "guacamole_provisioner_token" "GUACAMOLE_PROVISIONER_TOKEN"
call :WriteComposeSecret "aas_service_token" "AAS_SERVICE_TOKEN"
call :WriteComposeSecret "lab_admin_backend_token" "LAB_ADMIN_BACKEND_TOKEN"
call :WriteComposeSecret "fmu_station_internal_token" "FMU_STATION_INTERNAL_TOKEN"
call :WriteComposeSecret "auth_session_ticket_internal_token" "AUTH_SESSION_TICKET_INTERNAL_TOKEN"
call :WriteComposeSecret "session_observer_signing_secret" "SESSION_OBSERVER_SIGNING_SECRET"
call :WriteComposeSecret "fmu_proxy_signing_key" "FMU_PROXY_SIGNING_KEY"
call :SecureSecretTree "secrets"
exit /b

:WriteComposeSecret
set "secret_name=%~1"
set "secret_key=%~2"
set "secret_value="
call :ReadEnvValue "%ROOT_ENV_FILE%" "%secret_key%" secret_value
set "DL_COMPOSE_SECRET_PATH=%CD%\secrets\%secret_name%"
set "DL_COMPOSE_SECRET_VALUE=!secret_value!"
powershell -NoLogo -NoProfile -Command "[IO.File]::WriteAllText($env:DL_COMPOSE_SECRET_PATH, $env:DL_COMPOSE_SECRET_VALUE, [Text.UTF8Encoding]::new($false))"
exit /b

:ReadEnvValue
set "read_file=%~1"
set "read_key=%~2"
set "read_result="
if exist "%read_file%" (
    for /f "usebackq tokens=1* delims==" %%A in (`findstr /B /C:"%read_key%=" "%read_file%"`) do (
        set "read_result=%%B"
        goto read_done
    )
)
:read_done
if "%~3" NEQ "" set "%~3=%read_result%"
exit /b

:SecureEnvFile
set "secure_env_file=%~1"
if not exist "%secure_env_file%" exit /b
icacls "%secure_env_file%" /inheritance:r /grant:r "%USERNAME%:F" *S-1-5-18:F *S-1-5-32-544:F >nul 2>&1
if errorlevel 1 echo Warning: unable to restrict ACLs on %secure_env_file%.
exit /b

:SecureSecretTree
set "secure_tree=%~1"
if not exist "%secure_tree%" exit /b
icacls "%secure_tree%" /inheritance:r /grant:r "%USERNAME%:(OI)(CI)F" *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F /T /C >nul 2>&1
if errorlevel 1 echo Warning: unable to restrict ACLs on %secure_tree%.
exit /b

:GenerateHex
setlocal
set "_bytes=%~1"
if "%_bytes%"=="" set "_bytes=16"
for /f %%H in ('powershell -NoLogo -NoProfile -Command "$bytes = New-Object byte[](%_bytes%); [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes); [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()"') do set "_hex=%%H"
endlocal & set "%~2=%_hex%"
exit /b

:GenerateObserverSecret
setlocal
for /f %%H in ('powershell -NoLogo -NoProfile -Command "$bytes = New-Object byte[](32); [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes); [Convert]::ToBase64String($bytes).TrimEnd('=^').Replace('+','-').Replace('/','_')"') do set "_secret=%%H"
endlocal & set "%~1=%_secret%"
exit /b

:IsPlaceholderSecret
set "secret_value=%~1"
if /i "%secret_value%"=="" exit /b 0
if /i "%secret_value%"=="CHANGE_ME" exit /b 0
if /i "%secret_value%"=="CHANGEME" exit /b 0
if /i "%secret_value%"=="SECURE_PASSWORD" exit /b 0
if /i "%secret_value%"=="DB_PASSWORD" exit /b 0
if /i "%secret_value%"=="YOUR_PASSWORD" exit /b 0
if /i "%secret_value%"=="PASSWORD" exit /b 0
if /i "%secret_value%"=="TEST" exit /b 0
exit /b 1
