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
            code = getattr(err.response, "status_code", None)

            if code == 404:
                raise PlayerNotFound()
            elif code == 403:
                raise InvalidApiKey()
            elif code == 429:
                raise RateLimited()
            else:
                raise
