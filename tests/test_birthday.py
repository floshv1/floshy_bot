import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import yaml

from src.cogs.birthday import Birthday

# --- FIXTURES (Configuration) ---


@pytest.fixture
def temp_paths(tmp_path):
    """Crée des chemins temporaires pour ne pas casser vos vrais fichiers data."""
    db_path = tmp_path / "birthdays_test.yml"
    config_path = tmp_path / "birthday_config_test.yml"
    return str(db_path), str(config_path)


@pytest.fixture
def mock_bot():
    """Simule le bot Discord."""
    bot = MagicMock()
    bot.add_cog = AsyncMock()
    bot.wait_until_ready = AsyncMock()
    return bot


@pytest.fixture
def mock_channel():
    """Simule un salon Textuel."""
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = 111
    channel.send = AsyncMock()
    channel.fetch_message = AsyncMock()

    mock_msg = MagicMock()
    mock_msg.id = 999
    mock_msg.edit = AsyncMock()

    channel.send.return_value = mock_msg
    channel.fetch_message.return_value = mock_msg

    return channel


@pytest.fixture
def mock_guild(mock_channel):
    """Simule le serveur (Guild)."""
    guild = MagicMock()
    guild.id = 987654
    guild.default_role = MagicMock()

    guild.create_text_channel = AsyncMock(return_value=mock_channel)
    guild.get_channel.return_value = mock_channel

    return guild


@pytest.fixture
def mock_interaction(mock_guild):
    """Simule une interaction Discord."""
    interaction = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.followup.send = AsyncMock()

    interaction.user.id = 123456
    interaction.user.name = "TestUser"
    interaction.guild = mock_guild

    return interaction


@pytest.fixture
def birthday_cog(mock_bot, temp_paths):
    """Instancie le Cog."""
    db, config = temp_paths
    cog = Birthday(mock_bot, db_path=db, config_path=config)
    cog.reminder_task.cancel()
    return cog


# --- TESTS CORRIGÉS ---


@pytest.mark.asyncio
async def test_set_my_birthday_valid(birthday_cog, mock_interaction):
    """Test l'ajout d'un anniversaire valide."""
    # CORRECTION : Utilisation de .callback(self, ...)
    await birthday_cog.set_my_birthday.callback(birthday_cog, mock_interaction, 15, 5, 2000)

    assert os.path.exists(birthday_cog.db_path)

    with open(birthday_cog.db_path, "r") as f:
        data = yaml.safe_load(f)

    assert data["123456"]["jour"] == 15
    assert data["123456"]["mois"] == 5
    assert data["123456"]["annee"] == 2000

    mock_interaction.response.send_message.assert_called_once()
    assert "✅" in mock_interaction.response.send_message.call_args[0][0]


@pytest.mark.asyncio
async def test_set_my_birthday_invalid_date(birthday_cog, mock_interaction):
    """Test le rejet d'une date invalide."""
    # CORRECTION : Utilisation de .callback(self, ...)
    await birthday_cog.set_my_birthday.callback(birthday_cog, mock_interaction, 30, 2, 2000)

    assert not os.path.exists(birthday_cog.db_path)
    mock_interaction.response.send_message.assert_called_with("❌ Date invalide.", ephemeral=True)


@pytest.mark.asyncio
async def test_birthday_delete(birthday_cog, mock_interaction):
    """Test la suppression d'un anniversaire."""
    # Setup
    data = {"123456": {"jour": 1, "mois": 1, "annee": 2000, "username": "TestUser"}}
    with open(birthday_cog.db_path, "w") as f:
        yaml.dump(data, f)

    # CORRECTION : Utilisation de .callback(self, ...)
    await birthday_cog.birthday_delete.callback(birthday_cog, mock_interaction)

    # Vérification
    with open(birthday_cog.db_path, "r") as f:
        new_data = yaml.safe_load(f)

    assert "123456" not in new_data
    assert "🗑️" in mock_interaction.response.send_message.call_args[0][0]


@pytest.mark.asyncio
async def test_generate_embeds(birthday_cog):
    """Vérifie la génération des embeds (Fonction interne, pas besoin de .callback)."""
    data = {
        "1": {"jour": 1, "mois": 1, "annee": 2000, "username": "UserJanvier"},
    }
    with open(birthday_cog.db_path, "w") as f:
        yaml.dump(data, f)

    # Test Global
    embed_global = await birthday_cog._generate_global_embed()
    assert embed_global.title == "🎉 Anniversaires à venir"

    # Test Mois (avec Mock date)
    with patch("src.cogs.birthday.datetime") as mock_date:
        fixed_date = datetime(2024, 1, 10)
        mock_date.now.return_value = fixed_date
        mock_date.now.side_effect = lambda tz=None: fixed_date

        embed_month = await birthday_cog._generate_month_embed()

        assert "Janvier" in embed_month.title
        assert len(embed_month.fields) == 1
        assert "UserJanvier" in embed_month.fields[0].name


@pytest.mark.asyncio
async def test_setup_birthday(birthday_cog, mock_interaction, mock_guild, mock_channel):
    """Test complet de la commande setup."""

    # --- FIX IMPORTANT ---
    # On connecte le bot au serveur simulé pour que _refresh_displays travaille sur le bon objet
    birthday_cog.bot.get_guild.return_value = mock_guild
    # ---------------------

    with patch("discord.utils.get", return_value=None):

        await birthday_cog.setup_birthday.callback(birthday_cog, mock_interaction)

        mock_guild.create_text_channel.assert_called_once()
        assert mock_channel.send.call_count == 2

        with open(birthday_cog.config_path, "r") as f:
            config = yaml.safe_load(f)

        assert str(mock_guild.id) in config
        assert config[str(mock_guild.id)]["channel_id"] == 111

        mock_guild.get_channel.assert_called()
        assert mock_channel.fetch_message.call_count >= 2


@pytest.mark.asyncio
async def test_yaml_errors(birthday_cog):
    """Vérifie la robustesse si le YAML est corrompu ou illisible."""
    # Simulation d'une erreur de lecture
    with patch("builtins.open", side_effect=OSError("Disque plein")):
        data = birthday_cog._load_data("fake_path.yml")
        assert data == {}  # Doit retourner dict vide, pas crasher

    # Simulation d'une erreur d'écriture
    with patch("builtins.open", side_effect=OSError("Permission denied")):
        # Ne doit pas lever d'exception
        birthday_cog._save_data("fake_path.yml", {"test": 1})


@pytest.mark.asyncio
async def test_refresh_displays_edge_cases(birthday_cog, mock_channel):
    """Teste les cas tordus du rafraîchissement."""
    guild_id = 123

    # Setup de la config
    config = {str(guild_id): {"channel_id": 111, "msg_global_id": 999, "msg_month_id": 888}}
    with open(birthday_cog.config_path, "w") as f:
        yaml.dump(config, f)

    # Cas 1 : La guilde n'existe plus (bot kické)
    birthday_cog.bot.get_guild.return_value = None
    await birthday_cog._refresh_displays(guild_id)
    # Ça ne doit pas crasher

    # Cas 2 : Le salon n'est pas un TextChannel (ex: transformé en vocal)
    mock_guild = MagicMock()
    # On crée un salon qui N'EST PAS TextChannel
    voice_channel = MagicMock(spec=discord.VoiceChannel)
    mock_guild.get_channel.return_value = voice_channel
    birthday_cog.bot.get_guild.return_value = mock_guild

    await birthday_cog._refresh_displays(guild_id)
    # Le code doit s'arrêter à "if not isinstance(..., TextChannel)"
    # On vérifie que fetch_message n'est JAMAIS appelé
    voice_channel.fetch_message.assert_not_called()

    # Cas 3 : Les messages ont été supprimés manuellement
    # On remet un bon salon textuel
    mock_guild.get_channel.return_value = mock_channel
    # On simule une erreur 404 Not Found sur le fetch_message
    mock_channel.fetch_message.side_effect = discord.NotFound(MagicMock(), "Msg deleted")

    await birthday_cog._refresh_displays(guild_id)
    # Doit logger un warning mais pas crasher


@pytest.mark.asyncio
async def test_reminder_task_logic(birthday_cog, mock_guild, mock_channel):
    """
    Simule l'exécution de la tâche à minuit pile.
    Vérifie qu'elle envoie bien 'Joyeux Anniversaire'.
    """
    # 1. Setup des données : Un utilisateur a son anniv le 10 Janvier
    data = {"123": {"jour": 10, "mois": 1, "annee": 2000, "username": "BirthdayBoy"}}
    with open(birthday_cog.db_path, "w") as f:
        yaml.dump(data, f)

    # 2. Configurer le bot pour trouver le salon "général"
    mock_guild.text_channels = [mock_channel]
    mock_channel.name = "général"
    birthday_cog.bot.guilds = [mock_guild]

    # 3. Mocker datetime pour simuler le 10 Janvier à 00:00:00
    # C'est la partie critique : on force 'now'
    target_time = datetime(2024, 1, 10, 0, 0, 0)

    with patch("src.cogs.birthday.datetime") as mock_dt:
        mock_dt.now.return_value = target_time
        # Important pour `paris_tz`
        mock_dt.now.side_effect = lambda tz=None: target_time

        # 4. On appelle directement la coroutine de la tâche (sans la loop)
        # On accède à la fonction originale décorée via .coro
        await birthday_cog.reminder_task.coro(birthday_cog)

    # 5. Vérification
    # Le bot doit avoir envoyé un message dans le salon général
    mock_channel.send.assert_called_once()
    sent_text = mock_channel.send.call_args[0][0]
    assert "JOYEUX ANNIVERSAIRE" in sent_text
    assert "<@123>" in sent_text  # Mention de l'user
