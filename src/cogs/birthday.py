import asyncio
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import discord
import yaml
from discord import app_commands
from discord.ext import commands, tasks
from loguru import logger

paris_tz = ZoneInfo("Europe/Paris")

MOIS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


class Birthday(commands.Cog):
    def __init__(self, bot: commands.Bot, db_path: str = "./data/birthdays.yml", config_path: str = "./data/birthday_config.yml"):
        self.bot = bot
        self.db_path = db_path
        self.config_path = config_path

        # Création des dossiers si nécessaire
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)

    async def cog_load(self):
        """Démarrage des tâches au chargement du cog"""
        self.reminder_task.start()
        logger.success("Task Birthday reminder_task démarrée")

    def cog_unload(self):
        """Arrêt des tâches au déchargement"""
        self.reminder_task.cancel()

    # ============================================================================
    # GESTION DES DONNÉES (YAML)
    # ============================================================================

    def _load_data(self, path: str) -> dict:
        """Charge un fichier YAML."""
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Erreur lecture YAML {path}: {e}")
            return {}

    def _save_data(self, path: str, data: dict):
        """Sauvegarde des données dans un fichier YAML."""
        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        except Exception as e:
            logger.error(f"Erreur écriture YAML {path}: {e}")

    # ============================================================================
    # SETUP & CONFIGURATION
    # ============================================================================

    @app_commands.command(name="setup_birthday", description="Admin: Configure le salon et les messages d'anniversaire")
    @app_commands.default_permissions(administrator=True)
    async def setup_birthday(self, interaction: discord.Interaction):
        """Crée le salon et les messages initiaux."""
        if not interaction.guild:
            return await interaction.response.send_message("❌ Commande serveur uniquement.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        # 1. Création/Récupération du salon
        channel_name = "🎂-anniversaires"
        channel = discord.utils.get(guild.text_channels, name=channel_name)

        if not channel:
            default_role = guild.default_role
            if not default_role:
                return await interaction.followup.send("❌ Impossible de trouver le rôle @everyone.")

            # --- CORRECTION TYPE ICI ---
            # On ajoute '| discord.Object' dans la définition du type pour satisfaire MyPy
            overwrites: dict[discord.Role | discord.Member | discord.Object, discord.PermissionOverwrite] = {
                default_role: discord.PermissionOverwrite(send_messages=False),
                guild.me: discord.PermissionOverwrite(send_messages=True),
            }
            # ---------------------------

            try:
                channel = await guild.create_text_channel(channel_name, overwrites=overwrites)
                logger.info(f"Salon anniversaire créé : {channel.name}")
            except Exception as e:
                logger.error(f"Erreur création salon : {e}")
                return await interaction.followup.send(f"❌ Erreur création salon : {e}")

        # 2. Envoi des messages placeholders
        try:
            # Message Liste Globale
            embed_global = discord.Embed(title="🎉 Anniversaires à venir", description="Chargement...", color=discord.Color.blue())
            msg_global = await channel.send(embed=embed_global)

            # Message Mois en cours
            embed_month = discord.Embed(title="📅 Anniversaires du mois", description="Chargement...", color=discord.Color.purple())
            msg_month = await channel.send(embed=embed_month)

            # 3. Sauvegarde Config
            config = self._load_data(self.config_path)
            config[str(guild.id)] = {"channel_id": channel.id, "msg_global_id": msg_global.id, "msg_month_id": msg_month.id}
            self._save_data(self.config_path, config)

            # 4. Rafraîchissement immédiat
            await self._refresh_displays(guild.id)

            await interaction.followup.send(f"✅ Setup terminé dans {channel.mention} !")

        except Exception as e:
            logger.exception("Erreur lors du setup birthday")
            await interaction.followup.send(f"❌ Erreur interne : {e}")

    # ============================================================================
    # COMMANDES UTILISATEUR
    # ============================================================================

    @app_commands.command(name="set_my_birthday", description="Définit votre date d'anniversaire")
    @app_commands.describe(jour="1-31", mois="1-12", annee="Année de naissance")
    async def set_my_birthday(self, interaction: discord.Interaction, jour: int, mois: int, annee: int):
        # Validation basique
        try:
            date(annee, mois, jour)  # Vérifie si la date existe (ex: pas de 30 février)
            if not (1900 <= annee <= datetime.now().year):
                raise ValueError("Année invalide")
        except ValueError:
            return await interaction.response.send_message("❌ Date invalide.", ephemeral=True)

        birthdays = self._load_data(self.db_path)
        birthdays[str(interaction.user.id)] = {"jour": jour, "mois": mois, "annee": annee, "username": interaction.user.name}
        self._save_data(self.db_path, birthdays)

        logger.info(f"Anniversaire ajouté pour {interaction.user}: {jour}/{mois}/{annee}")
        await interaction.response.send_message(f"✅ Anniversaire enregistré : **{jour:02d}/{mois:02d}/{annee}**", ephemeral=True)

        if interaction.guild:
            await self._refresh_displays(interaction.guild.id)

    @app_commands.command(name="birthday_delete", description="Supprime votre date d'anniversaire")
    async def birthday_delete(self, interaction: discord.Interaction):
        birthdays = self._load_data(self.db_path)
        uid = str(interaction.user.id)

        if uid in birthdays:
            del birthdays[uid]
            self._save_data(self.db_path, birthdays)
            await interaction.response.send_message("🗑️ Anniversaire supprimé.", ephemeral=True)
            if interaction.guild:
                await self._refresh_displays(interaction.guild.id)
        else:
            await interaction.response.send_message("❌ Aucun anniversaire enregistré.", ephemeral=True)

    @app_commands.command(name="birthday_list", description="Affiche la liste des anniversaires (éphémère)")
    async def birthday_list(self, interaction: discord.Interaction):
        """Version éphémère de la liste."""
        embed = await self._generate_global_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ============================================================================
    # LOGIQUE D'AFFICHAGE ET TÂCHES
    # ============================================================================

    async def _refresh_displays(self, guild_id: int):
        """Met à jour les messages persistants."""
        config = self._load_data(self.config_path)
        if str(guild_id) not in config:
            return

        cfg = config[str(guild_id)]
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return

        channel = guild.get_channel(cfg["channel_id"])

        if not isinstance(channel, discord.TextChannel):
            return

        # Update Global List
        try:
            msg = await channel.fetch_message(cfg["msg_global_id"])
            embed = await self._generate_global_embed()
            await msg.edit(embed=embed)
        except discord.NotFound:
            logger.warning("Message birthday global introuvable")

        # Update Month List
        try:
            msg = await channel.fetch_message(cfg["msg_month_id"])
            embed = await self._generate_month_embed()
            await msg.edit(embed=embed)
        except discord.NotFound:
            logger.warning("Message birthday mois introuvable")

    async def _generate_global_embed(self) -> discord.Embed:
        birthdays = self._load_data(self.db_path)
        today = datetime.now(paris_tz).date()

        items = []
        for uid, data in birthdays.items():
            try:
                d_anniv = date(today.year, data["mois"], data["jour"])
                if d_anniv < today:
                    d_anniv = date(today.year + 1, data["mois"], data["jour"])
                items.append((uid, data, d_anniv))
            except ValueError:
                continue

        items.sort(key=lambda x: x[2])  # Tri par date la plus proche

        embed = discord.Embed(title="🎉 Anniversaires à venir", color=discord.Color.blue())
        if not items:
            embed.description = "Aucun anniversaire enregistré."
            return embed

        # Limite de champs Discord (25 max)
        for uid, data, d_anniv in items[:25]:
            delta = (d_anniv - today).days
            age = d_anniv.year - data["annee"]

            if delta == 0:
                jours_str = "**AUJOURD'HUI !** 🎂"
            elif delta == 1:
                jours_str = "Demain !"
            else:
                jours_str = f"dans {delta} jours"

            embed.add_field(name=f"{data['username']}", value=f"{data['jour']:02d}/{data['mois']:02d} ({age} ans) • {jours_str}", inline=False)

        if len(items) > 25:
            embed.set_footer(text=f"Et {len(items)-25} autres...")

        return embed

    async def _generate_month_embed(self) -> discord.Embed:
        birthdays = self._load_data(self.db_path)
        now = datetime.now(paris_tz)
        today = now.date()

        filtered = [v for k, v in birthdays.items() if v["mois"] == now.month]
        filtered.sort(key=lambda x: x["jour"])

        nom_mois = MOIS_FR[now.month - 1].capitalize()
        embed = discord.Embed(title=f"📅 Anniversaires de {nom_mois}", color=discord.Color.purple())

        if not filtered:
            embed.description = f"Aucun anniversaire en {nom_mois}."
        else:
            for data in filtered:
                age = now.year - data["annee"]
                try:
                    d_anniv = date(now.year, data["mois"], data["jour"])
                except ValueError:
                    continue

                if d_anniv < today:
                    status = "✅ Passé"
                elif d_anniv == today:
                    status = "🎂 **C'EST AUJOURD'HUI !**"
                else:
                    status = f"🔜 J-{ (d_anniv - today).days }"

                embed.add_field(name=data["username"], value=f"Le {data['jour']:02d} • {age} ans • {status}", inline=False)
        return embed

    @tasks.loop(minutes=1)
    async def reminder_task(self):
        """Vérifie les anniversaires chaque minute (pour être précis à minuit)."""
        now = datetime.now(paris_tz)

        # On exécute l'action uniquement à 00:00
        if now.hour == 0 and now.minute == 0:
            logger.info("🕛 Minuit : Vérification des anniversaires...")

            # 1. Mise à jour des affichages (changement de mois, de J-X...)
            config = self._load_data(self.config_path)
            for guild_id in config.keys():
                try:
                    await self._refresh_displays(int(guild_id))
                except Exception as e:
                    logger.error(f"Erreur refresh display guild {guild_id}: {e}")

            # 2. Annonce dans le général
            birthdays = self._load_data(self.db_path)
            todays_bd = [(uid, d) for uid, d in birthdays.items() if d["jour"] == now.day and d["mois"] == now.month]

            if todays_bd:
                # Pour chaque serveur configuré, on cherche le channel général
                # Note: Idéalement, l'ID du channel d'annonce devrait être dans la config
                # Ici on fait comme dans votre exemple : recherche par nom "général"
                for guild in self.bot.guilds:
                    channel = discord.utils.get(guild.text_channels, name="général")
                    if channel:
                        mentions = []
                        for uid, data in todays_bd:
                            age = now.year - data["annee"]
                            mentions.append(f"- <@{uid}> ({age} ans) 🎈")

                        try:
                            await channel.send("🎂 **JOYEUX ANNIVERSAIRE !** 🎂\n" + "\n".join(mentions))
                            logger.success(f"Annonce anniversaire envoyée sur {guild.name}")
                        except Exception as e:
                            logger.error(f"Erreur envoi message anniv: {e}")

    @reminder_task.before_loop
    async def before_reminder(self):
        await self.bot.wait_until_ready()
        # Synchro pour attendre la seconde 00
        now = datetime.now()
        await asyncio.sleep(60 - now.second)


async def setup(bot):
    await bot.add_cog(Birthday(bot))
    logger.info("Cog Birthday ajouté au bot.")
