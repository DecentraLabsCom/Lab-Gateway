@echo off
setlocal enabledelayedexpansion
REM =================================================================
REM DecentraLabs Gateway - Full Version Setup Script (Windows)
REM Complete blockchain-based authentication system with auth-service
REM =================================================================

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
)

echo Docker and Docker Compose are available
echo.

REM Check if .env already exists
if exist ".env" (
    echo .env file already exists!
    set /p "overwrite=Do you want to overwrite it? (y/N): "
    REM Clean the variable by removing spaces
    set "overwrite=!overwrite: =!"
    if /i not "!overwrite!"=="y" (
        echo Setup cancelled.
        pause
        exit /b
    )
    REM User said yes, so overwrite
    copy .env.example .env >nul
    echo Overwritten .env file from template
) else (
    REM No .env exists, create it
    copy .env.example .env >nul
    echo Created .env file from template
)
REM Ask for domain
echo.
echo Database Passwords
echo ===================
echo Enter database passwords (leave empty for auto-generated):
set /p "mysql_root_password=MySQL root password: "
set /p "mysql_password=Guacamole database password: "
set /p "redis_password=Redis password: "

if "%mysql_root_password%"=="" (
    set mysql_root_password=R00t_P@ss_%RANDOM%_%TIME:~9%
    set mysql_root_password=!mysql_root_password: =!
    echo Generated root password: !mysql_root_password!
)

if "%mysql_password%"=="" (
    set mysql_password=Gu@c_%RANDOM%_%TIME:~9%
    set mysql_password=!mysql_password: =!
    echo Generated database password: !mysql_password!
)

if "%redis_password%"=="" (
    set redis_password=Redis_%RANDOM%_%TIME:~9%
    set redis_password=!redis_password: =!
    echo Generated Redis password: !redis_password!
)

REM Update passwords in .env file
powershell -Command "(Get-Content .env) -replace 'MYSQL_ROOT_PASSWORD=.*', 'MYSQL_ROOT_PASSWORD=!mysql_root_password!' | Set-Content .env"
powershell -Command "(Get-Content .env) -replace 'MYSQL_PASSWORD=.*', 'MYSQL_PASSWORD=!mysql_password!' | Set-Content .env"
powershell -Command "(Get-Content .env) -replace 'REDIS_PASSWORD=.*', 'REDIS_PASSWORD=!redis_password!' | Set-Content .env"

REM Update Guacamole properties file to match the configuration in .env
echo Updating Guacamole configuration...
powershell -Command "(Get-Content guacamole/guacamole.properties) -replace 'mysql-password:.*', 'mysql-password: !mysql_password!' | Set-Content guacamole/guacamole.properties"

echo.
echo IMPORTANT: Save these passwords securely!
echo    Root password: !mysql_root_password!
echo    Database password: !mysql_password!
echo    Redis password: !redis_password!
echo.

echo Domain Configuration
echo =====================
echo Enter your domain name (or press Enter for localhost):
set /p "domain=Domain: "
REM Clean the domain variable and set default
if defined domain set "domain=!domain: =!"
if not defined domain set "domain=localhost"
if "!domain!"=="" set "domain=localhost"

REM Update .env file with intelligent defaults
if "!domain!"=="localhost" (
    echo Configuring for local development...
    powershell -Command "(Get-Content .env) -replace 'SERVER_NAME=.*', 'SERVER_NAME=localhost' | Set-Content .env"
    powershell -Command "(Get-Content .env) -replace 'BASE_DOMAIN=.*', 'BASE_DOMAIN=https://localhost' | Set-Content .env"
    powershell -Command "(Get-Content .env) -replace 'ISSUER=.*', 'ISSUER=https://localhost/auth' | Set-Content .env"
    powershell -Command "(Get-Content .env) -replace 'HTTPS_PORT=.*', 'HTTPS_PORT=8443' | Set-Content .env"
    powershell -Command "(Get-Content .env) -replace 'HTTP_PORT=.*', 'HTTP_PORT=8080' | Set-Content .env"
    echo    * Server: https://localhost:8443
    echo    * Using development ports ^(8443/8080^)
    goto config_done
)

REM If we get here, it's not localhost, so it's production
echo Configuring for production...
powershell -Command "(Get-Content .env) -replace 'SERVER_NAME=.*', 'SERVER_NAME=!domain!' | Set-Content .env"
powershell -Command "(Get-Content .env) -replace 'BASE_DOMAIN=.*', 'BASE_DOMAIN=https://!domain!' | Set-Content .env"
powershell -Command "(Get-Content .env) -replace 'ISSUER=.*', 'ISSUER=https://!domain!/auth' | Set-Content .env"
powershell -Command "(Get-Content .env) -replace 'HTTPS_PORT=.*', 'HTTPS_PORT=443' | Set-Content .env"
powershell -Command "(Get-Content .env) -replace 'HTTP_PORT=.*', 'HTTP_PORT=80' | Set-Content .env"
echo    * Server: https://!domain!
echo    * Using standard ports ^(443/80^)

:config_done

echo To use different ports, edit HTTPS_PORT/HTTP_PORT in .env after setup

echo.
echo SSL Certificates
echo ================

REM Check certificates
if not exist "certs" mkdir certs

if not exist certs\fullchain.pem (
    echo SSL certificates not found!
    echo.
    echo You need to add SSL certificates to the 'certs' folder:
    echo   * certs\fullchain.pem (certificate)
    echo   * certs\privkey.pem (private key)
    echo   * certs\public_key.pem (auth-service's public key)
    echo.
    if "!domain!"=="localhost" (
        echo We will generate self-signed certificates for you...
        goto ssl_info_done
    )
    
    REM If we get here, it's production
    echo You can get valid certificates from:
    echo   * Let's Encrypt (certbot)
    echo   * Your certificate authority
    echo   * Cloud provider (AWS ACM, etc.)
    
    :ssl_info_done
    goto ssl_check_done
)
echo SSL certificates found
:ssl_check_done

echo.
echo Next Steps
echo ==============
echo 1. Review and customize .env file if needed
echo 2. Ensure SSL certificates are in place
echo 3. Configure blockchain settings in .env (CONTRACT_ADDRESS, WALLET_ADDRESS)
echo 4. Run: docker-compose up -d
if "!domain!"=="localhost" (
    echo 5. Access: https://localhost:8443
    goto access_info_done
)
echo 5. Access: https://!domain!
:access_info_done
echo    * Guacamole: /guacamole/
echo    * Auth Service: /auth
echo.

REM Ask if user wants to start services
set /p "start_services=Do you want to start the services now? (Y/n): "
if /i "%start_services%"=="n" goto :skip_start
if /i "%start_services%"=="no" goto :skip_start

echo.
echo Building and starting services...
echo This may take several minutes on first run...

docker-compose down --remove-orphans
docker-compose build --no-cache
docker-compose up -d

if errorlevel 0 (
    echo.
    echo Services started successfully!
    if "!domain!"=="localhost" (
        echo Access your lab at: https://localhost:8443
        goto final_access_done
    )
    echo Access your lab at: https://!domain!
    :final_access_done
    echo    * Guacamole: /guacamole/ (guacadmin / guacadmin)
    echo    * Auth Service: /auth
    echo.
    echo To check status: docker-compose ps
    echo To view logs: docker-compose logs -f
    echo.
    echo Configuration:
    echo    Environment: .env
    echo    Certificates: certs\
    echo    Auth Service Config: auth-service\src\main\resources\
    echo.
    echo Full version deployment complete!
    echo Your blockchain-based authentication system is now running.
    goto docker_start_done
)
echo Failed to start services. Check the error messages above.
:docker_start_done
goto :end

:skip_start
echo Configuration complete!
echo.
echo Next steps:
echo 1. Configure blockchain settings in .env (CONTRACT_ADDRESS, WALLET_ADDRESS)
echo 2. Run: docker-compose up -d
echo 3. Access your services
echo.
echo For more information, see README.md

:end
echo.
pause