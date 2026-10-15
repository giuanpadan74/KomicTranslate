"""
Sub-modulo dedicato al processo di sbianchetta (pulizia balloon senza traduzione).
Espone la funzione `sbianchetta_batch_process` da usare come entry-point nel thread.
"""
from .step import sbianchetta_batch_process

__all__ = ["sbianchetta_batch_process"]