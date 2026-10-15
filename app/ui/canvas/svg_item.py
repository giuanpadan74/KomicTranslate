import os
import xml.etree.ElementTree as ET
from PySide6.QtCore import Qt, QRectF, QPointF, QSize, QSizeF, Signal, QByteArray
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QTransform
from PySide6.QtWidgets import QGraphicsItem, QGraphicsObject
from PySide6.QtSvg import QSvgRenderer
from .svg_style_utils import (
    svg_content_uses_complex_styling,
    svg_root_has_single_native_shape,
)
from .z_layers import (
    ACTIVE_IMPORTED_SHAPE_PREVIEW_Z,
    IMPORTED_SHAPE_LAYER_DEFAULT,
    clamp_imported_shape_z,
)
# Enum per modalità avanzate rimosse - mantenute solo funzionalità di base


class SvgItem(QGraphicsObject):
    """Elemento grafico che rappresenta un file SVG sul canvas con supporto per blending e compositing"""
    sizeChanged = Signal(float, float)
    
    # Segnali avanzati rimossi - mantenute solo funzionalità di base
    
    def __init__(self, svg_path, parent=None):
        super().__init__(parent)
        
        self.svg_path = svg_path
        self.svg_renderer = None
        self.svg_size = None
        self.scale_x = 1.0  # Fattore di scala per la larghezza
        self.scale_y = 1.0  # Fattore di scala per l'altezza
        
        # Contenuto XML dell'SVG
        self._original_svg_content = None
        self._modified_svg_content = None
        self._svg_root = None
        self._native_shape = None  # Per rendering ottimizzato di forme semplici
        self._uses_complex_styling = False
        
        # Proprietà avanzate rimosse - mantenute solo funzionalità di base
        
        # Proprietà di stile per bordo e riempimento
        self._border_color = QColor(0, 0, 0, 255)  # Nero di default
        self._border_width = 2.0  # Spessore di default
        self._fill_color = QColor(255, 255, 255, 0)  # Trasparente di default
        self._show_border = False  # Bordo disabilitato di default
        self._show_fill = False  # Riempimento disabilitato di default
        
        # Colori originali preservati dall'SVG
        self._original_fill_colors = {}  # Dict: element_id -> original_fill
        self._original_stroke_colors = {}  # Dict: element_id -> original_stroke
        
        # Proprietà dell'elemento
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        
        # Handle di ridimensionamento
        self._handle_size = 8.0
        self._handles = {}  # Punti di controllo per ridimensionamento
        self._handle_cursors = {
            'top_left': Qt.SizeFDiagCursor,
            'top': Qt.SizeVerCursor,
            'top_right': Qt.SizeBDiagCursor,
            'right': Qt.SizeHorCursor,
            'bottom_right': Qt.SizeFDiagCursor,
            'bottom': Qt.SizeVerCursor,
            'bottom_left': Qt.SizeBDiagCursor,
            'left': Qt.SizeHorCursor,
            'rotation': Qt.OpenHandCursor
        }
        self._handle_being_dragged = None
        self._drag_start_pos = None
        self._drag_start_scale = None
        
        # Handle specializzati
        self._specialized_handles = {}
        self._active_handle_mode = None  # Tipo di handle attivo: 'corners', 'path_points', 'bezier', 'nodes', 'radius', 'arcs', 'text'
        self._specialized_handle_size = 6
        
        # Handle di rotazione
        self._rotation_handle = None
        self._rotation_handle_being_dragged = False
        # None = nessun drag di rotazione in corso. Era 0.0, ma il codice
        # controlla 'is None': la guardia era sempre falsa, la rotazione
        # corrente non veniva mai letta e il balloon partiva da un
        # orientamento fisso invece che dalla sua rotazione.
        self._rotation_start_angle = None
        self._current_rotation = 0.0
        
        # Variabili per il ridimensionamento
        self._drag_start_item_pos = None
        self._drag_start_scale_x = None
        self._drag_start_scale_y = None
        self._drag_restore_z = None
        
        # Carica l'SVG
        self.load_svg()
    
    def _save_original_colors(self, element, element_id):
        """Salva i colori originali di un elemento SVG"""
        # Salva fill originale
        if 'fill' in element.attrib and element_id not in self._original_fill_colors:
            self._original_fill_colors[element_id] = element.get('fill')
        
        # Salva stroke originale
        if 'stroke' in element.attrib and element_id not in self._original_stroke_colors:
            self._original_stroke_colors[element_id] = element.get('stroke')
        
        # Salva anche opacity se presente
        if 'fill-opacity' in element.attrib:
            self._original_fill_colors[f"{element_id}_opacity"] = element.get('fill-opacity')
        if 'stroke-opacity' in element.attrib:
            self._original_stroke_colors[f"{element_id}_opacity"] = element.get('stroke-opacity')
    
    def load_svg(self):
        """Carica il file SVG con supporto migliorato per SVG semplificati"""
        print(f"DEBUG: load_svg chiamato per {os.path.basename(self.svg_path)}")
        
        if not os.path.exists(self.svg_path):
            print(f"Errore: File SVG non trovato: {self.svg_path}")
            return False
        
        try:
            # Leggi il contenuto XML dell'SVG
            with open(self.svg_path, 'r', encoding='utf-8') as f:
                self._original_svg_content = f.read()
            
            print(f"DEBUG: Contenuto SVG caricato ({len(self._original_svg_content)} caratteri)")
            
            # Verifica se l'SVG contiene attributi di stile inline (potrebbe essere semplificato)
            has_inline_styles = 'fill=' in self._original_svg_content or 'stroke=' in self._original_svg_content
            has_css_styles = '<style>' in self._original_svg_content or 'style=' in self._original_svg_content
            self._uses_complex_styling = svg_content_uses_complex_styling(self._original_svg_content)
            
            print(f"DEBUG: SVG ha stili inline: {has_inline_styles}, ha stili CSS: {has_css_styles}")
            print(f"DEBUG: SVG usa styling complesso: {self._uses_complex_styling}")
            
            # Parsa il contenuto XML
            self._svg_root = ET.fromstring(self._original_svg_content)
            self._modified_svg_content = self._original_svg_content
            
            # Analizza la struttura SVG per debug
            svg_elements = self._svg_root.findall('.//*')
            graphic_elements = [elem for elem in svg_elements if elem.tag.split('}')[-1] in ['path', 'circle', 'ellipse', 'rect', 'polygon', 'polyline', 'line']]
            print(f"DEBUG: Trovati {len(graphic_elements)} elementi grafici nell'SVG")
            
        except Exception as e:
            print(f"Errore nel parsing XML dell'SVG: {e}")
            return False
        
        # Crea il renderer SVG
        self.svg_renderer = QSvgRenderer(self.svg_path)
        
        if not self.svg_renderer.isValid():
            print(f"Errore: File SVG non valido: {self.svg_path}")
            return False
        
        # Ottieni le dimensioni originali dell'SVG
        self.svg_size = self.svg_renderer.defaultSize()
        print(f"DEBUG: Dimensioni SVG: {self.svg_size.width()}x{self.svg_size.height()}")
        
        # Carica la rotazione esistente dal file SVG
        self._load_existing_rotation()
        
        # Analizza se è una forma nativa semplice
        self._analyze_native_shape()
        
        # Prepara per il ridisegno
        self.prepareGeometryChange()
        self.update()
        
        print(f"DEBUG: load_svg completato con successo per {os.path.basename(self.svg_path)}")
        return True
    
    def _analyze_native_shape(self):
        """Analizza l'SVG per determinare se contiene una forma nativa semplice"""
        self._native_shape = None
        if self._svg_root is None:
            return

        # Gli SVG con style/CSS/opacity/filter vanno resi dal renderer completo
        # per preservare i colori originali senza perdere informazioni.
        if self._uses_complex_styling:
            print("DEBUG: Rendering nativo disabilitato per styling SVG complesso")
            return
            
        try:
            can_use_native_shape, native_element = svg_root_has_single_native_shape(
                self._svg_root
            )

            # Se c'è esattamente un elemento grafico supportato
            if can_use_native_shape:
                tag, element = native_element
                
                # Estrai stili originali
                orig_fill = element.get('fill', 'none')
                orig_stroke = element.get('stroke', 'none')
                try:
                    orig_stroke_width = float(element.get('stroke-width', 0.0))
                except:
                    orig_stroke_width = 0.0
                
                shape_data = {
                    'orig_fill': orig_fill,
                    'orig_stroke': orig_stroke,
                    'orig_stroke_width': orig_stroke_width
                }
                
                if tag == 'rect':
                    x = float(element.get('x', 0))
                    y = float(element.get('y', 0))
                    w = float(element.get('width', 0))
                    h = float(element.get('height', 0))
                    rx = float(element.get('rx', 0))
                    ry = float(element.get('ry', 0))
                    
                    shape_data.update({
                        'type': 'rect',
                        'rect': QRectF(x, y, w, h),
                        'rx': rx,
                        'ry': ry
                    })
                    self._native_shape = shape_data
                    print(f"DEBUG: Forma nativa rilevata: RECT {x},{y} {w}x{h}")
                    
                elif tag == 'circle':
                    cx = float(element.get('cx', 0))
                    cy = float(element.get('cy', 0))
                    r = float(element.get('r', 0))
                    
                    shape_data.update({
                        'type': 'ellipse',
                        'rect': QRectF(cx-r, cy-r, r*2, r*2)
                    })
                    self._native_shape = shape_data
                    print(f"DEBUG: Forma nativa rilevata: CIRCLE {cx},{cy} r={r}")
                    
                elif tag == 'ellipse':
                    cx = float(element.get('cx', 0))
                    cy = float(element.get('cy', 0))
                    rx = float(element.get('rx', 0))
                    ry = float(element.get('ry', 0))
                    
                    shape_data.update({
                        'type': 'ellipse',
                        'rect': QRectF(cx-rx, cy-ry, rx*2, ry*2)
                    })
                    self._native_shape = shape_data
                    print(f"DEBUG: Forma nativa rilevata: ELLIPSE {cx},{cy} r={rx},{ry}")
                    
        except Exception as e:
            print(f"Errore nell'analisi della forma nativa: {e}")
    
    def reload_svg_content(self):
        """Ricarica il contenuto SVG dal file su disco e aggiorna l'oggetto SvgItem"""
        try:
            if not self.svg_path or not os.path.exists(self.svg_path):
                print(f"[ERROR] File SVG non trovato: {self.svg_path}")
                return False
            
            print(f"[DEBUG] Ricaricamento SVG da: {self.svg_path}")
            
            # Leggi il nuovo contenuto dal file
            with open(self.svg_path, 'r', encoding='utf-8') as f:
                new_content = f.read()
            
            print(f"[DEBUG] Contenuto precedente: {len(self._original_svg_content)} caratteri")
            print(f"[DEBUG] Nuovo contenuto: {len(new_content)} caratteri")
            
            # Verifica se il contenuto è effettivamente cambiato
            if new_content == self._original_svg_content:
                print(f"[DEBUG] Il contenuto SVG non è cambiato, ricaricamento non necessario")
                return True
            
            # Salva gli stili correnti prima del ricaricamento
            current_border_color = self._border_color
            current_border_width = self._border_width
            current_show_border = self._show_border
            current_fill_color = self._fill_color
            current_show_fill = self._show_fill
            current_scale_x = self.scale_x
            current_scale_y = self.scale_y
            current_pos = self.pos()
            
            print(f"[DEBUG] Stili salvati - Bordo: {current_show_border}, Riempimento: {current_show_fill}")
            
            # Aggiorna il contenuto SVG interno
            self._original_svg_content = new_content
            self._modified_svg_content = new_content
            
            # Parsa il nuovo contenuto XML
            self._svg_root = ET.fromstring(self._original_svg_content)
            
            # Ricrea il renderer con il nuovo contenuto
            self.svg_renderer = QSvgRenderer(self.svg_path)
            if not self.svg_renderer.isValid():
                print(f"[ERROR] Impossibile caricare il nuovo contenuto SVG")
                return False
            
            print(f"[DEBUG] Renderer SVG aggiornato con successo")
            
            # Aggiorna le dimensioni originali
            old_size = self.svg_size
            self.svg_size = self.svg_renderer.defaultSize()
            print(f"[DEBUG] Dimensioni aggiornate da {old_size} a {self.svg_size}")
            
            # Riapplica gli stili salvati
            self._border_color = current_border_color
            self._border_width = current_border_width
            self._show_border = current_show_border
            self._fill_color = current_fill_color
            self._show_fill = current_show_fill
            
            # Riapplica gli stili al contenuto SVG
            if self._show_border or self._show_fill:
                self._apply_styles_to_svg()
                print(f"[DEBUG] Stili riapplicati al nuovo contenuto SVG")
            
            # Aggiorna la visualizzazione
            self.scale_x = current_scale_x
            self.scale_y = current_scale_y
            self.setPos(current_pos)
            self.prepareGeometryChange()
            self.update()
            
            print(f"[DEBUG] SVG ricaricato con successo - Controlli di stile dovrebbero ora funzionare")
            return True
            
        except Exception as e:
            print(f"[ERROR] Errore nel ricaricamento SVG: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _is_closed_path(self, element):
        """Determina se un elemento path rappresenta una forma chiusa"""
        if element.tag.lower().endswith('path'):
            d_attr = element.get('d', '')
            
            # Un path è considerato chiuso se:
            # 1. Contiene il comando 'Z' o 'z' (chiusura esplicita)
            if 'z' in d_attr.lower():
                return True
                
            # 2. Ha un fill-rule definito (indica intenzione di riempimento)
            if element.get('fill-rule') is not None:
                return True
                
            # 3. Il primo e ultimo punto coincidono (chiusura geometrica)
            return self._is_geometrically_closed(d_attr)
        return False
    
    def _is_geometrically_closed(self, d_attr):
        """Verifica se un path è chiuso geometricamente (primo e ultimo punto coincidono)"""
        try:
            import re
            
            # Rimuovi spazi extra e normalizza
            d_attr = re.sub(r'\s+', ' ', d_attr.strip())
            
            # Trova il primo comando di movimento (M o m)
            move_match = re.search(r'[Mm]\s*([\d.-]+)[\s,]+([\d.-]+)', d_attr)
            if not move_match:
                return False
                
            start_x = float(move_match.group(1))
            start_y = float(move_match.group(2))
            
            # Trova tutti i comandi e le loro coordinate
            commands = re.findall(r'([MmLlHhVvCcSsQqTtAa])([^MmLlHhVvCcSsQqTtAa]*)', d_attr)
            
            current_x, current_y = start_x, start_y
            
            for cmd, coords_str in commands:
                if not coords_str.strip():
                    continue
                    
                # Estrai le coordinate numeriche
                coords = re.findall(r'[\d.-]+', coords_str)
                coords = [float(c) for c in coords]
                
                if not coords:
                    continue
                
                # Aggiorna la posizione corrente in base al comando
                if cmd.upper() == 'M':  # Move
                    if len(coords) >= 2:
                        if cmd.isupper():  # Assoluto
                            current_x, current_y = coords[-2], coords[-1]
                        else:  # Relativo
                            current_x += coords[-2]
                            current_y += coords[-1]
                            
                elif cmd.upper() == 'L':  # Line
                    if len(coords) >= 2:
                        if cmd.isupper():  # Assoluto
                            current_x, current_y = coords[-2], coords[-1]
                        else:  # Relativo
                            current_x += coords[-2]
                            current_y += coords[-1]
                            
                elif cmd.upper() == 'H':  # Horizontal line
                    if len(coords) >= 1:
                        if cmd.isupper():  # Assoluto
                            current_x = coords[-1]
                        else:  # Relativo
                            current_x += coords[-1]
                            
                elif cmd.upper() == 'V':  # Vertical line
                    if len(coords) >= 1:
                        if cmd.isupper():  # Assoluto
                            current_y = coords[-1]
                        else:  # Relativo
                            current_y += coords[-1]
                            
                elif cmd.upper() == 'C':  # Cubic Bezier
                    if len(coords) >= 6:
                        if cmd.isupper():  # Assoluto
                            current_x, current_y = coords[-2], coords[-1]
                        else:  # Relativo
                            current_x += coords[-2]
                            current_y += coords[-1]
                            
                elif cmd.upper() == 'S':  # Smooth cubic Bezier
                    if len(coords) >= 4:
                        if cmd.isupper():  # Assoluto
                            current_x, current_y = coords[-2], coords[-1]
                        else:  # Relativo
                            current_x += coords[-2]
                            current_y += coords[-1]
                            
                elif cmd.upper() == 'Q':  # Quadratic Bezier
                    if len(coords) >= 4:
                        if cmd.isupper():  # Assoluto
                            current_x, current_y = coords[-2], coords[-1]
                        else:  # Relativo
                            current_x += coords[-2]
                            current_y += coords[-1]
                            
                elif cmd.upper() == 'T':  # Smooth quadratic Bezier
                    if len(coords) >= 2:
                        if cmd.isupper():  # Assoluto
                            current_x, current_y = coords[-2], coords[-1]
                        else:  # Relativo
                            current_x += coords[-2]
                            current_y += coords[-1]
                            
                elif cmd.upper() == 'A':  # Arc
                    if len(coords) >= 7:
                        if cmd.isupper():  # Assoluto
                            current_x, current_y = coords[-2], coords[-1]
                        else:  # Relativo
                            current_x += coords[-2]
                            current_y += coords[-1]
            
            # Verifica se il punto finale è vicino al punto iniziale (tolleranza per errori di arrotondamento)
            tolerance = 0.1
            return abs(current_x - start_x) < tolerance and abs(current_y - start_y) < tolerance
            
        except (ValueError, IndexError, AttributeError):
            # In caso di errore nel parsing, considera il path come non chiuso
            return False
    
    def _should_apply_fill(self, element, tag):
        """Determina se il riempimento dovrebbe essere applicato a questo elemento"""
        # Forme sempre chiuse per natura
        if tag in ['circle', 'ellipse', 'rect', 'polygon']:
            return True
        
        # Path solo se chiuso
        if tag == 'path':
            return self._is_closed_path(element)
        
        # Linee e gruppi non dovrebbero mai avere riempimento
        if tag in ['polyline', 'line', 'g']:
            return False
        
        # Per qualsiasi altro elemento, controlla se ha già un fill definito
        current_fill = element.get('fill', 'none')
        return current_fill != 'none'
    
    def _apply_styles_to_svg(self):
        """Applica gli stili correnti al contenuto XML dell'SVG con preservazione colori originali"""
        # Registra il namespace SVG di default per evitare prefissi 'ns0:' che rompono il rendering
        try:
            ET.register_namespace('', "http://www.w3.org/2000/svg")
        except:
            pass

        print(f"DEBUG: _apply_styles_to_svg chiamato - show_fill: {self._show_fill}, show_border: {self._show_border}")
        if self._svg_root is None:
            print("DEBUG: _svg_root è None, uscendo")
            return
        
        try:
            # Usa lo stato XML corrente come base per preservare transform
            # e altre modifiche strutturali già applicate all'SVG.
            base_svg_content = self._original_svg_content
            if self._svg_root is not None:
                base_svg_content = ET.tostring(self._svg_root, encoding='unicode')

            root_copy = ET.fromstring(base_svg_content)
            
            # Trova tutti gli elementi che possono avere stili
            styleable_elements = root_copy.findall('.//*')
            print(f"DEBUG: Trovati {len(styleable_elements)} elementi da stilizzare")
            
            elements_modified = 0
            for element in styleable_elements:
                tag = element.tag.lower()
                # Rimuovi namespace se presente
                if '}' in tag:
                    tag = tag.split('}')[1]
                
                # Applica stili solo agli elementi grafici
                if tag in ['path', 'circle', 'ellipse', 'rect', 'polygon', 'polyline', 'line', 'g']:
                    elements_modified += 1
                    
                    # Crea ID univoco per l'elemento
                    element_id = f"{tag}_{elements_modified}"
                    
                    # Salva i colori originali prima di modificarli
                    self._save_original_colors(element, element_id)
                    
                    # Gestisci il riempimento solo per forme chiuse
                    if self._show_fill and self._should_apply_fill(element, tag):
                        element.set('fill', self._fill_color.name())
                        if self._fill_color.alpha() < 255:
                            element.set('fill-opacity', str(self._fill_color.alpha() / 255.0))
                        else:
                            # Rimuovi fill-opacity se alpha è 255
                            if 'fill-opacity' in element.attrib:
                                del element.attrib['fill-opacity']
                    else:
                        # Ripristina i colori originali se disponibili, altrimenti rimuovi
                        original_fill = self._original_fill_colors.get(element_id)
                        if original_fill and not self._show_fill:
                            element.set('fill', original_fill)
                            # Ripristina anche l'opacity originale
                            original_opacity = self._original_fill_colors.get(f"{element_id}_opacity")
                            if original_opacity:
                                element.set('fill-opacity', original_opacity)
                        elif not self._show_fill:
                            # Solo se non c'è un colore originale, rimuovi
                            if 'fill' in element.attrib:
                                del element.attrib['fill']
                            if 'fill-opacity' in element.attrib:
                                del element.attrib['fill-opacity']
                    
                    # Gestisci il bordo
                    if self._show_border and self._border_width > 0:
                        element.set('stroke', self._border_color.name())
                        element.set('stroke-width', str(self._border_width))
                        if self._border_color.alpha() < 255:
                            element.set('stroke-opacity', str(self._border_color.alpha() / 255.0))
                        else:
                            # Rimuovi stroke-opacity se alpha è 255
                            if 'stroke-opacity' in element.attrib:
                                del element.attrib['stroke-opacity']
                    else:
                        # Ripristina i colori originali se disponibili, altrimenti rimuovi
                        original_stroke = self._original_stroke_colors.get(element_id)
                        if original_stroke and not self._show_border:
                            element.set('stroke', original_stroke)
                            # Ripristina anche l'opacity originale
                            original_opacity = self._original_stroke_colors.get(f"{element_id}_opacity")
                            if original_opacity:
                                element.set('stroke-opacity', original_opacity)
                        elif not self._show_border:
                            # Solo se non c'è un colore originale, rimuovi
                            if 'stroke' in element.attrib:
                                del element.attrib['stroke']
                            if 'stroke-width' in element.attrib:
                                del element.attrib['stroke-width']
                            if 'stroke-opacity' in element.attrib:
                                del element.attrib['stroke-opacity']
            
            print(f"DEBUG: Modificati {elements_modified} elementi grafici")
            
            # Converte l'elemento modificato in stringa
            self._modified_svg_content = ET.tostring(root_copy, encoding='unicode')
            print(f"DEBUG: Contenuto SVG modificato generato ({len(self._modified_svg_content)} caratteri)")
            
            # Ricarica il renderer con il contenuto modificato
            self._reload_svg_renderer()
            
        except Exception as e:
            print(f"Errore nell'applicazione degli stili SVG: {e}")
    
    def _reload_svg_renderer(self):
        """Ricarica il renderer SVG con il contenuto modificato"""
        print("DEBUG: _reload_svg_renderer chiamato")
        try:
            # Crea un QByteArray dal contenuto modificato
            svg_data = QByteArray(self._modified_svg_content.encode('utf-8'))
            print(f"DEBUG: Creato QByteArray di {svg_data.size()} bytes")
            
            # Crea un nuovo renderer con i dati modificati
            new_renderer = QSvgRenderer(svg_data)
            print(f"DEBUG: Nuovo renderer creato, valido: {new_renderer.isValid()}")
            
            if new_renderer.isValid():
                old_renderer_valid = self.svg_renderer.isValid() if self.svg_renderer else False
                self.svg_renderer = new_renderer
                print(f"DEBUG: Renderer aggiornato (vecchio valido: {old_renderer_valid}, nuovo valido: {new_renderer.isValid()})")
                self.update()
                print("DEBUG: update() chiamato")
            else:
                print("Errore: Renderer SVG non valido dopo la modifica")
                print(f"DEBUG: Contenuto SVG problematico (primi 200 caratteri): {self._modified_svg_content[:200]}")
                
        except Exception as e:
            print(f"Errore nel ricaricamento del renderer SVG: {e}")
    
    def boundingRect(self):
        """Restituisce il rettangolo di delimitazione dell'elemento"""
        if not self.svg_size:
            return QRectF()
        
        # Calcola le dimensioni scalate
        width = self.svg_size.width() * self.scale_x
        height = self.svg_size.height() * self.scale_y
        
        # Il bounding rect deve includere completamente bordo di selezione e handle.
        margin = max(2.0, self._handle_size / 2.0)
        return QRectF(-margin, -margin, width + 2*margin, height + 2*margin)
    
    def paint(self, painter, option, widget=None):
        """Disegna l'elemento SVG con qualità ottimizzata e supporto per forme native"""
        
        # Salva lo stato del painter
        painter.save()
        
        try:
            # Abilita l'antialiasing per una migliore qualità
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
            
            # Se è una forma nativa, disegnala direttamente (più veloce e preciso)
            if self._native_shape:
                # Calcola il rettangolo scalato
                # Nota: Non usiamo painter.scale() qui per evitare di scalare lo spessore del bordo
                scaled_width = self.svg_size.width() * self.scale_x
                scaled_height = self.svg_size.height() * self.scale_y
                scaled_rect = QRectF(0, 0, scaled_width, scaled_height)
                
                # Gestione Riempimento
                if self._show_fill:
                    painter.setBrush(QBrush(self._fill_color))
                else:
                    # Usa originale se possibile
                    orig_fill = self._native_shape.get('orig_fill', 'none')
                    if orig_fill != 'none':
                        painter.setBrush(QBrush(QColor(orig_fill)))
                    else:
                        painter.setBrush(Qt.NoBrush)
                
                # Gestione Bordo - Spessore costante (non scalato)
                if self._show_border:
                    if self._border_width > 0:
                        pen = QPen(self._border_color, self._border_width)
                        pen.setCosmetic(True) # Mantiene lo spessore costante indipendentemente dalla scala
                        painter.setPen(pen)
                    else:
                        # Spessore 0 esplicito -> Nascondi bordo
                        painter.setPen(Qt.NoPen)
                else:
                    # Usa originale se possibile
                    orig_stroke = self._native_shape.get('orig_stroke', 'none')
                    orig_width = self._native_shape.get('orig_stroke_width', 0.0)
                    if orig_stroke != 'none' and orig_width > 0:
                        pen = QPen(QColor(orig_stroke), orig_width)
                        pen.setCosmetic(True)
                        painter.setPen(pen)
                    else:
                        painter.setPen(Qt.NoPen)
                
                # Disegna la forma geometrica nel rettangolo scalato
                if self._native_shape['type'] == 'rect':
                    # Scala anche i raggi degli angoli
                    rx = self._native_shape.get('rx', 0) * self.scale_x
                    ry = self._native_shape.get('ry', 0) * self.scale_y
                    painter.drawRoundedRect(scaled_rect, rx, ry)
                    
                elif self._native_shape['type'] == 'ellipse':
                    painter.drawEllipse(scaled_rect)
                    
            # Altrimenti usa il renderer SVG standard (per path complessi)
            elif self.svg_renderer and self.svg_renderer.isValid():
                # Per gli SVG complessi, dobbiamo usare painter.scale()
                painter.scale(self.scale_x, self.scale_y)
                self.svg_renderer.render(painter, QRectF(0, 0, self.svg_size.width(), self.svg_size.height()))
            
        finally:
            # Ripristina lo stato del painter
            painter.restore()
        
        # Disegna il bordo di selezione se selezionato
        if self.isSelected():
            self.paint_selection_border(painter)
    
    def paint_selection_border(self, painter):
        """Disegna il bordo di selezione e gli handle di ridimensionamento"""
        if not self.svg_size:
            return
        
        # Salva lo stato del painter
        painter.save()
        
        # Configura il pen per il bordo con colore grigio chiaro e opacità ridotta
        border_color = QColor(150, 150, 150)
        border_color.setAlpha(int(255 * 0.6))  # 60% di opacità
        pen = QPen(border_color, 1, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(Qt.NoBrush))
        
        # Disegna il rettangolo di selezione
        width = self.svg_size.width() * self.scale_x
        height = self.svg_size.height() * self.scale_y
        painter.drawRect(QRectF(0, 0, width, height))
        
        # Ripristina lo stato del painter
        painter.restore()
        
        # Disegna gli handle di ridimensionamento
        self._paint_handles(painter)
    
    def set_scale(self, scale_x=None, scale_y=None, scale=None):
        """Imposta il fattore di scala dell'SVG"""
        target_scale_x = self.scale_x
        target_scale_y = self.scale_y

        if scale is not None:
            # Modalità proporzionale (compatibilità)
            if scale <= 0:
                return
            target_scale_x = max(0.1, min(scale, 10.0))
            target_scale_y = max(0.1, min(scale, 10.0))
        else:
            # Modalità indipendente
            if scale_x is not None:
                target_scale_x = max(0.1, min(scale_x, 10.0))
            if scale_y is not None:
                target_scale_y = max(0.1, min(scale_y, 10.0))

        if target_scale_x == self.scale_x and target_scale_y == self.scale_y:
            return

        self.prepareGeometryChange()
        self.scale_x = target_scale_x
        self.scale_y = target_scale_y
        self.update()
        
        # Emetti segnale di cambio dimensione
        current_size = self.get_scaled_size()
        if current_size:
            self.sizeChanged.emit(current_size.width(), current_size.height())

    def _begin_resize_preview(self):
        """Porta temporaneamente l'SVG sopra il testo durante il resize."""
        if self._drag_restore_z is None:
            self._drag_restore_z = float(self.zValue())
        if float(self.zValue()) < ACTIVE_IMPORTED_SHAPE_PREVIEW_Z:
            self.setZValue(ACTIVE_IMPORTED_SHAPE_PREVIEW_Z)

    def _end_resize_preview(self):
        """Ripristina lo Z originale dopo il resize interattivo."""
        if self._drag_restore_z is None:
            return
        restore_z = clamp_imported_shape_z(self._drag_restore_z)
        self._drag_restore_z = None
        if float(self.zValue()) != restore_z:
            self.setZValue(restore_z)
    
    def get_scale(self):
        """Restituisce i fattori di scala correnti (scale_x, scale_y)"""
        return self.scale_x, self.scale_y
    
    def get_uniform_scale(self):
        """Restituisce il fattore di scala uniforme (per compatibilità)"""
        return (self.scale_x + self.scale_y) / 2
    
    def get_svg_path(self):
        """Restituisce il percorso del file SVG"""
        return self.svg_path
    
    def get_filename(self):
        """Restituisce il nome del file SVG (solo il nome del file, non il percorso completo)"""
        return os.path.basename(self.svg_path)
    
    def get_svg_size(self):
        """Restituisce le dimensioni originali dell'SVG"""
        return self.svg_size
    
    def get_scaled_size(self):
        """Restituisce le dimensioni scalate dell'SVG"""
        if not self.svg_size:
            return None
        
        return QSizeF(self.svg_size.width() * self.scale_x, 
                     self.svg_size.height() * self.scale_y)
    
    
    
    def _update_handles(self):
        """Aggiorna la posizione degli handle basandosi sul boundingRect dell'SVG"""
        if not self.svg_size:
            return
        
        width = self.svg_size.width() * self.scale_x
        height = self.svg_size.height() * self.scale_y
        half_handle = self._handle_size / 2
        
        self._handles = {
            'top_left': QRectF(-half_handle, -half_handle, self._handle_size, self._handle_size),
            'top': QRectF(width/2 - half_handle, -half_handle, self._handle_size, self._handle_size),
            'top_right': QRectF(width - half_handle, -half_handle, self._handle_size, self._handle_size),
            'right': QRectF(width - half_handle, height/2 - half_handle, self._handle_size, self._handle_size),
            'bottom_right': QRectF(width - half_handle, height - half_handle, self._handle_size, self._handle_size),
            'bottom': QRectF(width/2 - half_handle, height - half_handle, self._handle_size, self._handle_size),
            'bottom_left': QRectF(-half_handle, height - half_handle, self._handle_size, self._handle_size),
            'left': QRectF(-half_handle, height/2 - half_handle, self._handle_size, self._handle_size)
        }
        
        
    
    def _update_specialized_handles(self):
        self._specialized_handles = {}
    
    def _paint_handles(self, painter):
        """Disegna gli handle di ridimensionamento se l'oggetto è selezionato"""
        if self.isSelected():
            # Aggiorna gli handle prima di disegnarli
            self._update_handles()
            self._update_specialized_handles()
            
            # Salva lo stato del painter
            painter.save()
            
            handle_border_color = QColor(120, 120, 120)
            handle_border_color.setAlpha(int(255 * 0.7))
            handle_fill_color = QColor(180, 180, 180)
            handle_fill_color.setAlpha(int(255 * 0.7))
            painter.setPen(QPen(handle_border_color, 1, Qt.SolidLine))
            painter.setBrush(QBrush(handle_fill_color))
            for handle_name, handle_pos in self._handles.items():
                painter.drawRect(handle_pos)
            
            
            
            # Ripristina lo stato del painter
            painter.restore()
    
    
    
    def handle_at(self, point):
        """Restituisce il tipo di handle alla posizione specificata, o None"""
        if not self.isSelected():
            return None
        
        for handle_name, handle_rect in self._handles.items():
            if handle_rect.contains(point):
                return handle_name
        
        return None
    
    # Metodo paint_background rimosso - funzionalità avanzate non più supportate
    
    # Metodi per l'opacità rimossi - funzionalità avanzate non più supportate
    
    # Metodi per la modalità di blending rimossi - funzionalità avanzate non più supportate
    
    # Metodi per gestire il background rimossi - funzionalità avanzate non più supportate
    
    # Metodi per le opzioni di rendering avanzate rimossi - funzionalità di base mantenute
    
    # Metodi per gestire il bordo
    def set_border_color(self, color):
        """Imposta il colore del bordo"""
        print(f"DEBUG: set_border_color chiamato con colore: {color}")
        if isinstance(color, str):
            color = QColor(color)
        elif isinstance(color, (list, tuple)) and len(color) >= 3:
            if len(color) == 3:
                color = QColor(color[0], color[1], color[2])
            else:
                color = QColor(color[0], color[1], color[2], color[3])
        
        if isinstance(color, QColor) and self._border_color != color:
            print(f"DEBUG: Cambiando colore bordo da {self._border_color.name()} a {color.name()}")
            self._border_color = color
            # Abilita automaticamente la visualizzazione del bordo
            print(f"DEBUG: Abilitando automaticamente show_border")
            self.set_show_border(True)
            self._apply_styles_to_svg()
            self.update()
    
    def border_color(self):
        """Restituisce il colore del bordo"""
        return self._border_color
    
    def set_border_width(self, width):
        """Imposta lo spessore del bordo"""
        print(f"DEBUG: set_border_width chiamato con spessore: {width}")
        width = max(0.0, float(width))
        if self._border_width != width:
            print(f"DEBUG: Cambiando spessore bordo da {self._border_width} a {width}")
            self._border_width = width
            # Abilita automaticamente la visualizzazione del bordo
            print(f"DEBUG: Abilitando automaticamente show_border")
            self.set_show_border(True)
            self._apply_styles_to_svg()
            self.update()
    
    def border_width(self):
        """Restituisce lo spessore del bordo"""
        return self._border_width
    
    def set_show_border(self, show):
        """Abilita/disabilita la visualizzazione del bordo"""
        print(f"DEBUG: set_show_border chiamato con valore: {show}, stato attuale: {self._show_border}")
        if self._show_border != show:
            print(f"DEBUG: Cambiando show_border da {self._show_border} a {show}")
            self._show_border = show
            self._apply_styles_to_svg()
            self.update()
        else:
            print(f"DEBUG: show_border già impostato a {show}, nessun cambiamento")
    
    def show_border(self):
        """Restituisce se il bordo è visibile"""
        return self._show_border
    
    # Metodi per gestire il riempimento
    def set_fill_color(self, color):
        """Imposta il colore di riempimento"""
        print(f"DEBUG: set_fill_color chiamato con colore: {color}")
        if isinstance(color, str):
            color = QColor(color)
        elif isinstance(color, (list, tuple)) and len(color) >= 3:
            if len(color) == 3:
                color = QColor(color[0], color[1], color[2])
            else:
                color = QColor(color[0], color[1], color[2], color[3])
        
        if isinstance(color, QColor) and self._fill_color != color:
            print(f"DEBUG: Cambiando colore riempimento da {self._fill_color.name()} a {color.name()}")
            self._fill_color = color
            # Abilita automaticamente la visualizzazione del riempimento
            print(f"DEBUG: Abilitando automaticamente show_fill")
            self.set_show_fill(True)
            self._apply_styles_to_svg()
            self.update()
    
    def fill_color(self):
        """Restituisce il colore di riempimento"""
        return self._fill_color
    
    def set_show_fill(self, show):
        """Abilita/disabilita la visualizzazione del riempimento"""
        print(f"DEBUG: set_show_fill chiamato con valore: {show}, stato attuale: {self._show_fill}")
        if self._show_fill != show:
            print(f"DEBUG: Cambiando show_fill da {self._show_fill} a {show}")
            self._show_fill = show
            self._apply_styles_to_svg()
            self.update()
        else:
            print(f"DEBUG: show_fill già impostato a {show}, nessun cambiamento")
    
    def show_fill(self):
        """Restituisce se il riempimento è visibile"""
        return self._show_fill
    
    def mousePressEvent(self, event):
        """Gestisce il click del mouse sull'elemento"""
        if event.button() == Qt.LeftButton:
            # Controlla se è stato cliccato un handle
            self._handle_being_dragged = self.handle_at(event.pos())
            if self._handle_being_dragged:
                self._drag_start_pos = event.pos()
                self._drag_start_item_pos = QPointF(self.pos())
                self._drag_start_scale_x = self.scale_x
                self._drag_start_scale_y = self.scale_y
                # Nuovo drag di rotazione: azzera l'angolo di partenza e
                # ricarica la rotazione corrente, così il balloon parte dalla
                # sua orientazione reale invece di scattare.
                if self._handle_being_dragged == 'rotation':
                    self._rotation_start_angle = None
                    existing_transform = self._get_svg_transform()
                    self._current_rotation = (
                        self._parse_svg_rotation(existing_transform)
                        if existing_transform else 0.0
                    )
                self._begin_resize_preview()
                
                
                
                event.accept()
                return
            
            # Seleziona l'elemento
            self.setSelected(True)
            print(f"SVG selezionato: {os.path.basename(self.svg_path)}")
        
        super().mousePressEvent(event)
    
    def mouseMoveEvent(self, event):
        """Gestisce il movimento del mouse per il ridimensionamento e la rotazione"""
        if self._handle_being_dragged and self._drag_start_pos is not None:
            if self._handle_being_dragged.startswith('corner_'):
                # Handle specializzati per i corni
                self._handle_corner_interaction(event.pos(), self._handle_being_dragged)
            elif self._handle_being_dragged.startswith('path_'):
                # Handle specializzati per i punti di percorso
                self._handle_path_point_interaction(event.pos(), self._handle_being_dragged)
            elif self._handle_being_dragged.startswith('bezier_'):
                # Handle specializzati per le curve di Bézier
                self._handle_bezier_interaction(event.pos(), self._handle_being_dragged)
            elif self._handle_being_dragged.startswith('node_'):
                # Handle specializzati per i nodi
                self._handle_node_interaction(event.pos(), self._handle_being_dragged)
            elif self._handle_being_dragged.startswith('radius_'):
                # Handle specializzati per il raggio
                self._handle_radius_interaction(event.pos(), self._handle_being_dragged)
            elif self._handle_being_dragged.startswith('arc_'):
                # Handle specializzati per gli archi
                self._handle_arc_interaction(event.pos(), self._handle_being_dragged)
            elif self._handle_being_dragged.startswith('text_'):
                # Handle specializzati per il testo
                self._handle_text_interaction(event.pos(), self._handle_being_dragged)
            else:
                # Per il ridimensionamento standard, usa le coordinate locali
                self._resize_by_handle(event.pos(), self._handle_being_dragged)
            event.accept()
        else:
            super().mouseMoveEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Gestisce il rilascio del mouse"""
        if self._handle_being_dragged:
            # Se la rotazione è stata modificata durante il drag, salva su disco una sola volta
            if getattr(self, '_rotation_dirty', False):
                self._save_svg_to_file()
                self._rotation_dirty = False
                print(f"Rotazione SVG salvata: {self._current_rotation:.2f}°")

            self._handle_being_dragged = None
            self._drag_start_pos = None
            self._drag_start_item_pos = None
            self._drag_start_scale_x = None
            self._drag_start_scale_y = None
            self._end_resize_preview()
            event.accept()
        else:
            super().mouseReleaseEvent(event)
    
    def hoverMoveEvent(self, event):
        """Gestisce il movimento del mouse sopra l'elemento per cambiare il cursore"""
        if self.isSelected():
            handle = self.handle_at(event.pos())
            if handle and handle in self._handle_cursors:
                self.setCursor(self._handle_cursors[handle])
            
            else:
                self.setCursor(Qt.ArrowCursor)
        else:
            self.setCursor(Qt.ArrowCursor)
        super().hoverMoveEvent(event)
    
    def mouseDoubleClickEvent(self, event):
        """Gestisce il doppio click sull'elemento"""
        if event.button() == Qt.LeftButton:
            # Esempio: raddoppia/dimezza la scala mantenendo le proporzioni
            current_scale = self.get_uniform_scale()
            new_scale = 2.0 if current_scale < 1.5 else 0.5
            self.set_scale(scale=new_scale)
            print(f"Scala SVG cambiata a: {new_scale}")
        
        super().mouseDoubleClickEvent(event)
    
    def _resize_by_handle(self, mouse_pos, handle):
        """Ridimensiona l'SVG in base all'handle selezionato"""
        if self._drag_start_pos is None or self.svg_size is None:
            return
        if (
            self._drag_start_scale_x is None
            or self._drag_start_scale_y is None
            or self._drag_start_item_pos is None
        ):
            return

        # Delta assoluto dal punto di press — non accumulato frame su frame
        delta = mouse_pos - self._drag_start_pos

        # Dimensioni originali al momento del press (base fissa)
        start_width = self.svg_size.width() * self._drag_start_scale_x
        start_height = self.svg_size.height() * self._drag_start_scale_y

        # Nuovi fattori di scala (calcolati dalla base fissa, non dalla scala corrente)
        new_scale_x = self._drag_start_scale_x
        new_scale_y = self._drag_start_scale_y

        # Posizione originale al momento del press
        start_pos = QPointF(self._drag_start_item_pos)
        new_pos = QPointF(start_pos)

        # Handle di rotazione
        if handle == 'rotation':
            self._rotate_by_handle(mouse_pos)
            return

        # Side handles — ridimensionamento indipendente
        if handle == 'left':
            new_width = max(10, start_width - delta.x())
            new_scale_x = new_width / self.svg_size.width()
            # Mantiene fisso il lato destro aggiustando la posizione X
            width_change = new_width - start_width
            new_pos = QPointF(start_pos.x() - width_change, start_pos.y())
        elif handle == 'right':
            new_width = max(10, start_width + delta.x())
            new_scale_x = new_width / self.svg_size.width()
        elif handle == 'top':
            new_height = max(10, start_height - delta.y())
            new_scale_y = new_height / self.svg_size.height()
            # Mantiene fisso il lato inferiore aggiustando la posizione Y
            height_change = new_height - start_height
            new_pos = QPointF(start_pos.x(), start_pos.y() - height_change)
        elif handle == 'bottom':
            new_height = max(10, start_height + delta.y())
            new_scale_y = new_height / self.svg_size.height()

        # Handle degli angoli — ridimensionamento proporzionale dalla base fissa
        elif handle in ['top_left', 'top_right', 'bottom_left', 'bottom_right']:
            if handle == 'top_left':
                new_width = start_width - delta.x()
                new_height = start_height - delta.y()
            elif handle == 'top_right':
                new_width = start_width + delta.x()
                new_height = start_height - delta.y()
            elif handle == 'bottom_left':
                new_width = start_width - delta.x()
                new_height = start_height + delta.y()
            elif handle == 'bottom_right':
                new_width = start_width + delta.x()
                new_height = start_height + delta.y()

            scale_x_candidate = new_width / self.svg_size.width()
            scale_y_candidate = new_height / self.svg_size.height()

            # Proporzioni mantenute: usa il fattore maggiore in valore assoluto
            scale_factor = max(abs(scale_x_candidate), abs(scale_y_candidate))
            scale_factor = max(0.1, scale_factor)

            new_scale_x = scale_factor
            new_scale_y = scale_factor

            new_width = self.svg_size.width() * new_scale_x
            new_height = self.svg_size.height() * new_scale_y

            # Mantiene fermo il corner opposto a quello trascinato.
            if handle == 'top_left':
                new_pos = QPointF(
                    start_pos.x() + (start_width - new_width),
                    start_pos.y() + (start_height - new_height),
                )
            elif handle == 'top_right':
                new_pos = QPointF(
                    start_pos.x(),
                    start_pos.y() + (start_height - new_height),
                )
            elif handle == 'bottom_left':
                new_pos = QPointF(
                    start_pos.x() + (start_width - new_width),
                    start_pos.y(),
                )

        # Applica limiti ai fattori di scala
        new_scale_x = max(0.1, min(10.0, new_scale_x))
        new_scale_y = max(0.1, min(10.0, new_scale_y))

        # Aggiorna la scala
        self.set_scale(scale_x=new_scale_x, scale_y=new_scale_y)

        # Aggiorna la posizione se necessario (handle left e top)
        if new_pos != self.pos():
            self.setPos(new_pos)

        self.update()
        if self.scene():
            self.scene().update()
    
    def _rotate_by_handle(self, mouse_pos):
        """Ruota l'elemento SVG basandosi sulla posizione del mouse rispetto al centro"""
        # Ottieni il centro dell'elemento in coordinate della scena
        item_rect = self.boundingRect()
        center = self.mapToScene(item_rect.center())

        # mouse_pos arriva da event.pos(), quindi è in coordinate LOCALI del
        # item (pre-trasformazione), mentre center è in coordinate SCENA.
        # Confrontarle direttamente dava un angolo sbagliato di un offset che
        # cresce con la posizione del balloon, e totalmente errato quando il
        # item aveva già una rotazione. Si riporta il mouse in scena.
        scene_mouse = self.mapToScene(mouse_pos)

        # Calcola l'angolo tra il centro e la posizione del mouse
        dx = scene_mouse.x() - center.x()
        dy = scene_mouse.y() - center.y()
        
        # Calcola l'angolo in radianti e convertilo in gradi
        import math
        angle_rad = math.atan2(dy, dx)
        angle_deg = math.degrees(angle_rad)
        
        # Normalizza l'angolo tra 0 e 360 gradi
        if angle_deg < 0:
            angle_deg += 360
        
        # Se è la prima volta che ruotiamo, salva l'angolo di partenza
        if not hasattr(self, '_rotation_start_angle') or self._rotation_start_angle is None:
            self._rotation_start_angle = angle_deg
            # Leggi la rotazione esistente dal file SVG
            existing_transform = self._get_svg_transform()
            self._current_rotation = self._parse_svg_rotation(existing_transform) if existing_transform else 0.0
            return
        
        # Calcola la differenza di rotazione
        rotation_delta = angle_deg - self._rotation_start_angle
        
        # Gestisci il passaggio attraverso 0/360 gradi
        if rotation_delta > 180:
            rotation_delta -= 360
        elif rotation_delta < -180:
            rotation_delta += 360
        
        # Applica la rotazione incrementale
        if not hasattr(self, '_current_rotation'):
            self._current_rotation = 0
        
        new_rotation = self._current_rotation + rotation_delta
        
        # Applica la trasformazione di rotazione attorno al centro dell'elemento (visualizzazione)
        from PySide6.QtGui import QTransform
        item_center = item_rect.center()
        transform = QTransform()
        transform.translate(item_center.x(), item_center.y())
        transform.rotate(new_rotation)
        transform.translate(-item_center.x(), -item_center.y())
        
        self.setTransform(transform)

        # Aggiorna il transform SVG in memoria (senza scrivere su disco ogni frame)
        self._set_svg_transform(new_rotation)
        self._rotation_dirty = True  # Il salvataggio su disco avviene in mouseReleaseEvent

        # Aggiorna la rotazione corrente e l'angolo di partenza
        self._current_rotation = new_rotation
        self._rotation_start_angle = angle_deg

        # Forza l'aggiornamento del rendering
        self.update()
        if self.scene():
            self.scene().update()
    
    def itemChange(self, change, value):
        """Gestisce i cambiamenti dell'elemento"""
        if change in (
            QGraphicsItem.ItemSceneHasChanged,
            QGraphicsItem.ItemSelectedChange,
        ):
            current_z = float(self.zValue())
            target_z = IMPORTED_SHAPE_LAYER_DEFAULT if current_z == 0.0 else clamp_imported_shape_z(current_z)
            if current_z != target_z:
                self.setZValue(target_z)

        if change == QGraphicsItem.ItemSelectedChange:
            # Aggiorna gli handle quando l'elemento viene selezionato
            if bool(value):
                self._update_handles()
            self.update()
            
            # Notifica alla finestra principale di aggiornare lo stato dei pulsanti handle SVG
            if self.scene() and hasattr(self.scene(), 'views'):
                for view in self.scene().views():
                    if hasattr(view, 'parent') and view.parent():
                        main_window = view.parent()
                        # Cerca la finestra principale risalendo la gerarchia
                        while main_window and not hasattr(main_window, 'update_svg_handle_buttons_state'):
                            main_window = main_window.parent()
                        if main_window and hasattr(main_window, 'update_svg_handle_buttons_state'):
                            # Usa QTimer per chiamare la funzione nel prossimo ciclo di eventi
                            from PySide6.QtCore import QTimer
                            QTimer.singleShot(0, main_window.update_svg_handle_buttons_state)
                            break
        elif change == QGraphicsItem.ItemPositionChange:
            # Qui si potrebbe aggiungere logica per limitare il movimento
            new_pos = value
            print(f"SVG spostato a: {new_pos.x():.1f}, {new_pos.y():.1f}")
        
        return super().itemChange(change, value)
    
    # Metodi di ridimensionamento programmatico
    def set_size(self, width, height, maintain_aspect_ratio=True):
        """Imposta la dimensione dell'SVG"""
        if not self.svg_size:
            return
        
        # Calcola i fattori di scala necessari
        scale_x = width / self.svg_size.width()
        scale_y = height / self.svg_size.height()
        
        if maintain_aspect_ratio:
            # Usa il fattore di scala minore per mantenere le proporzioni
            scale_factor = min(scale_x, scale_y)
            self.set_scale(scale=scale_factor)
        else:
            # Ridimensionamento indipendente
            self.set_scale(scale_x=scale_x, scale_y=scale_y)
    
    def fit_to_size(self, max_width, max_height):
        """Ridimensiona l'SVG per adattarlo alle dimensioni massime specificate"""
        if not self.svg_size:
            return
        
        # Calcola il fattore di scala necessario
        scale_x = max_width / self.svg_size.width()
        scale_y = max_height / self.svg_size.height()
        
        # Usa il fattore di scala minore per mantenere le proporzioni
        scale_factor = min(scale_x, scale_y)
        self.set_scale(scale=scale_factor)
    
    def reset_to_original_size(self):
        """Ripristina l'SVG alla sua dimensione originale"""
        self.set_scale(scale=1.0)
    
    def get_current_size(self):
        """Restituisce la dimensione attuale dell'SVG"""
        if not self.svg_size:
            return QSize(0, 0)
        
        return QSize(
            int(self.svg_size.width() * self.scale_x),
            int(self.svg_size.height() * self.scale_y)
        )
    
    def __str__(self):
        """Rappresentazione stringa dell'elemento"""
        return f"SvgItem({os.path.basename(self.svg_path)}, scale_x={self.scale_x:.2f}, scale_y={self.scale_y:.2f})"
    
    def _handle_corner_interaction(self, pos, handle_id):
        """Gestisce l'interazione con gli handle dei corni"""
        # Implementazione base per i corni - modifica la curvatura degli angoli
        delta = pos - self._drag_start_pos
        
        self.update()
        
        # TODO: Implementare logica specifica per modificare i corni dell'SVG
        print(f"Modifica corno {handle_id}: delta={delta.x()}, {delta.y()}")
    
    def _handle_path_point_interaction(self, pos, handle_id):
        """Gestisce l'interazione con gli handle dei punti di percorso"""
        # Implementazione base per i punti di percorso
        delta = pos - self._drag_start_pos
        
        self.update()
        
        # TODO: Implementare logica per spostare i punti del percorso SVG
        print(f"Modifica punto percorso {handle_id}: delta={delta.x()}, {delta.y()}")
    
    def _handle_bezier_interaction(self, pos, handle_id):
        """Gestisce l'interazione con gli handle delle curve di Bézier"""
        # Implementazione base per le curve di Bézier
        delta = pos - self._drag_start_pos
        
        self.update()
        
        # TODO: Implementare logica per modificare le curve di Bézier
        print(f"Modifica curva Bézier {handle_id}: delta={delta.x()}, {delta.y()}")
    
    def _handle_node_interaction(self, pos, handle_id):
        """Gestisce l'interazione con gli handle dei nodi"""
        # Implementazione base per i nodi
        delta = pos - self._drag_start_pos
        
        self.update()
        
        # TODO: Implementare logica per spostare i nodi dell'SVG
        print(f"Modifica nodo {handle_id}: delta={delta.x()}, {delta.y()}")
    
    def _handle_radius_interaction(self, pos, handle_id):
        """Gestisce l'interazione con gli handle del raggio"""
        # Implementazione base per il raggio
        delta = pos - self._drag_start_pos
        
        self.update()
        
        # TODO: Implementare logica per modificare il raggio degli elementi circolari
        print(f"Modifica raggio {handle_id}: delta={delta.x()}, {delta.y()}")
    
    def _handle_arc_interaction(self, pos, handle_id):
        """Gestisce l'interazione con gli handle degli archi"""
        # Implementazione base per gli archi
        delta = pos - self._drag_start_pos
        
        self.update()
        
        # TODO: Implementare logica per modificare gli archi dell'SVG
        print(f"Modifica arco {handle_id}: delta={delta.x()}, {delta.y()}")
    
    def _handle_text_interaction(self, pos, handle_id):
        """Gestisce l'interazione con gli handle del testo"""
        # Implementazione base per il testo
        delta = pos - self._drag_start_pos
        
        self.update()
        
        # TODO: Implementare logica per modificare il testo dell'SVG
        print(f"Modifica testo {handle_id}: delta={delta.x()}, {delta.y()}")
    
    # Metodi per gestire la rotazione nel file SVG
    def _get_svg_transform(self):
        """Legge l'attributo transform dall'elemento root dell'SVG"""
        if self._svg_root is None:
            return None
        
        transform_attr = self._svg_root.get('transform', '')
        return transform_attr if transform_attr else None
    
    def _parse_svg_rotation(self, transform_str):
        """Estrae il valore di rotazione da una stringa transform SVG"""
        if not transform_str:
            return 0.0
        
        import re
        # Cerca pattern come "rotate(45)" o "rotate(45 cx cy)"
        rotate_match = re.search(r'rotate\(([^)]+)\)', transform_str)
        if rotate_match:
            rotate_params = rotate_match.group(1).split()
            try:
                return float(rotate_params[0])
            except (ValueError, IndexError):
                return 0.0
        return 0.0
    
    def _set_svg_transform(self, rotation_angle):
        """Imposta l'attributo transform nell'elemento root dell'SVG"""
        if self._svg_root is None:
            return False
        
        try:
            # Calcola il centro dell'SVG per la rotazione
            if self.svg_size:
                cx = self.svg_size.width() / 2
                cy = self.svg_size.height() / 2
                
                # Crea la stringa transform con rotazione attorno al centro
                if abs(rotation_angle) < 0.01:  # Considera 0 se molto piccolo
                    # Rimuovi l'attributo transform se la rotazione è praticamente zero
                    if 'transform' in self._svg_root.attrib:
                        del self._svg_root.attrib['transform']
                else:
                    transform_str = f"rotate({rotation_angle:.2f} {cx:.2f} {cy:.2f})"
                    self._svg_root.set('transform', transform_str)
                
                return True
        except Exception as e:
            print(f"Errore nell'impostazione del transform SVG: {e}")
            return False
        
        return False
    
    def _save_svg_to_file(self):
        """Salva il contenuto SVG modificato nel file"""
        if self._svg_root is None or not self.svg_path:
            return False
        
        try:
            # Converte l'albero XML in stringa
            import xml.etree.ElementTree as ET
            ET.register_namespace('', 'http://www.w3.org/2000/svg')  # Preserva il namespace SVG
            
            # Crea una stringa XML formattata
            rough_string = ET.tostring(self._svg_root, encoding='unicode')
            
            # Aggiungi la dichiarazione XML se non presente
            if not rough_string.startswith('<?xml'):
                xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + rough_string
            else:
                xml_content = rough_string
            
            # Salva nel file
            with open(self.svg_path, 'w', encoding='utf-8') as f:
                f.write(xml_content)
            
            # Aggiorna il contenuto interno
            self._modified_svg_content = xml_content
            
            print(f"SVG salvato con successo: {os.path.basename(self.svg_path)}")
            return True
            
        except Exception as e:
            print(f"Errore nel salvataggio dell'SVG: {e}")
            return False

    def _get_svg_content_for_save(self):
        """Restituisce il contenuto SVG corrente da usare per il salvataggio."""
        if (self._show_border or self._show_fill) and self._modified_svg_content:
            return self._modified_svg_content

        if self._svg_root is not None:
            return ET.tostring(self._svg_root, encoding='unicode')

        return self._modified_svg_content or self._original_svg_content
    
    def save_to_file(self, file_path):
        """Salva l'SVG corrente con tutte le modifiche (colori, dimensioni) in un nuovo file"""
        if self._svg_root is None:
            return False
            
        try:
            import xml.etree.ElementTree as ET
            # Assicura namespace
            try:
                ET.register_namespace('', "http://www.w3.org/2000/svg")
            except:
                pass
                
            current_svg_content = self._get_svg_content_for_save()
            root_to_save = ET.fromstring(current_svg_content)
            
            # Scrivi su file
            tree = ET.ElementTree(root_to_save)
            with open(file_path, 'wb') as f:
                tree.write(f, encoding='utf-8', xml_declaration=True)
            
            print(f"SVG salvato con successo in: {file_path}")
            return True
            
        except Exception as e:
            print(f"Errore nel salvataggio SVG su file: {e}")
            return False

    def reset_rotation(self):
        """Ripristina la rotazione originale dell'SVG"""
        # Reset della trasformazione visiva
        self.setTransform(QTransform())
        self._current_rotation = 0.0
        
        # Reset della rotazione nel file SVG
        if self._set_svg_transform(0.0):
            self._save_svg_to_file()
            # Ricarica il renderer per riflettere i cambiamenti
            self._reload_svg_renderer()
        
        self.update()
        print("Rotazione SVG ripristinata")
    
    def reset_styles(self):
        """Ripristina gli stili originali dell'SVG"""
        # Disabilita tutti gli stili personalizzati
        self._show_fill = False
        self._show_border = False
        
        # Applica i cambiamenti
        self._apply_styles_to_svg()
        
        print("Stili SVG ripristinati ai valori originali")
    
    def _load_existing_rotation(self):
        """Carica la rotazione esistente dal file SVG e la applica alla visualizzazione"""
        try:
            # Leggi la rotazione dal file SVG
            existing_transform = self._get_svg_transform()
            if existing_transform:
                rotation = self._parse_svg_rotation(existing_transform)
                if rotation != 0.0:
                    # Applica la rotazione alla visualizzazione
                    from PySide6.QtGui import QTransform
                    item_rect = self.boundingRect()
                    item_center = item_rect.center()
                    
                    transform = QTransform()
                    transform.translate(item_center.x(), item_center.y())
                    transform.rotate(rotation)
                    transform.translate(-item_center.x(), -item_center.y())
                    
                    self.setTransform(transform)
                    
                    # Salva la rotazione corrente
                    self._current_rotation = rotation
                    
                    print(f"Rotazione esistente caricata: {rotation:.2f}°")
        except Exception as e:
            print(f"Errore nel caricare la rotazione esistente: {e}")
            # In caso di errore, inizializza con rotazione zero
            self._current_rotation = 0.0
