import os
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import yaml
from discord.ext import commands

# Import du code source
from src.cogs.setup_lol import SetupLol, setup
from src.lol.exceptions import InvalidApiKey, PlayerNotFound, RateLimited

# ============================================================================
# FIXTURES (CONFIGURATION DES TESTS)
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
    """
    Crée une instance du Cog avec des fichiers de données temporaires.
    """
    # Création de chemins temporaires pour les tests
    db_file = tmp_path / "users.yml"
    config_file = tmp_path / "config.yml"

    # Instanciation du Cog
    c = SetupLol(
        bot, league_service, db_path=str(db_file), config_path=str(config_file), start_tasks=False  # Note : Paramètre présent dans votre __init__
    )

    # Sécurité : on s'assure que la tâche est annulée pour éviter les fuites
    c.refresh_leaderboard.cancel()

    return c


@pytest.fixture
def interaction():
    """Mock complet d'une interaction Slash Command."""
    itr = MagicMock(spec=discord.Interaction)
    itr.guild = MagicMock()
    itr.guild.id = 987654321

    # Mock de l'utilisateur
    itr.user = MagicMock(spec=discord.Member)
    itr.user.id = 123456789
    itr.user.display_name = "TestUser"
    itr.user.display_avatar.url = "http://avatar.url"

    # Mock des réponses (AsyncMock est crucial ici)
    itr.response = MagicMock()
    itr.response.defer = AsyncMock()
    itr.response.send_message = AsyncMock()

    itr.followup = MagicMock()
    itr.followup.send = AsyncMock()

    return itr


# ============================================================================
# TESTS D'INITIALISATION ET GESTION DE FICHIERS
# ============================================================================


class TestInitAndData:
    def test_init_creates_directories(self, bot, league_service, tmp_path):
        """Vérifie que les dossiers sont créés à l'initialisation."""
        db_path = tmp_path / "new_folder" / "users.yml"

        SetupLol(bot, league_service, db_path=str(db_path))

        assert db_path.parent.exists()

    def test_save_and_load_user(self, cog):
        """Test la sauvegarde et le chargement d'un utilisateur."""
        cog._save_user(123, "puuid_abc", "Pseudo", "TAG")

        users = cog._load_users()
        assert "123" in users
        assert users["123"]["pseudo"] == "Pseudo"

    def test_save_config(self, cog):
        """Test la sauvegarde de la configuration leaderboard."""
        cog._save_config(111, 222, 333)

        config = cog._load_config()
        assert "leaderboards" in config
        assert config["leaderboards"]["111"]["channel_id"] == 222


# ============================================================================
# TESTS DES COMMANDES SLASH (/lol_link)
# ============================================================================


class TestLolLink:
    @pytest.mark.asyncio
    async def test_lol_link_success(self, cog, interaction, league_service):
        """Test un lien de compte réussi."""
        league_service.get_puuid.return_value = "puuid_123"

        # APPEL VIA .callback POUR LES SLASH COMMANDS
        await cog.lol_link.callback(cog, interaction, "Joueur#EUW")

        # Vérifications
        league_service.get_puuid.assert_called_once_with("Joueur", "EUW")
        interaction.followup.send.assert_called_once()

        # Vérifier que l'utilisateur est bien sauvegardé
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
        """Test joueur introuvable (Doit envoyer un message d'erreur, pas crasher)."""
        # On configure le service pour qu'il simule un joueur introuvable
        league_service.get_puuid.side_effect = PlayerNotFound()

        # On exécute la commande
        await cog.lol_link.callback(cog, interaction, "Introuvable#EUW")

        # On vérifie qu'au lieu de planter, le bot a envoyé un message à l'utilisateur
        interaction.followup.send.assert_called_once()

        # On récupère le message envoyé pour vérifier son contenu
        args, _ = interaction.followup.send.call_args
        message_envoye = args[0] if args else ""

        # On vérifie que le message contient bien l'avertissement
        assert "Impossible de trouver" in message_envoye
        assert "❌" in message_envoye


# ============================================================================
# TESTS DES COMMANDES SLASH (/lol_stats)
# ============================================================================


class TestLolStats:
    @pytest.mark.asyncio
    async def test_lol_stats_success_self(self, cog, interaction, league_service):
        """Test affichage de ses propres stats."""
        # Préparer les données
        cog._save_user(interaction.user.id, "puuid_123", "Moi", "EUW")

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

    @pytest.mark.asyncio
    async def test_lol_stats_api_error(self, cog, interaction, league_service):
        """Test erreur API (RateLimit)."""
        cog._save_user(interaction.user.id, "puuid_123", "Moi", "EUW")
        league_service.make_profile.side_effect = RateLimited()

        await cog.lol_stats.callback(cog, interaction, member=None)

        interaction.followup.send.assert_called()
        assert "⏳" in interaction.followup.send.call_args[0][0]


# ============================================================================
# TESTS DU LEADERBOARD (/lol_leaderboard_setup)
# ============================================================================


class TestLeaderboardSetup:
    @pytest.mark.asyncio
    async def test_setup_leaderboard(self, cog, interaction):
        """Test la configuration du leaderboard."""
        channel = MagicMock(spec=discord.TextChannel)
        channel.id = 555
        channel.send = AsyncMock()
        channel.send.return_value.id = 999  # Message ID

        await cog.lol_leaderboard_setup.callback(cog, interaction, channel)

        # Vérifie que le message est envoyé
        channel.send.assert_called_once()

        # Vérifie la sauvegarde
        config = cog._load_config()
        assert str(interaction.guild.id) in config["leaderboards"]
        assert config["leaderboards"][str(interaction.guild.id)]["message_id"] == 999


# ============================================================================
# TESTS DE LA TÂCHE DE FOND (REFRESH)
# ============================================================================


class TestRefreshTask:
    @pytest.mark.asyncio
    async def test_refresh_loop(self, cog, bot, league_service):
        """Test complet de la boucle de rafraîchissement."""
        # 1. Setup des données
        guild_id = 1000
        channel_id = 2000
        message_id = 3000

        cog._save_user(123, "puuid_1", "Player1", "EUW")
        cog._save_config(guild_id, channel_id, message_id)

        # 2. Mock du service Riot
        league_service.make_profile.return_value = {"name": "Player1", "tag": "EUW", "level": 50, "rankedStats": {"soloq": None, "flex": None}}

        # 3. Mock Discord (Guild -> Channel -> Message -> Member)
        guild = MagicMock()
        channel = MagicMock()
        message = MagicMock()
        message.edit = AsyncMock()
        member = MagicMock()
        member.display_name = "DiscordUser"

        bot.get_guild.return_value = guild
        guild.get_channel.return_value = channel
        channel.fetch_message = AsyncMock(return_value=message)
        guild.fetch_member = AsyncMock(return_value=member)

        # 4. Exécution manuelle d'un tour de boucle
        await cog.refresh_leaderboard()

        # 5. Vérifications
        bot.get_guild.assert_called_with(guild_id)
        guild.get_channel.assert_called_with(channel_id)
        channel.fetch_message.assert_called_with(message_id)

        # Vérifie que le message a été édité avec un Embed
        message.edit.assert_called_once()
        args, kwargs = message.edit.call_args
        assert isinstance(kwargs["embed"], discord.Embed)


# ============================================================================
# TESTS DE LA FONCTION SETUP (LOAD EXTENSION)
# ============================================================================


@pytest.mark.asyncio
async def test_setup_entry_point(bot):
    """Vérifie que le point d'entrée setup() fonctionne."""
    # Simulation de la variable d'environnement
    with patch.dict(os.environ, {"LOLAPI": "RGAPI-FAKE-KEY"}):
        with patch("src.cogs.setup_lol.RiotApiClient"):
            with patch("src.cogs.setup_lol.LeagueService"):
                await setup(bot)

                # Vérifie que le Cog est ajouté au bot
                bot.add_cog.assert_called_once()
                args = bot.add_cog.call_args[0]
                assert isinstance(args[0], SetupLol)


@pytest.mark.asyncio
async def test_setup_missing_key(bot):
    """Vérifie que setup() échoue sans clé API."""
    with patch.dict(os.environ, {}, clear=True):
        await setup(bot)
        bot.add_cog.assert_not_called()


class TestRankUtils:
    def test_get_rank_emoji(self, cog):
        """Test tous les cas d'emojis"""
        assert cog._get_rank_emoji("CHALLENGER") == "🏆"
        assert cog._get_rank_emoji("IRON") == "⚫"
        assert cog._get_rank_emoji("UNKNOWN_TIER") == "❓"  # Cas par défaut

    def test_get_rank_value_calculation(self, cog):
        """Test le calcul exact du score de rang"""
        # DIAMOND (6000) + II (200) + 50 LP = 6250
        player_data = {"soloq": {"tier": "DIAMOND", "rank": "II", "lp": 50}}
        assert cog._get_rank_value(player_data) == 6250

    def test_get_rank_value_unranked(self, cog):
        """Test valeur pour un joueur sans rang"""
        player_data = {"soloq": None}
        assert cog._get_rank_value(player_data) == -1


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_cog_load_starts_task(self, cog):
        """Vérifie que cog_load démarre la tâche"""
        # On mock la task pour vérifier l'appel
        with patch.object(cog.refresh_leaderboard, "start") as mock_start:
            await cog.cog_load()
            mock_start.assert_called_once()

    def test_cog_unload_stops_task(self, cog):
        """Vérifie que cog_unload arrête la tâche"""
        with patch.object(cog.refresh_leaderboard, "cancel") as mock_cancel:
            cog.cog_unload()
            mock_cancel.assert_called_once()


class TestLinkAccountExceptions:
    @pytest.mark.asyncio
    async def test_link_account_rate_limited(self, cog, interaction, league_service):
        """Test exception RateLimited"""
        league_service.get_puuid.side_effect = RateLimited()

        await cog._link_account(interaction, "Pseudo", "TAG")

        args = interaction.followup.send.call_args[0]
        assert "Trop de requêtes" in args[0]

    @pytest.mark.asyncio
    async def test_link_account_invalid_key(self, cog, interaction, league_service):
        """Test exception InvalidApiKey"""
        league_service.get_puuid.side_effect = InvalidApiKey()

        await cog._link_account(interaction, "Pseudo", "TAG")

        args = interaction.followup.send.call_args[0]
        assert "Clé API invalide" in args[0]

    @pytest.mark.asyncio
    async def test_link_account_generic_error(self, cog, interaction, league_service):
        """Test exception générique"""
        league_service.get_puuid.side_effect = Exception("Boom")

        await cog._link_account(interaction, "Pseudo", "TAG")

        args = interaction.followup.send.call_args[0]
        assert "erreur interne" in args[0]


class TestLeaderboardEdgeCases:
    @pytest.mark.asyncio
    async def test_refresh_leaderboard_guild_not_found(self, cog, bot):
        """Test quand le serveur (Guild) n'existe plus"""
        cog._save_config(999, 123, 456)
        bot.get_guild.return_value = None  # Guild introuvable

        # Ne doit pas planter
        await cog.refresh_leaderboard()
        # Le log warning est géré en interne

    @pytest.mark.asyncio
    async def test_refresh_leaderboard_channel_not_found(self, cog, bot):
        """Test quand le salon n'existe plus"""
        cog._save_config(123, 999, 456)
        mock_guild = MagicMock()
        bot.get_guild.return_value = mock_guild
        mock_guild.get_channel.return_value = None  # Channel introuvable

        await cog.refresh_leaderboard()

    @pytest.mark.asyncio
    async def test_refresh_leaderboard_message_not_found(self, cog, bot):
        """Test quand le message a été supprimé"""
        cog._save_config(123, 456, 999)
        mock_guild = MagicMock()
        mock_channel = MagicMock()
        bot.get_guild.return_value = mock_guild
        mock_guild.get_channel.return_value = mock_channel
        # Message introuvable
        mock_channel.fetch_message.side_effect = discord.NotFound(MagicMock(), MagicMock())

        await cog.refresh_leaderboard()

    @pytest.mark.asyncio
    async def test_create_embed_with_error_user(self, cog):
        """Test quand un utilisateur fait planter l'API"""
        # 1 valide, 1 erreur
        cog._save_user(1, "p1", "Valid", "EUW")
        cog._save_user(2, "p2", "Error", "EUW")

        mock_guild = MagicMock()
        mock_guild.get_member.return_value = MagicMock(display_name="User")

        # Le premier passe, le second lève une erreur
        cog.league_service.make_profile.side_effect = [
            {
                "name": "Valid",
                "tag": "EUW",
                "level": 30,
                "rankedStats": {"soloq": {"tier": "GOLD", "rank": "I", "lp": 10, "wins": 10, "losses": 10, "winrate": 50.0}, "flex": None},
            },
            Exception("API Error"),
        ]

        embed = await cog._create_leaderboard_embed(mock_guild)

        # CORRECTION : Le nouveau format affiche "**Valid**" (nom gras sans tag)
        assert "**Valid**" in embed.description
        # On vérifie que le joueur en erreur n'est pas là
        assert "Error" not in embed.description


class TestPersistenceEdgeCases:
    def test_save_user_appends_existing_file(self, cog):
        """Vérifie qu'on ajoute à un fichier existant sans l'écraser"""
        # Créer un fichier initial
        initial_data = {"111": {"pseudo": "Old"}}
        with open(cog.db_path, "w") as f:
            yaml.dump(initial_data, f)

        # Sauvegarder un nouveau user
        cog._save_user(222, "p2", "New", "TAG")

        # Vérifier que les deux existent
        with open(cog.db_path, "r") as f:
            data = yaml.safe_load(f)

        assert data["111"]["pseudo"] == "Old"
        assert data["222"]["pseudo"] == "New"

    def test_load_config_no_file(self, cog):
        """Vérifie le retour vide si pas de fichier config"""
        if os.path.exists(cog.config_path):
            os.remove(cog.config_path)
        assert cog._load_config() == {}


class TestLolStatsExceptions:
    @pytest.mark.asyncio
    async def test_lol_stats_player_not_found(self, cog, interaction, league_service):
        """Test PlayerNotFound dans lol_stats"""
        cog._save_user(interaction.user.id, "pid", "Name", "Tag")
        league_service.make_profile.side_effect = PlayerNotFound()

        await cog.lol_stats.callback(cog, interaction, member=None)

        args = interaction.followup.send.call_args[0]
        assert "Impossible de trouver" in args[0]

    @pytest.mark.asyncio
    async def test_lol_stats_rate_limited(self, cog, interaction, league_service):
        """Test RateLimited dans lol_stats"""
        cog._save_user(interaction.user.id, "pid", "Name", "Tag")
        league_service.make_profile.side_effect = RateLimited()

        await cog.lol_stats.callback(cog, interaction, member=None)

        args = interaction.followup.send.call_args[0]
        assert "Trop de requêtes" in args[0]

    @pytest.mark.asyncio
    async def test_lol_stats_generic_error(self, cog, interaction, league_service):
        """Test erreur générique dans lol_stats"""
        cog._save_user(interaction.user.id, "pid", "Name", "Tag")
        league_service.make_profile.side_effect = Exception("Crash")

        await cog.lol_stats.callback(cog, interaction, member=None)

        args = interaction.followup.send.call_args[0]
        assert "Une erreur est survenue" in args[0]


# --- Tests pour couvrir les lignes manquantes (100% Coverage) ---


class TestCoverageGaps:

    # Couvre les lignes 79-80 : _load_config avec fichier existant
    def test_load_config_file_exists(self, cog):
        # On écrit d'abord un fichier
        config_data = {"test": 123}
        with open(cog.config_path, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f)

        # On recharge
        loaded = cog._load_config()
        assert loaded["test"] == 123

    # Couvre la ligne 161 : lol_stats sur un autre membre non lié
    @pytest.mark.asyncio
    async def test_lol_stats_other_not_linked(self, cog, interaction):
        other_member = MagicMock(spec=discord.Member)
        other_member.id = 999
        other_member.mention = "<@999>"

        # Pas d'entrée dans la DB pour 999
        await cog.lol_stats.callback(cog, interaction, member=other_member)

        # Vérifie le message spécifique "n'a pas lié son compte"
        interaction.followup.send.assert_called_once()
        msg = interaction.followup.send.call_args[0][0]
        assert other_member.mention in msg

    # Couvre les lignes 188-193 et 202-206 : Affichage complet des rangs
    @pytest.mark.asyncio
    async def test_lol_stats_full_ranks(self, cog, interaction, league_service):
        cog._save_user(interaction.user.id, "pid", "Name", "Tag")

        # Données complètes SoloQ + Flex
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

        # Vérifie que le texte formaté est présent
        fields = {f.name: f.value for f in embed.fields}
        assert "Gold I" in fields["🏆 Solo/Duo"]
        assert "Silver II" in fields["👥 Flex 5v5"]

    # Couvre la ligne 225 : Erreur InvalidApiKey
    @pytest.mark.asyncio
    async def test_lol_stats_invalid_key(self, cog, interaction, league_service):
        cog._save_user(interaction.user.id, "pid", "Name", "Tag")
        league_service.make_profile.side_effect = InvalidApiKey()

        await cog.lol_stats.callback(cog, interaction, member=None)

        interaction.followup.send.assert_called()
        # CORRECTION : "clé" en minuscule pour correspondre exactement au message du bot
        assert "clé API" in interaction.followup.send.call_args[0][0]

    # Couvre les lignes 252-254 : Erreur dans setup leaderboard
    @pytest.mark.asyncio
    async def test_leaderboard_setup_crash(self, cog, interaction):
        # Simule une erreur (ex: échec d'envoi du message)
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock(side_effect=Exception("Boom"))

        await cog.lol_leaderboard_setup.callback(cog, interaction, mock_channel)

        interaction.followup.send.assert_called()
        assert "Erreur lors de la création" in interaction.followup.send.call_args[0][0]

    # Couvre la ligne 267 : refresh sans la clé 'leaderboards'
    @pytest.mark.asyncio
    async def test_refresh_no_key(self, cog):
        # Fichier config vide mais existant (sans la clé 'leaderboards')
        with open(cog.config_path, "w") as f:
            yaml.dump({"autre_chose": 1}, f)

        await cog.refresh_leaderboard()
        # Ne doit pas planter, return silent

    # Couvre les lignes 294-295 : Exception dans la boucle de refresh
    @pytest.mark.asyncio
    async def test_refresh_exception_in_loop(self, cog, bot):
        # Config valide
        cog._save_config(123, 456, 789)
        # Mais le bot lève une erreur inattendue
        bot.get_guild.side_effect = Exception("Crash Loop")

        await cog.refresh_leaderboard()
        # Le log exception doit être appelé, mais pas de crash

    # Couvre les lignes 345-351 : Embed leaderboard vide (tous les joueurs en erreur)
    @pytest.mark.asyncio
    async def test_create_embed_all_errors(self, cog):
        """Test quand aucun joueur n'est récupérable"""
        cog._save_user(1, "p1", "Name", "Tag")

        mock_guild = MagicMock()
        cog.league_service.make_profile.side_effect = Exception("API Down")

        embed = await cog._create_leaderboard_embed(mock_guild)

        # Le code retourne un embed spécifique si vide
        assert "Aucun joueur" in embed.description or "Impossible" in embed.description

    def test_save_config_preserves_existing_data(self, cog):
        """Vérifie que _save_config lit le fichier existant (Lignes 79-80)"""
        # 1. On crée d'abord un fichier config existant avec des données
        existing_data = {"leaderboards": {"999": {"channel_id": 111, "message_id": 222}}, "autre_parametre": "test"}
        with open(cog.config_path, "w", encoding="utf-8") as f:
            yaml.dump(existing_data, f)

        # 2. On appelle _save_config pour ajouter une nouvelle guild
        cog._save_config(guild_id=123, channel_id=456, message_id=789)

        # 3. On vérifie que les anciennes données sont toujours là (fusion)
        config = cog._load_config()

        # La nouvelle donnée est là
        assert config["leaderboards"]["123"]["channel_id"] == 456
        # L'ancienne donnée est préservée
        assert config["leaderboards"]["999"]["channel_id"] == 111
        # Les autres paramètres aussi
        assert config["autre_parametre"] == "test"

    def test_save_config_handles_empty_file(self, cog):
        """Vérifie le cas 'or {}' à la ligne 80 si le fichier est vide"""
        # Créer un fichier vide (0 octets)
        with open(cog.config_path, "w", encoding="utf-8"):
            pass

        # La méthode ne doit pas planter et doit initialiser le dict
        cog._save_config(123, 456, 789)

        config = cog._load_config()
        assert config["leaderboards"]["123"]["message_id"] == 789

    # 1. Test de sécurité : Commande lancée en DM (Ligne 242)
    @pytest.mark.asyncio
    async def test_leaderboard_setup_dm(self, cog, interaction):
        """Vérifie que la commande est bloquée si pas de guilde."""
        interaction.guild = None  # Simule un Message Privé

        await cog.lol_leaderboard_setup.callback(cog, interaction, MagicMock())

        interaction.response.send_message.assert_called_with("❌ Cette commande doit être utilisée sur un serveur.", ephemeral=True)

    # 2. Test technique : Attente du bot ready (Ligne 310)
    @pytest.mark.asyncio
    async def test_before_refresh_leaderboard(self, cog, bot):
        """Vérifie que la tâche attend que le bot soit prêt."""
        await cog.before_refresh_leaderboard()
        bot.wait_until_ready.assert_called_once()

    # 3. Test logique : Membre parti du serveur (Ligne 328)
    @pytest.mark.asyncio
    async def test_create_embed_member_left(self, cog):
        """Vérifie qu'on ignore un joueur s'il a quitté le Discord."""
        cog._save_user(123, "puuid", "Parti", "Tag")

        mock_guild = MagicMock()
        # get_member renvoie None = le membre n'est plus là
        mock_guild.get_member.return_value = None

        embed = await cog._create_leaderboard_embed(mock_guild)

        # Le pseudo ne doit PAS apparaître dans le tableau
        assert "Parti" not in embed.description

    # 4. Test formatage : Rang Apex / Master+ (Ligne 338)
    @pytest.mark.asyncio
    async def test_create_embed_apex_tier(self, cog):
        """Vérifie l'affichage compact pour Master (M), GM, Chall."""
        cog._save_user(123, "puuid", "Pro", "Tag")

        mock_guild = MagicMock()
        mock_guild.get_member.return_value = MagicMock(display_name="User")

        # Simulation d'un joueur Master
        cog.league_service.make_profile.return_value = {
            "name": "Pro",
            "tag": "Tag",
            "level": 999,
            "rankedStats": {"soloq": {"tier": "MASTER", "rank": "I", "lp": 800, "wins": 100, "losses": 50, "winrate": 66.6}, "flex": None},
        }

        embed = await cog._create_leaderboard_embed(mock_guild)

        # VERIFICATION FORMAT COMPACT :
        # On cherche "M" (Master raccourci) et "800LP" (collé)
        assert "M " in embed.description
        assert "800LP" in embed.description

    @pytest.mark.asyncio
    async def test_create_embed_specific_short_tiers(self, cog):
        """Couvre les abréviations spécifiques : PLAT, EMER, DIAM."""
        # On enregistre 3 utilisateurs
        cog._save_user(1, "p1", "PlatUser", "TAG")
        cog._save_user(2, "p2", "EmerUser", "TAG")
        cog._save_user(3, "p3", "DiamUser", "TAG")

        mock_guild = MagicMock()
        # On simule que les membres sont présents sur le discord
        mock_guild.get_member.return_value = MagicMock(display_name="User")

        # On simule les réponses de l'API Riot pour chaque utilisateur
        cog.league_service.make_profile.side_effect = [
            {
                "name": "P1",
                "tag": "Tag",
                "level": 100,
                "rankedStats": {"soloq": {"tier": "PLATINUM", "rank": "IV", "lp": 10, "wins": 0, "losses": 0, "winrate": 50}, "flex": None},
            },
            {
                "name": "P2",
                "tag": "Tag",
                "level": 100,
                "rankedStats": {"soloq": {"tier": "EMERALD", "rank": "IV", "lp": 10, "wins": 0, "losses": 0, "winrate": 50}, "flex": None},
            },
            {
                "name": "P3",
                "tag": "Tag",
                "level": 100,
                "rankedStats": {"soloq": {"tier": "DIAMOND", "rank": "IV", "lp": 10, "wins": 0, "losses": 0, "winrate": 50}, "flex": None},
            },
        ]

        embed = await cog._create_leaderboard_embed(mock_guild)

        # On vérifie que les abréviations sont bien dans la description
        assert "PLAT" in embed.description
        assert "EMER" in embed.description
        assert "DIAM" in embed.description

    @pytest.mark.asyncio
    async def test_create_embed_long_name_truncation(self, cog):
        """Couvre la troncature des noms trop longs (>10 chars)."""
        # Un pseudo très long (18 caractères)
        long_name = "VeryLongNameIndeed"
        cog._save_user(1, "puuid", long_name, "TAG")

        mock_guild = MagicMock()
        mock_guild.get_member.return_value = MagicMock(display_name="User")

        cog.league_service.make_profile.return_value = {
            "name": long_name,
            "tag": "Tag",
            "level": 100,
            "rankedStats": {"soloq": {"tier": "GOLD", "rank": "IV", "lp": 10, "wins": 0, "losses": 0, "winrate": 50}, "flex": None},
        }

        embed = await cog._create_leaderboard_embed(mock_guild)

        # Le code coupe à 9 caractères + "…"
        # "VeryLongNameIndeed" -> "VeryLongN…"
        expected_name = "VeryLongN…"

        assert expected_name in embed.description
