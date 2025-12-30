from riotwatcher import LolWatcher, RiotWatcher


class RiotApiClient:
    def __init__(
        self,
        api_key: str,
        lol_region: str = "euw1",
        riot_region: str = "europe",
    ):
        self.lol_region = lol_region
        self.riot_region = riot_region

        self.lol = LolWatcher(api_key)
        self.riot = RiotWatcher(api_key)

    def get_puuid(self, pseudo: str, tag: str):
        account = self.riot.account.by_riot_id(self.riot_region, pseudo, tag)
        puuid = account["puuid"]
        return puuid

    def make_profile(self, puuid: str):
        account = self.riot.account.by_puuid(self.riot_region, puuid)
        summoner = self.lol.summoner.by_puuid(self.lol_region, puuid)
        ranked_entries = self.lol.league.by_puuid(self.lol_region, puuid)

        def extract(queue_type):
            for entry in ranked_entries:
                if entry["queueType"] == queue_type:
                    wins = entry["wins"]
                    losses = entry["losses"]
                    total = wins + losses

                    return {
                        "tier": entry["tier"],
                        "rank": entry["rank"],
                        "lp": entry["leaguePoints"],
                        "wins": wins,
                        "losses": losses,
                        "winrate": round((wins / total) * 100, 1) if total else 0.0,
                    }
            return None

        return {
            "name": account["gameName"],
            "tag": account["tagLine"],
            "level": summoner["summonerLevel"],
            "profileIconId": summoner["profileIconId"],
            "rankedStats": {
                "soloq": extract("RANKED_SOLO_5x5"),
                "flex": extract("RANKED_FLEX_SR"),
            },
        }

    def get_match_ids(self, puuid: str, start: int = 0, count: int = 10, queue: int | None = None):
        return self.lol.match.matchlist_by_puuid(self.lol_region, puuid, start=start, count=count, queue=queue)

    def get_match_info(self, match_id: str):
        return self.lol.match.by_id(self.lol_region, match_id)

    def get_player_match_stats(self, match_id: str, puuid: str):
        """
        Stats principales d'un joueur pour un match.
        """
        match = self.get_match_info(match_id)
        info = match["info"]

        participant = next((p for p in info["participants"] if p["puuid"] == puuid), None)
        if not participant:
            return None

        duration_min = info["gameDuration"] / 60  # secondes -> minutes
        total_minions = participant["totalMinionsKilled"] + participant.get("neutralMinionsKilled", 0)

        return {
            "champion": participant["championName"],
            "kills": participant["kills"],
            "deaths": participant["deaths"],
            "assists": participant["assists"],
            "kda": round(
                (participant["kills"] + participant["assists"]) / max(1, participant["deaths"]),
                2,
            ),
            "cs": total_minions,
            "cs_per_min": round(total_minions / duration_min, 1),
            "gold": participant["goldEarned"],
            "gold_per_min": round(participant["goldEarned"] / duration_min, 1),
            "damageDealt": participant["totalDamageDealtToChampions"],
            "damage_per_min": round(participant["totalDamageDealtToChampions"] / duration_min, 1),
            "win": participant["win"],
            "duration_min": round(duration_min, 1),
            "summonerSpells": [participant["summoner1Id"], participant["summoner2Id"]],
            "items": [participant[f"item{i}"] for i in range(7)],
        }

    def get_matches_summary(self, puuid: str, count: int = 10, queue: int | None = None):
        match_ids = self.get_match_ids(puuid, count=count, queue=queue)
        summaries = []

        for match_id in match_ids:
            stats = self.get_player_match_stats(match_id, puuid)
            if stats:
                summaries.append(stats)

        return summaries
