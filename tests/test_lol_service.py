from unittest.mock import MagicMock

import pytest
from riotwatcher import ApiError

from src.lol.exceptions import InvalidApiKey, PlayerNotFound, RateLimited
from src.lol.service import LeagueService


@pytest.fixture
def client_mock():
    return MagicMock()


@pytest.fixture
def service(client_mock):
    return LeagueService(client_mock)


# --- Tests de succès ---


def test_get_match_history_calls_client(service, client_mock):
    client_mock.get_puuid.return_value = "PUUID_123"
    client_mock.get_match_ids.return_value = ["M1", "M2"]

    history = service.get_match_history("Pseudo", "TAG", count=2)

    assert history == ["M1", "M2"]
    client_mock.get_puuid.assert_called_once_with("Pseudo", "TAG")


# --- Tests d'erreurs (Fix des échecs MagicMock) ---


def test_get_match_history_error(service, client_mock):
    """Couvre les lignes 39-40 : ApiError dans l'historique"""
    client_mock.get_puuid.return_value = "PUUID_123"

    # Utilisation d'un objet response mocké avec status_code
    mock_res = MagicMock(status_code=403)
    client_mock.get_match_ids.side_effect = ApiError(response=mock_res)

    with pytest.raises(InvalidApiKey):
        service.get_match_history("Pseudo", "TAG")


def test_get_match_details_success(service, client_mock):
    """Couvre les lignes 43-44 : Succès de get_match_details"""
    client_mock.get_match_info.return_value = {"info": "ok"}
    res = service.get_match_details("MATCH_ID")
    assert res == {"info": "ok"}


def test_get_match_details_error(service, client_mock):
    """Couvre les lignes 46-47 : Erreur dans get_match_details"""
    mock_res = MagicMock(status_code=404)
    client_mock.get_match_info.side_effect = ApiError(response=mock_res)

    with pytest.raises(PlayerNotFound):
        service.get_match_details("BAD_ID")


@pytest.mark.parametrize(
    "status_code, expected_exception",
    [(403, InvalidApiKey), (404, PlayerNotFound), (429, RateLimited)],
)
def test_handle_api_errors(service, client_mock, status_code, expected_exception):
    """Vérifie le mapping de _handle_api_error (lignes 53-58)"""
    mock_response = MagicMock(status_code=status_code)
    client_mock.make_profile.side_effect = ApiError(response=mock_response)

    with pytest.raises(expected_exception):
        service.make_profile("any-puuid")


def test_unknown_error_propagation(service, client_mock):
    """Couvre la ligne 60 : Propagation d'erreur inconnue"""
    mock_response = MagicMock(status_code=500)
    api_error = ApiError(response=mock_response)
    client_mock.get_puuid.side_effect = api_error

    with pytest.raises(ApiError) as exc_info:
        service.get_puuid("Pseudo", "TAG")
    assert exc_info.value == api_error
