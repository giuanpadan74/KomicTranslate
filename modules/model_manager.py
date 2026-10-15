"""Shim di compatibilita': il manager canonico e' modules.utils.model_manager.

Questo modulo esiste solo per non rompere import storici
(`from modules.model_manager import ...`). Non aggiungere logica qui.
"""
from modules.utils.model_manager import ModelInfo, ModelStatus, ModelManager, model_manager  # noqa: F401
