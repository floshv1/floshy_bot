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

    def _save_user(self, discord_id: int, puuid: str, pseudo: str, tag: str, stats):
        """Enregistre l'utilisateur et met en cache ses dernières stats connues."""
        logger.debug(f"Sauvegarde YAML pour {discord_id} ({pseudo}#{tag})")

        data: dict[str, Any] = {}

        if os.path.exists(self.db_path):
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

        # On prépare l'objet utilisateur
        user_entry = {"puuid": puuid, "pseudo": pseudo, "tag": tag}

        # Si on fournit des stats (lors d'un refresh réussi), on les sauvegarde
        if stats:
            user_entry["cached_stats"] = stats
        # Sinon, on garde les anciennes stats s'il y en avait
        elif str(discord_id) in data and "cached_stats" in data[str(discord_id)]:
            user_entry["cached_stats"] = data[str(discord_id)]["cached_stats"]

        data[str(discord_id)] = user_entry

        with open(self.db_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

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
            self._save_user(interaction.user.id, puuid, pseudo, tag, stats=None)

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
        logger.info(f"Requête /lol_link par {interaction.user} pour {pseudo}#{tag}")
        await self._link_account(interaction, pseudo, tag)
        await self.refresh_leaderboard()

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
        """Génère le leaderboard (API Live -> Fallback Cache)."""
        users = self._load_users()
        players: list[dict[str, Any]] = []
        api_down = False  # Pour savoir si on doit changer le footer

        for d_id, u_data in users.items():
            member = guild.get_member(int(d_id))
            if not member:
                continue

            p = None
            try:
                # 1. Tentative appel API Live
                profile = self.league_service.make_profile(u_data["puuid"])

                # Si succès, on prépare les données pour l'affichage ET le cache
                s = profile["rankedStats"]["soloq"]

                # On structure ce qu'on veut sauvegarder
                cached_data = {"name": profile["name"], "tag": profile["tag"], "level": profile["level"], "soloq": s}  # Peut être None si unranked

                # Mise à jour du cache (Sauvegarde disque)
                self._save_user(int(d_id), u_data["puuid"], u_data["pseudo"], u_data["tag"], stats=cached_data)

                # On utilise ces données pour la suite
                p = cached_data

            except Exception as e:
                # 2. Si l'API échoue, on tente de charger le CACHE
                logger.warning(f"API Error pour {u_data['pseudo']} ({e}). Utilisation du cache.")
                api_down = True

                if "cached_stats" in u_data:
                    p = u_data["cached_stats"]
                else:
                    logger.error(f"Aucun cache disponible pour {u_data['pseudo']}")
                    continue  # Vraiment rien à afficher

            # --- Construction de l'objet joueur pour le tableau ---
            # À partir d'ici, 'p' contient les données (soit live, soit cache)
            if p:
                s = p["soloq"]
                if s:
                    # Logique de formatage identique à avant
                    tier = s["tier"].title()
                    if tier in ["Master", "Grandmaster", "Challenger"]:
                        rank_str = f"{tier} • {s['lp']} LP"
                    else:
                        rank_str = f"{tier} {s['rank']} • {s['lp']} LP"

                    stats_str = f"{s['winrate']}% WR"
                    emoji = self._get_rank_emoji(s["tier"])
                    sort_val = self._get_rank_value({"soloq": s})
                else:
                    rank_str = "Unranked"
                    stats_str = "-"
                    emoji = "⚫"
                    sort_val = -1

                players.append(
                    {
                        "sort_val": sort_val,
                        "emoji": emoji,
                        "name": f"{p['name']}#{p.get('tag', '')}",  # .get car le tag n'est pas toujours dans les vieux caches
                        "rank_text": rank_str,
                        "stats_text": stats_str,
                        "level_text": f"Niv. {p['level']}",
                    }
                )

        if not players:
            return discord.Embed(title="🏆 Classement", description="Aucune donnée disponible (API HS et pas de cache).", color=discord.Color.red())

        # Tri et Affichage (inchangé)
        players.sort(key=lambda x: x["sort_val"], reverse=True)
        top_players = players[:20]

        max_name_len = max([len(p["name"]) for p in top_players] + [10])
        max_rank_len = max([len(p["rank_text"]) for p in top_players] + [10])

        lines = []
        for p in top_players:
            line = f"{p['emoji']} " f"{p['name']:<{max_name_len}} : " f"{p['rank_text']:<{max_rank_len}} - " f"{p['stats_text']}"
            lines.append(line)

        description = "```\n" + "\n".join(lines) + "\n```"

        # Titre et couleur changent si l'API est down
        color = discord.Color.gold() if not api_down else discord.Color.orange()
        title = f"🏆 Leaderboard — {guild.name}"
        if api_down:
            title += " (⚠️ Mode Hors-Ligne)"

        embed = discord.Embed(title=title, description=description, color=color)

        footer_text = "Mis à jour toutes les heures"
        if api_down:
            footer_text = "⚠️ API Riot indisponible • Affichage des dernières données connues"

        embed.set_footer(text=footer_text)
        embed.timestamp = discord.utils.utcnow()

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
        # ON NE FAIT PLUS DE RETURN, juste un gros warning
        logger.warning("⚠️ LOLAPI non défini ! Le bot fonctionnera uniquement avec le CACHE existant.")
        # On peut mettre une fausse clé ou gérer le None dans le client,
        # mais le plus simple est de laisser le code planter dans le try/except plus haut

    # On initialise quand même (si pas de clé, RiotApiClient plantera aux appels,
    # mais notre nouveau try/except dans _create_leaderboard_embed gérera ça)
    client = RiotApiClient(api_key if api_key else "NO_KEY")
    service = LeagueService(client)

    cog = SetupLol(bot, service)
    await bot.add_cog(cog)
    logger.info("Cog SetupLol ajouté au bot.")
