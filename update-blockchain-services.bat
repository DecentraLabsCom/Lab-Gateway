@echo off
REM Script to update blockchain-services submodule automatically
REM Usage: update-blockchain-services.bat "commit message"

setlocal enabledelayedexpansion

set "COMMIT_MESSAGE=%~1"
if "%COMMIT_MESSAGE%"=="" set "COMMIT_MESSAGE=Update blockchain-services submodule"

echo Updating blockchain-services submodule...
echo Strategy: full branch to main branch (blockchain-services)

REM Update the submodule to latest main branch
git submodule update --remote --merge blockchain-services
if errorlevel 1 (
    echo Failed to update submodule
    exit /b 1
)

REM Check if there are changes (basic check)
git diff --quiet blockchain-services
if not errorlevel 1 (
    echo Blockchain-services is already up to date
    exit /b 0
)

REM Add and commit the submodule update
git add blockchain-services
if errorlevel 1 (
    echo Failed to add submodule changes
    exit /b 1
)

git commit -m "%COMMIT_MESSAGE%"
if errorlevel 1 (
    echo Failed to commit submodule changes
    exit /b 1
)

echo Blockchain-services submodule updated successfully!
echo Commit message: %COMMIT_MESSAGE%
echo Don't forget to: git push