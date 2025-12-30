# tests/test_bot.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord.ext import commands

from src.main import DiscordBot


class TestDiscordBotInitialization:
    """Tests pour l'initialisation du DiscordBot"""

    def test_bot_initialization(self):
        """Vérifie que le bot s'initialise correctement"""
        bot = DiscordBot()

        assert bot is not None
        assert bot.command_prefix == "!"
        assert bot.help_command is None

    def test_bot_intents(self):
        """Vérifie que les intents sont configurés correctement"""
        bot = DiscordBot()

        assert bot.intents.message_content is True
        assert bot.intents.members is True

    def test_bot_extends_commands_bot(self):
        """Vérifie que DiscordBot hérite de commands.Bot"""
        bot = DiscordBot()
        assert isinstance(bot, commands.Bot)


class TestBotSetupHook:
    """Tests pour la méthode setup_hook"""

    @pytest.mark.asyncio
    async def test_setup_hook_calls_load_cogs(self):
        """Vérifie que setup_hook appelle load_cogs"""
        bot = DiscordBot()

        with patch.object(bot, "load_cogs", new_callable=AsyncMock) as mock_load:
            with patch.object(bot.tree, "sync", new_callable=AsyncMock, return_value=[]):
                await bot.setup_hook()
                mock_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_hook_syncs_commands(self):
        """Vérifie que setup_hook synchronise les commandes slash"""
        bot = DiscordBot()

        with patch.object(bot, "load_cogs", new_callable=AsyncMock):
            with patch.object(bot.tree, "sync", new_callable=AsyncMock, return_value=[]) as mock_sync:
                await bot.setup_hook()
                mock_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_setup_hook_handles_sync_error(self):
        """Vérifie que les erreurs de sync sont gérées"""
        bot = DiscordBot()

        with patch.object(bot, "load_cogs", new_callable=AsyncMock):
            with patch.object(
                bot.tree,
                "sync",
                new_callable=AsyncMock,
                side_effect=Exception("Sync error"),
            ):
                # Ne devrait pas lever d'exception
                await bot.setup_hook()


class TestBotLoadCogs:
    """Tests pour la méthode load_cogs"""

    @pytest.mark.asyncio
    async def test_load_cogs_with_no_cogs(self):
        """Vérifie que load_cogs fonctionne sans cogs"""
        bot = DiscordBot()

        with patch("src.main.Path") as mock_path:
            mock_cogs_dir = MagicMock()
            mock_cogs_dir.glob.return_value = []
            mock_path.return_value.parent = MagicMock()
            mock_path.return_value.parent.__truediv__ = MagicMock(return_value=mock_cogs_dir)

            # Ne devrait pas lever d'exception
            await bot.load_cogs()

    @pytest.mark.asyncio
    async def test_load_cogs_skips_init_file(self):
        """Vérifie que load_cogs ignore __init__.py"""
        bot = DiscordBot()

        with patch("src.main.Path") as mock_path:
            # Créer un mock pour un fichier __init__.py
            mock_init_file = MagicMock()
            mock_init_file.stem = "__init__"

            mock_cogs_dir = MagicMock()
            mock_cogs_dir.glob.return_value = [mock_init_file]

            mock_path.return_value.parent = MagicMock()
            mock_path.return_value.parent.__truediv__ = MagicMock(return_value=mock_cogs_dir)

            with patch.object(bot, "load_extension", new_callable=AsyncMock) as mock_load_ext:
                await bot.load_cogs()
                # load_extension ne devrait pas être appelé pour __init__.py
                mock_load_ext.assert_not_called()


class TestBotErrorHandlers:
    """Tests pour les handlers d'erreurs"""

    @pytest.mark.asyncio
    async def test_on_command_error_command_not_found(self):
        """Vérifie que CommandNotFound est ignoré silencieusement"""
        bot = DiscordBot()
        ctx = MagicMock()
        error = commands.CommandNotFound()

        # Ne devrait pas lever d'exception
        await bot.on_command_error(ctx, error)

    @pytest.mark.asyncio
    async def test_on_command_error_missing_permissions(self):
        """Vérifie la gestion des erreurs de permissions"""
        bot = DiscordBot()
        ctx = MagicMock()
        ctx.reply = AsyncMock()
        ctx.author = "TestUser"
        ctx.command = "test_command"

        error = commands.MissingPermissions(["administrator"])

        await bot.on_command_error(ctx, error)

        # Vérifie que reply a été appelé
        ctx.reply.assert_called_once()
        call_args = ctx.reply.call_args[0][0]
        assert "permissions" in call_args.lower()

    @pytest.mark.asyncio
    async def test_on_command_error_missing_required_argument(self):
        """Vérifie la gestion des arguments manquants"""
        bot = DiscordBot()
        ctx = MagicMock()
        ctx.reply = AsyncMock()
        ctx.command = "test_command"

        param = MagicMock()
        param.name = "user_id"
        error = commands.MissingRequiredArgument(param)

        await bot.on_command_error(ctx, error)

        ctx.reply.assert_called_once()
        call_args = ctx.reply.call_args[0][0]
        assert "user_id" in call_args or "argument" in call_args.lower()

    @pytest.mark.asyncio
    async def test_on_command_error_cooldown(self):
        """Vérifie la gestion du cooldown"""
        bot = DiscordBot()
        ctx = MagicMock()
        ctx.reply = AsyncMock()
        ctx.author = "TestUser"
        ctx.command = "test_command"

        # CommandOnCooldown nécessite un type (cooldown type)
        error = commands.CommandOnCooldown(5.0, 10.0, commands.BucketType.default)

        await bot.on_command_error(ctx, error)

        ctx.reply.assert_called_once()
        call_args = ctx.reply.call_args[0][0]
        assert "cooldown" in call_args.lower() or "⏳" in call_args

    @pytest.mark.asyncio
    async def test_on_error_event_error(self):
        """Vérifie la gestion des erreurs d'événements"""
        bot = DiscordBot()

        # Ne devrait pas lever d'exception
        await bot.on_error("test_event")


class TestBotEvents:
    """Tests pour les événements du bot"""

    @pytest.mark.asyncio
    async def test_on_command_logging(self):
        """Vérifie que on_command enregistre l'utilisation"""
        bot = DiscordBot()
        ctx = MagicMock()
        ctx.command = "ping"
        ctx.author = "TestUser"
        ctx.channel = "general"
        ctx.guild = "TestGuild"

        # Ne devrait pas lever d'exception
        await bot.on_command(ctx)
