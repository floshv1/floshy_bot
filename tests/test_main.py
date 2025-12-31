# tests/test_main.py (ajoutez ces tests)
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import discord
import pytest
from discord.ext import commands

from src.main import DiscordBot, main


class TestDiscordBot:
    """Tests pour la classe DiscordBot"""

    @pytest.fixture
    def bot(self):
        """Fixture pour créer une instance du bot"""
        with patch("src.main.setup_logger"):
            return DiscordBot()

    def test_bot_initialization(self, bot):
        """Vérifie l'initialisation correcte du bot"""
        assert bot.command_prefix == "!"
        assert bot.help_command is None
        assert bot.status == discord.Status.online
        assert bot.intents.message_content is True
        assert bot.intents.members is True

    @pytest.mark.asyncio
    async def test_setup_hook_success(self, bot):
        """Test setup_hook avec succès"""
        with patch.object(bot, "load_cogs", new_callable=AsyncMock) as mock_load:
            with patch.object(bot.tree, "sync", new_callable=AsyncMock, return_value=[1, 2, 3]):
                await bot.setup_hook()

                mock_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_hook_sync_error(self, bot):
        """Test setup_hook quand la synchronisation échoue"""
        with patch.object(bot, "load_cogs", new_callable=AsyncMock):
            with patch.object(
                bot.tree,
                "sync",
                new_callable=AsyncMock,
                side_effect=Exception("Sync error"),
            ):
                # Ne doit pas lever d'exception
                await bot.setup_hook()

    @pytest.mark.asyncio
    async def test_load_cogs_success(self, bot):
        """Test chargement des cogs avec succès"""
        mock_cog_file = MagicMock()
        mock_cog_file.stem = "test_cog"
        mock_cog_file.name = "test_cog.py"

        with patch.object(Path, "glob", return_value=[mock_cog_file]):
            with patch.object(bot, "load_extension", new_callable=AsyncMock):
                await bot.load_cogs()

                bot.load_extension.assert_called_once_with("src.cogs.test_cog")

    @pytest.mark.asyncio
    async def test_load_cogs_skip_init(self, bot):
        """Test que __init__.py est ignoré"""
        mock_init = MagicMock()
        mock_init.stem = "__init__"

        mock_valid = MagicMock()
        mock_valid.stem = "valid_cog"

        with patch.object(Path, "glob", return_value=[mock_init, mock_valid]):
            with patch.object(bot, "load_extension", new_callable=AsyncMock):
                await bot.load_cogs()

                # Doit être appelé 1 fois (pas pour __init__)
                assert bot.load_extension.call_count == 1
                bot.load_extension.assert_called_with("src.cogs.valid_cog")

    @pytest.mark.asyncio
    async def test_load_cogs_handles_errors(self, bot):
        """Test gestion des erreurs lors du chargement"""
        mock_cog = MagicMock()
        mock_cog.stem = "broken_cog"

        with patch.object(Path, "glob", return_value=[mock_cog]):
            with patch.object(
                bot,
                "load_extension",
                new_callable=AsyncMock,
                side_effect=Exception("Load error"),
            ):
                # Ne doit pas lever d'exception
                await bot.load_cogs()

    @pytest.mark.asyncio
    async def test_on_ready(self):
        """Test l'événement on_ready"""
        with patch("src.main.setup_logger"):
            with patch("src.main.logger") as mock_logger:  # Mock le logger
                bot = DiscordBot()

                # Créer un mock pour user
                mock_user = MagicMock()
                mock_user.name = "TestBot"
                mock_user.id = 123456

                # Créer des mocks pour guilds
                mock_guild1 = MagicMock()
                mock_guild1.member_count = 100
                mock_guild2 = MagicMock()
                mock_guild2.member_count = 50

                # Patcher les propriétés avec PropertyMock
                with patch.object(
                    DiscordBot,
                    "user",
                    new_callable=PropertyMock,
                    return_value=mock_user,
                ):
                    with patch.object(
                        DiscordBot,
                        "guilds",
                        new_callable=PropertyMock,
                        return_value=[mock_guild1, mock_guild2],
                    ):
                        with patch.object(bot, "change_presence", new_callable=AsyncMock) as mock_presence:
                            await bot.on_ready()

                            # Vérifie que change_presence a été appelé correctement
                            mock_presence.assert_called_once()
                            args, kwargs = mock_presence.call_args
                            assert kwargs["status"] == discord.Status.online
                            assert kwargs["activity"].name == "Charbonne"
                            assert kwargs["activity"].type == discord.ActivityType.playing

                            # Vérifie que les logs ont été appelés
                            assert mock_logger.info.called
                            assert mock_logger.success.called

    @pytest.mark.asyncio
    async def test_on_command(self, bot):
        """Test on_command logging"""
        ctx = MagicMock()
        ctx.command = "test"
        ctx.author = "TestUser"
        ctx.channel = MagicMock()
        ctx.guild = "TestGuild"

        # Ne doit pas lever d'exception
        await bot.on_command(ctx)

    @pytest.mark.asyncio
    async def test_on_command_error_not_found(self, bot):
        """Test erreur CommandNotFound (doit être ignorée)"""
        ctx = MagicMock()
        ctx.reply = AsyncMock()
        error = commands.CommandNotFound()

        await bot.on_command_error(ctx, error)

        # Reply ne doit pas être appelé
        ctx.reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_command_error_missing_permissions(self, bot):
        """Test erreur MissingPermissions"""
        ctx = MagicMock()
        ctx.reply = AsyncMock()
        ctx.command = "admin"
        ctx.author = "User"
        error = commands.MissingPermissions(["administrator"])

        await bot.on_command_error(ctx, error)

        ctx.reply.assert_called_once()
        assert "permissions" in ctx.reply.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_on_command_error_missing_argument(self, bot):
        """Test erreur MissingRequiredArgument"""
        ctx = MagicMock()
        ctx.reply = AsyncMock()
        ctx.command = "test"

        param = MagicMock()
        param.name = "user"
        error = commands.MissingRequiredArgument(param)

        await bot.on_command_error(ctx, error)

        ctx.reply.assert_called_once()
        assert "user" in ctx.reply.call_args[0][0]

    @pytest.mark.asyncio
    async def test_on_command_error_cooldown(self, bot):
        """Test erreur CommandOnCooldown"""
        ctx = MagicMock()
        ctx.reply = AsyncMock()
        ctx.command = "test"
        ctx.author = "User"

        # Créer un Cooldown mock
        cooldown = commands.Cooldown(1, 60.0)
        error = commands.CommandOnCooldown(cooldown, 30.5, commands.BucketType.user)

        await bot.on_command_error(ctx, error)

        ctx.reply.assert_called_once()
        assert "30.5" in ctx.reply.call_args[0][0]

    @pytest.mark.asyncio
    async def test_on_command_error_generic(self, bot):
        """Test erreur générique"""
        ctx = MagicMock()
        ctx.reply = AsyncMock()
        ctx.command = "test"
        error = Exception("Test error")

        await bot.on_command_error(ctx, error)

        ctx.reply.assert_called_once()
        assert "erreur" in ctx.reply.call_args[0][0].lower()

    @pytest.mark.asyncio
    async def test_on_error(self, bot):
        """Test on_error pour les événements"""
        # Ne doit pas lever d'exception
        await bot.on_error("on_message", MagicMock(), MagicMock())

        # tests/test_main.py - Ajoutez ces tests à la classe TestMainFunction


class TestMainFunction:
    # ... vos tests existants ...

    @pytest.mark.asyncio
    async def test_main_finally_block_on_success(self):
        """Vérifie que le bloc finally s'exécute même en cas de succès"""
        token = "test_token"

        with patch.dict(os.environ, {"DISCORD_TOKEN": token}):
            with patch("src.main.setup_logger"):
                with patch("src.main.logger") as mock_logger:
                    with patch.object(DiscordBot, "start", new_callable=AsyncMock):
                        await main()

                        # Vérifie que les logs du finally ont été appelés
                        assert any("Fermeture" in str(call) for call in mock_logger.info.call_args_list)
                        mock_logger.success.assert_called()

    @pytest.mark.asyncio
    async def test_main_finally_block_on_keyboard_interrupt(self):
        """Vérifie que le bloc finally s'exécute après KeyboardInterrupt"""
        token = "test_token"

        with patch.dict(os.environ, {"DISCORD_TOKEN": token}):
            with patch("src.main.setup_logger"):
                with patch("src.main.logger") as mock_logger:
                    with patch.object(
                        DiscordBot,
                        "start",
                        new_callable=AsyncMock,
                        side_effect=KeyboardInterrupt,
                    ):
                        await main()

                        # Vérifie le log warning
                        mock_logger.warning.assert_called_once()
                        assert "Interruption clavier" in str(mock_logger.warning.call_args)

                        # Vérifie que les logs du finally ont été appelés
                        assert any("Fermeture" in str(call) for call in mock_logger.info.call_args_list)
                        mock_logger.success.assert_called()

    @pytest.mark.asyncio
    async def test_main_finally_block_on_login_failure(self):
        """Vérifie que le bloc finally s'exécute après LoginFailure"""
        token = "invalid_token"

        with patch.dict(os.environ, {"DISCORD_TOKEN": token}):
            with patch("src.main.setup_logger"):
                with patch("src.main.logger") as mock_logger:
                    with patch.object(
                        DiscordBot,
                        "start",
                        new_callable=AsyncMock,
                        side_effect=discord.LoginFailure,
                    ):
                        with pytest.raises(SystemExit) as exc_info:
                            await main()

                        assert exc_info.value.code == 1

                        # Vérifie le log critical
                        mock_logger.critical.assert_called()
                        assert "Token invalide" in str(mock_logger.critical.call_args)

                        # Vérifie que les logs du finally ont été appelés
                        assert any("Fermeture" in str(call) for call in mock_logger.info.call_args_list)
                        mock_logger.success.assert_called()

    @pytest.mark.asyncio
    async def test_main_finally_block_on_generic_exception(self):
        """Vérifie que le bloc finally s'exécute après une exception générique"""
        token = "test_token"

        with patch.dict(os.environ, {"DISCORD_TOKEN": token}):
            with patch("src.main.setup_logger"):
                with patch("src.main.logger") as mock_logger:
                    with patch.object(
                        DiscordBot,
                        "start",
                        new_callable=AsyncMock,
                        side_effect=Exception("Test error"),
                    ):
                        with pytest.raises(SystemExit) as exc_info:
                            await main()

                        assert exc_info.value.code == 1

                        # Vérifie les logs critical et exception
                        assert mock_logger.critical.call_count >= 1
                        mock_logger.exception.assert_called_once()
                        assert "Stacktrace" in str(mock_logger.exception.call_args)

                        # Vérifie que les logs du finally ont été appelés
                        assert any("Fermeture" in str(call) for call in mock_logger.info.call_args_list)
                        mock_logger.success.assert_called()

    @pytest.mark.asyncio
    async def test_main_startup_log(self):
        """Vérifie que le log de démarrage est appelé"""
        token = "test_token"

        with patch.dict(os.environ, {"DISCORD_TOKEN": token}):
            with patch("src.main.setup_logger"):
                with patch("src.main.logger") as mock_logger:
                    with patch.object(DiscordBot, "start", new_callable=AsyncMock):
                        await main()

                        # Vérifie que "Démarrage du bot..." a été loggué
                        assert any("Démarrage" in str(call) for call in mock_logger.info.call_args_list)

    @pytest.mark.asyncio
    async def test_main_missing_token_critical_log(self):
        """Vérifie le log critical quand le token manque"""
        with patch.dict(os.environ, {}, clear=True):
            with patch("src.main.setup_logger"):
                with patch("src.main.logger") as mock_logger:
                    with pytest.raises(SystemExit) as exc_info:
                        await main()

                    assert exc_info.value.code == 1
                    # Vérifie le log critical
                    mock_logger.critical.assert_called_once()
                    # On ajuste ici pour correspondre au message de src/main.py
                    assert "DISCORD_TOKEN non défini" in str(mock_logger.critical.call_args)
