@echo off
setlocal enabledelayedexpansion
REM =================================================================
REM DecentraLabs Gateway - Full Version Setup Script (Windows)
REM Complete blockchain-based authentication system with blockchain-services
REM =================================================================

set "ROOT_ENV_FILE=.env"
set "BLOCKCHAIN_ENV_FILE=blockchain-services\.env"
set "compose_cmd=docker-compose"

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

docker-compose --version >nul 2>&1
if errorlevel 1 (
    docker compose version >nul 2>&1
    if errorlevel 1 (
        echo Docker Compose is not installed.
        echo    Visit: https://docs.docker.com/compose/install/
        pause
        exit /b 1
    )
    set "compose_cmd=docker compose"
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
    echo Failed to initialize blockchain-services. Please check your Git setup.
    pause
    exit /b 1
)
echo blockchain-services submodule ready.
echo.

REM Check if .env already exists
if exist "%ROOT_ENV_FILE%" (
    echo .env file already exists!
    set /p "overwrite=Do you want to overwrite it? (y/N): "
    set "overwrite=!overwrite: =!"
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
echo.

REM Database Passwords
echo Database Passwords
echo ===================
echo Enter database passwords (leave empty for auto-generated):
set "mysql_root_password="
set "mysql_password="
set /p "mysql_root_password=MySQL root password: "
set /p "mysql_password=Guacamole database password: "

if "!mysql_root_password!"=="" (
    set mysql_root_password=R00t_P@ss_%RANDOM%_%TIME:~9%
    set mysql_root_password=!mysql_root_password: =!
    echo Generated root password: !mysql_root_password!
)

if "!mysql_password!"=="" (
    set mysql_password=Gu@c_%RANDOM%_%TIME:~9%
    set mysql_password=!mysql_password: =!
    echo Generated database password: !mysql_password!
)

call :UpdateEnvBoth "MYSQL_ROOT_PASSWORD" "!mysql_root_password!"
call :UpdateEnvBoth "MYSQL_PASSWORD" "!mysql_password!"

echo Updating Guacamole configuration...
powershell -NoLogo -Command ^
    "& { (Get-Content 'guacamole/guacamole.properties') -replace 'mysql-password:.*', 'mysql-password: !mysql_password!' | Set-Content 'guacamole/guacamole.properties' -Encoding UTF8 }"

echo.
echo IMPORTANT: Save these passwords securely!
echo    Root password: !mysql_root_password!
echo    Database password: !mysql_password!
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
    call :UpdateEnv "%ROOT_ENV_FILE%" "ISSUER" "https://localhost/auth"
    call :UpdateEnv "%ROOT_ENV_FILE%" "HTTPS_PORT" "8443"
    call :UpdateEnv "%ROOT_ENV_FILE%" "HTTP_PORT" "8080"
    echo    * Server: https://localhost:8443
    echo    * Using development ports (8443/8080)
) else (
    echo Configuring for production...
    call :UpdateEnv "%ROOT_ENV_FILE%" "SERVER_NAME" "!domain!"
    call :UpdateEnv "%ROOT_ENV_FILE%" "ISSUER" "https://!domain!/auth"
    call :UpdateEnv "%ROOT_ENV_FILE%" "HTTPS_PORT" "443"
    call :UpdateEnv "%ROOT_ENV_FILE%" "HTTP_PORT" "80"
    echo    * Server: https://!domain!
    echo    * Using standard ports (443/80)
)

echo To use different ports, edit HTTPS_PORT/HTTP_PORT in .env after setup
echo.

if not exist certs mkdir certs
if not exist blockchain-data mkdir blockchain-data

set "has_openssl=0"
where openssl >nul 2>&1
if not errorlevel 1 set "has_openssl=1"

echo SSL Certificates
echo ================
if not exist certs\fullchain.pem (
    echo SSL certificates not found!
    echo   * certs\fullchain.pem (certificate)
    echo   * certs\privkey.pem (private key)
    if /i "!domain!"=="localhost" if "!has_openssl!"=="1" (
        set /p "generate_cert=Generate a self-signed certificate for localhost now? (Y/n): "
        set "generate_cert=!generate_cert: =!"
        if "!generate_cert!"=="" set "generate_cert=y"
        if /i "!generate_cert!"=="y" (
            openssl req -x509 -nodes -newkey rsa:2048 ^
                -keyout certs\privkey.pem ^
                -out certs\fullchain.pem ^
                -days 365 ^
                -subj "/CN=localhost"
            if errorlevel 1 (
                echo Failed to generate self-signed certificate.
            ) else (
                echo Generated self-signed certificate for localhost.
            )
        )
    ) else (
        echo Provide valid certificates (Let's Encrypt, CA, or cloud provider).
    )
) else (
    if not exist certs\privkey.pem (
        echo Found certs\fullchain.pem but privkey.pem is missing.
    ) else (
        echo SSL certificates found.
    )
)
echo.

echo JWT Signing Keys
echo =================
if not exist certs\private_key.pem (
    echo Blockchain Services requires certs\private_key.pem and certs\public_key.pem
    if "!has_openssl!"=="1" (
        set /p "generate_keys=Generate RSA key pair for JWT signing now? (Y/n): "
        set "generate_keys=!generate_keys: =!"
        if "!generate_keys!"=="" set "generate_keys=y"
        if /i "!generate_keys!"=="y" (
            openssl genrsa -out certs\private_key.pem 2048
            if not errorlevel 1 (
                openssl rsa -in certs\private_key.pem -pubout -out certs\public_key.pem
                copy /Y certs\public_key.pem certs\certificate.pem >nul
                echo Generated RSA key pair for blockchain-services.
            ) else (
                echo Failed to generate RSA key pair.
            )
        )
    ) else (
        echo Install OpenSSL or copy the RSA key pair manually.
    )
) else (
    if not exist certs\public_key.pem (
        echo private_key.pem found but public_key.pem is missing.
    ) else (
        echo JWT signing key pair found.
    )
)
echo.

echo Blockchain Services Configuration
echo ==================================
call :ReadEnvValue "%ROOT_ENV_FILE%" "CONTRACT_ADDRESS" contract_default
if not defined contract_default set "contract_default=0xYourDiamondContractAddress"
set /p "contract_address=Contract address [!contract_default!]: "
if "!contract_address!"=="" set "contract_address=!contract_default!"
if not "!contract_address!"=="" (
    call :UpdateEnvBoth "CONTRACT_ADDRESS" "!contract_address!"
)

call :ReadEnvValue "%ROOT_ENV_FILE%" "RPC_URL" rpc_default
if not defined rpc_default set "rpc_default=https://1rpc.io/sepolia"
set /p "rpc_url=Fallback RPC URL [!rpc_default!]: "
if "!rpc_url!"=="" set "rpc_url=!rpc_default!"
if not "!rpc_url!"=="" (
    call :UpdateEnvBoth "RPC_URL" "!rpc_url!"
)

call :ReadEnvValue "%ROOT_ENV_FILE%" "ETHEREUM_SEPOLIA_RPC_URL" sepolia_default
if not defined sepolia_default set "sepolia_default=https://1rpc.io/sepolia,https://rpc.sepolia.org"
set /p "sepolia_rpc=Sepolia RPC URLs (comma separated) [!sepolia_default!]: "
if "!sepolia_rpc!"=="" set "sepolia_rpc=!sepolia_default!"
if not "!sepolia_rpc!"=="" (
    call :UpdateEnvBoth "ETHEREUM_SEPOLIA_RPC_URL" "!sepolia_rpc!"
)

call :ReadEnvValue "%ROOT_ENV_FILE%" "ALLOWED_ORIGINS" origins_default
if not defined origins_default set "origins_default=http://localhost:3000"
set /p "allowed_origins=Allowed origins for CORS [!origins_default!]: "
if "!allowed_origins!"=="" set "allowed_origins=!origins_default!"
if not "!allowed_origins!"=="" (
    call :UpdateEnvBoth "ALLOWED_ORIGINS" "!allowed_origins!"
)

call :ReadEnvValue "%ROOT_ENV_FILE%" "MARKETPLACE_PUBLIC_KEY_URL" mpk_default
if not defined mpk_default set "mpk_default=https://marketplace-decentralabs.vercel.app/.well-known/public-key.pem"
set /p "marketplace_pk=Marketplace public key URL [!mpk_default!]: "
if "!marketplace_pk!"=="" set "marketplace_pk=!mpk_default!"
if not "!marketplace_pk!"=="" (
    call :UpdateEnvBoth "MARKETPLACE_PUBLIC_KEY_URL" "!marketplace_pk!"
)

echo.
echo Institutional Wallet Reminder
echo -----------------------------
echo Wallet creation/import is handled inside the blockchain-services web console.
echo After creating the wallet, update these variables in both %ROOT_ENV_FILE% and %BLOCKCHAIN_ENV_FILE%:
echo    * INSTITUTIONAL_WALLET_ADDRESS
echo    * INSTITUTIONAL_WALLET_PASSWORD
echo Wallet data will be persisted in the blockchain-data\ directory.
echo.

echo Next Steps
echo ==========
echo 1. Review and customize %ROOT_ENV_FILE% if needed
echo 2. Ensure SSL certificates and RSA keys are present in certs\
echo 3. Review blockchain settings in %ROOT_ENV_FILE% and %BLOCKCHAIN_ENV_FILE%
echo 4. Run: %compose_cmd% up -d
if /i "!domain!"=="localhost" (
    echo 5. Access: https://localhost:8443
) else (
    echo 5. Access: https://!domain!
)
echo    * Guacamole: /guacamole/
echo    * Blockchain Services API: /auth
echo.

set /p "start_services=Do you want to start the services now? (Y/n): "
if /i "!start_services!"=="n" goto skip_start
if /i "!start_services!"=="no" goto skip_start

echo.
echo Building and starting services...
echo This may take several minutes on first run...

call %compose_cmd% down --remove-orphans
if errorlevel 1 goto compose_fail
call %compose_cmd% build --no-cache
if errorlevel 1 goto compose_fail
call %compose_cmd% up -d
if errorlevel 1 goto compose_fail
goto compose_success

:compose_fail
echo Failed to start services. Check the error messages above.
goto docker_start_done

:compose_success
echo.
echo Services started successfully!
if /i "!domain!"=="localhost" (
    echo Access your lab at: https://localhost:8443
) else (
    echo Access your lab at: https://!domain!
)
echo    * Guacamole: /guacamole/ (guacadmin / guacadmin)
echo    * Blockchain Services API: /auth
echo.
echo To check status: %compose_cmd% ps
echo To view logs: %compose_cmd% logs -f
echo.
echo Configuration:
echo    Environment: %ROOT_ENV_FILE%
echo    Blockchain Services Config: %BLOCKCHAIN_ENV_FILE%
echo    Certificates & Keys: certs\
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
echo 2. Run: %compose_cmd% up -d
echo 3. Access your services as listed above.
echo.
echo For more information, see README.md

:docker_start_done
goto end

:end
echo.
pause
goto :eof

:UpdateEnvBoth
call :UpdateEnv "%ROOT_ENV_FILE%" "%~1" "%~2"
if exist "%BLOCKCHAIN_ENV_FILE%" call :UpdateEnv "%BLOCKCHAIN_ENV_FILE%" "%~1" "%~2"
exit /b

:UpdateEnv
set "env_file=%~1"
set "env_key=%~2"
set "env_value=%~3"
powershell -NoLogo -Command ^
    "& {
        param($file,$key,$value)
        if (-not (Test-Path $file)) { New-Item -Path $file -ItemType File -Force | Out-Null }
        $content = Get-Content -Path $file
        $pattern = '^' + [regex]::Escape($key) + '=.*$'
        $replacement = \"$key=$value\"
        $updated = $false
        for ($i = 0; $i -lt $content.Count; $i++) {
            if ($content[$i] -match $pattern) {
                $content[$i] = $replacement
                $updated = $true
            }
        }
        if (-not $updated) {
            $content += $replacement
        }
        $content | Set-Content -Path $file -Encoding UTF8
    }" "%env_file%" "%env_key%" "%env_value%"
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
