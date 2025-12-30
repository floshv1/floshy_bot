from riotwatcher import ApiError

from src.lol.client import RiotApiClient
from src.lol.exceptions import InvalidApiKey, PlayerNotFound, RateLimited


class LeagueService:
    def __init__(self, client: RiotApiClient):
        self.client = client

    def get_puuid(self, pseudo: str, tag: str):
        try:
            return self.client.get_puuid(pseudo, tag)

        except ApiError as err:
            self._handle_api_error(err)

    def make_profile(self, puuid: str):
        try:
            return self.client.make_profile(puuid)
        except ApiError as err:
            self._handle_api_error(err)

    def get_match_history(
        self,
        pseudo: str,
        tag: str,
        count: int = 10,
        queue: int | None = None,
    ):
        try:
            puuid = self.get_puuid(pseudo, tag)
            return self.client.get_match_ids(
                puuid=puuid,
                count=count,
                queue=queue,
            )

        except ApiError as err:
            self._handle_api_error(err)

    def get_match_details(self, match_id: str):
        try:
            return self.client.get_match_info(match_id)

        except ApiError as err:
            self._handle_api_error(err)

    @staticmethod
    def _handle_api_error(err: ApiError):
        code = getattr(err.response, "status_code", None)

        if code == 404:
            raise PlayerNotFound()
        elif code == 403:
            raise InvalidApiKey()
        elif code == 429:
            raise RateLimited()
        else:
            raise
