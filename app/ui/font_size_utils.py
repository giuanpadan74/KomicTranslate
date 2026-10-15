"""Helpers per la gestione delle dimensioni font con step 0.5.

Il dropdown della sidebar non contiene valori hardcoded: mostra i numeri
nel range [min, max] con intervallo 0.5.
Esempio: min=9, max=12 -> 9, 9.5, 10, 10.5, 11, 11.5, 12.
"""


def parse_font_size(text, default=12.0):
    """Converte il testo del dropdown in float.

    Accetta sia il punto che la virgola come separatore decimale
    (es. '9.5' e '9,5') per compatibilita' con la notazione italiana.
    """
    try:
        if text is None:
            return float(default)
        s = str(text).strip().replace(',', '.')
        if not s:
            return float(default)
        return float(s)
    except (ValueError, TypeError):
        try:
            return float(default)
        except (ValueError, TypeError):
            return 12.0


def format_font_size(value):
    """Formatta un font size: '9' per interi, '9.5' altrimenti."""
    try:
        v = float(str(value).replace(',', '.')) if isinstance(value, str) else float(value)
    except (ValueError, TypeError):
        return str(value)
    if abs(v - round(v)) < 1e-9:
        return str(int(round(v)))
    # Rimuove zeri superflui (es. 9.50 -> 9.5)
    s = f"{v:.2f}".rstrip('0').rstrip('.')
    return s


def font_size_range(min_value, max_value, step=0.5):
    """Restituisce la lista di stringhe nel range [min, max] con passo step."""
    try:
        lo = float(min_value)
    except (ValueError, TypeError):
        lo = 9.0
    try:
        hi = float(max_value)
    except (ValueError, TypeError):
        hi = 40.0
    if lo > hi:
        lo, hi = hi, lo
    if step <= 0:
        step = 0.5
    values = []
    # Numero di passi arrotondato per evitare errori float
    n_steps = int(round((hi - lo) / step))
    for i in range(n_steps + 1):
        v = lo + i * step
        # Clamp per errori di arrotondamento sull'ultimo valore
        if v > hi + 1e-9:
            break
        if i == n_steps:
            v = hi
        values.append(format_font_size(v))
    if not values:
        values = [format_font_size(lo)]
    return values
