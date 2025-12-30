# src/cogs/setup_lol.py - Version complète avec LeagueService

import os

import discord
import yaml
from discord.ext import commands

from src.lol.exceptions import InvalidApiKey, PlayerNotFound, RateLimited


class SetupLol(commands.Cog):
    def __init__(self, bot, league_service):
        self.bot = bot
        self.league_service = league_service
        self.db_path = "./data/users.yml"
        # S'assurer que le dossier data existe
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _save_user(self, discord_id, puuid, pseudo, tag):
        """Enregistre ou met à jour un utilisateur dans le fichier YAML."""
        data = {}
        if os.path.exists(self.db_path):
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

        data[str(discord_id)] = {"puuid": puuid, "pseudo": pseudo, "tag": tag}

        # S'assurer que le dossier existe avant d'écrire
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with open(self.db_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    def _load_users(self):
        """Charge tous les utilisateurs depuis le fichier YAML."""
        if not os.path.exists(self.db_path):
            return {}

        with open(self.db_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    @commands.command(name="link_lol", help="Lier votre compte Discord à votre compte Riot.")
    async def link_lol(self, ctx, name_with_tag: str):
        """
        Lie votre compte Discord à votre compte Riot.
        Usage: !link_lol Pseudo#TAG
        """
        if "#" not in name_with_tag:
            return await ctx.send("❌ Format invalide. Utilisez : `Pseudo#TAG`")

        pseudo, tag = name_with_tag.split("#", 1)

        async with ctx.typing():
            try:
                # Récupérer le PUUID via le service
                puuid = self.league_service.get_puuid(pseudo, tag)

                # Sauvegarder dans le YAML
                self._save_user(ctx.author.id, puuid, pseudo, tag)

                embed = discord.Embed(
                    title="✅ Compte lié avec succès !",
                    description=f"Le compte **{pseudo}#{tag}** est " "maintenant associé à votre Discord.",
                    color=discord.Color.green(),
                )
                embed.add_field(name="PUUID", value=f"`{puuid[:15]}...`", inline=False)
                await ctx.send(embed=embed)

            except PlayerNotFound:
                await ctx.send(f"❌ Impossible de trouver le joueur **{pseudo}#{tag}**.")
            except RateLimited:
                await ctx.send("⏳ Trop de requêtes à l'API Riot. Réessayez dans une minute.")
            except InvalidApiKey:
                await ctx.send("⚠️ La clé API Riot est expirée ou invalide.")
            except Exception as e:
                await ctx.send(f"💥 Une erreur est survenue : {e}")

    @commands.command(
        name="lol_leaderboard",
        aliases=["leaderboard", "ladder", "classement"],
        help="Affiche le classement de tous les joueurs liés",
    )
    async def lol_leaderboard(self, ctx):
        """
        Affiche un tableau avec tous les joueurs qui ont lié leur compte.
        Usage: !lol_leaderboard
        """
        # Charger les utilisateurs
        users = self._load_users()

        if not users:
            return await ctx.send("❌ Aucun compte n'est lié pour le moment.")

        await ctx.send("⏳ Récupération des stats... Cela peut prendre quelques secondes.")

        async with ctx.typing():
            try:
                # Récupérer les profils de tous les joueurs
                players = []

                for discord_id, user_data in users.items():
                    try:
                        puuid = user_data["puuid"]

                        # Utiliser le service pour récupérer le profil
                        profile = self.league_service.make_profile(puuid)

                        # Récupérer le membre Discord

                        member = await ctx.guild.fetch_member(int(discord_id))
                        discord_name = member.display_name

                        players.append(
                            {
                                "discord_name": discord_name,
                                "riot_name": f"{profile['name']}#{profile['tag']}",
                                "level": profile["level"],
                                "soloq": profile["rankedStats"]["soloq"],
                                "flex": profile["rankedStats"]["flex"],
                            }
                        )

                    except (PlayerNotFound, RateLimited, InvalidApiKey):
                        # Skip ce joueur en cas d'erreur
                        continue
                    except Exception:
                        # Skip ce joueur en cas d'erreur
                        continue

                if not players:
                    return await ctx.send("❌ Impossible de récupérer les stats des joueurs.")

                # Trier par rang (Solo/Duo)
                players.sort(key=self._get_rank_value, reverse=True)

                # Créer l'embed
                embed = discord.Embed(
                    title="🏆 Classement Solo/Duo",
                    description="Tous les joueurs qui ont lié leur compte",
                    color=discord.Color.gold(),
                )

                # Construire le tableau
                max_name_len = max(len(p["riot_name"]) for p in players)
                max_name_len = min(max_name_len, 20)  # Limiter à 20 caractères

                # Header
                table = "```\n"
                table += f"{'Pseudo':<{max_name_len}} | {'Lvl':>4} | {'Rank':<15} | {'WR':>5}\n"
                table += "─" * (max_name_len + 33) + "\n"

                # Lignes de joueurs
                for i, player in enumerate(players, 1):
                    name = player["riot_name"][:max_name_len]
                    level = player["level"]

                    if player["soloq"]:
                        soloq = player["soloq"]
                        tier = soloq["tier"].title()
                        rank = soloq["rank"]
                        lp = soloq["lp"]
                        rank_display = f"{tier} {rank} {lp} LP"[:15]
                        winrate = f"{soloq['winrate']:.1f}%"
                    else:
                        rank_display = "Unranked".ljust(15)
                        winrate = "N/A"

                    # Emoji pour le top 3
                    medal = ""
                    if i == 1:
                        medal = "🥇 "
                    elif i == 2:
                        medal = "🥈 "
                    elif i == 3:
                        medal = "🥉 "

                    line_name = f"{medal}{name}"
                    # Ajuster la longueur pour l'emoji
                    table += f"{line_name:<{max_name_len}} | {level:>4} | {rank_display:<15} | {winrate:>5}\n"

                table += "```"

                # Vérifier la longueur
                if len(table) > 1024:
                    # Limiter à 15 joueurs
                    players_limited = players[:15]
                    table = self._build_table(players_limited, max_name_len)
                    embed.add_field(
                        name=f"📊 Top 15 sur {len(players)} joueur(s)",
                        value=table,
                        inline=False,
                    )
                else:
                    embed.add_field(
                        name=f"📊 {len(players)} joueur(s) classé(s)",
                        value=table,
                        inline=False,
                    )

                # Footer
                embed.set_footer(
                    text=f"Demandé par {ctx.author.display_name}",
                    icon_url=ctx.author.display_avatar.url,
                )

                await ctx.send(embed=embed)

            except RateLimited:
                await ctx.send("⏳ Trop de requêtes à l'API Riot. Réessayez dans une minute.")
            except InvalidApiKey:
                await ctx.send("⚠️ La clé API Riot est expirée ou invalide.")
            except Exception as e:
                await ctx.send(f"💥 Une erreur est survenue : {e}")

    @commands.command(
        name="lol_stats",
        aliases=["stats", "profile"],
        help="Affiche les stats LoL d'un joueur lié",
    )
    async def lol_stats(self, ctx, member: discord.Member):
        """
        Affiche les statistiques League of Legends d'un joueur.
        Usage: !lol_stats [@mention]
        Si aucun membre n'est mentionné, affiche vos propres stats.
        """
        # Si aucun membre mentionné, utiliser l'auteur
        target = member or ctx.author

        # Charger les utilisateurs
        users = self._load_users()

        # Vérifier si l'utilisateur a lié son compte
        user_id = str(target.id)
        if user_id not in users:
            if target == ctx.author:
                return await ctx.send("❌ Vous n'avez pas lié votre compte ! " "Utilisez `!link_lol Pseudo#TAG`")
            else:
                return await ctx.send(f"❌ {target.mention} n'a pas lié son compte.")

        user_data = users[user_id]
        puuid = user_data["puuid"]

        async with ctx.typing():
            try:
                # Récupérer le profil via le service
                profile = self.league_service.make_profile(puuid)

                # Créer l'embed
                embed = discord.Embed(
                    title="📊 Profil League of Legends",
                    description=f"**{profile['name']}#{profile['tag']}**",
                    color=discord.Color.blue(),
                )

                # Icône de profil
                icon_id = profile["profileIconId"]
                icon_url = f"https://ddragon.leagueoflegends.com/cdn/14.1.1/img/profileicon/{icon_id}.png"
                embed.set_thumbnail(url=icon_url)

                # Niveau
                embed.add_field(name="📈 Niveau", value=f"**{profile['level']}**", inline=True)

                # Stats Ranked Solo/Duo
                soloq = profile["rankedStats"]["soloq"]
                if soloq:
                    rank_emoji = self._get_rank_emoji(soloq["tier"])
                    soloq_text = (
                        f"{rank_emoji} **{soloq['tier'].title()} {soloq['rank']}** - {soloq['lp']} LP\n"
                        f"🎮 {soloq['wins']}W / {soloq['losses']}L ({soloq['winrate']}%)\n"
                        f"📊 {soloq['wins'] + soloq['losses']} parties jouées"
                    )
                else:
                    soloq_text = "Non classé"

                embed.add_field(name="🏆 Solo/Duo", value=soloq_text, inline=False)

                # Stats Ranked Flex
                flex = profile["rankedStats"]["flex"]
                if flex:
                    rank_emoji = self._get_rank_emoji(flex["tier"])
                    flex_text = (
                        f"{rank_emoji} **{flex['tier'].title()} {flex['rank']}** - {flex['lp']} LP\n"
                        f"🎮 {flex['wins']}W / {flex['losses']}L ({flex['winrate']}%)"
                    )
                else:
                    flex_text = "Non classé"

                embed.add_field(name="👥 Flex 5v5", value=flex_text, inline=False)

                # Footer
                embed.set_footer(
                    text=f"Demandé par {ctx.author.display_name}",
                    icon_url=ctx.author.display_avatar.url,
                )

                await ctx.send(embed=embed)

            except PlayerNotFound:
                await ctx.send("❌ Impossible de trouver les stats. " "Le compte a peut-être changé de nom.")
            except RateLimited:
                await ctx.send("⏳ Trop de requêtes à l'API Riot. Réessayez dans une minute.")
            except InvalidApiKey:
                await ctx.send("⚠️ La clé API Riot est expirée ou invalide.")
            except Exception as e:
                await ctx.send(f"💥 Une erreur est survenue : {e}")

    def _build_table(self, players, max_name_len):
        """Construit un tableau formaté pour l'embed"""
        table = "```\n"
        table += f"{'Pseudo':<{max_name_len}} | {'Lvl':>4} | {'Rank':<15} | {'WR':>5}\n"
        table += "─" * (max_name_len + 33) + "\n"

        for i, player in enumerate(players, 1):
            name = player["riot_name"][:max_name_len]
            level = player["level"]

            if player["soloq"]:
                soloq = player["soloq"]
                tier = soloq["tier"].title()
                rank = soloq["rank"]
                lp = soloq["lp"]
                rank_display = f"{tier} {rank} {lp} LP"[:15]
                winrate = f"{soloq['winrate']:.1f}%"
            else:
                rank_display = "Unranked".ljust(15)
                winrate = "N/A"

            medal = ""
            if i == 1:
                medal = "🥇 "
            elif i == 2:
                medal = "🥈 "
            elif i == 3:
                medal = "🥉 "

            line_name = f"{medal}{name}"
            table += f"{line_name:<{max_name_len}} | {level:>4} | {rank_display:<15} | {winrate:>5}\n"

        table += "```"
        return table

    def _get_rank_value(self, player):
        """Retourne une valeur numérique pour trier les joueurs par rang"""
        if not player["soloq"]:
            return -1  # Unranked en dernier

        tier_values = {
            "IRON": 0,
            "BRONZE": 1,
            "SILVER": 2,
            "GOLD": 3,
            "PLATINUM": 4,
            "EMERALD": 5,
            "DIAMOND": 6,
            "MASTER": 7,
            "GRANDMASTER": 8,
            "CHALLENGER": 9,
        }
        rank_values = {"IV": 0, "III": 1, "II": 2, "I": 3}

        soloq = player["soloq"]
        tier = soloq["tier"]
        rank = soloq["rank"]
        lp = soloq["lp"]

        return tier_values.get(tier, 0) * 1000 + rank_values.get(rank, 0) * 100 + lp

    def _get_rank_emoji(self, tier: str) -> str:
        """Retourne un emoji correspondant au rang"""
        tier_emojis = {
            "IRON": "⚫",
            "BRONZE": "🟤",
            "SILVER": "⚪",
            "GOLD": "🟡",
            "PLATINUM": "🔵",
            "EMERALD": "🟢",
            "DIAMOND": "💎",
            "MASTER": "🔴",
            "GRANDMASTER": "🔴",
            "CHALLENGER": "🏆",
        }
        return tier_emojis.get(tier.upper(), "❓")


async def setup_cog(bot, league_service):
    """Fonction pour charger le cog"""
    await bot.add_cog(SetupLol(bot, league_service))
