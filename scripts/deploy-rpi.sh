#!/bin/bash
# scripts/deploy-rpi.sh - Script de déploiement pour Raspberry Pi

set -e  # Arrêter en cas d'erreur

echo "🚀 Déploiement du bot Discord sur RPi..."

# Configuration
BOT_DIR="/home/pi/floshy_bot"  # À adapter à ton chemin
LOG_FILE="$BOT_DIR/deploy.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "Démarrage du déploiement..."

# Aller dans le répertoire du bot
cd "$BOT_DIR" || exit 1

# Pull les changements
log "📥 Récupération des derniers changements..."
git pull origin main

# Arrêter le bot actuel
log "⛔ Arrêt du bot en cours..."
docker compose down || true

# Mettre à jour les dépendances et rebuild
log "📦 Reconstruction de l'image Docker..."
docker compose build

# Nettoyer les vieilles images
docker system prune -f

# Redémarrer le bot
log "✅ Démarrage du bot..."
docker compose up -d

# Attendre un peu et vérifier l'état
sleep 3
if docker compose ps | grep -q "Up"; then
    log "✨ Bot démarré avec succès!"
    docker compose logs --tail=20 bot >> "$LOG_FILE"
else
    log "❌ Erreur: Le bot n'a pas démarré!"
    docker compose logs bot >> "$LOG_FILE"
    exit 1
fi

log "✅ Déploiement terminé!"
