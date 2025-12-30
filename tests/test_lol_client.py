import unittest
from unittest.mock import MagicMock, patch

from riotwatcher import ApiError

from src.lol.client import RiotApiClient


class TestRiotApiClient(unittest.TestCase):

    @patch("src.lol.client.LolWatcher")
    @patch("src.lol.client.RiotWatcher")
    def test_get_puuid_success(self, mock_riot_cls, mock_lol_cls):
        # Arrange
        mock_riot = mock_riot_cls.return_value
        mock_lol = mock_lol_cls.return_value

        mock_riot.account.by_riot_id.return_value = {"puuid": "PUUID_TEST"}

        mock_lol.summoner.by_puuid.return_value = {}

        client = RiotApiClient("FAKE_API_KEY")

        # Act
        result = client.get_puuid("floshv1", "LDV")

        # Assert
        self.assertEqual(result, "PUUID_TEST")
        mock_riot.account.by_riot_id.assert_called_once_with("europe", "floshv1", "LDV")
        mock_lol.summoner.by_puuid.assert_called_once_with("euw1", "PUUID_TEST")

    @patch("src.lol.client.RiotWatcher")
    def test_get_puuid_api_error_propagated(self, mock_riot_cls):
        mock_riot = mock_riot_cls.return_value

        mock_riot.account.by_riot_id.side_effect = ApiError(
            response=MagicMock(status_code=403)
        )

        client = RiotApiClient("FAKE_API_KEY")

        with self.assertRaises(ApiError):
            client.get_puuid("floshv1", "LDV")
