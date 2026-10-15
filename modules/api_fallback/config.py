"""Pattern per il riconoscimento degli errori API.

Un tempo questo file conteneva anche la configurazione della rotazione
delle chiavi per provider (OpenAI, Anthropic, ...). Con la rimozione
dello strato LLM resta solo ciò che serve a error_detector.py: i pattern
per distinguere "quota esaurita" / "rate limit" / "errore di auth" da
un errore transitorio, cosi' da attivare o no il fallback verso DocTR.
"""
from typing import Dict, List

FALLBACK_CONFIG: Dict[str, object] = {
    # Cooldown di base (secondi) prima di ritentare un'operazione fallita.
    'cooldown_period': 60,

    # Pattern che indicano che la quota del provider e' esaurita.
    'quota_error_patterns': [
        r'quota',
        r'rate.*exceeded',
        r'resource.*exhausted',
        r'usage.*limit',
        r'insufficient.*quota',
        r'you exceeded your current quota',
        r'billing',
    ],

    # Pattern che indicano rate limiting temporaneo.
    'rate_limit_patterns': [
        r'rate.?limit',
        r'too many requests',
        r'429',
        r'slow down',
    ],

    # Pattern che indicano credenziali non valide.
    'auth_error_patterns': [
        r'unauthorized',
        r'invalid.*api.*key',
        r'invalid.*token',
        r'authentication',
        r'permission.*denied',
        r'401',
        r'403',
    ],
}

# Rimosso: PROVIDER_CONFIG, che mappava ogni provider LLM ai suoi
# endpoint e alle sue chiavi. Non resta piu' nessun provider online da
# distinguere, quindi error_detector usa solo i pattern generici sopra.
PROVIDER_CONFIG: Dict[str, Dict[str, object]] = {}
