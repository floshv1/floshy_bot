#!/bin/bash
# scripts/webhook-receiver.sh - Webhook pour déploiement automatique (à héberger sur RPi)

# Simple webhook receiver que tu peux lancer avec un service systemd
# Port par défaut: 8888

PORT=${1:-8888}
BOT_DIR="/home/pi/floshy_bot"

while true; do
    # Écoute les requêtes sur le port
    { echo -ne "HTTP/1.1 200 OK\r\nContent-Length: 7\r\n\r\nSuccess"; } | nc -l -p $PORT -q 1

    echo "Webhook reçu ! Déploiement..."
    cd "$BOT_DIR"
    
    # Déployer
    bash scripts/deploy-rpi.sh
    
    echo "Déploiement terminé à $(date)"
done
