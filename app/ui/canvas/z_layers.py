"""Gerarchia canonica dei layer Z del canvas.

Questa e' la fonte unica per i valori ``z`` usati dal canvas. Quando un
elemento deve cambiare livello, usare sempre queste costanti invece di
numeri hardcoded.

Tabella tecnica definitiva ``elemento -> costante -> z``:

+-----------------------------+--------------------+-------+
| Elemento                    | Costante           | Z     |
+-----------------------------+--------------------+-------+
| Sfondo pagina               | BACKGROUND_Z       | 0.0   |
| Tratti brush / inpaint      | BRUSH_STROKE_Z     | 1.0   |
| Box di lavoro / selezione   | WORK_SELECTION_Z   | 2.0   |
| Overlay poligonale          | POLYGON_OVERLAY_Z  | 3.0   |
| Testo renderizzato          | TEXT_BOX_Z         | 4.0   |
| Forme importate min         | IMPORTED_SHAPE_LAYER_MIN | 3.10 |
| Forme chiuse PNG / SVG      | IMPORTED_SHAPE_LAYER_DEFAULT | 3.50 |
| Forme importate max         | IMPORTED_SHAPE_LAYER_MAX | 3.99 |
| Marker UI min               | MARKER_LAYER_MIN   | 10.0  |
| Marker numerici             | MARKER_LAYER_DEFAULT | 10.0 |
| Marker UI max               | MARKER_LAYER_MAX   | 19.99 |
| Handle UI min               | HANDLE_LAYER_MIN   | 100.0 |
| Handle UI di move / resize  | HANDLE_LAYER_DEFAULT | 100.0 |
| Handle UI max               | HANDLE_LAYER_MAX   | 199.99 |
| Handle poligono min         | POLYGON_HANDLE_LAYER_MIN | 200.0 |
| Handle vertici poligonali   | POLYGON_HANDLE_LAYER_DEFAULT | 200.0 |
| Handle poligono max         | POLYGON_HANDLE_LAYER_MAX | 299.99 |
+-----------------------------+--------------------+-------+

Regole pratiche:
- I layer contenuto stanno sotto i layer UI.
- I layer UI usano sottorange separati per marker e handle.
- Marker e handle devono restare sempre sopra il contenuto.
- Le forme importate usano un range dedicato separato dai layer di lavoro.
- Sopra le forme importate deve stare solo il testo tra i layer contenuto.
"""

# Contenuto base
BACKGROUND_Z = 0.0
BRUSH_STROKE_Z = 1.0
WORK_SELECTION_Z = 2.0
POLYGON_OVERLAY_Z = 3.0
TEXT_BOX_Z = 4.0
WORK_LAYER_MAX = TEXT_BOX_Z

# Forme importate: sopra i layer di lavoro ma sotto il testo
IMPORTED_SHAPE_LAYER_MIN = 3.10
IMPORTED_SHAPE_LAYER_DEFAULT = 3.50
IMPORTED_SHAPE_LAYER_MAX = 3.99
ACTIVE_IMPORTED_SHAPE_PREVIEW_Z = 4.01

# Alias mantenuto per compatibilita' con il codice esistente
CLOSED_SHAPE_Z = IMPORTED_SHAPE_LAYER_DEFAULT

# UI di supporto e modifica: sottorange dedicati
MARKER_LAYER_MIN = 10.0
MARKER_LAYER_DEFAULT = 10.0
MARKER_LAYER_MAX = 19.99

HANDLE_LAYER_MIN = 100.0
HANDLE_LAYER_DEFAULT = 100.0
HANDLE_LAYER_MAX = 199.99

POLYGON_HANDLE_LAYER_MIN = 200.0
POLYGON_HANDLE_LAYER_DEFAULT = 200.0
POLYGON_HANDLE_LAYER_MAX = 299.99

# Alias mantenuti per compatibilita' con il codice esistente
MARKER_Z = MARKER_LAYER_DEFAULT
HANDLE_Z = HANDLE_LAYER_DEFAULT
POLYGON_HANDLE_Z = POLYGON_HANDLE_LAYER_DEFAULT


def clamp_imported_shape_z(z_value):
    """Mantiene un valore Z nel range dedicato alle forme importate."""
    return max(IMPORTED_SHAPE_LAYER_MIN, min(float(z_value), IMPORTED_SHAPE_LAYER_MAX))


def clamp_marker_z(z_value):
    """Mantiene un valore Z nel range dedicato ai marker UI."""
    return max(MARKER_LAYER_MIN, min(float(z_value), MARKER_LAYER_MAX))


def clamp_handle_z(z_value):
    """Mantiene un valore Z nel range dedicato agli handle UI."""
    return max(HANDLE_LAYER_MIN, min(float(z_value), HANDLE_LAYER_MAX))


def clamp_polygon_handle_z(z_value):
    """Mantiene un valore Z nel range dedicato agli handle del poligono."""
    return max(
        POLYGON_HANDLE_LAYER_MIN,
        min(float(z_value), POLYGON_HANDLE_LAYER_MAX),
    )
