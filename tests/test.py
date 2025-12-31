import os

from dotenv import load_dotenv

from src.lol.client import RiotApiClient
from src.lol.service import LeagueService

load_dotenv()

api_key = os.getenv("LOLAPI")

client = RiotApiClient(api_key)

service = LeagueService(client)
puuid = service.get_puuid("NicoBooy", "CNTH")
print("PUUID:", puuid)

profile = service.make_profile(puuid)
print("Profile:", profile)

matches_summary = client.get_matches_summary(puuid, count=1, queue=420)  # Ranked solo

get_match_ids = client.get_match_ids(puuid, count=1, queue=420)
print("Match IDs:", get_match_ids)

for i in get_match_ids:
    match_info = client.get_match_info(i)
    print(f"Match Info for {i}:", match_info)

"""print("Derniers matchs classés :")
for match in matches_summary:
    print(match)"""
