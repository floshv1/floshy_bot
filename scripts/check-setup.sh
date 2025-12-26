#!/bin/bash
# scripts/check-setup.sh - Vérifie que la CI/CD est bien configurée

set -e

echo "🔍 Vérification de la configuration CI/CD..."
echo ""

PASS="✅"
FAIL="❌"
WARN="⚠️"

checks_passed=0
checks_failed=0

check() {
    local name=$1
    local condition=$2
    
    if [ "$condition" = "true" ]; then
        echo "$PASS $name"
        ((checks_passed++))
    else
        echo "$FAIL $name"
        ((checks_failed++))
    fi
}

echo "📋 Configuration locale:"
echo "========================"

# Check Git repo
if [ -d .git ]; then
    check "Repo Git" "true"
    REMOTE=$(git remote get-url origin 2>/dev/null || echo "")
    if [[ $REMOTE == *"github.com"* ]]; then
        check "Repo GitHub" "true"
    else
        check "Repo GitHub" "false"
    fi
else
    check "Repo Git" "false"
fi

# Check structure
[ -d ".github/workflows" ] && check "Dossier .github/workflows" "true" || check "Dossier .github/workflows" "false"
[ -f ".github/workflows/ci.yml" ] && check "Workflow CI" "true" || check "Workflow CI" "false"
[ -f ".github/workflows/deploy.yml" ] && check "Workflow Deploy" "true" || check "Workflow Deploy" "false"

# Check scripts
[ -f "scripts/test-ssh.sh" ] && check "Script test-ssh.sh" "true" || check "Script test-ssh.sh" "false"
[ -f "scripts/setup-rpi.sh" ] && check "Script setup-rpi.sh" "true" || check "Script setup-rpi.sh" "false"

# Check .env
[ -f ".env" ] && check "Fichier .env local" "true" || echo "$WARN Fichier .env local manquant (pas grave pour le repo)"
[ -f ".env.example" ] && check "Fichier .env.example" "true" || check "Fichier .env.example" "false"

# Check gitignore
if [ -f ".gitignore" ]; then
    check "Fichier .gitignore" "true"
    if grep -q "^\.env$" .gitignore; then
        check ".env dans .gitignore" "true"
    else
        check ".env dans .gitignore" "false"
    fi
fi

# Check dependencies
if [ -f "pyproject.toml" ]; then
    check "Fichier pyproject.toml" "true"
    if grep -q "pytest" pyproject.toml; then
        check "pytest dans dépendances" "true"
    else
        check "pytest dans dépendances" "false"
    fi
fi

echo ""
echo "📍 Configuration RPi:"
echo "===================="

# Check RPi host
if [ -n "$RPI_HOST" ]; then
    check "RPI_HOST défini" "true"
else
    echo "$WARN RPI_HOST non défini (voir documentation)"
fi

if [ -n "$RPI_USER" ]; then
    check "RPI_USER défini" "true"
else
    echo "$WARN RPI_USER non défini (voir documentation)"
fi

echo ""
echo "🧪 Tests locaux:"
echo "================"

# Check if tests exist
[ -f "tests/test_bot.py" ] && check "Tests bot" "true" || check "Tests bot" "false"
[ -f "tests/test_logger.py" ] && check "Tests logger" "true" || check "Tests logger" "false"
[ -f "tests/test_main.py" ] && check "Tests main" "true" || check "Tests main" "false"

# Try to run tests (if pytest installed)
if command -v pytest &> /dev/null; then
    if pytest --collect-only tests/ 2>/dev/null | grep -q "test session"; then
        TEST_COUNT=$(pytest --collect-only tests/ -q 2>/dev/null | grep "test_" | wc -l)
        check "Tests trouvés ($TEST_COUNT tests)" "true"
    fi
fi

echo ""
echo "🐳 Docker:"
echo "=========="

# Check Docker files
[ -f "Dockerfile" ] && check "Dockerfile" "true" || check "Dockerfile" "false"
[ -f "docker-compose.yml" ] && check "docker-compose.yml" "true" || check "docker-compose.yml" "false"

# Check if Docker is installed
if command -v docker &> /dev/null; then
    check "Docker installé" "true"
else
    echo "$WARN Docker pas installé localement (pas grave, nécessaire sur RPi)"
fi

echo ""
echo "📊 Résumé:"
echo "=========="
echo "✅ Checks passés: $checks_passed"
echo "❌ Checks échoués: $checks_failed"

if [ $checks_failed -eq 0 ]; then
    echo ""
    echo "🎉 Configuration OK! Tu peux:"
    echo "   1. bash scripts/test-ssh.sh  # Tester connexion RPi"
    echo "   2. bash scripts/setup-rpi.sh # Setup initial RPi"
    echo "   3. git push origin main      # Déclencher déploiement"
    exit 0
else
    echo ""
    echo "⚠️  Il y a des choses à fixer:"
    echo "   Voir SETUP_CICD.md pour les détails"
    exit 1
fi
