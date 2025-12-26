#!/bin/bash
# scripts/test-ssh.sh - Tester la connexion SSH à la RPi

echo "🔍 Test de connexion SSH à la RPi..."

# Charger les variables d'environnement
if [ -f .env ]; then
    export $(cat .env | xargs)
fi

# Infos
RPI_USER="${RPI_USER:-pi}"
RPI_HOST="${RPI_HOST:-}"

if [ -z "$RPI_HOST" ]; then
    echo "❌ RPI_HOST non défini!"
    echo "Définir dans .env ou en variable d'environnement"
    exit 1
fi

echo "📍 Configuration:"
echo "   Host: $RPI_HOST"
echo "   User: $RPI_USER"
echo ""

# Test 1: Connexion de base
echo "1️⃣  Test de connexion basique..."
if ssh -o StrictHostKeyChecking=no "$RPI_USER@$RPI_HOST" "echo 'SSH OK'" 2>/dev/null; then
    echo "   ✅ Connexion SSH OK"
else
    echo "   ❌ Erreur de connexion SSH"
    exit 1
fi

# Test 2: Docker disponible
echo ""
echo "2️⃣  Test de Docker..."
if ssh "$RPI_USER@$RPI_HOST" "docker --version" 2>/dev/null; then
    echo "   ✅ Docker installé"
else
    echo "   ❌ Docker non trouvé"
    exit 1
fi

# Test 3: Docker Compose
echo ""
echo "3️⃣  Test de Docker Compose..."
if ssh "$RPI_USER@$RPI_HOST" "docker compose --version" 2>/dev/null; then
    echo "   ✅ Docker Compose installé"
else
    echo "   ❌ Docker Compose non trouvé"
    exit 1
fi

# Test 4: Répertoire du bot
echo ""
echo "4️⃣  Test du répertoire du bot..."
BOT_DIR="${BOT_DIR:-/home/$RPI_USER/floshy_bot}"
if ssh "$RPI_USER@$RPI_HOST" "test -d $BOT_DIR && echo 'Répertoire trouvé'" 2>/dev/null; then
    echo "   ✅ Répertoire du bot trouvé: $BOT_DIR"
else
    echo "   ⚠️  Répertoire du bot non trouvé"
    echo "      Utilise setup-rpi.sh pour l'initialiser"
fi

# Test 5: .env présent
echo ""
echo "5️⃣  Test du fichier .env..."
if ssh "$RPI_USER@$RPI_HOST" "test -f $BOT_DIR/.env && echo '.env trouvé'" 2>/dev/null; then
    echo "   ✅ Fichier .env trouvé"
else
    echo "   ❌ Fichier .env non trouvé"
    echo "      Ajouter manuellement: scp .env.example pi@$RPI_HOST:$BOT_DIR/.env"
fi

echo ""
echo "✨ Configuration SSH prête!"
