# 🤖 Floshy Bot - Discord Bot avec CI/CD

Bot Discord performant avec déploiement automatique sur Raspberry Pi via GitHub Actions.

**Status:** ✅ CI/CD configuré | 🚀 Prêt pour production

---

## 🚀 Démarrage rapide (10 min)

Voir [QUICK_START.md](QUICK_START.md) pour les instructions étape par étape.

```bash
# 1. Setup sur RPi
bash scripts/setup-rpi.sh

# 2. Tester la connexion
bash scripts/test-ssh.sh

# 3. Push et déployer
git push origin main
```

---

## 📋 Requirements

- **Python** 3.12+
- **Docker** & **docker-compose**
- **Raspberry Pi** avec SSH access
- **GitHub** repo

Voir [VERSIONS.md](VERSIONS.md) pour les détails.

---

## 📚 Documentation

| Document | Contenu |
|----------|---------|
| [QUICK_START.md](QUICK_START.md) | **Commence ici!** (10 min) |
| [SETUP_CICD.md](SETUP_CICD.md) | Guide complet détaillé |
| [CI_CD.md](CI_CD.md) | Architecture globale |
| [CI_CD_SUMMARY.md](CI_CD_SUMMARY.md) | Résumé et checklist |
| [README_CICD.md](README_CICD.md) | Troubleshooting |
| [TESTS.md](TESTS.md) | Guide des tests |
| [VERSIONS.md](VERSIONS.md) | Versions et dépendances |

---

## 🏗️ Architecture

```
PC (VSCode)
    ↓
git push origin main
    ↓
GitHub Actions CI
  ├─ pytest         (tests)
  ├─ ruff           (lint)
  └─ mypy           (types)
    ↓
  IF OK → Deploy to RPi via SSH
    ↓
Raspberry Pi
  ├─ git pull
  ├─ docker build
  └─ docker up
    ↓
Bot en production ✨
```

---

## 🔄 Workflow CI/CD

### Tests automatiques (CI)

Chaque push → Lancent les tests

```bash
# Local
pytest tests/ -v

# Via Actions (automatique)
GitHub → Actions → ci.yml
```

### Déploiement automatique (CD)

Push sur `main` + tests OK → Déploie sur RPi

```
main branch ✅ → Déploie sur RPi
```

---

## 📦 Structure du projet

```
floshy_bot/
├── src/
│   ├── main.py              # Point d'entrée bot
│   ├── cogs/                # Commandes Discord
│   └── utils/
│       ├── logger.py        # Configuration logging
│       └── __init__.py
├── tests/
│   ├── test_bot.py
│   ├── test_logger.py
│   ├── test_main.py
│   ├── conftest.py          # Fixtures pytest
│   └── __init__.py
├── scripts/
│   ├── setup-rpi.sh         # Setup initial RPi
│   ├── deploy-rpi.sh        # Déploiement manuel
│   ├── test-ssh.sh          # Test SSH
│   └── check-setup.sh       # Vérifier config
├── .github/workflows/
│   ├── ci.yml               # Tests CI
│   ├── deploy.yml           # Déploiement CD
│   └── release.yml          # Releases
├── Dockerfile               # RPi optimisé (ARM)
├── docker-compose.yml
├── pyproject.toml
├── pytest.ini
├── .env.example
├── .gitignore
└── README.md
```

---

## 🛠️ Outils utilisés

| Outil | Raison |
|-------|--------|
| **discord.py** | API Discord |
| **loguru** | Logging avancé |
| **pytest** | Tests unitaires |
| **GitHub Actions** | CI/CD |
| **Docker** | Isolation & portabilité |
| **uv** | Package manager rapide |
| **ruff** | Linting performant |
| **mypy** | Type checking |

---

## 🧪 Tests

```bash
# Lancer tous les tests
pytest tests/ -v

# Test spécifique
pytest tests/test_bot.py::TestDiscordBotInitialization -v

# Avec couverture
pytest tests/ --cov=src --cov-report=html

# Watch mode
ptw
```

Voir [TESTS.md](TESTS.md) pour plus de détails.

---

## 🚀 Déploiement

### Déploiement automatique

```bash
git push origin main
# GitHub Actions s'occupe du reste
```

### Déploiement manuel

```bash
# Option 1: Via script
ssh pi@192.168.1.100
bash ~/floshy_bot/scripts/deploy-rpi.sh

# Option 2: Workflow
gh workflow run deploy.yml --ref main
```

---

## 📝 Configuration

### `.env` (local et RPi)

```bash
DISCORD_TOKEN=your_token_here
LOG_LEVEL=INFO
```

Ne jamais commiter `.env` (protégé dans `.gitignore`)

### Secrets GitHub

```
RPI_HOST      → Adresse IP RPi
RPI_USER      → Utilisateur SSH (pi)
RPI_SSH_KEY   → Clé privée SSH
```

---

## 📊 Monitoring

### Logs GitHub Actions

```
github.com/USERNAME/floshy_bot/actions
```

### Logs RPi

```bash
ssh pi@192.168.1.100
docker compose logs -f bot
```

### Health Check

```bash
docker compose ps
# Doit montrer "Up" pour le service bot
```

---

## 🔐 Sécurité

✅ Configuré:

- `.env` ignoré (pas dans git)
- SSH keys sécurisées
- Secrets GitHub pour credentials

📋 À ajouter (optionnel):

- [ ] Branch protection sur `main`
- [ ] CODEOWNERS
- [ ] Dependabot
- [ ] Code scanning

Voir [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md)

---

## 🎯 Commandes utiles

### Development

```bash
# Tests
pytest tests/ -v

# Lint
ruff check src/

# Format
black src/

# Type check
mypy src/
```

### Docker (local)

```bash
docker compose build
docker compose up
docker compose down
docker compose logs -f bot
```

### RPi (SSH)

```bash
ssh pi@192.168.1.100
docker compose logs -f bot          # Logs
docker compose ps                    # Status
docker compose restart bot           # Restart
docker compose down && docker compose up -d  # Reset
```

---

## 🐛 Troubleshooting

| Problème | Solution |
|----------|----------|
| Tests échouent | `pytest tests/ -v` pour le détail |
| SSH refuse | Vérify secrets GitHub et clé autorisée |
| Docker not found | Installer Docker sur RPi |
| Bot ne démarre | `docker compose logs bot` pour les erreurs |
| Déploiement bloqué | Assure-toi que les tests passent |

Voir [README_CICD.md](README_CICD.md) pour plus de dépannage.

---

## 📞 Support

### Local development

1. Cherche dans [SETUP_CICD.md](SETUP_CICD.md)
2. Check [TESTS.md](TESTS.md) pour les tests

### Déploiement

1. Cherche dans [README_CICD.md](README_CICD.md)
2. Vérify les logs GitHub Actions

### Configuration

1. Check [VERSIONS.md](VERSIONS.md)
2. Relance `scripts/check-setup.sh`

---

## 🎓 Learning resources

- [Discord.py Docs](https://discordpy.readthedocs.io/)
- [GitHub Actions Docs](https://docs.github.com/en/actions)
- [Docker Docs](https://docs.docker.com/)
- [pytest Docs](https://pytest.org/)

---

## 📈 Roadmap

- [ ] Commandes de base (ping, help, etc.)
- [ ] Logging avancé
- [ ] Monitoring en temps réel
- [ ] Auto-backup des logs
- [ ] Metrics Prometheus
- [ ] Graphana dashboard

---

## 📄 License

[Ajoute ta license ici]

---

## 👨‍💻 Contribution

1. Fork le repo
2. Crée une feature branch (`git checkout -b feature/amazing`)
3. Commit (`git commit -m "feat: amazing feature"`)
4. Push (`git push origin feature/amazing`)
5. Ouvre une PR

---

## ⭐ Status

| Aspect | Status |
|--------|--------|
| Tests | ✅ Passent |
| Linting | ✅ OK |
| Type checking | ✅ OK |
| CI/CD | ✅ Configuré |
| Production | 🚀 Prêt |

---

**Dernière mise à jour:** 2025-12-26

**Pour commencer:** Lis [QUICK_START.md](QUICK_START.md) 👈
