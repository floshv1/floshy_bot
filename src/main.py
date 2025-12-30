# src/main.py
import asyncio
import os
import sys
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv
from loguru import logger

from .utils.logger import setup_logger

# Charger les variables d'environnement
load_dotenv()


class DiscordBot(commands.Bot):
    """Bot Discord simple pour démarrer"""

    def __init__(self):
        # Configuration des intents
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            status=discord.Status.online,
        )

    async def setup_hook(self):
        """Appelé au démarrage du bot avant la connexion"""
        logger.info("Chargement des cogs...")
        await self.load_cogs()

        logger.info("Synchronisation des commandes slash...")
        try:
            synced = await self.tree.sync()
            logger.success(f"{len(synced)} commandes synchronisées")
        except Exception as e:
            logger.error(f"Erreur lors de la synchronisation : {e}")

    async def load_cogs(self):
        """Charge tous les cogs depuis le dossier cogs/"""
        cogs_path = Path(__file__).parent / "cogs"

        loaded = 0
        failed = 0

        for cog_file in cogs_path.glob("*.py"):
            if cog_file.stem == "__init__":
                continue

            try:
                await self.load_extension(f"src.cogs.{cog_file.stem}")
                logger.success(f"Cog chargé : {cog_file.stem}")
                loaded += 1
            except Exception as e:
                logger.error(f"Erreur avec {cog_file.stem} : {e}")
                failed += 1

        logger.info(f"Cogs chargés : {loaded} | Échecs : {failed}")

    async def on_ready(self):
        """Appelé quand le bot est connecté et prêt"""
        logger.info("━" * 50)
        logger.success(f"Bot connecté : {self.user.name}")
        logger.info(f"ID : {self.user.id}")
        logger.info(f"Serveurs : {len(self.guilds)}")
        logger.info(f"Utilisateurs : {sum(g.member_count for g in self.guilds)}")
        logger.info(f"discord.py : {discord.__version__}")

        # Changer le statut (online, idle, dnd, invisible)
        activity = discord.Activity(type=discord.ActivityType.playing, name="Charbonne")
        await self.change_presence(activity=activity, status=discord.Status.online)

        logger.info("Status : online")

        logger.info("━" * 50)

    async def on_command(self, ctx):
        """Log quand une commande est utilisée"""
        logger.debug(
            f"Commande '{ctx.command}' utilisée par {ctx.author} "
            f"dans #{ctx.channel} ({ctx.guild})"
        )

    async def on_command_error(self, ctx, error):
        """Gestion globale des erreurs de commandes"""

        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingPermissions):
            logger.warning(
                f"{ctx.author} a tenté d'utiliser {ctx.command} " f"sans permissions"
            )
            await ctx.reply("❌ Tu n'as pas les permissions nécessaires !")
            return

        if isinstance(error, commands.MissingRequiredArgument):
            logger.warning(f"Argument manquant pour {ctx.command} : {error.param.name}")
            await ctx.reply(f"❌ Argument manquant : `{error.param.name}`")
            return

        if isinstance(error, commands.CommandOnCooldown):
            logger.debug(f"{ctx.author} en cooldown pour {ctx.command}")
            await ctx.reply(f"⏳ Cooldown ! Réessaie dans {error.retry_after:.1f}s")
            return

        # Log et affiche les autres erreurs
        logger.exception(f"Erreur non gérée dans {ctx.command} : {error}")
        await ctx.reply(f"❌ Une erreur est survenue : {error}")

    async def on_error(self, event_method: str, *args, **kwargs):
        """Gestion des erreurs d'événements"""
        logger.exception(f"Erreur dans l'événement {event_method}")


async def main():
    """Fonction principale pour lancer le bot"""

    # Configurer le logger
    log_level = os.getenv("LOG_LEVEL", "INFO")
    setup_logger(log_level)

    # Vérifier que le token existe
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.critical("DISCORD_TOKEN non trouvé dans .env")
        sys.exit(1)

    # Créer et lancer le bot
    bot = DiscordBot()

    try:
        logger.info("Démarrage du bot...")
        await bot.start(token)
    except KeyboardInterrupt:
        logger.warning("Interruption clavier détectée")
    except discord.LoginFailure:
        logger.critical("Token invalide ! Vérifie ton .env")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Erreur fatale : {e}")
        logger.exception("Stacktrace complète :")
        sys.exit(1)
    finally:
        logger.info("Fermeture du bot...")
        logger.success("Bot arrêté proprement")


if __name__ == "__main__":
    asyncio.run(main())
