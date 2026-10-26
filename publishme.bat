@echo off
rem ============================================================================
rem  publishme.bat - create github.com/jumpifequal/mcp-freesound and push it
rem
rem  Requirements: git and GitHub CLI (https://cli.github.com), logged in as
rem  jumpifequal ("gh auth login"). Safe to run again: it reuses the existing
rem  repository and only pushes new commits.
rem
rem  Usage: publishme.bat [public|private]     (default: public)
rem ============================================================================
setlocal EnableExtensions EnableDelayedExpansion

set "OWNER=jumpifequal"
set "REPO=mcp-freesound"
set "VERSION=1.0.0"
set "DESCRIPTION=Pure-Python, zero-dependency MCP server for Freesound.org audio search (stdio or HTTP + bearer token) with a configuration GUI"
set "TOPICS=mcp,model-context-protocol,freesound,audio,sound-effects,claude,python,llm-tools"
set "VISIBILITY=%~1"
if "%VISIBILITY%"=="" set "VISIBILITY=public"
if /I not "%VISIBILITY%"=="public" if /I not "%VISIBILITY%"=="private" (
    echo [ERROR] Visibility must be "public" or "private".
    exit /b 1
)

cd /d "%~dp0"
echo.
echo === Publishing %OWNER%/%REPO% (%VISIBILITY%) ===
echo.

rem ---- prerequisites ---------------------------------------------------------
where git >nul 2>&1 || (echo [ERROR] git not found. Install it from https://git-scm.com & exit /b 1)
where gh  >nul 2>&1 || (echo [ERROR] GitHub CLI not found. Install it from https://cli.github.com & exit /b 1)

call gh auth status >nul 2>&1
if errorlevel 1 (
    echo You are not logged in to GitHub CLI. Starting "gh auth login"...
    call gh auth login || exit /b 1
)

for /f "delims=" %%L in ('gh api user --jq .login 2^>nul') do set "LOGIN=%%L"
if /I not "!LOGIN!"=="%OWNER%" (
    echo [WARNING] GitHub CLI is logged in as "!LOGIN!", not "%OWNER%".
    choice /M "Continue anyway"
    if errorlevel 2 exit /b 1
)

for /f "delims=" %%N in ('git config user.name 2^>nul') do set "GITNAME=%%N"
if "!GITNAME!"=="" (
    echo [ERROR] git user.name is not set. Run:
    echo     git config --global user.name "Your Name"
    echo     git config --global user.email "you@example.com"
    exit /b 1
)

rem ---- local repository ------------------------------------------------------
if not exist ".git" (
    echo Initialising git repository...
    git init -b main || exit /b 1
)

rem ---- safety: never publish local secrets ----------------------------------
for %%F in (.env config.json) do (
    if exist "%%F" (
        git check-ignore -q "%%F" 2>nul
        if errorlevel 1 (
            echo [ERROR] %%F exists and is not ignored by .gitignore. Remove it before publishing.
            exit /b 1
        )
    )
)

git add -A || exit /b 1
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "Release v%VERSION%" || exit /b 1
) else (
    echo Nothing new to commit.
)
git branch -M main

rem ---- remote repository -----------------------------------------------------
call gh repo view %OWNER%/%REPO% >nul 2>&1
if errorlevel 1 (
    echo Creating https://github.com/%OWNER%/%REPO% ...
    call gh repo create %OWNER%/%REPO% --%VISIBILITY% --description "%DESCRIPTION%" --source . --remote origin --push || exit /b 1
) else (
    echo Repository already exists, pushing...
    git remote get-url origin >nul 2>&1 || git remote add origin https://github.com/%OWNER%/%REPO%.git
    git push -u origin main || exit /b 1
)

call gh repo edit %OWNER%/%REPO% --add-topic "%TOPICS%" --homepage "https://github.com/%OWNER%/%REPO%#readme" >nul 2>&1

rem ---- optional tag + GitHub release ----------------------------------------
git rev-parse -q --verify "refs/tags/v%VERSION%" >nul 2>&1
if errorlevel 1 (
    choice /M "Create tag v%VERSION% and a GitHub release"
    if not errorlevel 2 (
        git tag -a v%VERSION% -m "v%VERSION%" || exit /b 1
        git push origin v%VERSION% || exit /b 1
        call gh release create v%VERSION% --repo %OWNER%/%REPO% --title "mcp-freesound v%VERSION%" --notes "See [CHANGELOG.md](CHANGELOG.md) for details." || exit /b 1
    )
) else (
    echo Tag v%VERSION% already exists, skipping release.
)

echo.
echo Done: https://github.com/%OWNER%/%REPO%
endlocal
