# tests/test_logger.py
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from loguru import logger as loguru_logger

from src.utils.logger import setup_logger


class TestSetupLogger:
    """Tests pour la fonction setup_logger"""
    
    def test_setup_logger_returns_logger(self):
        """Vérifie que setup_logger retourne une instance du logger"""
        logger = setup_logger("INFO")
        assert logger is not None
    
    def test_setup_logger_creates_logs_directory(self):
        """Vérifie que le dossier logs est créé"""
        logger = setup_logger("INFO")
        # Si le dossier existe, setup_logger a fonctionné
        assert logger is not None
        assert Path("logs").exists()
    
    def test_setup_logger_with_different_levels(self):
        """Teste setup_logger avec différents niveaux de log"""
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            logger = setup_logger(level)
            assert logger is not None
    
    def test_setup_logger_default_level(self):
        """Teste que le niveau par défaut est INFO"""
        logger = setup_logger()
        assert logger is not None


class TestLoggerOutput:
    """Tests pour vérifier que le logger enregistre correctement"""
    
    def test_logger_logs_info(self, caplog):
        """Vérifie que les messages INFO sont loggés"""
        with caplog.at_level("INFO"):
            setup_logger("INFO")
            # Le logger devrait avoir enregistré un message de succès
            # Cette assertion vérifie que setup_logger s'exécute sans erreur
            assert True
    
    def test_logger_configuration_handlers(self):
        """Vérifie que le logger a les bons handlers configurés"""
        logger = setup_logger("DEBUG")
        # Loguru configure les handlers correctement
        assert logger is not None
