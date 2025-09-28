@echo off
REM DecentraLabs Gateway - Full Version Deployment Script
REM This script deploys the complete blockchain-based authentication system

echo.
echo 🚀 DecentraLabs Gateway - Full Version Deployment
echo ==================================================
echo.

REM Check if Docker is running
docker info >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker is not running. Please start Docker and try again.
    pause
    exit /b 1
)

REM Check if docker-compose is available
docker-compose --version >nul 2>&1
if errorlevel 1 (
    echo ❌ docker-compose is not installed. Please install Docker Compose and try again.
    pause
    exit /b 1
)

echo ✅ Docker and Docker Compose are available
echo.

REM Check if .env file exists
if not exist .env (
    echo 📝 Creating .env file from template...
    if exist .env.full (
        copy .env.full .env >nul
        echo ✅ Copied .env.full to .env
    ) else (
        echo ❌ .env.full template not found. Please create .env manually.
        pause
        exit /b 1
    )
) else (
    echo ✅ .env file already exists
)

REM Check if certificates exist
if not exist certs\fullchain.pem (
    echo.
    echo ⚠️  SSL certificates not found in certs\ directory
    echo    You need the following files:
    echo    - certs\fullchain.pem ^(SSL certificate^)
    echo    - certs\privkey.pem ^(SSL private key^)
    echo    - certs\public_key.pem ^(JWT public key^)
    echo.
    set /p continue="Continue without certificates? [y/N]: "
    if /i not "%continue%"=="y" (
        echo Please add certificates to certs\ directory and try again.
        pause
        exit /b 1
    )
)

echo.
echo 🏗️  Building and starting services...
echo    This may take several minutes on first run...
echo.

REM Build and start services
docker-compose down --remove-orphans
docker-compose build --no-cache
docker-compose up -d

echo.
echo ⏳ Waiting for services to be ready...

REM Wait a bit for services to start
timeout /t 30 /nobreak >nul

echo.
echo 🎉 Deployment completed!
echo.
echo 📋 Service Status:
docker-compose ps

echo.
echo 🌐 Access URLs:
for /f "tokens=2 delims==" %%i in ('findstr SERVER_NAME .env') do set SERVER_NAME=%%i
echo    Homepage: https://%SERVER_NAME%
echo    Guacamole: https://%SERVER_NAME%/guacamole/
echo    Auth Service: https://%SERVER_NAME%/auth

echo.
echo 🔑 Default Guacamole Credentials:
for /f "tokens=2 delims==" %%i in ('findstr GUAC_ADMIN_USER .env') do set GUAC_USER=%%i
for /f "tokens=2 delims==" %%i in ('findstr GUAC_ADMIN_PASS .env') do set GUAC_PASS=%%i
echo    Username: %GUAC_USER%
echo    Password: %GUAC_PASS%

echo.
echo 📊 Useful Commands:
echo    View logs: docker-compose logs -f [service_name]
echo    Restart service: docker-compose restart [service_name]
echo    Stop all: docker-compose down
echo    Update: docker-compose pull ^&^& docker-compose up -d

echo.
echo 🔧 Configuration:
echo    Environment: .env
echo    Certificates: certs\
echo    Auth Service Config: auth-service\src\main\resources\

echo.
echo ✨ Full version deployment complete!
echo    Your blockchain-based authentication system is now running.
echo.
pause