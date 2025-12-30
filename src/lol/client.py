from riotwatcher import LolWatcher, RiotWatcher


class RiotApiClient:
    def __init__(self, api_key: str, region="euw1"):
        self.region = region
        self.lol = LolWatcher(api_key)
        self.riot = RiotWatcher(api_key)

    def get_puuid(self, pseudo: str, tag: str):
        account = self.riot.account.by_riot_id("europe", pseudo, tag)
        puuid = account["puuid"]
        self.lol.summoner.by_puuid(self.region, puuid)
        return puuid
