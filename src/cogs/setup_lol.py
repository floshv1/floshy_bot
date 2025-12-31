# src/cogs/setup_lol.py - Version avec Slash Commands et Leaderboard Auto

import os
from typing import Any, Optional

import discord
import yaml
from discord import app_commands
from discord.ext import commands, tasks
from loguru import logger

from src.lol.client import RiotApiClient
from src.lol.exceptions import InvalidApiKey, PlayerNotFound, RateLimited
from src.lol.service import LeagueService


# src/cogs/setup_lol.py
class SetupLol(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        league_service,
        db_path: str = "./data/users.yml",
        config_path: str = "./data/config.yml",
        start_tasks: bool = True,  # ← CLÉ POUR LES TESTS
    ):
        self.bot = bot
        self.league_service = league_service
        self.db_path = db_path
        self.config_path = config_path

        # Création des dossiers
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

        self._start_tasks = start_tasks

    async def cog_load(self):
        """Appelé automatiquement quand le cog est chargé"""
        self.refresh_leaderboard.start()
        logger.success("Task refresh_leaderboard démarrée")

    def cog_unload(self):
        """Appelé quand le cog est déchargé"""
        self.refresh_leaderboard.cancel()

    # ============================================================================
    # GESTION DES DONNÉES
    # ============================================================================

    def _save_user(self, discord_id: int, puuid: str, pseudo: str, tag: str):
        """Enregistre ou met à jour un utilisateur dans le fichier YAML."""
        logger.debug(f"Sauvegarde YAML pour {discord_id} ({pseudo}#{tag})")

        # Initialisation explicite pour MyPy
        data: dict[str, Any] = {}

        # Chargement des données existantes
        if os.path.exists(self.db_path):
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

        # Mise à jour des données
        data[str(discord_id)] = {"puuid": puuid, "pseudo": pseudo, "tag": tag}

        # Sauvegarde
        with open(self.db_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

        logger.success(f"Données enregistrées pour {pseudo}#{tag}")

    def _load_users(self) -> dict:
        """Charge tous les utilisateurs depuis le fichier YAML."""
        if not os.path.exists(self.db_path):
            return {}

        with open(self.db_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _save_config(self, guild_id: int, channel_id: int, message_id: int):
        """Sauvegarde la config du leaderboard permanent."""
        config: dict[str, Any] = {}
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

        if "leaderboards" not in config:
            config["leaderboards"] = {}

        config["leaderboards"][str(guild_id)] = {
            "channel_id": channel_id,
            "message_id": message_id,
        }

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False)

        logger.success(f"Config leaderboard sauvegardée pour guild {guild_id}")

    def _load_config(self) -> dict:
        """Charge la configuration."""
        if not os.path.exists(self.config_path):
            return {}

        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    async def _link_account(self, interaction: discord.Interaction, pseudo: str, tag: str):
        await interaction.response.defer(ephemeral=True)

        try:
            # Tentative de récupération du PUUID
            puuid = self.league_service.get_puuid(pseudo, tag)
            self._save_user(interaction.user.id, puuid, pseudo, tag)

            embed = discord.Embed(
                title="✅ Compte lié avec succès !",
                description=f"Le compte **{pseudo}#{tag}** est maintenant associé à votre Discord.",
                color=discord.Color.green(),
            )
            embed.add_field(name="PUUID", value=f"`{puuid[:15]}...`", inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)

        except PlayerNotFound:
            logger.warning(f"Joueur introuvable lors du link : {pseudo}#{tag}")
            await interaction.followup.send(f"❌ Impossible de trouver le joueur **{pseudo}#{tag}**. Vérifiez l'orthographe.", ephemeral=True)
        except RateLimited:
            logger.warning("Rate limit atteint lors du link")
            await interaction.followup.send("⏳ Trop de requêtes à l'API Riot. Réessayez dans une minute.", ephemeral=True)
        except InvalidApiKey:
            logger.error("Clé API invalide lors du link")
            await interaction.followup.send("⚠️ Erreur de configuration : Clé API invalide.", ephemeral=True)
        except Exception as e:
            logger.exception(f"Erreur inattendue lors du link : {e}")
            await interaction.followup.send("💥 Une erreur interne est survenue.", ephemeral=True)

    # ============================================================================
    # COMMANDES SLASH
    # ============================================================================

    @app_commands.command(name="lol_link", description="Liez votre compte Discord à votre compte Riot")
    async def lol_link(self, interaction: discord.Interaction, riot_id: str):
        if "#" not in riot_id:
            return await interaction.response.send_message("❌ Format invalide. Utilisez : `Pseudo#TAG`", ephemeral=True)
        pseudo, tag = riot_id.split("#", 1)
        await self._link_account(interaction, pseudo, tag)

    @app_commands.command(name="lol_stats", description="Affiche les statistiques LoL d'un joueur")
    @app_commands.describe(member="Le membre dont vous voulez voir les stats (laissez vide pour vos propres stats)")
    async def lol_stats(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        """Affiche les statistiques League of Legends d'un joueur."""
        target = member or interaction.user
        logger.info(f"Requête /lol_stats par {interaction.user} pour {target}")

        await interaction.response.defer()

        # Charger les utilisateurs
        users = self._load_users()
        user_id = str(target.id)

        if user_id not in users:
            if target == interaction.user:
                return await interaction.followup.send("❌ Vous n'avez pas lié votre compte ! Utilisez `/lol_link`")
            else:
                return await interaction.followup.send(f"❌ {target.mention} n'a pas lié son compte.")

        user_data = users[user_id]
        puuid = user_data["puuid"]

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
                text=f"Demandé par {interaction.user.display_name}",
                icon_url=interaction.user.display_avatar.url,
            )

            await interaction.followup.send(embed=embed)

        except PlayerNotFound:
            await interaction.followup.send("❌ Impossible de trouver les stats. Le compte a peut-être changé de nom.")
        except RateLimited:
            await interaction.followup.send("⏳ Trop de requêtes à l'API Riot. Réessayez dans une minute.")
        except InvalidApiKey:
            await interaction.followup.send("⚠️ La clé API Riot est expirée ou invalide.")
        except Exception as e:
            await interaction.followup.send(f"💥 Une erreur est survenue : {e}")

    @app_commands.command(name="lol_leaderboard_setup", description="Configure un leaderboard permanent")
    @app_commands.describe(channel="Le salon où afficher le leaderboard permanent")
    @app_commands.default_permissions(administrator=True)
    async def lol_leaderboard_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        """Configure un leaderboard permanent."""
        # --- AJOUT SÉCURITÉ ---
        if not interaction.guild:
            return await interaction.response.send_message("❌ Cette commande doit être utilisée sur un serveur.", ephemeral=True)
        # ----------------------

        logger.info(f"Setup leaderboard par {interaction.user} dans {channel}")
        await interaction.response.defer(ephemeral=True)

        try:
            # Créer l'embed initial
            embed = await self._create_leaderboard_embed(interaction.guild)

            # Envoyer le message
            message = await channel.send(embed=embed)

            # Sauvegarder la config
            self._save_config(interaction.guild.id, channel.id, message.id)

            await interaction.followup.send(
                f"✅ Leaderboard permanent créé dans {channel.mention}\n" f"🔄 Il se rafraîchira automatiquement toutes les heures.", ephemeral=True
            )

        except Exception as e:
            logger.exception("Erreur lors du setup du leaderboard")
            await interaction.followup.send(f"❌ Erreur lors de la création du leaderboard : {e}", ephemeral=True)

    # ============================================================================
    # TÂCHE PÉRIODIQUE - REFRESH LEADERBOARD
    # ============================================================================

    @tasks.loop(hours=1)
    async def refresh_leaderboard(self):
        """Rafraîchit tous les leaderboards permanents toutes les heures."""
        logger.info("Début du refresh des leaderboards permanents")

        config = self._load_config()
        if "leaderboards" not in config:
            return

        for guild_id, lb_config in config["leaderboards"].items():
            try:
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    logger.warning(f"Guild {guild_id} introuvable")
                    continue

                channel = guild.get_channel(lb_config["channel_id"])
                if not channel:
                    logger.warning(f"Channel {lb_config['channel_id']} introuvable")
                    continue

                try:
                    message = await channel.fetch_message(lb_config["message_id"])
                except discord.NotFound:
                    logger.warning(f"Message leaderboard {lb_config['message_id']} introuvable")
                    continue

                # Créer le nouvel embed
                embed = await self._create_leaderboard_embed(guild)

                # Mettre à jour le message
                await message.edit(embed=embed)
                logger.success(f"Leaderboard rafraîchi pour guild {guild_id}")

            except Exception:
                logger.exception(f"Erreur lors du refresh du leaderboard pour guild {guild_id}")

    @refresh_leaderboard.before_loop
    async def before_refresh_leaderboard(self):
        """Attend que le bot soit prêt avant de démarrer la boucle."""
        await self.bot.wait_until_ready()

    # ============================================================================
    # FONCTIONS UTILITAIRES
    # ============================================================================

    async def _create_leaderboard_embed(self, guild: discord.Guild) -> discord.Embed:
        """Crée un embed de leaderboard pour une guild."""
        users = self._load_users()

        if not users:
            embed = discord.Embed(
                title="🏆 Classement Solo/Duo",
                description="Aucun compte lié pour le moment.\nUtilisez `/lol_link` pour vous ajouter !",
                color=discord.Color.gold(),
            )
            embed.set_footer(text="🔄 Rafraîchi toutes les heures")
            return embed

        # Récupérer les profils de tous les joueurs
        players = []

        for discord_id, user_data in users.items():
            try:
                puuid = user_data["puuid"]
                profile = self.league_service.make_profile(puuid)

                member = await guild.fetch_member(int(discord_id))
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

            except Exception as e:
                logger.warning(f"Impossible de récupérer {user_data['pseudo']}: {e}")
                continue

        if not players:
            embed = discord.Embed(
                title="🏆 Classement Solo/Duo",
                description="❌ Impossible de récupérer les stats des joueurs.",
                color=discord.Color.gold(),
            )
            embed.set_footer(text="🔄 Rafraîchi toutes les heures")
            return embed

        # Trier par rang
        players.sort(key=self._get_rank_value, reverse=True)

        # Créer l'embed
        embed = discord.Embed(
            title="🏆 Classement Solo/Duo",
            description=f"**{len(players)} joueur(s) classé(s)**",
            color=discord.Color.gold(),
        )

        # Construire le tableau
        max_name_len = max(len(p["riot_name"]) for p in players)
        max_name_len = min(max_name_len, 20)

        table = "```\n"
        table += f"{'Pseudo':<{max_name_len}} | {'Lvl':>4} | {'Rank':<15} | {'WR':>5}\n"
        table += "─" * (max_name_len + 33) + "\n"

        for i, player in enumerate(players[:15], 1):  # Limiter à 15 joueurs
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

            # Médailles pour le top 3
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

        embed.add_field(name="📊 Classement", value=table, inline=False)

        # Footer avec timestamp
        from datetime import datetime

        embed.set_footer(text="🔄 Dernière mise à jour")
        embed.timestamp = datetime.utcnow()

        return embed

    def _get_rank_value(self, player: dict) -> int:
        """Retourne une valeur numérique pour trier les joueurs par rang."""
        if not player["soloq"]:
            return -1

        tier_values: dict[str, int] = {
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
        rank_values: dict[str, int] = {"IV": 0, "III": 1, "II": 2, "I": 3}

        soloq = player["soloq"]
        tier = soloq["tier"]
        rank = soloq["rank"]
        lp = int(soloq["lp"])  # Force le type int

        return tier_values.get(tier, 0) * 1000 + rank_values.get(rank, 0) * 100 + lp

    def _get_rank_emoji(self, tier: str) -> str:
        """Retourne un emoji correspondant au rang."""
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


async def setup(bot):
    api_key = os.getenv("LOLAPI")
    if not api_key:
        # Correction du nom de la variable dans le log
        logger.critical("LOLAPI non défini dans les variables d'environnement.")
        return

    client = RiotApiClient(api_key)
    service = LeagueService(client)

    cog = SetupLol(bot, service)
    await bot.add_cog(cog)
    logger.info("Cog SetupLol ajouté au bot.")
