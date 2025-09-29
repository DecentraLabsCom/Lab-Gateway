@echo off
REM Script to update auth-service submodule automatically
REM Usage: update-auth-service.bat "commit message"

setlocal enabledelayedexpansion

set "COMMIT_MESSAGE=%~1"
if "%COMMIT_MESSAGE%"=="" set "COMMIT_MESSAGE=Update auth-service submodule"

echo Updating auth-service submodule...
echo Strategy: full branch to main branch (auth-service)

REM Update the submodule to latest main branch
git submodule update --remote --merge auth-service
if errorlevel 1 (
    echo Failed to update submodule
    exit /b 1
)

REM Check if there are changes (basic check)
git diff --quiet auth-service
if not errorlevel 1 (
    echo Auth-service is already up to date
    exit /b 0
)

REM Add and commit the submodule update
git add auth-service
if errorlevel 1 (
    echo Failed to add submodule changes
    exit /b 1
)

git commit -m "%COMMIT_MESSAGE%"
if errorlevel 1 (
    echo Failed to commit submodule changes
    exit /b 1
)

echo Auth-service submodule updated successfully!
echo Commit message: %COMMIT_MESSAGE%
echo Don't forget to: git push