# tests/test_main.py
import pytest
import os
import sys
from unittest.mock import patch, AsyncMock, MagicMock
import discord

from src.main import main, DiscordBot


class TestMainFunction:
    """Tests pour la fonction main"""
    
    @pytest.mark.asyncio
    async def test_main_missing_token(self):
        """Vérifie que main lève une erreur si DISCORD_TOKEN est absent"""
        with patch.dict(os.environ, {}, clear=True):
            with patch('src.main.setup_logger'):
                with pytest.raises(SystemExit) as exc_info:
                    await main()
                assert exc_info.value.code == 1
    
    @pytest.mark.asyncio
    async def test_main_with_valid_token(self):
        """Vérifie que main démarre le bot avec un token valide"""
        token = "test_token_12345"
        
        with patch.dict(os.environ, {'DISCORD_TOKEN': token}):
            with patch('src.main.setup_logger'):
                with patch.object(DiscordBot, 'start', new_callable=AsyncMock) as mock_start:
                    try:
                        await main()
                    except SystemExit:
                        # main appelle sys.exit dans le except
                        pass
                    
                    # Vérifie que bot.start a été appelé avec le token
                    mock_start.assert_called_once_with(token)
    
    @pytest.mark.asyncio
    async def test_main_handles_keyboard_interrupt(self):
        """Vérifie la gestion de KeyboardInterrupt"""
        token = "test_token"
        
        with patch.dict(os.environ, {'DISCORD_TOKEN': token}):
            with patch('src.main.setup_logger'):
                with patch.object(DiscordBot, 'start', new_callable=AsyncMock, side_effect=KeyboardInterrupt):
                    # Ne devrait pas lever d'exception
                    await main()
    
    @pytest.mark.asyncio
    async def test_main_handles_login_failure(self):
        """Vérifie la gestion de LoginFailure"""
        token = "invalid_token"
        
        with patch.dict(os.environ, {'DISCORD_TOKEN': token}):
            with patch('src.main.setup_logger'):
                with patch.object(DiscordBot, 'start', new_callable=AsyncMock, side_effect=discord.LoginFailure):
                    with pytest.raises(SystemExit) as exc_info:
                        await main()
                    assert exc_info.value.code == 1
    
    @pytest.mark.asyncio
    async def test_main_handles_generic_exception(self):
        """Vérifie la gestion des exceptions générales"""
        token = "test_token"
        
        with patch.dict(os.environ, {'DISCORD_TOKEN': token}):
            with patch('src.main.setup_logger'):
                with patch.object(DiscordBot, 'start', new_callable=AsyncMock, side_effect=Exception("Test error")):
                    with pytest.raises(SystemExit) as exc_info:
                        await main()
                    assert exc_info.value.code == 1
    
    @pytest.mark.asyncio
    async def test_main_log_level_from_env(self):
        """Vérifie que le niveau de log peut être configuré via ENV"""
        token = "test_token"
        
        with patch.dict(os.environ, {'DISCORD_TOKEN': token, 'LOG_LEVEL': 'DEBUG'}):
            with patch('src.main.setup_logger') as mock_setup_logger:
                with patch.object(DiscordBot, 'start', new_callable=AsyncMock):
                    try:
                        await main()
                    except:
                        pass
                    
                    # Vérifie que setup_logger a été appelé avec DEBUG
                    mock_setup_logger.assert_called_once_with('DEBUG')
    
    @pytest.mark.asyncio
    async def test_main_log_level_default(self):
        """Vérifie que le niveau de log par défaut est INFO"""
        token = "test_token"
        
        with patch.dict(os.environ, {'DISCORD_TOKEN': token}, clear=True):
            with patch('src.main.setup_logger') as mock_setup_logger:
                with patch.object(DiscordBot, 'start', new_callable=AsyncMock):
                    try:
                        await main()
                    except:
                        pass
                    
                    # Vérifie que setup_logger a été appelé avec INFO (par défaut)
                    mock_setup_logger.assert_called_once_with('INFO')
