from unittest.mock import MagicMock

import pytest
from riotwatcher import ApiError

from src.lol.exceptions import InvalidApiKey, PlayerNotFound, RateLimited
from src.lol.service import LeagueService


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
    ],
)
def test_get_puuid_errors(league_service, client_mock, status_code, expected_exception):
    # Arrange
    client_mock.get_puuid.side_effect = ApiError(
        response=MagicMock(status_code=status_code)
    )

    # Act & Assert
    with pytest.raises(expected_exception):
        league_service.get_puuid("floshv1", "LDV")


def test_get_puuid_unknown_error(league_service, client_mock):
    """Test qu'une erreur API inconnue est bien propagée"""
    # Arrange - Code d'erreur non géré (ex: 500, 503, etc.)
    api_error = ApiError(response=MagicMock(status_code=500))
    client_mock.get_puuid.side_effect = api_error

    # Act & Assert - L'erreur ApiError originale doit être propagée
    with pytest.raises(ApiError) as exc_info:
        league_service.get_puuid("floshv1", "LDV")

    # Vérifier que c'est bien la même erreur
    assert exc_info.value == api_error
