# Makefile - Floshy Bot
.PHONY: help install dev sync add add-dev update \
        test test-cov lint format \
        docker-build docker-build-no-cache docker-up docker-down docker-logs docker-restart docker-shell docker-status docker-pull \
        docker-push docker-clean \
        run stop logs shell \
        clean clean-all \
        show-deps show-outdated \
        health watchtower-logs

COMPOSE_FILE := docker/docker-compose.yml
DOCKER_COMPOSE := docker compose -f $(COMPOSE_FILE)

# ============================================================================
# DÉPENDANCES (UV)
# ============================================================================

help:
	@echo "╔════════════════════════════════════════════════════════════════╗"
	@echo "║           Floshy Bot - Makefile Commands                       ║"
	@echo "╚════════════════════════════════════════════════════════════════╝"
	@echo ""
	@echo "📦 DÉPENDANCES (UV):"
	@echo "  make install          - Installer les dépendances"
	@echo "  make dev              - Installer avec extras dev"
	@echo "  make sync             - Sync avec uv.lock (frozen)"
	@echo "  make add PKG=...      - Ajouter une dépendance"
	@echo "  make add-dev PKG=...  - Ajouter une dépendance dev"
	@echo "  make update           - Mettre à jour uv.lock"
	@echo ""
	@echo "🧪 TESTS & QUALITÉ:"
	@echo "  make test             - Lancer les tests"
	@echo "  make test-cov         - Tests avec couverture (HTML)"
	@echo "  make lint             - Vérifier la qualité du code"
	@echo "  make format           - Formatter le code"
	@echo ""
	@echo "🐳 DOCKER (Développement):"
	@echo "  make docker-build     - Builder l'image Docker"
	@echo "  make docker-up        - Lancer les conteneurs"
	@echo "  make docker-down      - Arrêter les conteneurs"
	@echo "  make docker-restart   - Redémarrer les conteneurs"
	@echo "  make docker-logs      - Voir les logs du bot"
	@echo "  make docker-shell     - Shell dans le conteneur bot"
	@echo "  make docker-status    - État des conteneurs"
	@echo ""
	@echo "🚀 DÉPLOIEMENT:"
	@echo "  make docker-pull      - Télécharger l'image du registry"
	@echo "  make docker-push      - Pusher l'image au registry (need local build)"
	@echo "  make watchtower-logs  - Logs de Watchtower"
	@echo ""
	@echo "🧹 NETTOYAGE:"
	@echo "  make clean            - Nettoyer cache Python"
	@echo "  make clean-docker     - Arrêter et nettoyer Docker"
	@echo "  make clean-all        - Tout nettoyer"

install:
	uv sync

dev:
	uv sync --all-extras

sync:
	uv sync --frozen

add:
	@if [ -z "$(PKG)" ]; then echo "Usage: make add PKG=package-name"; exit 1; fi
	uv add $(PKG)

add-dev:
	@if [ -z "$(PKG)" ]; then echo "Usage: make add-dev PKG=package-name"; exit 1; fi
	uv add --dev $(PKG)

update:
	uv lock --upgrade

# ============================================================================
# TESTS & QUALITÉ
# ============================================================================

test:
	$(DOCKER_COMPOSE) exec -T bot uv run pytest

test-cov:
	$(DOCKER_COMPOSE) exec -T bot uv run pytest --cov=src --cov-report=html
	@echo "📊 Rapport de couverture: htmlcov/index.html"

lint:
	$(DOCKER_COMPOSE) exec -T bot uv run ruff check src/ tests/
	$(DOCKER_COMPOSE) exec -T bot uv run mypy src/

format:
	$(DOCKER_COMPOSE) exec -T bot uv run black src/ tests/
	$(DOCKER_COMPOSE) exec -T bot uv run ruff check --fix src/ tests/

# ============================================================================
# DOCKER - DÉVELOPPEMENT
# ============================================================================

docker-build:
	$(DOCKER_COMPOSE) build

docker-build-no-cache:
	$(DOCKER_COMPOSE) build --no-cache

docker-up:
	@docker container rm -f floshy-bot 2>/dev/null || true
	$(DOCKER_COMPOSE) up -d
	@echo "✅ Conteneurs lancés!"
	@make docker-status

docker-down:
	$(DOCKER_COMPOSE) down
	@echo "❌ Conteneurs arrêtés"

docker-restart:
	$(DOCKER_COMPOSE) restart bot
	@echo "🔄 Bot redémarré"

docker-logs:
	$(DOCKER_COMPOSE) logs -f bot

docker-shell:
	$(DOCKER_COMPOSE) exec bot /bin/bash

docker-status:
	@echo "📊 État des conteneurs:"
	$(DOCKER_COMPOSE) ps

docker-clean:
	$(DOCKER_COMPOSE) down -v
	@echo "🧹 Volumes supprimés"

# ============================================================================
# DÉPLOIEMENT & REGISTRY
# ============================================================================

docker-pull:
	docker pull ghcr.io/${GITHUB_REPOSITORY:-floshy-bot}:latest
	@echo "✅ Image téléchargée"

docker-push:
	@echo "⚠️  Note: Cette commande requiert que l'image soit builée localement"
	@echo "Sur GitHub Actions, c'est fait automatiquement au push sur 'main'"
	docker tag floshy-bot:latest ghcr.io/${GITHUB_REPOSITORY:-floshy-bot}:latest
	docker push ghcr.io/${GITHUB_REPOSITORY:-floshy-bot}:latest

watchtower-logs:
	$(DOCKER_COMPOSE) logs -f watchtower

health:
	@echo "🏥 Vérification de la santé du bot..."
	$(DOCKER_COMPOSE) exec -T bot python -c "import discord; print('✅ Discord.py OK')"

# ============================================================================
# UTILITAIRES
# ============================================================================

run: docker-up health
	@echo "🤖 Bot en cours d'exécution!"

stop:
	make docker-down

logs:
	make docker-logs

shell:
	make docker-shell

show-deps:
	$(DOCKER_COMPOSE) exec -T bot uv pip list

show-outdated:
	$(DOCKER_COMPOSE) exec -T bot uv pip list --outdated

# ============================================================================
# NETTOYAGE
# ============================================================================

clean:
	@echo "🧹 Nettoyage des fichiers Python..."
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov/ dist/ build/ *.egg-info

clean-docker:
	@echo "🧹 Nettoyage Docker..."
	$(DOCKER_COMPOSE) down -v
	docker system prune -f --volumes

clean-all: clean clean-docker
	@echo "✅ Tout nettoyé!"



