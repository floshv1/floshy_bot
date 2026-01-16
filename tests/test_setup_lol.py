import os
from datetime import datetime, timedelta
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
    history_file = tmp_path / "lp_history.yml"

    c = SetupLol(
        bot,
        league_service,
        db_path=str(db_file),
        config_path=str(config_file),
        history_path=str(history_file),
        start_tasks=False,
    )

    c.refresh_leaderboard.cancel()
    c.track_lp_changes.cancel()
    return c


@pytest.fixture
def interaction():
    """Mock complet d'une interaction Slash Command."""
    itr = MagicMock(spec=discord.Interaction)
    itr.guild = MagicMock()
    itr.guild.id = 987654321
    itr.guild.get_member = MagicMock()

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
        history_path = tmp_path / "new_folder" / "lp_history.yml"

        SetupLol(bot, league_service, db_path=str(db_path), history_path=str(history_path), start_tasks=False)

        assert db_path.parent.exists()
        assert history_path.parent.exists()

    def test_save_and_load_user(self, cog):
        """Test la sauvegarde et le chargement d'un utilisateur."""
        cog._save_user(123, "puuid_abc", "Pseudo", "TAG", stats=None)

        users = cog._load_users()
        assert "123" in users
        assert users["123"]["pseudo"] == "Pseudo"
        assert users["123"]["puuid"] == "puuid_abc"

    def test_save_config_soloq(self, cog):
        """Test la sauvegarde de la configuration leaderboard Solo/Duo."""
        cog._save_config(111, 222, 333, "soloq")

        config = cog._load_config()
        assert "leaderboards" in config
        assert config["leaderboards"]["111"]["soloq"]["channel_id"] == 222
        assert config["leaderboards"]["111"]["soloq"]["message_id"] == 333

    def test_save_config_flex(self, cog):
        """Test la sauvegarde de la configuration leaderboard Flex."""
        cog._save_config(111, 444, 555, "flex")

        config = cog._load_config()
        assert config["leaderboards"]["111"]["flex"]["channel_id"] == 444
        assert config["leaderboards"]["111"]["flex"]["message_id"] == 555

    def test_save_config_both_queues(self, cog):
        """Test sauvegarde des deux types de leaderboards."""
        cog._save_config(111, 222, 333, "soloq")
        cog._save_config(111, 444, 555, "flex")

        config = cog._load_config()
        assert "soloq" in config["leaderboards"]["111"]
        assert "flex" in config["leaderboards"]["111"]


# ============================================================================
# TESTS LP TRACKING
# ============================================================================


class TestLPTracking:
    def test_save_lp_snapshot(self, cog):
        """Test sauvegarde d'un snapshot de LP."""
        lp_data = {
            "tier": "PLATINUM",
            "rank": "II",
            "lp": 75,
            "wins": 10,
            "losses": 5,
        }

        cog._save_lp_snapshot(123, "soloq", lp_data)

        history = cog._load_lp_history()
        assert "123" in history
        assert "soloq" in history["123"]
        assert len(history["123"]["soloq"]) == 1
        assert history["123"]["soloq"][0]["tier"] == "PLATINUM"
        assert history["123"]["soloq"][0]["lp"] == 75

    def test_save_multiple_snapshots(self, cog):
        """Test sauvegarde de plusieurs snapshots."""
        lp_data_1 = {"tier": "GOLD", "rank": "I", "lp": 50, "wins": 5, "losses": 5}
        lp_data_2 = {"tier": "GOLD", "rank": "I", "lp": 75, "wins": 6, "losses": 5}

        cog._save_lp_snapshot(123, "soloq", lp_data_1)
        cog._save_lp_snapshot(123, "soloq", lp_data_2)

        history = cog._load_lp_history()
        assert len(history["123"]["soloq"]) == 2

    def test_cleanup_old_snapshots(self, cog):
        """Test nettoyage des snapshots > 7 jours."""
        # Créer un vieux snapshot
        old_snapshot = {
            "timestamp": (datetime.utcnow() - timedelta(days=10)).isoformat(),
            "tier": "SILVER",
            "rank": "I",
            "lp": 0,
            "wins": 1,
            "losses": 1,
        }

        history = {"123": {"soloq": [old_snapshot]}}
        with open(cog.history_path, "w") as f:
            yaml.dump(history, f)

        # Ajouter un nouveau snapshot
        new_lp_data = {"tier": "GOLD", "rank": "I", "lp": 50, "wins": 5, "losses": 5}
        cog._save_lp_snapshot(123, "soloq", new_lp_data)

        # Vérifier que le vieux a été supprimé
        history = cog._load_lp_history()
        assert len(history["123"]["soloq"]) == 1
        assert history["123"]["soloq"][0]["tier"] == "GOLD"

    def test_get_total_lp_normal_rank(self, cog):
        """Test calcul de LP total pour un rang normal."""
        rank_data = {"tier": "PLATINUM", "rank": "II", "lp": 50}
        total_lp = cog._get_total_lp(rank_data)
        # PLATINUM = 1600, II = 200, LP = 50
        assert total_lp == 1850

    def test_get_total_lp_master_tier(self, cog):
        """Test calcul de LP total pour Master+."""
        rank_data = {"tier": "MASTER", "lp": 150}
        total_lp = cog._get_total_lp(rank_data)
        # MASTER = 2800, LP = 150
        assert total_lp == 2950

    def test_calculate_lp_change_no_history(self, cog):
        """Test calcul de changement sans historique."""
        result = cog._calculate_lp_change(999, "soloq", "day")
        assert result is None

    def test_calculate_lp_change_no_old_snapshot(self, cog):
        """Test calcul sans snapshot assez ancien."""
        recent_snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "tier": "GOLD",
            "rank": "I",
            "lp": 50,
            "wins": 5,
            "losses": 5,
        }

        history = {"123": {"soloq": [recent_snapshot]}}
        with open(cog.history_path, "w") as f:
            yaml.dump(history, f)

        result = cog._calculate_lp_change(123, "soloq", "day")
        assert result is None

    def test_calculate_lp_change_day(self, cog):
        """Test calcul de changement sur 24h."""
        old_snapshot = {
            "timestamp": (datetime.utcnow() - timedelta(days=1, hours=1)).isoformat(),
            "tier": "GOLD",
            "rank": "III",
            "lp": 50,
            "wins": 5,
            "losses": 5,
        }

        new_snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "tier": "GOLD",
            "rank": "II",
            "lp": 25,
            "wins": 7,
            "losses": 5,
        }

        history = {"123": {"soloq": [old_snapshot, new_snapshot]}}
        with open(cog.history_path, "w") as f:
            yaml.dump(history, f)

        result = cog._calculate_lp_change(123, "soloq", "day")
        # GOLD III 50 LP = 1200 + 100 + 50 = 1350
        # GOLD II 25 LP = 1200 + 200 + 25 = 1425
        # Différence = 75 LP
        assert result == 75

    def test_calculate_lp_change_hour(self, cog):
        """Test calcul de changement sur 1h."""
        old_snapshot = {
            "timestamp": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
            "tier": "PLATINUM",
            "rank": "I",
            "lp": 80,
            "wins": 10,
            "losses": 5,
        }

        new_snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "tier": "PLATINUM",
            "rank": "I",
            "lp": 60,
            "wins": 10,
            "losses": 6,
        }

        history = {"123": {"soloq": [old_snapshot, new_snapshot]}}
        with open(cog.history_path, "w") as f:
            yaml.dump(history, f)

        result = cog._calculate_lp_change(123, "soloq", "hour")
        assert result == -20


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
    async def test_lol_stats_with_lp_change(self, cog, interaction, league_service):
        """Test affichage des stats avec changement de LP."""
        cog._save_user(interaction.user.id, "puuid_123", "Player", "EUW", stats=None)

        # Créer un historique de LP
        old_snapshot = {
            "timestamp": (datetime.utcnow() - timedelta(days=1, hours=1)).isoformat(),
            "tier": "GOLD",
            "rank": "II",
            "lp": 50,
            "wins": 10,
            "losses": 10,
        }

        new_snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "tier": "GOLD",
            "rank": "I",
            "lp": 75,
            "wins": 15,
            "losses": 10,
        }

        history = {str(interaction.user.id): {"soloq": [old_snapshot, new_snapshot]}}
        with open(cog.history_path, "w") as f:
            yaml.dump(history, f)

        league_service.make_profile.return_value = {
            "name": "Player",
            "tag": "EUW",
            "level": 100,
            "profileIconId": 1,
            "rankedStats": {
                "soloq": {"tier": "GOLD", "rank": "I", "lp": 75, "wins": 15, "losses": 10, "winrate": 60.0},
                "flex": None,
            },
        }

        await cog.lol_stats.callback(cog, interaction, member=None)

        kwargs = interaction.followup.send.call_args.kwargs
        embed = kwargs["embed"]
        # Vérifier que le changement de LP est affiché
        solo_field = next(f for f in embed.fields if "Solo/Duo" in f.name)
        assert "+125 LP (24h)" in solo_field.value  # GOLD II 50 -> GOLD I 75 = 125 LP

    @pytest.mark.asyncio
    async def test_lol_stats_not_linked(self, cog, interaction):
        """Test stats sans compte lié."""
        await cog.lol_stats.callback(cog, interaction, member=None)

        interaction.followup.send.assert_called()
        args = interaction.followup.send.call_args[0]
        assert "❌" in args[0]
        assert "pas lié" in args[0]

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
        assert "Silver" in fields["💥 Flex 5v5"]


# ============================================================================
# TESTS /lol_leaderboard_setup
# ============================================================================


class TestLeaderboardSetup:
    @pytest.mark.asyncio
    async def test_setup_leaderboard_soloq(self, cog, interaction):
        """Test la configuration du leaderboard Solo/Duo."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 555
        channel.send = AsyncMock()

        message_mock = MagicMock()
        message_mock.id = 999
        channel.send.return_value = message_mock
        channel.mention = "#test"

        await cog.lol_leaderboard_setup.callback(cog, interaction, channel, "soloq")

        channel.send.assert_called_once()

        config = cog._load_config()
        assert str(interaction.guild.id) in config["leaderboards"]
        assert "soloq" in config["leaderboards"][str(interaction.guild.id)]
        assert config["leaderboards"][str(interaction.guild.id)]["soloq"]["message_id"] == 999

    @pytest.mark.asyncio
    async def test_setup_leaderboard_flex(self, cog, interaction):
        """Test la configuration du leaderboard Flex."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 666
        channel.send = AsyncMock()

        message_mock = MagicMock()
        message_mock.id = 888
        channel.send.return_value = message_mock
        channel.mention = "#flex"

        await cog.lol_leaderboard_setup.callback(cog, interaction, channel, "flex")

        config = cog._load_config()
        assert "flex" in config["leaderboards"][str(interaction.guild.id)]
        assert config["leaderboards"][str(interaction.guild.id)]["flex"]["message_id"] == 888

    @pytest.mark.asyncio
    async def test_leaderboard_setup_dm(self, cog, interaction):
        """Test commande en DM (pas de guild)."""
        interaction.guild = None

        await cog.lol_leaderboard_setup.callback(cog, interaction, MagicMock(), "soloq")

        interaction.response.send_message.assert_called_with("❌ Cette commande doit être utilisée sur un serveur.", ephemeral=True)


# ============================================================================
# TESTS /lol_lp_recap
# ============================================================================


class TestLPRecap:
    @pytest.mark.asyncio
    async def test_lp_recap_no_data(self, cog, interaction):
        """Test récap sans données."""
        await cog.lol_lp_recap.callback(cog, interaction, "day", "soloq")

        kwargs = interaction.followup.send.call_args.kwargs
        embed = kwargs["embed"]
        assert "Aucune donnée disponible" in embed.title

    @pytest.mark.asyncio
    async def test_lp_recap_with_data(self, cog, interaction):
        """Test récap avec données."""
        # Créer des utilisateurs
        cog._save_user(111, "p1", "Player1", "EUW", stats=None)
        cog._save_user(222, "p2", "Player2", "EUW", stats=None)

        # Créer un historique
        old_time = datetime.utcnow() - timedelta(days=1, hours=1)
        new_time = datetime.utcnow()

        history = {
            "111": {
                "soloq": [
                    {
                        "timestamp": old_time.isoformat(),
                        "tier": "GOLD",
                        "rank": "II",
                        "lp": 50,
                        "wins": 10,
                        "losses": 10,
                    },
                    {
                        "timestamp": new_time.isoformat(),
                        "tier": "GOLD",
                        "rank": "I",
                        "lp": 75,
                        "wins": 15,
                        "losses": 10,
                    },
                ]
            },
            "222": {
                "soloq": [
                    {
                        "timestamp": old_time.isoformat(),
                        "tier": "PLATINUM",
                        "rank": "III",
                        "lp": 90,
                        "wins": 20,
                        "losses": 10,
                    },
                    {
                        "timestamp": new_time.isoformat(),
                        "tier": "PLATINUM",
                        "rank": "III",
                        "lp": 70,
                        "wins": 20,
                        "losses": 11,
                    },
                ]
            },
        }

        with open(cog.history_path, "w") as f:
            yaml.dump(history, f)

        # Mock des membres
        member1 = MagicMock()
        member1.id = 111
        member2 = MagicMock()
        member2.id = 222

        interaction.guild.get_member.side_effect = lambda x: member1 if x == 111 else member2 if x == 222 else None

        await cog.lol_lp_recap.callback(cog, interaction, "day", "soloq")

        kwargs = interaction.followup.send.call_args.kwargs
        embed = kwargs["embed"]
        assert "Récapitulatif LP" in embed.title
        assert "Player1#EUW" in embed.description
        assert "Player2#EUW" in embed.description
        assert "+125 LP" in embed.description  # Player1 gain
        assert "-20 LP" in embed.description  # Player2 loss

    @pytest.mark.asyncio
    async def test_lp_recap_dm(self, cog, interaction):
        """Test récap en DM."""
        interaction.guild = None

        await cog.lol_lp_recap.callback(cog, interaction, "day", "soloq")

        interaction.response.send_message.assert_called_with("❌ Cette commande doit être utilisée sur un serveur.", ephemeral=True)


# ============================================================================
# TESTS REFRESH LEADERBOARD
# ============================================================================


class TestRefreshTask:
    @pytest.mark.asyncio
    async def test_refresh_both_queues(self, cog, bot, league_service):
        """Test refresh de soloq et flex."""
        guild_id = 1000
        channel_id_soloq = 2000
        message_id_soloq = 3000
        channel_id_flex = 2001
        message_id_flex = 3001

        cog._save_user(123, "puuid_1", "Player1", "EUW", stats=None)
        cog._save_config(guild_id, channel_id_soloq, message_id_soloq, "soloq")
        cog._save_config(guild_id, channel_id_flex, message_id_flex, "flex")

        league_service.make_profile.return_value = {
            "name": "Player1",
            "tag": "EUW",
            "level": 50,
            "rankedStats": {
                "soloq": {"tier": "GOLD", "rank": "I", "lp": 50, "wins": 10, "losses": 10, "winrate": 50.0},
                "flex": {"tier": "SILVER", "rank": "II", "lp": 30, "wins": 5, "losses": 5, "winrate": 50.0},
            },
        }

        guild = MagicMock()
        channel_soloq = MagicMock()
        channel_flex = MagicMock()
        message_soloq = MagicMock()
        message_flex = MagicMock()
        message_soloq.edit = AsyncMock()
        message_flex.edit = AsyncMock()
        member = MagicMock()
        member.display_name = "DiscordUser"

        bot.get_guild.return_value = guild
        guild.get_channel.side_effect = lambda x: channel_soloq if x == channel_id_soloq else channel_flex
        guild.get_member.return_value = member
        channel_soloq.fetch_message = AsyncMock(return_value=message_soloq)
        channel_flex.fetch_message = AsyncMock(return_value=message_flex)

        await cog.refresh_leaderboard()

        # Vérifier que les deux messages ont été modifiés
        message_soloq.edit.assert_called_once()
        message_flex.edit.assert_called_once()


# ============================================================================
# TESTS TRACK LP CHANGES TASK
# ============================================================================


class TestTrackLPTask:
    @pytest.mark.asyncio
    async def test_track_lp_changes(self, cog, league_service):
        """Test de la tâche de tracking de LP."""
        cog._save_user(123, "puuid_1", "Player1", "EUW", stats=None)
        cog._save_user(456, "puuid_2", "Player2", "EUW", stats=None)

        league_service.make_profile.side_effect = [
            {
                "name": "Player1",
                "tag": "EUW",
                "level": 50,
                "rankedStats": {
                    "soloq": {"tier": "GOLD", "rank": "I", "lp": 50, "wins": 10, "losses": 10, "winrate": 50.0},
                    "flex": None,
                },
            },
            {
                "name": "Player2",
                "tag": "EUW",
                "level": 60,
                "rankedStats": {
                    "soloq": None,
                    "flex": {"tier": "SILVER", "rank": "II", "lp": 30, "wins": 5, "losses": 5, "winrate": 50.0},
                },
            },
        ]

        await cog.track_lp_changes()

        history = cog._load_lp_history()
        assert "123" in history
        assert "soloq" in history["123"]
        assert history["123"]["soloq"][0]["tier"] == "GOLD"

        assert "456" in history
        assert "flex" in history["456"]
        assert history["456"]["flex"][0]["tier"] == "SILVER"

    @pytest.mark.asyncio
    async def test_track_lp_error_handling(self, cog, league_service):
        """Test gestion d'erreurs dans le tracking."""
        cog._save_user(123, "puuid_error", "ErrorPlayer", "EUW", stats=None)
        league_service.make_profile.side_effect = Exception("API Error")

        # Ne devrait pas planter
        await cog.track_lp_changes()


# ============================================================================
# TESTS CREATE LEADERBOARD EMBED
# ============================================================================


class TestCreateLeaderboardEmbed:
    @pytest.mark.asyncio
    async def test_create_embed_new_format(self, cog):
        """Test du nouveau format de leaderboard."""
        cog._save_user(123, "puuid", "Player", "TAG", stats=None)
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.get_member.return_value = MagicMock(display_name="User")

        cog.league_service.make_profile.return_value = {
            "name": "Player",
            "tag": "TAG",
            "level": 100,
            "rankedStats": {
                "soloq": {"tier": "PLATINUM", "rank": "I", "lp": 57, "wins": 9, "losses": 0, "winrate": 100.0},
                "flex": None,
            },
        }

        embed = await cog._create_leaderboard_embed(mock_guild, "soloq")

        # Vérifier le nouveau format : P I • 57 LP - 100.0% WR - 09
        assert "P I" in embed.description  # Rang raccourci
        assert "57 LP" in embed.description
        assert "100.0% WR" in embed.description
        assert "09" in embed.description  # Nombre de games sur 2 chiffres

    @pytest.mark.asyncio
    async def test_create_embed_losing_winrate(self, cog):
        """Test format winrate avec L pour < 50%."""
        cog._save_user(123, "puuid", "Loser", "TAG", stats=None)
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.get_member.return_value = MagicMock(display_name="User")

        cog.league_service.make_profile.return_value = {
            "name": "Loser",
            "tag": "TAG",
            "level": 100,
            "rankedStats": {
                "soloq": {"tier": "GOLD", "rank": "III", "lp": 20, "wins": 10, "losses": 20, "winrate": 33.3},
                "flex": None,
            },
        }

        embed = await cog._create_leaderboard_embed(mock_guild, "soloq")

        # Vérifier le L devant le winrate
        assert "L33.3% WR" in embed.description

    @pytest.mark.asyncio
    async def test_create_embed_flex_queue(self, cog):
        """Test création de leaderboard Flex."""
        cog._save_user(123, "puuid", "FlexPlayer", "TAG", stats=None)
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.get_member.return_value = MagicMock(display_name="User")

        cog.league_service.make_profile.return_value = {
            "name": "FlexPlayer",
            "tag": "TAG",
            "level": 100,
            "rankedStats": {
                "soloq": None,
                "flex": {"tier": "EMERALD", "rank": "IV", "lp": 75, "wins": 15, "losses": 15, "winrate": 50.0},
            },
        }

        embed = await cog._create_leaderboard_embed(mock_guild, "flex")

        assert "Flex 5v5" in embed.title
        assert "E IV" in embed.description  # Emerald raccourci
        assert "75 LP" in embed.description

    @pytest.mark.asyncio
    async def test_create_embed_master_tier_format(self, cog):
        """Test format Master/GM/Challenger (pas de division)."""
        cog._save_user(123, "puuid", "Master", "TAG", stats=None)
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.get_member.return_value = MagicMock(display_name="User")

        cog.league_service.make_profile.return_value = {
            "name": "Master",
            "tag": "TAG",
            "level": 500,
            "rankedStats": {
                "soloq": {"tier": "MASTER", "lp": 250, "wins": 100, "losses": 50, "winrate": 66.7},
                "flex": None,
            },
        }

        embed = await cog._create_leaderboard_embed(mock_guild, "soloq")

        # Format Master : M • 250 LP (pas de rank)
        assert "M • 250 LP" in embed.description
        assert " I" not in embed.description  # Pas de division

    @pytest.mark.asyncio
    async def test_create_embed_with_cached_stats(self, cog):
        """Test utilisation du cache quand l'API échoue."""
        cached_stats = {
            "name": "CachedPlayer",
            "tag": "EUW",
            "level": 150,
            "soloq": {"tier": "PLATINUM", "rank": "II", "lp": 75, "wins": 20, "losses": 20, "winrate": 50.0},
        }

        cog._save_user(123, "puuid123", "CachedPlayer", "EUW", stats=cached_stats)

        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.get_member.return_value = MagicMock(display_name="User")

        cog.league_service.make_profile.side_effect = Exception("API Down")

        embed = await cog._create_leaderboard_embed(mock_guild, "soloq")

        assert "CachedPlayer" in embed.description
        assert "P II" in embed.description
        assert "75 LP" in embed.description
        assert "Mode Hors-Ligne" in embed.title

    @pytest.mark.asyncio
    async def test_create_embed_member_left(self, cog):
        """Test quand un membre a quitté le serveur."""
        cog._save_user(123, "puuid", "Parti", "Tag", stats=None)

        mock_guild = MagicMock()
        mock_guild.get_member.return_value = None

        embed = await cog._create_leaderboard_embed(mock_guild, "soloq")

        assert "Parti" not in embed.description

    @pytest.mark.asyncio
    async def test_create_embed_unranked_player(self, cog):
        """Test affichage d'un joueur unranked."""
        cog._save_user(123, "puuid", "Unranked", "TAG", stats=None)
        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.get_member.return_value = MagicMock(display_name="User")

        cog.league_service.make_profile.return_value = {
            "name": "Unranked",
            "tag": "TAG",
            "level": 30,
            "rankedStats": {"soloq": None, "flex": None},
        }

        embed = await cog._create_leaderboard_embed(mock_guild, "soloq")

        assert "Unranked" in embed.description
        assert "00" in embed.description  # 0 games

    @pytest.mark.asyncio
    async def test_create_embed_sorting(self, cog):
        """Test tri correct des joueurs."""
        cog._save_user(1, "p1", "Diamond", "TAG", stats=None)
        cog._save_user(2, "p2", "Platinum", "TAG", stats=None)
        cog._save_user(3, "p3", "Gold", "TAG", stats=None)

        mock_guild = MagicMock()
        mock_guild.name = "Test Guild"
        mock_guild.get_member.return_value = MagicMock(display_name="User")

        cog.league_service.make_profile.side_effect = [
            {
                "name": "Diamond",
                "tag": "TAG",
                "level": 100,
                "rankedStats": {
                    "soloq": {"tier": "DIAMOND", "rank": "IV", "lp": 10, "wins": 10, "losses": 10, "winrate": 50.0},
                    "flex": None,
                },
            },
            {
                "name": "Platinum",
                "tag": "TAG",
                "level": 100,
                "rankedStats": {
                    "soloq": {"tier": "PLATINUM", "rank": "I", "lp": 99, "wins": 10, "losses": 10, "winrate": 50.0},
                    "flex": None,
                },
            },
            {
                "name": "Gold",
                "tag": "TAG",
                "level": 100,
                "rankedStats": {
                    "soloq": {"tier": "GOLD", "rank": "I", "lp": 50, "wins": 10, "losses": 10, "winrate": 50.0},
                    "flex": None,
                },
            },
        ]

        embed = await cog._create_leaderboard_embed(mock_guild, "soloq")

        # Vérifier l'ordre dans la description
        lines = embed.description.split("\n")
        # Diamond devrait être en premier
        assert "Diamond" in lines[1]  # ligne 0 = ```, ligne 1 = premier joueur


# ============================================================================
# TESTS UTILITAIRES
# ============================================================================


class TestRankUtils:
    def test_get_rank_emoji(self, cog):
        """Test tous les emojis de rang."""
        assert cog._get_rank_emoji("CHALLENGER") == "🏆"
        assert cog._get_rank_emoji("IRON") == "⚫"
        assert cog._get_rank_emoji("DIAMOND") == "💎"
        assert cog._get_rank_emoji("EMERALD") == "🟢"
        assert cog._get_rank_emoji("PLATINUM") == "🔵"
        assert cog._get_rank_emoji("MASTER") == "🟣"
        assert cog._get_rank_emoji("GRANDMASTER") == "🔴"
        assert cog._get_rank_emoji("UNKNOWN") == "❓"

    def test_get_rank_value_calculation(self, cog):
        """Test calcul du score de rang."""
        player_data = {"soloq": {"tier": "DIAMOND", "rank": "II", "lp": 50}}
        assert cog._get_rank_value(player_data) == 6250

    def test_get_rank_value_flex(self, cog):
        """Test calcul pour flex queue."""
        player_data = {"flex": {"tier": "PLATINUM", "rank": "III", "lp": 75}}
        assert cog._get_rank_value(player_data) == 4175

    def test_get_rank_value_unranked(self, cog):
        """Test valeur pour unranked."""
        player_data = {"soloq": None}
        assert cog._get_rank_value(player_data) == -1

    def test_get_rank_value_master_tier(self, cog):
        """Test calcul pour Master+."""
        player_data = {"soloq": {"tier": "CHALLENGER", "lp": 1500}}
        assert cog._get_rank_value(player_data) == 10800  # 9*1000 + 3*100 + 1500


# ============================================================================
# TESTS LIFECYCLE
# ============================================================================


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_cog_load_starts_tasks(self, cog):
        """Test que cog_load démarre les tâches."""
        with patch.object(cog.refresh_leaderboard, "start") as mock_refresh:
            with patch.object(cog.track_lp_changes, "start") as mock_track:
                await cog.cog_load()
                mock_refresh.assert_called_once()
                mock_track.assert_called_once()

    def test_cog_unload_stops_tasks(self, cog):
        """Test que cog_unload arrête les tâches."""
        with patch.object(cog.refresh_leaderboard, "cancel") as mock_refresh:
            with patch.object(cog.track_lp_changes, "cancel") as mock_track:
                cog.cog_unload()
                mock_refresh.assert_called_once()
                mock_track.assert_called_once()

    @pytest.mark.asyncio
    async def test_before_tasks(self, cog, bot):
        """Test que les tâches attendent que le bot soit prêt."""
        await cog.before_tasks()
        bot.wait_until_ready.assert_called_once()


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
        """Test préservation des stats en cache lors d'une mise à jour sans nouvelles stats."""
        initial_data = {
            "123": {
                "pseudo": "Player",
                "puuid": "puuid123",
                "tag": "EUW",
                "cached_stats": {
                    "name": "Player",
                    "tag": "EUW",
                    "level": 100,
                    "soloq": {"tier": "GOLD", "rank": "I", "lp": 50, "wins": 10, "losses": 10, "winrate": 50.0},
                },
            }
        }
        with open(cog.db_path, "w") as f:
            yaml.dump(initial_data, f)

        cog._save_user(123, "puuid123", "Player", "EUW", stats=None)

        with open(cog.db_path, "r") as f:
            data = yaml.safe_load(f)

        assert "cached_stats" in data["123"]
        assert data["123"]["cached_stats"]["level"] == 100
        assert data["123"]["cached_stats"]["soloq"]["tier"] == "GOLD"

    def test_save_user_updates_cached_stats(self, cog):
        """Test mise à jour des stats en cache."""
        initial_data = {
            "123": {
                "pseudo": "Player",
                "puuid": "puuid123",
                "tag": "EUW",
                "cached_stats": {
                    "name": "Player",
                    "tag": "EUW",
                    "level": 100,
                    "soloq": {"tier": "GOLD", "rank": "I", "lp": 50, "wins": 10, "losses": 10, "winrate": 50.0},
                },
            }
        }
        with open(cog.db_path, "w") as f:
            yaml.dump(initial_data, f)

        new_stats = {
            "name": "Player",
            "tag": "EUW",
            "level": 150,
            "soloq": {"tier": "PLATINUM", "rank": "III", "lp": 75, "wins": 20, "losses": 10, "winrate": 66.7},
        }

        cog._save_user(123, "puuid123", "Player", "EUW", stats=new_stats)

        with open(cog.db_path, "r") as f:
            data = yaml.safe_load(f)

        assert data["123"]["cached_stats"]["level"] == 150
        assert data["123"]["cached_stats"]["soloq"]["tier"] == "PLATINUM"

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
        existing = {
            "leaderboards": {"999": {"soloq": {"channel_id": 111, "message_id": 222}}},
            "autre": "test",
        }
        with open(cog.config_path, "w", encoding="utf-8") as f:
            yaml.dump(existing, f)

        cog._save_config(123, 456, 789, "flex")

        config = cog._load_config()
        assert config["leaderboards"]["123"]["flex"]["channel_id"] == 456
        assert config["leaderboards"]["999"]["soloq"]["channel_id"] == 111
        assert config["autre"] == "test"

    def test_load_lp_history_no_file(self, cog):
        """Test chargement historique sans fichier."""
        if os.path.exists(cog.history_path):
            os.remove(cog.history_path)
        assert cog._load_lp_history() == {}

    def test_load_lp_history_with_data(self, cog):
        """Test chargement historique avec données."""
        history_data = {
            "123": {
                "soloq": [
                    {
                        "timestamp": datetime.utcnow().isoformat(),
                        "tier": "GOLD",
                        "rank": "I",
                        "lp": 50,
                        "wins": 10,
                        "losses": 10,
                    }
                ]
            }
        }
        with open(cog.history_path, "w", encoding="utf-8") as f:
            yaml.dump(history_data, f)

        loaded = cog._load_lp_history()
        assert "123" in loaded
        assert loaded["123"]["soloq"][0]["tier"] == "GOLD"


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
