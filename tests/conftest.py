# tests/conftest.py
"""Configuration pytest et fixtures communes pour tous les tests"""
import pytest
import os
from pathlib import Path
from unittest.mock import MagicMock


@pytest.fixture
def temp_env():
    """Fixture pour gérer les variables d'environnement temporaires"""
    original_env = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_discord_bot():
    """Fixture pour créer un bot Discord mocké"""
    from src.main import DiscordBot
    bot = DiscordBot()
    return bot


@pytest.fixture
def mock_context():
    """Fixture pour créer un contexte de commande mocké"""
    ctx = MagicMock()
    ctx.author = "TestUser"
    ctx.guild = "TestGuild"
    ctx.channel = "general"
    ctx.command = "test_command"
    return ctx
