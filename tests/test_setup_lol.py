from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
import yaml
from discord.ext import commands

from src.cogs.setup_lol import SetupLol
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

    # Annulation des tâches pour éviter qu'elles tournent pendant les tests
    c.refresh_leaderboard.cancel()
    c.daily_lp_reset.cancel()
    return c


@pytest.fixture
def interaction():
    """Mock complet d'une interaction Slash Command."""
    itr = MagicMock(spec=discord.Interaction)
    itr.guild = MagicMock()
    itr.guild.id = 987654321
    itr.guild.name = "Test Guild"
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
# TESTS D'INITIALISATION & DATA
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

    def test_lp_change_calculation(self, cog):
        """Test du calcul de changement de LP."""
        # Cas simple : 100 LP actuels - 50 LP enregistrés = +50
        cog._save_lp_tracking({"123": {"soloq": {"daily_lp": 50}}})
        change = cog._get_lp_change(123, "soloq", 100)
        assert change == 50

    def test_lp_change_no_data(self, cog):
        """Test changement LP sans données précédentes."""
        change = cog._get_lp_change(999, "soloq", 100)
        assert change == 0  # 100 - 100 (défaut)


# ============================================================================
# TESTS COMMANDES : /lol_link
# ============================================================================


class TestLolLink:
    @pytest.mark.asyncio
    async def test_lol_link_success_full(self, cog, interaction, league_service):
        """Test lien de compte complet avec initialisation tracking."""
        league_service.get_puuid.return_value = "puuid_123"
        # Simulation d'un profil classé pour déclencher le tracking
        league_service.make_profile.return_value = {"rankedStats": {"soloq": {"tier": "GOLD", "rank": "IV", "lp": 0}, "flex": None}}

        await cog.lol_link.callback(cog, interaction, "Joueur#EUW")

        # Vérifier sauvegarde user
        users = cog._load_users()
        assert users[str(interaction.user.id)]["puuid"] == "puuid_123"

        # Vérifier tracking initialisé
        tracking = cog._load_lp_tracking()
        assert str(interaction.user.id) in tracking
        assert "soloq" in tracking[str(interaction.user.id)]

    @pytest.mark.asyncio
    async def test_lol_link_tracking_fail_sliently(self, cog, interaction, league_service):
        """Test lien réussi même si l'initialisation du tracking échoue (API down)."""
        league_service.get_puuid.return_value = "puuid_123"
        # get_puuid marche, mais make_profile plante
        league_service.make_profile.side_effect = Exception("API Error")

        await cog.lol_link.callback(cog, interaction, "Joueur#EUW")

        # L'utilisateur doit être sauvegardé quand même
        users = cog._load_users()
        assert str(interaction.user.id) in users

        # Le message de succès doit être envoyé
        interaction.followup.send.assert_called()

        # Récupération de l'embed via kwargs (correction de l'erreur précédente)
        kwargs = interaction.followup.send.call_args.kwargs
        embed = kwargs.get("embed")

        assert embed is not None
        assert "Compte lié avec succès" in embed.title

    @pytest.mark.asyncio
    async def test_lol_link_errors(self, cog, interaction, league_service):
        """Test des différentes erreurs possibles lors du lien."""
        # Cas 1: PlayerNotFound
        league_service.get_puuid.side_effect = PlayerNotFound()
        await cog.lol_link.callback(cog, interaction, "Inconnu#TAG")
        assert "Impossible de trouver" in interaction.followup.send.call_args[0][0]

        # Cas 2: RateLimited
        league_service.get_puuid.side_effect = RateLimited()
        await cog.lol_link.callback(cog, interaction, "Spam#TAG")
        assert "Trop de requêtes" in interaction.followup.send.call_args[0][0]

        # Cas 3: InvalidApiKey
        league_service.get_puuid.side_effect = InvalidApiKey()
        await cog.lol_link.callback(cog, interaction, "Key#TAG")
        assert "Clé API invalide" in interaction.followup.send.call_args[0][0]


# ============================================================================
# TESTS COMMANDES : /lol_stats
# ============================================================================


class TestLolStats:
    @pytest.mark.asyncio
    async def test_lol_stats_display(self, cog, interaction, league_service):
        """Test affichage standard des stats."""
        cog._save_user(interaction.user.id, "pid", "Name", "Tag", stats=None)
        league_service.make_profile.return_value = {
            "name": "Name",
            "tag": "Tag",
            "level": 100,
            "profileIconId": 1,
            "rankedStats": {"soloq": {"tier": "GOLD", "rank": "I", "lp": 50, "wins": 10, "losses": 10, "winrate": 50}, "flex": None},
        }

        await cog.lol_stats.callback(cog, interaction, member=None)

        embed = interaction.followup.send.call_args.kwargs["embed"]
        assert "Name#Tag" in embed.description
        # CORRECTION : Le code utilise .title() donc "Gold I" et non "GOLD I"
        assert "Gold I" in embed.fields[1].value

    @pytest.mark.asyncio
    async def test_lol_stats_error_handling(self, cog, interaction, league_service):
        """Test gestion erreurs API dans stats."""
        cog._save_user(interaction.user.id, "pid", "Name", "Tag", stats=None)

        # Test PlayerNotFound (ex: changement de nom)
        league_service.make_profile.side_effect = PlayerNotFound()
        await cog.lol_stats.callback(cog, interaction, member=None)
        assert "Impossible de trouver" in interaction.followup.send.call_args[0][0]

        # Test RateLimited
        league_service.make_profile.side_effect = RateLimited()
        await cog.lol_stats.callback(cog, interaction, member=None)
        assert "Trop de requêtes" in interaction.followup.send.call_args[0][0]


# ============================================================================
# TESTS COMMANDES : Setup (Leaderboard & Recap)
# ============================================================================


class TestSetups:
    @pytest.mark.asyncio
    async def test_leaderboard_setup(self, cog, interaction):
        """Test configuration leaderboard."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 100
        channel.send = AsyncMock()
        channel.send.return_value.id = 200  # message_id

        await cog.lol_leaderboard_setup.callback(cog, interaction, channel, "soloq")

        config = cog._load_config()
        assert config["leaderboards"][str(interaction.guild.id)]["soloq"]["channel_id"] == 100
        assert config["leaderboards"][str(interaction.guild.id)]["soloq"]["message_id"] == 200

    @pytest.mark.asyncio
    async def test_lp_recap_setup(self, cog, interaction):
        """Test configuration LP Recap."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 300
        channel.send = AsyncMock()
        channel.send.return_value.id = 400

        await cog.lol_lp_recap_setup.callback(cog, interaction, channel, "flex")

        config = cog._load_config()
        assert config["lp_recaps"][str(interaction.guild.id)]["flex"]["channel_id"] == 300

    @pytest.mark.asyncio
    async def test_setup_exception(self, cog, interaction):
        """Test erreur lors du setup (ex: pas de perm)."""
        channel = MagicMock()
        # CORRECTION : discord.Forbidden nécessite (response, message)
        # On utilise ici Exception générique ou on construit correctement Forbidden
        channel.send.side_effect = discord.Forbidden(MagicMock(), "Pas de perm")

        await cog.lol_leaderboard_setup.callback(cog, interaction, channel, "soloq")

        # Vérifie qu'un message d'erreur est envoyé à l'utilisateur
        args = interaction.followup.send.call_args[0]
        assert "Erreur" in args[0]


# ============================================================================
# TESTS TÂCHES PÉRIODIQUES (Edge Cases)
# ============================================================================


class TestTasksEdgeCases:
    @pytest.mark.asyncio
    async def test_refresh_leaderboard_missing_elements(self, cog, bot):
        """Test refresh avec guild/channel/message manquants."""
        # Config avec 2 guilds
        config = {
            "leaderboards": {
                "111": {"soloq": {"channel_id": 222, "message_id": 333}},  # Guild ok, Channel missing
                "444": {"soloq": {"channel_id": 555, "message_id": 666}},  # Guild missing
            }
        }
        with open(cog.config_path, "w") as f:
            yaml.dump(config, f)

        # Mock Bot
        guild_111 = MagicMock()
        guild_111.get_channel.return_value = None  # Channel introuvable

        # get_guild retourne guild_111 pour id 111, None pour 444
        bot.get_guild.side_effect = lambda x: guild_111 if x == 111 else None

        # Exécuter la tâche (ne doit pas planter)
        await cog.refresh_leaderboard()

        # Si on arrive ici sans crash, le test passe (les logs warning sont gérés en interne)

    @pytest.mark.asyncio
    async def test_refresh_leaderboard_message_deleted(self, cog, bot):
        """Test refresh si le message a été supprimé."""
        cog._save_config(111, 222, 333, "soloq")

        guild = MagicMock()
        channel = MagicMock()
        # fetch_message lève NotFound
        # CORRECTION: fetch_message est async, donc side_effect sur un AsyncMock ou résultat awaitable
        channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "Msg gone"))

        bot.get_guild.return_value = guild
        guild.get_channel.return_value = channel

        await cog.refresh_leaderboard()
        # Succès si pas de crash

    @pytest.mark.asyncio
    async def test_daily_lp_reset_logic(self, cog, league_service):
        """Test que le reset met bien à jour les valeurs dans le fichier."""
        # User avec 1000 LP hier
        cog._save_user(1, "uid", "Name", "Tag", stats=None)
        tracking = {"1": {"soloq": {"daily_lp": 1000, "last_reset": "old"}}}
        cog._save_lp_tracking(tracking)

        # API dit 1100 LP aujourd'hui
        league_service.make_profile.return_value = {
            "rankedStats": {"soloq": {"tier": "SILVER", "rank": "II", "lp": 100}, "flex": None}  # 800+200+100=1100
        }

        await cog.daily_lp_reset()

        new_tracking = cog._load_lp_tracking()
        # daily_lp doit être mis à jour à 1100 pour le nouveau jour
        assert new_tracking["1"]["soloq"]["daily_lp"] == 1100
        assert new_tracking["1"]["soloq"]["last_reset"] == datetime.utcnow().strftime("%d/%m/%Y")

    @pytest.mark.asyncio
    async def test_daily_lp_reset_recap_update(self, cog, bot):
        """Test que le reset met aussi à jour les messages de recap."""
        # Config recap
        cog._save_config(111, 222, 333, "soloq", "lp_recap")

        guild = MagicMock()
        channel = MagicMock()
        message = MagicMock()
        # CORRECTION CRITIQUE: edit est une coroutine
        message.edit = AsyncMock()

        bot.get_guild.return_value = guild
        guild.get_channel.return_value = channel

        # CORRECTION CRITIQUE : fetch_message est appelé avec await, donc il faut un AsyncMock
        channel.fetch_message = AsyncMock(return_value=message)

        # User fictif pour générer du contenu
        cog._save_user(1, "uid", "P", "T", stats=None)

        await cog.daily_lp_reset()

        # Vérifier que le message a été édité
        message.edit.assert_called_once()


# ============================================================================
# TESTS LOGIQUE EMBEDS
# ============================================================================


class TestEmbeds:
    @pytest.mark.asyncio
    async def test_create_leaderboard_offline_mode(self, cog):
        """Test l'affichage hors ligne (API Down)."""
        guild = MagicMock()
        guild.name = "Guild"
        member = MagicMock()
        guild.get_member.return_value = member

        # User avec cache
        cached_stats = {
            "name": "CacheUser",
            "tag": "TAG",
            "level": 50,
            "soloq": {"tier": "GOLD", "rank": "IV", "lp": 10, "wins": 1, "losses": 1, "winrate": 50},
        }
        cog._save_user(1, "uid", "Name", "Tag", stats=cached_stats)

        # API plante
        cog.league_service.make_profile.side_effect = Exception("Down")

        embed = await cog._create_leaderboard_embed(guild, "soloq")

        assert "Mode Hors-Ligne" in embed.title
        assert "CacheUser" in embed.description  # Utilise le cache

    @pytest.mark.asyncio
    async def test_create_lp_recap_embed_content(self, cog):
        """Test le contenu visuel du recap."""
        guild = MagicMock()
        cog._save_user(1, "uid", "Player", "Tag", stats=None)

        # Tracking: 1000 LP. Actuel: 1050 LP. Diff: +50
        cog._save_lp_tracking({"1": {"soloq": {"daily_lp": 1000}}})

        cog.league_service.make_profile.return_value = {"rankedStats": {"soloq": {"tier": "SILVER", "rank": "II", "lp": 50}, "flex": None}}  # 1050 total

        embed = await cog._create_lp_recap_embed(guild, "soloq")

        assert "+50 LP" in embed.description
        assert "📈" in embed.description  # Emoji gain
