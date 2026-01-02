import os
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import yaml
from discord.ext import commands

from src.cogs.setup_lol import SetupLol, setup
from src.lol.exceptions import InvalidApiKey, PlayerNotFound, RateLimited

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def bot():
    """Mock du bot Discord."""
    b = MagicMock(spec=commands.Bot)
    b.add_cog = AsyncMock()
    b.wait_until_ready = AsyncMock()
    b.get_guild = MagicMock()
    return b


@pytest.fixture
def league_service():
    """Mock du service League of Legends."""
    s = MagicMock()
    s.get_puuid = MagicMock()
    s.make_profile = MagicMock()
    return s


@pytest.fixture
def cog(bot, league_service, tmp_path):
    """Crée une instance du Cog avec des fichiers temporaires."""
    db_file = tmp_path / "users.yml"
    config_file = tmp_path / "config.yml"

    c = SetupLol(bot, league_service, db_path=str(db_file), config_path=str(config_file), start_tasks=False)

    c.refresh_leaderboard.cancel()
    return c


@pytest.fixture
def interaction():
    """Mock complet d'une interaction Slash Command."""
    itr = MagicMock(spec=discord.Interaction)
    itr.guild = MagicMock()
    itr.guild.id = 987654321

    itr.user = MagicMock(spec=discord.Member)
    itr.user.id = 123456789
    itr.user.display_name = "TestUser"
    itr.user.display_avatar.url = "http://avatar.url"
    itr.user.mention = "<@123456789>"

    itr.response = MagicMock()
    itr.response.defer = AsyncMock()
    itr.response.send_message = AsyncMock()

    itr.followup = MagicMock()
    itr.followup.send = AsyncMock()

    return itr


# ============================================================================
# TESTS D'INITIALISATION
# ============================================================================


class TestInitAndData:
    def test_init_creates_directories(self, bot, league_service, tmp_path):
        """Vérifie que les dossiers sont créés à l'initialisation."""
        db_path = tmp_path / "new_folder" / "users.yml"

        SetupLol(bot, league_service, db_path=str(db_path), start_tasks=False)

        assert db_path.parent.exists()

    def test_save_and_load_user(self, cog):
        """Test la sauvegarde et le chargement d'un utilisateur."""
        cog._save_user(123, "puuid_abc", "Pseudo", "TAG", stats=None)

        users = cog._load_users()
        assert "123" in users
        assert users["123"]["pseudo"] == "Pseudo"
        assert users["123"]["puuid"] == "puuid_abc"

    def test_save_config(self, cog):
        """Test la sauvegarde de la configuration leaderboard."""
        cog._save_config(111, 222, 333)

        config = cog._load_config()
        assert "leaderboards" in config
        assert config["leaderboards"]["111"]["channel_id"] == 222
        assert config["leaderboards"]["111"]["message_id"] == 333


# ============================================================================
# TESTS /lol_link
# ============================================================================


class TestLolLink:
    @pytest.mark.asyncio
    async def test_lol_link_success(self, cog, interaction, league_service):
        """Test un lien de compte réussi."""
        league_service.get_puuid.return_value = "puuid_123"

        await cog.lol_link.callback(cog, interaction, "Joueur#EUW")

        league_service.get_puuid.assert_called_once_with("Joueur", "EUW")
        interaction.followup.send.assert_called_once()

        users = cog._load_users()
        assert str(interaction.user.id) in users
        assert users[str(interaction.user.id)]["puuid"] == "puuid_123"

    @pytest.mark.asyncio
    async def test_lol_link_invalid_format(self, cog, interaction):
        """Test format invalide (pas de #)."""
        await cog.lol_link.callback(cog, interaction, "PasDeTag")

        interaction.response.send_message.assert_called_with("❌ Format invalide. Utilisez : `Pseudo#TAG`", ephemeral=True)

    @pytest.mark.asyncio
    async def test_lol_link_not_found(self, cog, interaction, league_service):
        """Test joueur introuvable."""
        league_service.get_puuid.side_effect = PlayerNotFound()

        await cog.lol_link.callback(cog, interaction, "Introuvable#EUW")

        interaction.followup.send.assert_called_once()
        args, _ = interaction.followup.send.call_args
        message = args[0] if args else ""
        assert "Impossible de trouver" in message

    @pytest.mark.asyncio
    async def test_lol_link_rate_limited(self, cog, interaction, league_service):
        """Test rate limit."""
        league_service.get_puuid.side_effect = RateLimited()

        await cog._link_account(interaction, "Pseudo", "TAG")

        args = interaction.followup.send.call_args[0]
        assert "Trop de requêtes" in args[0]

    @pytest.mark.asyncio
    async def test_lol_link_invalid_key(self, cog, interaction, league_service):
        """Test clé API invalide."""
        league_service.get_puuid.side_effect = InvalidApiKey()

        await cog._link_account(interaction, "Pseudo", "TAG")

        args = interaction.followup.send.call_args[0]
        assert "Clé API invalide" in args[0]

    @pytest.mark.asyncio
    async def test_lol_link_generic_error(self, cog, interaction, league_service):
        """Test erreur générique."""
        league_service.get_puuid.side_effect = Exception("Boom")

        await cog._link_account(interaction, "Pseudo", "TAG")

        args = interaction.followup.send.call_args[0]
        assert "erreur interne" in args[0]


# ============================================================================
# TESTS /lol_stats
# ============================================================================


class TestLolStats:
    @pytest.mark.asyncio
    async def test_lol_stats_success_self(self, cog, interaction, league_service):
        """Test affichage de ses propres stats."""
        cog._save_user(interaction.user.id, "puuid_123", "Moi", "EUW", stats=None)

        league_service.make_profile.return_value = {
            "name": "Moi",
            "tag": "EUW",
            "level": 100,
            "profileIconId": 1,
            "rankedStats": {"soloq": None, "flex": None},
        }

        await cog.lol_stats.callback(cog, interaction, member=None)

        interaction.followup.send.assert_called_once()
        kwargs = interaction.followup.send.call_args.kwargs
        embed = kwargs["embed"]
        assert "Moi#EUW" in embed.description

    @pytest.mark.asyncio
    async def test_lol_stats_not_linked(self, cog, interaction):
        """Test stats sans compte lié."""
        await cog.lol_stats.callback(cog, interaction, member=None)

        interaction.followup.send.assert_called()
        args = interaction.followup.send.call_args[0]
        assert "❌" in args[0]
        assert "pas lié" in args[0]

    @pytest.mark.asyncio
    async def test_lol_stats_other_not_linked(self, cog, interaction):
        """Test stats d'un autre membre non lié."""
        other_member = MagicMock(spec=discord.Member)
        other_member.id = 999
        other_member.mention = "<@999>"

        await cog.lol_stats.callback(cog, interaction, member=other_member)

        interaction.followup.send.assert_called_once()
        msg = interaction.followup.send.call_args[0][0]
        assert other_member.mention in msg
        assert "n'a pas lié son compte" in msg

    @pytest.mark.asyncio
    async def test_lol_stats_player_not_found(self, cog, interaction, league_service):
        """Test PlayerNotFound dans lol_stats."""
        cog._save_user(interaction.user.id, "pid", "Name", "Tag", stats=None)
        league_service.make_profile.side_effect = PlayerNotFound()

        await cog.lol_stats.callback(cog, interaction, member=None)

        args = interaction.followup.send.call_args[0]
        assert "Impossible de trouver" in args[0]

    @pytest.mark.asyncio
    async def test_lol_stats_rate_limited(self, cog, interaction, league_service):
        """Test RateLimited dans lol_stats."""
        cog._save_user(interaction.user.id, "pid", "Name", "Tag", stats=None)
        league_service.make_profile.side_effect = RateLimited()

        await cog.lol_stats.callback(cog, interaction, member=None)

        args = interaction.followup.send.call_args[0]
        assert "Trop de requêtes" in args[0]

    @pytest.mark.asyncio
    async def test_lol_stats_invalid_key(self, cog, interaction, league_service):
        """Test InvalidApiKey dans lol_stats."""
        cog._save_user(interaction.user.id, "pid", "Name", "Tag", stats=None)
        league_service.make_profile.side_effect = InvalidApiKey()

        await cog.lol_stats.callback(cog, interaction, member=None)

        args = interaction.followup.send.call_args[0]
        msg = args[0].lower()
        assert "api" in msg and ("clé" in msg or "cle" in msg)

    @pytest.mark.asyncio
    async def test_lol_stats_generic_error(self, cog, interaction, league_service):
        """Test erreur générique dans lol_stats."""
        cog._save_user(interaction.user.id, "pid", "Name", "Tag", stats=None)
        league_service.make_profile.side_effect = Exception("Crash")

        await cog.lol_stats.callback(cog, interaction, member=None)

        args = interaction.followup.send.call_args[0]
        assert "erreur" in args[0].lower()

    @pytest.mark.asyncio
    async def test_lol_stats_full_ranks(self, cog, interaction, league_service):
        """Test affichage complet avec SoloQ et Flex."""
        cog._save_user(interaction.user.id, "pid", "Name", "Tag", stats=None)

        league_service.make_profile.return_value = {
            "name": "Name",
            "tag": "Tag",
            "level": 100,
            "profileIconId": 1,
            "rankedStats": {
                "soloq": {"tier": "GOLD", "rank": "I", "lp": 50, "wins": 10, "losses": 10, "winrate": 50.0},
                "flex": {"tier": "SILVER", "rank": "II", "lp": 20, "wins": 5, "losses": 5, "winrate": 50.0},
            },
        }

        await cog.lol_stats.callback(cog, interaction, member=None)

        kwargs = interaction.followup.send.call_args.kwargs
        embed = kwargs["embed"]
        fields = {f.name: f.value for f in embed.fields}

        assert "Gold" in fields["🏆 Solo/Duo"]
        assert "Silver" in fields["👥 Flex 5v5"]


# ============================================================================
# TESTS /lol_leaderboard_setup
# ============================================================================


class TestLeaderboardSetup:
    @pytest.mark.asyncio
    async def test_setup_leaderboard(self, cog, interaction):
        """Test la configuration du leaderboard."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 555
        channel.send = AsyncMock()

        message_mock = MagicMock()
        message_mock.id = 999
        channel.send.return_value = message_mock
        channel.mention = "#test"

        await cog.lol_leaderboard_setup.callback(cog, interaction, channel)

        channel.send.assert_called_once()

        config = cog._load_config()
        assert str(interaction.guild.id) in config["leaderboards"]
        assert config["leaderboards"][str(interaction.guild.id)]["message_id"] == 999

    @pytest.mark.asyncio
    async def test_leaderboard_setup_dm(self, cog, interaction):
        """Test commande en DM (pas de guild)."""
        interaction.guild = None

        await cog.lol_leaderboard_setup.callback(cog, interaction, MagicMock())

        interaction.response.send_message.assert_called_with("❌ Cette commande doit être utilisée sur un serveur.", ephemeral=True)

    @pytest.mark.asyncio
    async def test_leaderboard_setup_crash(self, cog, interaction):
        """Test erreur lors du setup."""
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock(side_effect=Exception("Boom"))

        await cog.lol_leaderboard_setup.callback(cog, interaction, mock_channel)

        interaction.followup.send.assert_called()
        msg = interaction.followup.send.call_args[0][0]
        assert "Erreur lors de la création" in msg


# ============================================================================
# TESTS REFRESH LEADERBOARD
# ============================================================================


class TestRefreshTask:
    @pytest.mark.asyncio
    async def test_refresh_loop(self, cog, bot, league_service):
        """Test complet de la boucle de rafraîchissement."""
        guild_id = 1000
        channel_id = 2000
        message_id = 3000

        cog._save_user(123, "puuid_1", "Player1", "EUW", stats=None)
        cog._save_config(guild_id, channel_id, message_id)

        league_service.make_profile.return_value = {"name": "Player1", "tag": "EUW", "level": 50, "rankedStats": {"soloq": None, "flex": None}}

        guild = MagicMock()
        channel = MagicMock()
        message = MagicMock()
        message.edit = AsyncMock()
        member = MagicMock()
        member.display_name = "DiscordUser"

        bot.get_guild.return_value = guild
        guild.get_channel.return_value = channel
        guild.get_member.return_value = member
        channel.fetch_message = AsyncMock(return_value=message)

        await cog.refresh_leaderboard()

        bot.get_guild.assert_called_with(guild_id)
        guild.get_channel.assert_called_with(channel_id)
        channel.fetch_message.assert_called_with(message_id)
        message.edit.assert_called_once()

        args, kwargs = message.edit.call_args
        assert isinstance(kwargs["embed"], discord.Embed)

    @pytest.mark.asyncio
    async def test_refresh_no_key(self, cog):
        """Test refresh sans la clé 'leaderboards'."""
        with open(cog.config_path, "w") as f:
            yaml.dump({"autre_chose": 1}, f)

        await cog.refresh_leaderboard()

    @pytest.mark.asyncio
    async def test_refresh_guild_not_found(self, cog, bot):
        """Test quand le serveur n'existe plus."""
        cog._save_config(999, 123, 456)
        bot.get_guild.return_value = None

        await cog.refresh_leaderboard()

    @pytest.mark.asyncio
    async def test_refresh_channel_not_found(self, cog, bot):
        """Test quand le salon n'existe plus."""
        cog._save_config(123, 999, 456)
        mock_guild = MagicMock()
        bot.get_guild.return_value = mock_guild
        mock_guild.get_channel.return_value = None

        await cog.refresh_leaderboard()

    @pytest.mark.asyncio
    async def test_refresh_message_not_found(self, cog, bot):
        """Test quand le message a été supprimé."""
        cog._save_config(123, 456, 999)
        mock_guild = MagicMock()
        mock_channel = MagicMock()
        bot.get_guild.return_value = mock_guild
        mock_guild.get_channel.return_value = mock_channel
        mock_channel.fetch_message.side_effect = discord.NotFound(MagicMock(), MagicMock())

        await cog.refresh_leaderboard()

    @pytest.mark.asyncio
    async def test_refresh_exception_in_loop(self, cog, bot):
        """Test exception dans la boucle de refresh."""
        cog._save_config(123, 456, 789)
        bot.get_guild.side_effect = Exception("Crash Loop")

        await cog.refresh_leaderboard()

    @pytest.mark.asyncio
    async def test_before_refresh_leaderboard(self, cog, bot):
        """Test que la tâche attend que le bot soit prêt."""
        await cog.before_refresh_leaderboard()
        bot.wait_until_ready.assert_called_once()


# ============================================================================
# TESTS CREATE LEADERBOARD EMBED
# ============================================================================


class TestCreateLeaderboardEmbed:
    @pytest.mark.asyncio
    async def test_create_embed_member_left(self, cog):
        """Test quand un membre a quitté le serveur."""
        cog._save_user(123, "puuid", "Parti", "Tag", stats=None)

        mock_guild = MagicMock()
        mock_guild.get_member.return_value = None

        embed = await cog._create_leaderboard_embed(mock_guild)

        assert "Parti" not in embed.description

    @pytest.mark.asyncio
    async def test_create_embed_with_cached_stats(self, cog):
        """Test LIGNE 355 : utilisation du cache quand l'API échoue."""
        # Créer un utilisateur avec des stats en cache
        cached_stats = {"name": "CachedPlayer", "tag": "EUW", "level": 150, "soloq": {"tier": "PLATINUM", "rank": "II", "lp": 75, "winrate": 55.5}}

        cog._save_user(123, "puuid123", "CachedPlayer", "EUW", stats=cached_stats)

        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.get_member.return_value = MagicMock(display_name="User")

        # Forcer l'API à échouer pour utiliser le cache (ligne 355)
        cog.league_service.make_profile.side_effect = Exception("API Down")

        embed = await cog._create_leaderboard_embed(mock_guild)

        # Vérifier que les données du cache sont utilisées
        assert "CachedPlayer" in embed.description
        assert "Platinum" in embed.description
        assert "75" in embed.description  # LP du cache
        assert "Mode Hors-Ligne" in embed.title  # Indicateur d'API down

    @pytest.mark.asyncio
    async def test_create_embed_apex_tier(self, cog):
        """Test affichage rang Master."""
        cog._save_user(123, "puuid", "Pro", "Tag", stats=None)
        mock_guild = MagicMock()
        mock_guild.get_member.return_value = MagicMock(display_name="User")

        cog.league_service.make_profile.return_value = {
            "name": "Pro",
            "tag": "Tag",
            "level": 999,
            "rankedStats": {"soloq": {"tier": "MASTER", "rank": "I", "lp": 800, "winrate": 66.6}, "flex": None},
        }

        embed = await cog._create_leaderboard_embed(mock_guild)

        assert "Master" in embed.description
        assert "800" in embed.description

    @pytest.mark.asyncio
    async def test_create_embed_all_tiers(self, cog):
        """Test tous les rangs."""
        cog._save_user(1, "p1", "Plat", "TAG", stats=None)
        cog._save_user(2, "p2", "Emer", "TAG", stats=None)
        cog._save_user(3, "p3", "Diam", "TAG", stats=None)

        mock_guild = MagicMock()
        mock_guild.get_member.return_value = MagicMock(display_name="User")

        cog.league_service.make_profile.side_effect = [
            {
                "name": "Plat",
                "tag": "T",
                "level": 100,
                "rankedStats": {"soloq": {"tier": "PLATINUM", "rank": "IV", "lp": 10, "winrate": 50}, "flex": None},
            },
            {
                "name": "Emer",
                "tag": "T",
                "level": 100,
                "rankedStats": {"soloq": {"tier": "EMERALD", "rank": "IV", "lp": 10, "winrate": 50}, "flex": None},
            },
            {
                "name": "Diam",
                "tag": "T",
                "level": 100,
                "rankedStats": {"soloq": {"tier": "DIAMOND", "rank": "IV", "lp": 10, "winrate": 50}, "flex": None},
            },
        ]

        embed = await cog._create_leaderboard_embed(mock_guild)

        assert "Platinum" in embed.description
        assert "Emerald" in embed.description
        assert "Diamond" in embed.description

    @pytest.mark.asyncio
    async def test_create_embed_with_error_user(self, cog):
        """Test quand un utilisateur fait planter l'API."""
        cog._save_user(1, "p1", "Valid", "EUW", stats=None)
        cog._save_user(2, "p2", "Error", "EUW", stats=None)

        mock_guild = MagicMock()
        mock_guild.get_member.return_value = MagicMock(display_name="User")

        cog.league_service.make_profile.side_effect = [
            {
                "name": "Valid",
                "tag": "EUW",
                "level": 30,
                "rankedStats": {"soloq": {"tier": "GOLD", "rank": "I", "lp": 10, "winrate": 50.0}, "flex": None},
            },
            Exception("API Error"),
        ]

        embed = await cog._create_leaderboard_embed(mock_guild)

        assert "Valid" in embed.description
        assert "Error" not in embed.description


# ============================================================================
# TESTS UTILITAIRES
# ============================================================================


class TestRankUtils:
    def test_get_rank_emoji(self, cog):
        """Test tous les emojis de rang."""
        assert cog._get_rank_emoji("CHALLENGER") == "🏆"
        assert cog._get_rank_emoji("IRON") == "⚫"
        assert cog._get_rank_emoji("DIAMOND") == "💎"
        assert cog._get_rank_emoji("UNKNOWN") == "❓"

    def test_get_rank_value_calculation(self, cog):
        """Test calcul du score de rang."""
        player_data = {"soloq": {"tier": "DIAMOND", "rank": "II", "lp": 50}}
        assert cog._get_rank_value(player_data) == 6250

    def test_get_rank_value_unranked(self, cog):
        """Test valeur pour unranked."""
        player_data = {"soloq": None}
        assert cog._get_rank_value(player_data) == -1


# ============================================================================
# TESTS LIFECYCLE
# ============================================================================


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_cog_load_starts_task(self, cog):
        """Test que cog_load démarre la tâche."""
        with patch.object(cog.refresh_leaderboard, "start") as mock_start:
            await cog.cog_load()
            mock_start.assert_called_once()

    def test_cog_unload_stops_task(self, cog):
        """Test que cog_unload arrête la tâche."""
        with patch.object(cog.refresh_leaderboard, "cancel") as mock_cancel:
            cog.cog_unload()
            mock_cancel.assert_called_once()


# ============================================================================
# TESTS PERSISTENCE
# ============================================================================


class TestPersistence:
    def test_save_user_appends_existing_file(self, cog):
        """Test ajout sans écraser."""
        initial_data = {"111": {"pseudo": "Old", "puuid": "old", "tag": "TAG"}}
        with open(cog.db_path, "w") as f:
            yaml.dump(initial_data, f)

        cog._save_user(222, "p2", "New", "TAG", stats=None)

        with open(cog.db_path, "r") as f:
            data = yaml.safe_load(f)

        assert data["111"]["pseudo"] == "Old"
        assert data["222"]["pseudo"] == "New"

    def test_save_user_preserves_cached_stats(self, cog):
        """Test LIGNE 69 : préservation des stats en cache lors d'une mise à jour sans nouvelles stats."""
        # Créer un utilisateur avec des stats en cache
        initial_data = {
            "123": {
                "pseudo": "Player",
                "puuid": "puuid123",
                "tag": "EUW",
                "cached_stats": {"name": "Player", "tag": "EUW", "level": 100, "soloq": {"tier": "GOLD", "rank": "I", "lp": 50, "winrate": 50.0}},
            }
        }
        with open(cog.db_path, "w") as f:
            yaml.dump(initial_data, f)

        # Mise à jour sans fournir de nouvelles stats (stats=None)
        cog._save_user(123, "puuid123", "Player", "EUW", stats=None)

        # Vérifier que les anciennes stats sont conservées
        with open(cog.db_path, "r") as f:
            data = yaml.safe_load(f)

        assert "cached_stats" in data["123"]
        assert data["123"]["cached_stats"]["level"] == 100
        assert data["123"]["cached_stats"]["soloq"]["tier"] == "GOLD"

    def test_load_config_no_file(self, cog):
        """Test chargement sans fichier."""
        if os.path.exists(cog.config_path):
            os.remove(cog.config_path)
        assert cog._load_config() == {}

    def test_load_config_file_exists(self, cog):
        """Test chargement avec fichier existant."""
        config_data = {"test": 123}
        with open(cog.config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f)

        loaded = cog._load_config()
        assert loaded["test"] == 123

    def test_save_config_preserves_existing(self, cog):
        """Test que save_config préserve les données."""
        existing = {"leaderboards": {"999": {"channel_id": 111, "message_id": 222}}, "autre": "test"}
        with open(cog.config_path, "w", encoding="utf-8") as f:
            yaml.dump(existing, f)

        cog._save_config(123, 456, 789)

        config = cog._load_config()
        assert config["leaderboards"]["123"]["channel_id"] == 456
        assert config["leaderboards"]["999"]["channel_id"] == 111
        assert config["autre"] == "test"

    def test_save_config_handles_empty_file(self, cog):
        """Test fichier vide."""
        with open(cog.config_path, "w", encoding="utf-8"):
            pass

        cog._save_config(123, 456, 789)

        config = cog._load_config()
        assert config["leaderboards"]["123"]["message_id"] == 789


# ============================================================================
# TESTS SETUP FUNCTION
# ============================================================================


@pytest.mark.asyncio
async def test_setup_entry_point(bot):
    """Test du point d'entrée setup()."""
    with patch.dict(os.environ, {"LOLAPI": "RGAPI-FAKE-KEY"}):
        with patch("src.cogs.setup_lol.RiotApiClient"):
            with patch("src.cogs.setup_lol.LeagueService"):
                await setup(bot)

                bot.add_cog.assert_called_once()
                args = bot.add_cog.call_args[0]
                assert isinstance(args[0], SetupLol)


@pytest.mark.asyncio
async def test_setup_missing_key(bot):
    """Test setup sans clé API."""
    with patch.dict(os.environ, {}, clear=True):
        with patch("src.cogs.setup_lol.RiotApiClient"):
            with patch("src.cogs.setup_lol.LeagueService"):
                await setup(bot)
                bot.add_cog.assert_called_once()
