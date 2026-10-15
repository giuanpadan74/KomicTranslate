"""
PolygonInpaintMixin - Gestione della commutazione poligono/rettangolo per inpainting.

Permette di convertire la selezione inpainting da poligono (automatico) a rettangolo
per ottenere un riempimento più preciso e privo di errori.
"""
import numpy as np
from typing import List, Optional

from modules.utils.polygon_region import polygon_to_bbox, normalize_polygon_points


class PolygonInpaintMixin:
    """Mixin per gestire la commutazione poligono/rettangolo per inpainting."""

    def _get_selected_rect_items_for_inpaint(self) -> List:
        """Ottiene i rect_item selezionati per l'inpainting."""
        if not hasattr(self, 'image_viewer'):
            return []
        return self.image_viewer.get_selected_rectangles()

    def refresh_polygon_inpaint_button_state(self):
        """Aggiorna lo stato del pulsante polygon_inpaint_button."""
        button = getattr(self, 'polygon_inpaint_button', None)
        if button is None:
            return

        selected_rects = self._get_selected_rect_items_for_inpaint()
        has_selection = len(selected_rects) > 0

        button.blockSignals(True)
        button.setVisible(True)
        button.setEnabled(has_selection)

        # Se c'è selezione, verifica lo stato del primo elemento
        if has_selection:
            first_rect = selected_rects[0]
            blk = getattr(first_rect, 'text_block', None)
            if blk is not None:
                # Checked = modalità poligono, Unchecked = modalità rettangolo
                use_polygon = getattr(blk, 'use_polygon_inpaint', True)
                button.setChecked(use_polygon)
                self._update_button_icon(button, use_polygon)
        else:
            button.setChecked(False)
            self._update_button_icon(button, False)
            button.setToolTip(
                "Commuta: seleziona una casella di testo per passare tra Rettangolo e Poligono"
            )
        button.blockSignals(False)

    def _update_button_icon(self, button, is_polygon_mode: bool):
        """Mantiene un'icona unica e aggiorna il tooltip in base alla modalità."""
        button.set_dayu_svg("square-pentagon-outline.svg")
        if is_polygon_mode:
            button.setToolTip(
                "Commuta: modalità inpainting attiva Poligono"
            )
        else:
            button.setToolTip(
                "Commuta: modalità inpainting attiva Rettangolo"
            )

    def toggle_polygon_inpaint_mode(self, checked: bool):
        """
        Commuta la modalità di selezione inpainting per gli elementi selezionati.

        Args:
            checked: True = modalità poligono, False = modalità rettangolo
        """
        selected_rects = self._get_selected_rect_items_for_inpaint()
        if not selected_rects:
            self.refresh_polygon_inpaint_button_state()
            return

        for rect_item in selected_rects:
            blk = getattr(rect_item, 'text_block', None)
            if blk is None:
                continue

            if checked:
                # Modalità poligono: ripristina il poligono originale
                self._restore_polygon_mode(blk, rect_item)
            else:
                # Modalità rettangolo: converti in bounding box
                self._convert_to_rectangle_mode(blk, rect_item)

            # Aggiorna l'overlay visivo
            self._refresh_inpaint_overlay_for_block(blk, rect_item, checked)

        # Salva lo stato
        if hasattr(self, '_schedule_save_current_image_state'):
            self._schedule_save_current_image_state(100)

        # Aggiorna l'icona del pulsante
        button = getattr(self, 'polygon_inpaint_button', None)
        if button is not None:
            self._update_button_icon(button, checked)

        self.refresh_polygon_inpaint_button_state()

    def _convert_to_rectangle_mode(self, blk, rect_item):
        """Converte il poligono in un rettangolo per inpainting."""
        # Usa il bounding box del poligono come rettangolo
        xyxy = getattr(blk, 'xyxy', None)
        if xyxy is None:
            return

        # Crea punti rettangolari dal bounding box
        x1, y1, x2, y2 = [int(v) for v in xyxy]
        rect_points = np.array(
            [
                [x1, y1],
                [x2, y1],
                [x2, y2],
                [x1, y2],
            ],
            dtype=np.int32,
        )

        # Salva il poligono originale per eventuale ripristino
        if not hasattr(blk, '_original_polygon_points'):
            blk._original_polygon_points = getattr(blk, 'polygon_points', None)

        # Imposta i nuovi punti
        blk.polygon_points = rect_points
        blk.segm_pts = rect_points
        blk.use_polygon_inpaint = False

        # Aggiorna bubble_xyxy
        bbox = polygon_to_bbox(rect_points)
        if bbox is not None:
            blk.bubble_xyxy = bbox

        # Filtra le bbox inpainting
        blk.filter_inpaint_bboxes()

    def _restore_polygon_mode(self, blk, rect_item):
        """Ripristina il poligono originale."""
        # Ripristina il poligono originale se disponibile
        original_polygon = getattr(blk, '_original_polygon_points', None)

        if original_polygon is not None:
            blk.polygon_points = normalize_polygon_points(original_polygon)
        else:
            # Se non c'è un poligono originale, ricrea dal bounding box
            xyxy = getattr(blk, 'xyxy', None)
            if xyxy is not None:
                x1, y1, x2, y2 = [int(v) for v in xyxy]
                blk.polygon_points = np.array(
                    [
                        [x1, y1],
                        [x2, y1],
                        [x2, y2],
                        [x1, y2],
                    ],
                    dtype=np.int32,
                )

        blk.segm_pts = blk.polygon_points
        blk.use_polygon_inpaint = True

        # Aggiorna bubble_xyxy
        if blk.polygon_points is not None:
            bbox = polygon_to_bbox(blk.polygon_points)
            if bbox is not None:
                blk.bubble_xyxy = bbox

        # Filtra le bbox inpainting
        blk.filter_inpaint_bboxes()

    def _refresh_inpaint_overlay_for_block(self, blk, rect_item, is_polygon_mode: bool):
        """Aggiorna l'overlay visivo per il blocco."""
        if not hasattr(self, 'image_viewer'):
            return

        if hasattr(self, "_attach_polygon_overlay"):
            self._attach_polygon_overlay(rect_item)

        # Ottieni o crea l'overlay
        overlay = getattr(rect_item, 'polygon_overlay', None)
        if overlay is None:
            return

        overlay.refresh_from_block()
        overlay.set_selected(bool(is_polygon_mode and getattr(rect_item, "selected", False)))
        overlay.show()
