# Makefile
.PHONY: install dev sync add add-dev update run test test-cov lint format clean clean-docker docker-build docker-build-no-cache docker-up docker-down docker-logs docker-restart docker-shell docker-build-prod docker-run-prod show-deps show-outdated venv-activate help

# Installation et gestion des dépendances avec UV
install:
	uv sync

dev:
	uv sync --all-extras

sync:
	uv sync --frozen

# Ajouter une dépendance
add:
	@echo "Usage: make add PKG=package-name"
	uv add $(PKG)

add-dev:
	@echo "Usage: make add-dev PKG=package-name"
	uv add --dev $(PKG)

# Mise à jour
update:
	uv lock --upgrade

# Lancement
run: docker-up
	docker compose exec -T bot uv run python -m src.main

# Tests et qualité de code
test:
	docker compose exec -T bot uv run pytest

test-cov:
	docker compose exec -T bot uv run pytest --cov=src --cov-report=html

lint:
	docker compose exec -T bot uv run ruff check src/ tests/
	docker compose exec -T bot uv run mypy src/

format:
	docker compose exec -T bot uv run black src/ tests/
	docker compose exec -T bot uv run ruff check --fix src/ tests/

# Docker avec UV
docker-build:
	docker compose build

docker-build-no-cache:
	docker compose build --no-cache

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f bot

docker-restart:
	docker compose restart bot

docker-shell:
	docker compose exec bot /bin/bash

# Docker Production
docker-build-prod:
	docker build -f Dockerfile.production -t discord-bot:latest .

docker-run-prod:
	docker run -d \
		--name discord-bot \
		--env-file .env \
		-v $(PWD)/data:/app/data \
		--restart unless-stopped \
		discord-bot:latest

# Nettoyage
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov/

clean-docker:
	docker-compose down -v
	docker system prune -f

# Utilitaires
show-deps:
	docker-compose exec -T bot uv pip list

show-outdated:
	docker-compose exec -T bot uv pip list --outdated

venv-activate:
	@echo "Run: source .venv/bin/activate"



