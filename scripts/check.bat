@echo off
REM scripts/check.bat
REM Script de vérification simplifié

echo ========================================
echo Formatage avec Black...
echo ========================================
uv run black .
if %ERRORLEVEL% neq 0 (
    echo Erreur de formatage
    exit /b 1
)

echo.
echo ========================================
echo 🔍 Linting avec Ruff...
echo ========================================
uv run ruff check . --fix
if %ERRORLEVEL% neq 0 (
    echo Erreur de linting
    exit /b 1
)

echo.
echo ========================================
echo Type checking avec MyPy...
echo ========================================
uv run mypy src
if %ERRORLEVEL% neq 0 (
    echo Erreur de typage
    exit /b 1
)

echo.
echo ========================================
echo Tests avec Pytest...
echo ========================================
uv run pytest
if %ERRORLEVEL% neq 0 (
    echo Tests échoués
    exit /b 1
)

echo.
echo ========================================
echo Toutes les verifications sont passees !
echo ========================================
exit /b 0