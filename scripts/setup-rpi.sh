#!/bin/bash
# scripts/setup-rpi.sh - Configuration initiale de la RPi

echo "🔧 Configuration initiale du bot Discord sur RPi..."

# Répertoire du bot
BOT_DIR="/home/pi/floshy_bot"

# Créer le répertoire s'il n'existe pas
mkdir -p "$BOT_DIR"
cd "$BOT_DIR"

# Clone le repo (ou pull s'il existe déjà)
if [ ! -d .git ]; then
    echo "📥 Clonage du repo..."
    git clone https://github.com/VOTRE_USERNAME/floshy_bot.git .
else
    echo "📥 Pull des changements..."
    git pull
fi

# Créer le dossier logs
mkdir -p logs

# Créer le fichier .env s'il n'existe pas
if [ ! -f .env ]; then
    echo "📝 Création du fichier .env..."
    read -p "Entrez votre DISCORD_TOKEN: " TOKEN
    read -p "Entrez le LOG_LEVEL (DEBUG/INFO/WARNING/ERROR): " LOG_LEVEL
    
    cat > .env << EOF
DISCORD_TOKEN=$TOKEN
LOG_LEVEL=${LOG_LEVEL:-INFO}
EOF
    
    chmod 600 .env
    echo "✅ .env créé (sécurisé avec permissions 600)"
fi

# Build l'image Docker
echo "🐳 Build de l'image Docker..."
docker compose build

# Créer un service systemd pour redémarrer auto
echo "⚙️  Création du service systemd..."
sudo tee /etc/systemd/system/floshy-bot.service > /dev/null << EOF
[Unit]
Description=Floshy Discord Bot
After=docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=$BOT_DIR
ExecStart=/usr/bin/docker compose up
ExecStop=/usr/bin/docker compose down
Restart=always
RestartSec=10
User=pi

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable floshy-bot.service

echo "✅ Setup terminé!"
echo ""
echo "Pour démarrer le bot:"
echo "  sudo systemctl start floshy-bot"
echo ""
echo "Pour voir les logs:"
echo "  docker compose logs -f bot"
echo ""
echo "Pour arrêter:"
echo "  sudo systemctl stop floshy-bot"
