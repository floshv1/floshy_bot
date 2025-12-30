import pytest
from unittest.mock import MagicMock
from riotwatcher import ApiError

from src.lol.service import LeagueService
from src.lol.exceptions import InvalidApiKey, PlayerNotFound, RateLimited

@pytest.fixture
def client_mock():
    return MagicMock()

@pytest.fixture
def league_service(client_mock):
    return LeagueService(client_mock)

def test_get_puuid_success(league_service, client_mock):
    # Arrange
    client_mock.get_puuid.return_value = "PUUID_TEST"

    # Act
    result = league_service.get_puuid("floshv1", "LDV")

    # Assert
    assert result == "PUUID_TEST"
    client_mock.get_puuid.assert_called_once_with("floshv1", "LDV")

@pytest.mark.parametrize(
    "status_code,expected_exception",
    [
        (403, InvalidApiKey),
        (404, PlayerNotFound),
        (429, RateLimited),
    ]
)
def test_get_puuid_errors(league_service, client_mock, status_code, expected_exception):
    # Arrange
    client_mock.get_puuid.side_effect = ApiError(
        response=MagicMock(status_code=status_code)
    )

    # Act & Assert
    with pytest.raises(expected_exception):
        league_service.get_puuid("floshv1", "LDV")
