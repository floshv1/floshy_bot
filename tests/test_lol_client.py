# tests/test_lol_client.py - Ajoutez ces tests

from unittest.mock import MagicMock, patch

import pytest

from src.lol.client import RiotApiClient


@pytest.fixture
def client():
    # On mock les watchers pour éviter tout appel réseau réel
    with patch("src.lol.client.LolWatcher"), patch("src.lol.client.RiotWatcher"):
        return RiotApiClient("FAKE_KEY")


def test_get_puuid_success(client):
    """Couvre RiotApiClient.get_puuid (0% -> 100%)"""
    client.riot.account.by_riot_id.return_value = {"puuid": "puuid_de_test_123"}

    puuid = client.get_puuid("Pseudo", "Tag")

    assert puuid == "puuid_de_test_123"
    client.riot.account.by_riot_id.assert_called_once_with("europe", "Pseudo", "Tag")


def test_make_profile_extract_none(client):
    """Couvre RiotApiClient.make_profile.extract (29% -> 100%)"""
    client.riot.account.by_puuid.return_value = {"gameName": "Nom", "tagLine": "Tag"}
    client.lol.summoner.by_puuid.return_value = {
        "summonerLevel": 30,
        "profileIconId": 1,
    }

    # Liste vide pour forcer extract à retourner None
    client.lol.league.by_puuid.return_value = []

    profile = client.make_profile("puuid-vide")

    assert profile["rankedStats"]["soloq"] is None
    assert profile["rankedStats"]["flex"] is None


def test_make_profile_extract_with_stats(client):
    """Test extract avec des stats ranked (couvre les calculs de winrate)"""
    client.riot.account.by_puuid.return_value = {"gameName": "Player", "tagLine": "EUW"}
    client.lol.summoner.by_puuid.return_value = {
        "summonerLevel": 100,
        "profileIconId": 5,
    }

    # Mock avec stats soloq et flex
    client.lol.league.by_puuid.return_value = [
        {
            "queueType": "RANKED_SOLO_5x5",
            "tier": "DIAMOND",
            "rank": "II",
            "leaguePoints": 75,
            "wins": 60,
            "losses": 40,
        },
        {
            "queueType": "RANKED_FLEX_SR",
            "tier": "PLATINUM",
            "rank": "I",
            "leaguePoints": 50,
            "wins": 30,
            "losses": 20,
        },
    ]

    profile = client.make_profile("puuid-with-stats")

    # Vérifier soloq
    assert profile["rankedStats"]["soloq"]["tier"] == "DIAMOND"
    assert profile["rankedStats"]["soloq"]["rank"] == "II"
    assert profile["rankedStats"]["soloq"]["lp"] == 75
    assert profile["rankedStats"]["soloq"]["wins"] == 60
    assert profile["rankedStats"]["soloq"]["losses"] == 40
    assert profile["rankedStats"]["soloq"]["winrate"] == 60.0  # 60/(60+40) * 100

    # Vérifier flex
    assert profile["rankedStats"]["flex"]["tier"] == "PLATINUM"
    assert profile["rankedStats"]["flex"]["winrate"] == 60.0  # 30/(30+20) * 100


def test_make_profile_extract_zero_games(client):
    """Test extract avec 0 games (couvre le cas winrate = 0)"""
    client.riot.account.by_puuid.return_value = {"gameName": "New", "tagLine": "EUW"}
    client.lol.summoner.by_puuid.return_value = {
        "summonerLevel": 30,
        "profileIconId": 1,
    }

    # Ranked avec 0 wins et 0 losses
    client.lol.league.by_puuid.return_value = [
        {
            "queueType": "RANKED_SOLO_5x5",
            "tier": "IRON",
            "rank": "IV",
            "leaguePoints": 0,
            "wins": 0,
            "losses": 0,
        }
    ]

    profile = client.make_profile("puuid-zero-games")

    assert profile["rankedStats"]["soloq"]["winrate"] == 0.0


def test_get_match_ids(client):
    """Couvre RiotApiClient.get_match_ids (0% -> 100%)"""
    client.lol.match.matchlist_by_puuid.return_value = [
        "EUW1_123456",
        "EUW1_123457",
        "EUW1_123458",
    ]

    match_ids = client.get_match_ids("puuid-test", start=0, count=3)

    assert len(match_ids) == 3
    assert "EUW1_123456" in match_ids
    client.lol.match.matchlist_by_puuid.assert_called_once_with("euw1", "puuid-test", start=0, count=3, queue=None)


def test_get_match_ids_with_queue(client):
    """Test get_match_ids avec filtre de queue"""
    client.lol.match.matchlist_by_puuid.return_value = ["EUW1_ranked"]

    match_ids = client.get_match_ids("puuid-test", count=5, queue=420)

    # Vérifier le résultat
    assert match_ids == ["EUW1_ranked"]

    # Vérifier l'appel
    client.lol.match.matchlist_by_puuid.assert_called_once_with("euw1", "puuid-test", start=0, count=5, queue=420)


def test_get_match_info(client):
    """Couvre RiotApiClient.get_match_info (0% -> 100%)"""
    mock_match_data = {"info": {"gameDuration": 1800, "participants": []}}
    client.lol.match.by_id.return_value = mock_match_data

    match_info = client.get_match_info("EUW1_123456")

    assert match_info == mock_match_data
    client.lol.match.by_id.assert_called_once_with("euw1", "EUW1_123456")


def test_get_player_match_stats_full_calculation(client):
    """Couvre RiotApiClient.get_player_match_stats (88% -> 100%)"""
    mock_match = {
        "info": {
            "gameDuration": 1200,  # 20 minutes
            "participants": [
                {
                    "puuid": "target-puuid",
                    "championName": "Aatrox",
                    "kills": 10,
                    "deaths": 2,
                    "assists": 5,
                    "totalMinionsKilled": 150,
                    "neutralMinionsKilled": 10,
                    "goldEarned": 10000,
                    "totalDamageDealtToChampions": 25000,
                    "win": True,
                    "summoner1Id": 4,
                    "summoner2Id": 12,
                    **{f"item{i}": i for i in range(7)},
                }
            ],
        }
    }
    client.get_match_info = MagicMock(return_value=mock_match)

    stats = client.get_player_match_stats("MATCH_ID", "target-puuid")

    # Vérifier tous les calculs
    assert stats["champion"] == "Aatrox"
    assert stats["kills"] == 10
    assert stats["deaths"] == 2
    assert stats["assists"] == 5
    assert stats["kda"] == 7.5  # (10 + 5) / 2
    assert stats["cs"] == 160  # 150 + 10
    assert stats["cs_per_min"] == 8.0  # 160 / 20
    assert stats["gold"] == 10000
    assert stats["gold_per_min"] == 500.0  # 10000 / 20
    assert stats["damageDealt"] == 25000
    assert stats["damage_per_min"] == 1250.0  # 25000 / 20
    assert stats["win"] is True
    assert stats["duration_min"] == 20.0
    assert stats["summonerSpells"] == [4, 12]
    assert len(stats["items"]) == 7


def test_get_player_match_stats_player_not_found(client):
    """Test quand le joueur n'est pas dans le match (ligne manquante)"""
    mock_match = {
        "info": {
            "gameDuration": 1200,
            "participants": [
                {
                    "puuid": "other-player",
                    "championName": "Yasuo",
                    "kills": 5,
                    "deaths": 10,
                    "assists": 3,
                    "totalMinionsKilled": 100,
                    "goldEarned": 5000,
                    "totalDamageDealtToChampions": 10000,
                    "win": False,
                    "summoner1Id": 4,
                    "summoner2Id": 7,
                    **{f"item{i}": 0 for i in range(7)},
                }
            ],
        }
    }
    client.get_match_info = MagicMock(return_value=mock_match)

    # Le puuid demandé n'est pas dans les participants
    stats = client.get_player_match_stats("MATCH_ID", "wrong-puuid")

    # Doit retourner None (couvre le return None ligne 77)
    assert stats is None


def test_get_matches_summary(client):
    """Couvre RiotApiClient.get_matches_summary (0% -> 100%)"""
    # Mock les IDs de matchs
    client.get_match_ids = MagicMock(return_value=["MATCH_1", "MATCH_2", "MATCH_3"])

    # Mock les stats pour chaque match
    client.get_player_match_stats = MagicMock(
        side_effect=[
            {
                "champion": "Zed",
                "kills": 10,
                "deaths": 2,
                "assists": 5,
                "kda": 7.5,
                "win": True,
            },
            {
                "champion": "Yasuo",
                "kills": 5,
                "deaths": 8,
                "assists": 3,
                "kda": 1.0,
                "win": False,
            },
            None,  # Un match où le joueur n'est pas trouvé
        ]
    )

    summaries = client.get_matches_summary("puuid-test", count=3)

    # Vérifie qu'on a bien 2 résultats (le None est exclu)
    assert len(summaries) == 2
    assert summaries[0]["champion"] == "Zed"
    assert summaries[0]["win"] is True
    assert summaries[1]["champion"] == "Yasuo"
    assert summaries[1]["win"] is False

    # Vérifie les appels
    client.get_match_ids.assert_called_once_with("puuid-test", count=3, queue=None)
    assert client.get_player_match_stats.call_count == 3


def test_get_matches_summary_with_queue_filter(client):
    """Test get_matches_summary avec filtre de queue"""
    client.get_match_ids = MagicMock(return_value=["RANKED_1"])
    client.get_player_match_stats = MagicMock(return_value={"champion": "Jinx", "win": True})

    summaries = client.get_matches_summary("puuid-test", count=5, queue=420)

    # Vérifie que le filtre queue est bien passé
    client.get_match_ids.assert_called_once_with("puuid-test", count=5, queue=420)
    assert len(summaries) == 1
