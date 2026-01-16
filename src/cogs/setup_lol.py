# src/cogs/setup_lol.py - Version améliorée avec nouveaux leaderboards

import os
from datetime import datetime, timedelta
from typing import Any, Optional

import discord
import yaml
from discord import app_commands
from discord.ext import commands, tasks
from loguru import logger

from src.lol.client import RiotApiClient
from src.lol.exceptions import InvalidApiKey, PlayerNotFound, RateLimited
from src.lol.service import LeagueService


class SetupLol(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        league_service,
        db_path: str = "./data/users.yml",
        config_path: str = "./data/config.yml",
        history_path: str = "./data/lp_history.yml",
        start_tasks: bool = True,
    ):
        self.bot = bot
        self.league_service = league_service
        self.db_path = db_path
        self.config_path = config_path
        self.history_path = history_path

        # Création des dossiers
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.history_path), exist_ok=True)

        self._start_tasks = start_tasks

    async def cog_load(self):
        """Appelé automatiquement quand le cog est chargé"""
        self.refresh_leaderboard.start()
        self.track_lp_changes.start()
        logger.success("Tasks refresh_leaderboard et track_lp_changes démarrées")

    def cog_unload(self):
        """Appelé quand le cog est déchargé"""
        self.refresh_leaderboard.cancel()
        self.track_lp_changes.cancel()

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

        user_entry = {"puuid": puuid, "pseudo": pseudo, "tag": tag}

        if stats:
            user_entry["cached_stats"] = stats
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

    def _save_config(self, guild_id: int, channel_id: int, message_id: int, queue_type: str = "soloq"):
        """Sauvegarde la config du leaderboard permanent."""
        config: dict[str, Any] = {}
        if os.path.exists(self.config_path):
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}

        if "leaderboards" not in config:
            config["leaderboards"] = {}

        if str(guild_id) not in config["leaderboards"]:
            config["leaderboards"][str(guild_id)] = {}

        config["leaderboards"][str(guild_id)][queue_type] = {
            "channel_id": channel_id,
            "message_id": message_id,
        }

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False)

        logger.success(f"Config leaderboard {queue_type} sauvegardée pour guild {guild_id}")

    def _load_config(self) -> dict:
        """Charge la configuration."""
        if not os.path.exists(self.config_path):
            return {}

        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _save_lp_snapshot(self, discord_id: int, queue_type: str, lp_data: dict):
        """Sauvegarde un snapshot de LP pour le tracking."""
        history: dict[str, Any] = {}

        if os.path.exists(self.history_path):
            with open(self.history_path, "r", encoding="utf-8") as f:
                history = yaml.safe_load(f) or {}

        user_key = str(discord_id)
        if user_key not in history:
            history[user_key] = {}

        if queue_type not in history[user_key]:
            history[user_key][queue_type] = []

        # Ajouter le snapshot avec timestamp
        snapshot = {
            "timestamp": datetime.utcnow().isoformat(),
            "tier": lp_data["tier"],
            "rank": lp_data.get("rank", "I"),
            "lp": lp_data["lp"],
            "wins": lp_data["wins"],
            "losses": lp_data["losses"],
        }

        history[user_key][queue_type].append(snapshot)

        # Garder seulement les 7 derniers jours
        cutoff = datetime.utcnow() - timedelta(days=7)
        history[user_key][queue_type] = [s for s in history[user_key][queue_type] if datetime.fromisoformat(s["timestamp"]) > cutoff]

        with open(self.history_path, "w", encoding="utf-8") as f:
            yaml.dump(history, f, default_flow_style=False)

    def _load_lp_history(self) -> dict:
        """Charge l'historique de LP."""
        if not os.path.exists(self.history_path):
            return {}

        with open(self.history_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _calculate_lp_change(self, discord_id: int, queue_type: str, period: str = "day") -> Optional[int]:
        """Calcule le changement de LP sur une période donnée."""
        history = self._load_lp_history()
        user_key = str(discord_id)

        if user_key not in history or queue_type not in history[user_key]:
            return None

        snapshots = history[user_key][queue_type]
        if not snapshots:
            return None

        # Déterminer la période
        if period == "day":
            cutoff = datetime.utcnow() - timedelta(days=1)
        else:  # hour
            cutoff = datetime.utcnow() - timedelta(hours=1)

        # Trouver le snapshot le plus récent dans la période
        old_snapshot = None
        for snapshot in snapshots:
            ts = datetime.fromisoformat(snapshot["timestamp"])
            if ts <= cutoff:
                old_snapshot = snapshot

        if not old_snapshot:
            return None

        current_snapshot = snapshots[-1]

        # Calculer la différence de LP
        old_total_lp = self._get_total_lp(old_snapshot)
        current_total_lp = self._get_total_lp(current_snapshot)

        return current_total_lp - old_total_lp

    def _get_total_lp(self, rank_data: dict) -> int:  # <--- Ajout du type de retour
        """Convertit un rang en LP total pour comparaison."""
        tier_values = {
            "IRON": 0,
            "BRONZE": 400,
            "SILVER": 800,
            "GOLD": 1200,
            "PLATINUM": 1600,
            "EMERALD": 2000,
            "DIAMOND": 2400,
            "MASTER": 2800,
            "GRANDMASTER": 3200,
            "CHALLENGER": 3600,
        }
        rank_values = {"IV": 0, "III": 100, "II": 200, "I": 300}

        tier = rank_data["tier"]
        rank = rank_data.get("rank", "I")
        lp = int(rank_data["lp"])  # <--- Conversion explicite en int

        if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]:
            return tier_values[tier] + lp

        return tier_values.get(tier, 0) + rank_values.get(rank, 0) + lp

    async def _link_account(self, interaction: discord.Interaction, pseudo: str, tag: str):
        await interaction.response.defer(ephemeral=True)

        try:
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
            profile = self.league_service.make_profile(puuid)

            embed = discord.Embed(
                title="📊 Profil League of Legends",
                description=f"**{profile['name']}#{profile['tag']}**",
                color=discord.Color.blue(),
            )

            icon_id = profile["profileIconId"]
            icon_url = f"https://ddragon.leagueoflegends.com/cdn/14.1.1/img/profileicon/{icon_id}.png"
            embed.set_thumbnail(url=icon_url)

            embed.add_field(name="📈 Niveau", value=f"**{profile['level']}**", inline=True)

            # Stats Ranked Solo/Duo avec changement de LP
            soloq = profile["rankedStats"]["soloq"]
            if soloq:
                rank_emoji = self._get_rank_emoji(soloq["tier"])
                lp_change_day = self._calculate_lp_change(target.id, "soloq", "day")
                lp_change_str = ""
                if lp_change_day is not None:
                    sign = "+" if lp_change_day >= 0 else ""
                    lp_change_str = f"\n📊 {sign}{lp_change_day} LP (24h)"

                soloq_text = (
                    f"{rank_emoji} **{soloq['tier'].title()} {soloq['rank']}** - {soloq['lp']} LP\n"
                    f"🎮 {soloq['wins']}W / {soloq['losses']}L ({soloq['winrate']}%)\n"
                    f"📊 {soloq['wins'] + soloq['losses']} parties jouées{lp_change_str}"
                )
            else:
                soloq_text = "Non classé"

            embed.add_field(name="🏆 Solo/Duo", value=soloq_text, inline=False)

            # Stats Ranked Flex avec changement de LP
            flex = profile["rankedStats"]["flex"]
            if flex:
                rank_emoji = self._get_rank_emoji(flex["tier"])
                lp_change_day = self._calculate_lp_change(target.id, "flex", "day")
                lp_change_str = ""
                if lp_change_day is not None:
                    sign = "+" if lp_change_day >= 0 else ""
                    lp_change_str = f"\n📊 {sign}{lp_change_day} LP (24h)"

                flex_text = (
                    f"{rank_emoji} **{flex['tier'].title()} {flex['rank']}** - {flex['lp']} LP\n"
                    f"🎮 {flex['wins']}W / {flex['losses']}L ({flex['winrate']}%){lp_change_str}"
                )
            else:
                flex_text = "Non classé"

            embed.add_field(name="💥 Flex 5v5", value=flex_text, inline=False)

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
    @app_commands.describe(channel="Le salon où afficher le leaderboard permanent", queue_type="Type de file (Solo/Duo ou Flex)")
    @app_commands.choices(queue_type=[app_commands.Choice(name="Solo/Duo", value="soloq"), app_commands.Choice(name="Flex 5v5", value="flex")])
    @app_commands.default_permissions(administrator=True)
    async def lol_leaderboard_setup(self, interaction: discord.Interaction, channel: discord.TextChannel, queue_type: str = "soloq"):
        """Configure un leaderboard permanent."""
        if not interaction.guild:
            return await interaction.response.send_message("❌ Cette commande doit être utilisée sur un serveur.", ephemeral=True)

        logger.info(f"Setup leaderboard {queue_type} par {interaction.user} dans {channel}")
        await interaction.response.defer(ephemeral=True)

        try:
            embed = await self._create_leaderboard_embed(interaction.guild, queue_type)
            message = await channel.send(embed=embed)
            self._save_config(interaction.guild.id, channel.id, message.id, queue_type)

            queue_name = "Solo/Duo" if queue_type == "soloq" else "Flex 5v5"
            await interaction.followup.send(
                f"✅ Leaderboard {queue_name} permanent créé dans {channel.mention}\n" f"🔄 Il se rafraîchira automatiquement toutes les heures.",
                ephemeral=True,
            )

        except Exception as e:
            logger.exception("Erreur lors du setup du leaderboard")
            await interaction.followup.send(f"❌ Erreur lors de la création du leaderboard : {e}", ephemeral=True)

    @app_commands.command(name="lol_lp_recap", description="Affiche le récapitulatif de gain/perte de LP")
    @app_commands.describe(period="Période de récapitulatif", queue_type="Type de file")
    @app_commands.choices(
        period=[app_commands.Choice(name="Dernière heure", value="hour"), app_commands.Choice(name="Dernières 24 heures", value="day")],
        queue_type=[app_commands.Choice(name="Solo/Duo", value="soloq"), app_commands.Choice(name="Flex 5v5", value="flex")],
    )
    async def lol_lp_recap(self, interaction: discord.Interaction, period: str = "day", queue_type: str = "soloq"):
        """Affiche un récapitulatif des changements de LP."""
        if not interaction.guild:
            return await interaction.response.send_message("❌ Cette commande doit être utilisée sur un serveur.", ephemeral=True)

        await interaction.response.defer()

        users = self._load_users()
        # Explicit type hinting for the list ensures mypy knows the structure
        changes: list[dict[str, Any]] = []

        for d_id, u_data in users.items():
            member = interaction.guild.get_member(int(d_id))
            if not member:
                continue

            lp_change = self._calculate_lp_change(int(d_id), queue_type, period)
            if lp_change is None:
                continue

            changes.append({"member": member, "name": f"{u_data['pseudo']}#{u_data['tag']}", "change": lp_change})

        if not changes:
            period_text = "de la dernière heure" if period == "hour" else "des dernières 24 heures"
            queue_name = "Solo/Duo" if queue_type == "soloq" else "Flex 5v5"
            embed_error = discord.Embed(
                title="❌ Aucune donnée disponible",
                description=f"Aucune donnée de LP disponible pour la période {period_text} en {queue_name}.",
                color=discord.Color.red(),
            )
            return await interaction.followup.send(embed=embed_error)

        # Fix: Cast to int in lambda so sort knows how to compare
        changes.sort(key=lambda x: int(x["change"]), reverse=True)

        # Créer l'embed
        period_text = "Dernière heure" if period == "hour" else "Dernières 24h"
        queue_name = "Solo/Duo" if queue_type == "soloq" else "Flex 5v5"

        embed = discord.Embed(title=f"📊 Récapitulatif LP - {queue_name}", description=f"**{period_text}**", color=discord.Color.gold())

        lines = []
        for i, change_data in enumerate(changes[:20], 1):
            # Fix: Explicitly extract as int to satisfy mypy comparators
            amount = int(change_data["change"])

            sign = "+" if amount >= 0 else ""
            emoji = "📈" if amount > 0 else "📉" if amount < 0 else "➖"
            lines.append(f"{i}. {emoji} **{change_data['name']}** : {sign}{amount} LP")

        # Fix: Handle Optional[str] for embed.description
        current_desc = embed.description or ""
        embed.description = current_desc + "\n\n" + "\n".join(lines)
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed)

    # ============================================================================
    # TÂCHES PÉRIODIQUES
    # ============================================================================

    @tasks.loop(hours=1)
    async def refresh_leaderboard(self):
        """Rafraîchit tous les leaderboards permanents toutes les heures."""
        logger.info("Début du refresh des leaderboards permanents")

        config = self._load_config()
        if "leaderboards" not in config:
            return

        for guild_id, lb_configs in config["leaderboards"].items():
            try:
                guild = self.bot.get_guild(int(guild_id))
                if not guild:
                    logger.warning(f"Guild {guild_id} introuvable")
                    continue

                # Rafraîchir chaque type de leaderboard (soloq et flex)
                for queue_type, lb_config in lb_configs.items():
                    try:
                        channel = guild.get_channel(lb_config["channel_id"])
                        if not channel:
                            logger.warning(f"Channel {lb_config['channel_id']} introuvable")
                            continue

                        try:
                            message = await channel.fetch_message(lb_config["message_id"])
                        except discord.NotFound:
                            logger.warning(f"Message leaderboard {lb_config['message_id']} introuvable")
                            continue

                        embed = await self._create_leaderboard_embed(guild, queue_type)
                        await message.edit(embed=embed)
                        logger.success(f"Leaderboard {queue_type} rafraîchi pour guild {guild_id}")

                    except Exception:
                        logger.exception(f"Erreur lors du refresh du leaderboard {queue_type} pour guild {guild_id}")

            except Exception:
                logger.exception(f"Erreur lors du refresh des leaderboards pour guild {guild_id}")

    @tasks.loop(hours=1)
    async def track_lp_changes(self):
        """Enregistre les changements de LP toutes les heures."""
        logger.info("Début du tracking de LP")

        users = self._load_users()

        for d_id, u_data in users.items():
            try:
                profile = self.league_service.make_profile(u_data["puuid"])

                # Enregistrer soloq
                if profile["rankedStats"]["soloq"]:
                    self._save_lp_snapshot(int(d_id), "soloq", profile["rankedStats"]["soloq"])

                # Enregistrer flex
                if profile["rankedStats"]["flex"]:
                    self._save_lp_snapshot(int(d_id), "flex", profile["rankedStats"]["flex"])

                logger.debug(f"LP tracked pour {u_data['pseudo']}#{u_data['tag']}")

            except Exception as e:
                logger.warning(f"Erreur tracking LP pour {u_data['pseudo']}: {e}")

    @refresh_leaderboard.before_loop
    @track_lp_changes.before_loop
    async def before_tasks(self):
        """Attend que le bot soit prêt avant de démarrer les boucles."""
        await self.bot.wait_until_ready()

    # ============================================================================
    # FONCTIONS UTILITAIRES
    # ============================================================================

    async def _create_leaderboard_embed(self, guild: discord.Guild, queue_type: str = "soloq") -> discord.Embed:
        """Génère le leaderboard avec le nouveau format."""
        users = self._load_users()
        players: list[dict[str, Any]] = []
        api_down = False

        for d_id, u_data in users.items():
            member = guild.get_member(int(d_id))
            if not member:
                continue

            p = None
            try:
                profile = self.league_service.make_profile(u_data["puuid"])

                s = profile["rankedStats"][queue_type]
                cached_data = {"name": profile["name"], "tag": profile["tag"], "level": profile["level"], queue_type: s}

                self._save_user(int(d_id), u_data["puuid"], u_data["pseudo"], u_data["tag"], stats=cached_data)
                p = cached_data

            except Exception:
                # logger.warning(...)
                api_down = True
                if "cached_stats" in u_data:
                    p = u_data["cached_stats"]
                else:
                    continue

            if p:
                s = p.get(queue_type)
                if s:
                    tier = s["tier"]
                    rank = s.get("rank", "")
                    lp = s["lp"]

                    # Nouveau format : P I au lieu de Platinum I
                    tier_short = tier[0]  # Première lettre
                    if tier in ["MASTER", "GRANDMASTER", "CHALLENGER"]:
                        rank_str = f"{tier_short} • {lp} LP"
                    else:
                        rank_str = f"{tier_short} {rank} • {lp} LP"

                    winrate = s["winrate"]

                    # --- MODIFICATION ICI : Définition du préfixe de ligne ---
                    if winrate < 50:
                        line_prefix = "-"  # Rendra la ligne ROUGE
                    else:
                        line_prefix = "+"  # Rendra la ligne VERTE

                    wr_str = f"{winrate}% WR"
                    # ---------------------------------------------------------

                    # Nombre de games
                    games = s["wins"] + s["losses"]
                    games_str = f"{games:02d}"

                    sort_val = self._get_rank_value({queue_type: s})

                    players.append(
                        {
                            "sort_val": sort_val,
                            "line_prefix": line_prefix,  # On stocke le préfixe
                            "name": f"{p['name']}#{p.get('tag', '')}",
                            "rank_text": rank_str,
                            "wr_text": wr_str,
                            "games_text": games_str,
                        }
                    )
                else:
                    players.append(
                        {
                            "sort_val": -1,
                            "line_prefix": "#",  # Gris en diff
                            "name": f"{p['name']}#{p.get('tag', '')}",
                            "rank_text": "Unranked",
                            "wr_text": "-",
                            "games_text": "00",
                        }
                    )

        if not players:
            return discord.Embed(title="🏆 Classement", description="Aucune donnée disponible.", color=discord.Color.red())

        players.sort(key=lambda x: x["sort_val"], reverse=True)
        top_players = players[:20]

        # Calculer les largeurs maximales
        max_name_len = max([len(p["name"]) for p in top_players] + [10])
        max_rank_len = max([len(p["rank_text"]) for p in top_players] + [10])
        max_wr_len = max([len(p["wr_text"]) for p in top_players] + [10])

        lines = []
        for p in top_players:
            # --- MODIFICATION ICI : Construction de la ligne diff ---
            # Le préfixe (+ ou -) doit être le tout premier caractère
            line = f"{p['line_prefix']} {p['name']:<{max_name_len}} : {p['rank_text']:<{max_rank_len}} - {p['wr_text']:<{max_wr_len}} - {p['games_text']}"
            lines.append(line)

        # --- MODIFICATION ICI : Changement du type de bloc de code ---
        description = "```diff\n" + "\n".join(lines) + "\n```"

        queue_name = "Solo/Duo" if queue_type == "soloq" else "Flex 5v5"
        color = discord.Color.gold() if not api_down else discord.Color.orange()
        title = f"🏆 Leaderboard {queue_name} — {guild.name}"
        if api_down:
            title += " (⚠️ Mode Hors-Ligne)"

        embed = discord.Embed(title=title, description=description, color=color)

        footer_text = "Mis à jour toutes les heures • Rouge < 50% • Vert > 50%"
        if api_down:
            footer_text = "⚠️ API Riot indisponible • Affichage des dernières données connues"

        embed.set_footer(text=footer_text)
        embed.timestamp = discord.utils.utcnow()

        return embed

    def _get_rank_value(self, player: dict) -> int:
        """Retourne une valeur numérique pour trier les joueurs par rang."""
        # Détecter le type de queue (soloq ou flex)
        queue_data = player.get("soloq") or player.get("flex")

        if not queue_data:
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

        tier = queue_data["tier"]
        rank = queue_data.get("rank", "I")
        lp = int(queue_data["lp"])

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
            "MASTER": "🟣",
            "GRANDMASTER": "🔴",
            "CHALLENGER": "🏆",
        }
        return tier_emojis.get(tier.upper(), "❓")


async def setup(bot):
    api_key = os.getenv("LOLAPI")

    if not api_key:
        logger.warning("⚠️ LOLAPI non défini ! Le bot fonctionnera uniquement avec le CACHE existant.")

    client = RiotApiClient(api_key if api_key else "NO_KEY")
    service = LeagueService(client)

    cog = SetupLol(bot, service)
    await bot.add_cog(cog)
    logger.info("Cog SetupLol ajouté au bot.")
