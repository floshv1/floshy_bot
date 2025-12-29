# src/utils/logger.py
import sys
from pathlib import Path
from loguru import logger


def setup_logger(log_level: str = "INFO"):
    """Configure Loguru pour le bot"""
    
    # Créer le dossier logs
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Retirer le handler par défaut
    logger.remove()
    
    # Handler pour la console avec couleurs
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>",
        level=log_level,
        colorize=True,
    )
    
    # Handler pour le fichier général
    logger.add(
        log_dir / "bot.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        rotation="10 MB",  # Rotation à 10MB
        retention="1 week",  # Garder 1 semaine
        compression="zip",  # Compresser les anciens logs
        encoding="utf-8",
    )
    
    # Handler pour les erreurs uniquement
    logger.add(
        log_dir / "errors.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="ERROR",
        rotation="5 MB",
        retention="2 weeks",
        compression="zip",
        encoding="utf-8",
        backtrace=True,  # Trace complète des erreurs
        diagnose=True,   # Informations de diagnostic
    )
    
    logger.info("Logger configuré avec succès")
    return logger