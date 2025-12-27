# Multi-stage build pour optimiser la taille
FROM python:3.12-slim as builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Mount cache pour les dépendances
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Stage final - RPi optimisé
FROM python:3.12-slim

# Installer les dépendances système nécessaires pour discord.py
RUN apt-get update && apt-get install -y --no-install-recommends \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copier l'environnement virtuel du builder
COPY --from=builder /app/.venv /app/.venv

# Copier le code source
COPY . /app

# Activer le venv
ENV PATH="/app/.venv/bin:$PATH"
ENV VIRTUAL_ENV="/app/.venv"

# Créer le dossier logs
RUN mkdir -p /app/logs

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import discord; print('OK')" || exit 1

# Lancer le bot
CMD ["python", "-m", "src.main"]