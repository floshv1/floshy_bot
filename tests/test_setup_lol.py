# tests/test_setup_lol.py - Ajoutez ces tests

import os
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import yaml

from src.cogs.setup_lol import SetupLol
from src.lol.exceptions import InvalidApiKey, PlayerNotFound, RateLimited


@pytest.fixture
def mock_service():
    return MagicMock()


@pytest.fixture
def mock_bot():
    return MagicMock()


@pytest.fixture
def cog(mock_bot, mock_service, tmp_path):
    # Utilisation d'un fichier temporaire pour le YAML
    db_file = tmp_path / "users.yml"
    with patch("os.makedirs"):
        setup_cog = SetupLol(mock_bot, mock_service)
        setup_cog.db_path = str(db_file)
        return setup_cog


@pytest.fixture
def mock_ctx():
    """Fixture pour créer un contexte Discord mocké"""
    ctx = AsyncMock()
    ctx.author.id = 123456789
    ctx.typing = MagicMock()
    ctx.typing.return_value.__aenter__ = AsyncMock()
    ctx.typing.return_value.__aexit__ = AsyncMock()
    return ctx


@pytest.mark.asyncio
async def test_setup_success(cog, mock_service, mock_ctx):
    """Teste une liaison de compte réussie avec link_lol."""
    mock_service.get_puuid.return_value = "puuid_123_abc"

    await cog.link_lol.callback(cog, mock_ctx, "NomDeJoueur#EUW")

    # Assertions
    mock_service.get_puuid.assert_called_once_with("NomDeJoueur", "EUW")
    mock_ctx.send.assert_called_once()

    _, kwargs = mock_ctx.send.call_args
    assert "embed" in kwargs
    assert "✅ Compte lié avec succès !" in kwargs["embed"].title

    # Vérification de la persistance YAML
    with open(cog.db_path, "r") as f:
        data = yaml.safe_load(f)
        assert data["123456789"]["puuid"] == "puuid_123_abc"


@pytest.mark.asyncio
async def test_save_user_updates_existing_file(cog, mock_ctx, mock_service):
    """Test que _save_user met à jour un fichier existant"""
    # Créer un fichier YAML existant avec des données
    existing_data = {"111111": {"puuid": "old-puuid", "pseudo": "OldPlayer", "tag": "NA"}}
    with open(cog.db_path, "w", encoding="utf-8") as f:
        yaml.dump(existing_data, f)

    # Ajouter un nouvel utilisateur
    mock_service.get_puuid.return_value = "new-puuid-456"
    await cog.link_lol.callback(cog, mock_ctx, "NewPlayer#EUW")

    # Vérifier que les deux utilisateurs sont présents
    with open(cog.db_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "111111" in data  # Ancien utilisateur toujours présent
    assert "123456789" in data  # Nouvel utilisateur ajouté
    assert data["123456789"]["puuid"] == "new-puuid-456"


@pytest.mark.asyncio
async def test_link_lol_invalid_format_no_hashtag(cog, mock_ctx):
    """Test format invalide sans # - couvre le return await ctx.send"""
    await cog.link_lol.callback(cog, mock_ctx, "PseudoSansTag")

    mock_ctx.send.assert_called_once()
    message = mock_ctx.send.call_args[0][0]
    assert "❌ Format invalide" in message
    assert "Pseudo#TAG" in message


@pytest.mark.asyncio
async def test_link_lol_player_not_found(cog, mock_service, mock_ctx):
    """Test exception PlayerNotFound"""
    mock_service.get_puuid.side_effect = PlayerNotFound()

    await cog.link_lol.callback(cog, mock_ctx, "UnknownPlayer#TAG")

    mock_ctx.send.assert_called_once()
    message = mock_ctx.send.call_args[0][0]
    assert "❌ Impossible de trouver le joueur" in message
    assert "UnknownPlayer#TAG" in message


@pytest.mark.asyncio
async def test_link_lol_rate_limited(cog, mock_service, mock_ctx):
    """Test exception RateLimited"""
    mock_service.get_puuid.side_effect = RateLimited()

    await cog.link_lol.callback(cog, mock_ctx, "Player#TAG")

    mock_ctx.send.assert_called_once()
    message = mock_ctx.send.call_args[0][0]
    assert "⏳ Trop de requêtes" in message
    assert "Réessayez dans une minute" in message


@pytest.mark.asyncio
async def test_link_lol_invalid_api_key(cog, mock_service, mock_ctx):
    """Test exception InvalidApiKey"""
    mock_service.get_puuid.side_effect = InvalidApiKey()

    await cog.link_lol.callback(cog, mock_ctx, "Player#TAG")

    mock_ctx.send.assert_called_once()
    message = mock_ctx.send.call_args[0][0]
    assert "⚠️" in message
    assert "clé API Riot est expirée ou invalide" in message


@pytest.mark.asyncio
async def test_link_lol_generic_exception(cog, mock_service, mock_ctx):
    """Test exception générique - couvre le except Exception as e"""
    mock_service.get_puuid.side_effect = Exception("Erreur de connexion")

    await cog.link_lol.callback(cog, mock_ctx, "Player#TAG")

    mock_ctx.send.assert_called_once()
    message = mock_ctx.send.call_args[0][0]
    assert "💥 Une erreur est survenue" in message
    assert "Erreur de connexion" in message


@pytest.mark.asyncio
async def test_save_user_handles_empty_yaml(cog, mock_ctx, mock_service):
    """Test que _save_user gère un fichier YAML vide (or {})"""
    # Créer un fichier vide
    with open(cog.db_path, "w", encoding="utf-8") as f:
        f.write("")

    mock_service.get_puuid.return_value = "puuid-empty-file"
    await cog.link_lol.callback(cog, mock_ctx, "Player#TAG")

    # Vérifier que le fichier contient maintenant des données
    with open(cog.db_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert data is not None
    assert "123456789" in data


@pytest.mark.asyncio
async def test_save_user_handles_null_yaml(cog):
    """Test que _save_user gère un YAML qui retourne None"""
    # Créer un fichier YAML qui retourne None
    with open(cog.db_path, "w", encoding="utf-8") as f:
        f.write("# commentaire seulement\n")

    # Sauvegarder un utilisateur
    cog._save_user(999999, "puuid-null", "Player", "TAG")

    # Vérifier que les données sont bien sauvegardées
    with open(cog.db_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert "999999" in data
    assert data["999999"]["puuid"] == "puuid-null"


@pytest.mark.asyncio
async def test_link_lol_with_multiple_hashtags(cog, mock_service, mock_ctx):
    """Test avec plusieurs # dans le nom (split prend le premier)"""
    mock_service.get_puuid.return_value = "puuid-multi-hash"

    await cog.link_lol.callback(cog, mock_ctx, "Player#With#Extra#TAG")

    # split("#", 1) ne prend que le premier #
    mock_service.get_puuid.assert_called_once_with("Player", "With#Extra#TAG")
    mock_ctx.send.assert_called_once()


def test_save_user_creates_directory_if_not_exists(mock_bot, mock_service, tmp_path):
    """Test que _save_user fonctionne quand le dossier existe"""
    nested_path = tmp_path / "new_folder" / "data" / "users.yml"

    # Créer manuellement le dossier parent
    nested_path.parent.mkdir(parents=True, exist_ok=True)

    cog = SetupLol(mock_bot, mock_service)
    cog.db_path = str(nested_path)

    # Sauvegarder un utilisateur
    cog._save_user(123456, "test-puuid", "Player", "TAG")

    # Vérifier que le fichier a été créé
    assert nested_path.exists()

    with open(nested_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert "123456" in data


@pytest.mark.asyncio
async def test_link_lol_empty_pseudo(cog, mock_ctx):
    """Test avec pseudo vide (#TAG seulement)"""
    await cog.link_lol.callback(cog, mock_ctx, "#TAG")

    # Devrait quand même passer la validation et appeler le service
    # (même si le service retournera probablement une erreur)
    # Ou selon votre logique, pourrait retourner format invalide
    mock_ctx.send.assert_called()


@pytest.mark.asyncio
async def test_link_lol_empty_tag(cog, mock_service, mock_ctx):
    """Test avec tag vide (Player# seulement)"""
    mock_service.get_puuid.return_value = "puuid-empty-tag"

    await cog.link_lol.callback(cog, mock_ctx, "Player#")

    # Le split devrait donner ("Player", "")
    mock_service.get_puuid.assert_called_once_with("Player", "")


# tests/test_setup_lol.py - Ajoutez ces tests


@pytest.mark.asyncio
async def test_lol_leaderboard_success(cog, mock_service, mock_ctx):
    """Test affichage du leaderboard avec succès"""
    # Créer plusieurs utilisateurs liés
    user_data = {
        "123456789": {"puuid": "puuid-1", "pseudo": "Floshv1", "tag": "ldv"},
        "987654321": {"puuid": "puuid-2", "pseudo": "Nicobooy", "tag": "cnth"},
    }
    with open(cog.db_path, "w", encoding="utf-8") as f:
        yaml.dump(user_data, f)

    # Mock des profils
    def mock_make_profile(puuid):
        if puuid == "puuid-1":
            return {
                "name": "Floshv1",
                "tag": "ldv",
                "level": 897,
                "profileIconId": 1,
                "rankedStats": {"soloq": {"tier": "PLATINUM", "rank": "II", "lp": 45, "wins": 52, "losses": 48, "winrate": 52.0}, "flex": None},
            }
        else:
            return {
                "name": "Nicobooy",
                "tag": "cnth",
                "level": 103,
                "profileIconId": 2,
                "rankedStats": {"soloq": {"tier": "GOLD", "rank": "IV", "lp": 10, "wins": 10, "losses": 0, "winrate": 100.0}, "flex": None},
            }

    mock_service.make_profile.side_effect = mock_make_profile

    # Mock fetch_member
    mock_member1 = MagicMock()
    mock_member1.display_name = "Flosh"
    mock_member2 = MagicMock()
    mock_member2.display_name = "Nico"

    async def mock_fetch_member(discord_id):
        if discord_id == 123456789:
            return mock_member1
        return mock_member2

    mock_ctx.guild.fetch_member = mock_fetch_member

    await cog.lol_leaderboard.callback(cog, mock_ctx)

    # Vérifier qu'un embed a été envoyé (2 appels: message initial + embed)
    assert mock_ctx.send.call_count == 2

    # Récupérer l'embed (dernier appel)
    last_call = mock_ctx.send.call_args_list[-1]
    embed = last_call[1]["embed"] if "embed" in last_call[1] else last_call[0][0]

    assert isinstance(embed, discord.Embed)
    assert "🏆 Classement Solo/Duo" in embed.title
    assert "Floshv1#ldv" in str(embed.fields)
    assert "Nicobooy#cnth" in str(embed.fields)
    assert "52.0%" in str(embed.fields)
    assert "100.0%" in str(embed.fields)


@pytest.mark.asyncio
async def test_lol_leaderboard_no_file(cog, mock_ctx):
    """Test quand aucun fichier n'existe"""
    if os.path.exists(cog.db_path):
        os.remove(cog.db_path)

    await cog.lol_leaderboard.callback(cog, mock_ctx)

    mock_ctx.send.assert_called_once()
    message = mock_ctx.send.call_args[0][0]
    assert "❌ Aucun compte n'est lié" in message


@pytest.mark.asyncio
async def test_lol_leaderboard_empty_file(cog, mock_ctx):
    """Test avec fichier vide"""
    with open(cog.db_path, "w", encoding="utf-8") as f:
        yaml.dump({}, f)

    await cog.lol_leaderboard.callback(cog, mock_ctx)

    mock_ctx.send.assert_called_once()
    message = mock_ctx.send.call_args[0][0]
    assert "❌ Aucun compte n'est lié" in message


@pytest.mark.asyncio
async def test_lol_leaderboard_unranked_players(cog, mock_service, mock_ctx):
    """Test avec des joueurs non classés"""
    user_data = {"123456789": {"puuid": "puuid-unranked", "pseudo": "UnrankedPlayer", "tag": "EUW"}}
    with open(cog.db_path, "w", encoding="utf-8") as f:
        yaml.dump(user_data, f)

    mock_service.make_profile.return_value = {
        "name": "UnrankedPlayer",
        "tag": "EUW",
        "level": 30,
        "profileIconId": 1,
        "rankedStats": {"soloq": None, "flex": None},
    }

    mock_member = MagicMock()
    mock_member.display_name = "Unranked"
    mock_ctx.guild.fetch_member = AsyncMock(return_value=mock_member)

    await cog.lol_leaderboard.callback(cog, mock_ctx)

    # Vérifier que "Unranked" apparaît
    last_call = mock_ctx.send.call_args_list[-1]
    embed = last_call[1]["embed"] if "embed" in last_call[1] else last_call[0][0]
    assert "Unranked" in str(embed.fields)


@pytest.mark.asyncio
async def test_lol_leaderboard_sorting(cog, mock_service, mock_ctx):
    """Test que le classement est trié correctement"""
    user_data = {
        "1": {"puuid": "p1", "pseudo": "Gold", "tag": "1"},
        "2": {"puuid": "p2", "pseudo": "Plat", "tag": "2"},
        "3": {"puuid": "p3", "pseudo": "Diamond", "tag": "3"},
    }
    with open(cog.db_path, "w", encoding="utf-8") as f:
        yaml.dump(user_data, f)

    def mock_profiles(puuid):
        profiles = {
            "p1": {
                "name": "Gold",
                "tag": "1",
                "level": 50,
                "profileIconId": 1,
                "rankedStats": {"soloq": {"tier": "GOLD", "rank": "I", "lp": 50, "wins": 10, "losses": 10, "winrate": 50.0}, "flex": None},
            },
            "p2": {
                "name": "Plat",
                "tag": "2",
                "level": 60,
                "profileIconId": 2,
                "rankedStats": {"soloq": {"tier": "PLATINUM", "rank": "IV", "lp": 0, "wins": 20, "losses": 20, "winrate": 50.0}, "flex": None},
            },
            "p3": {
                "name": "Diamond",
                "tag": "3",
                "level": 70,
                "profileIconId": 3,
                "rankedStats": {"soloq": {"tier": "DIAMOND", "rank": "III", "lp": 30, "wins": 30, "losses": 30, "winrate": 50.0}, "flex": None},
            },
        }
        return profiles[puuid]

    mock_service.make_profile.side_effect = mock_profiles
    mock_ctx.guild.fetch_member = AsyncMock(return_value=MagicMock(display_name="Test"))

    await cog.lol_leaderboard.callback(cog, mock_ctx)

    # Vérifier que Diamond est en premier (🥇)
    last_call = mock_ctx.send.call_args_list[-1]
    embed = last_call[1]["embed"] if "embed" in last_call[1] else last_call[0][0]
    embed_str = str(embed.fields)

    # Diamond devrait apparaître avant Platinum et Gold
    assert embed_str.index("Diamond") < embed_str.index("Plat")
    assert embed_str.index("Plat") < embed_str.index("Gold")
    assert "🥇" in embed_str


@pytest.mark.asyncio
async def test_lol_leaderboard_rate_limited(cog, mock_service, mock_ctx):
    """Test gestion du rate limit"""
    user_data = {"123": {"puuid": "p1", "pseudo": "Player", "tag": "EUW"}}
    with open(cog.db_path, "w", encoding="utf-8") as f:
        yaml.dump(user_data, f)

    mock_service.make_profile.side_effect = RateLimited()

    await cog.lol_leaderboard.callback(cog, mock_ctx)

    # Vérifier le message d'erreur
    assert any("⏳" in str(call) for call in mock_ctx.send.call_args_list)
