"""
Block synchronization mixin for BatchMixin.

Handles checking existing blocks and syncing with UI rectangles.
"""
import os
import logging
import numpy as np
from shiboken6 import isValid

from constants import BLOCK_MATCH_DIST_THRESHOLD
from modules.detection import get_inpaint_bboxes
from modules.utils.textblock import TextBlock

logger = logging.getLogger(__name__)


class BlockSyncMixin:
    """Block synchronization functionality for batch operations."""

    def _get_valid_visible_rects_for_batch(self):
        """Restituisce solo rettangoli Qt ancora validi e presenti nella scena."""
        scene = getattr(self.image_viewer, "_scene", None)
        if scene is None:
            return []

        valid_rects = []
        stale_refs = []
        for rect in list(getattr(self.image_viewer, "rectangles", []) or []):
            try:
                if not rect or not isValid(rect):
                    stale_refs.append(rect)
                    continue
                if rect.scene() != scene or not rect.isVisible():
                    continue
            except RuntimeError:
                stale_refs.append(rect)
                continue
            valid_rects.append(rect)

        if stale_refs:
            self.image_viewer.rectangles = [
                rect for rect in self.image_viewer.rectangles
                if rect not in stale_refs
            ]
            logger.warning(
                "[SYNC] Rimossi %d riferimenti a rettangoli Qt non piu validi",
                len(stale_refs),
            )

        return valid_rects

    def _check_existing_blocks_batch(self):
        """Verifica quali immagini hanno già caselle di testo valide"""
        images_with_blocks = []
        for image_path in self.image_files:
            if self.pipeline._are_blocks_valid(image_path):
                image_state = self.image_states[image_path]
                # Priorità a blk_list. Fallback a text_blocks solo se blk_list non è presente nello stato.
                if 'blk_list' in image_state:
                    existing_blocks = image_state['blk_list']
                else:
                    existing_blocks = image_state.get('text_blocks', [])
                if existing_blocks and len(existing_blocks) > 0:
                    images_with_blocks.append(image_path)
                    logger.info(f"[BATCH_CHECK] {os.path.basename(image_path)}: {len(existing_blocks)} caselle esistenti")
        return images_with_blocks

    def _sync_blocks_with_ui(self):
        """Sincronizza i blocchi in memoria con i rettangoli visibili a schermo"""
        if not self.image_viewer.hasPhoto():
            return

        visible_rects = self._get_valid_visible_rects_for_batch()

        logger.info(f"[SYNC] Inizio sync: {len(visible_rects)} rettangoli vs {len(self.blk_list)} blocchi")

        new_blk_list = []
        matched_blks = set()
        image = None  # Cache variable to avoid repeated get_cv2_image calls

        for rect_item in visible_rects:
            scene_rect = rect_item.mapRectToScene(rect_item.rect())
            rect_coords = scene_rect.getCoords()

            blk = self.find_corresponding_text_block(rect_coords, 0.5)

            if not blk:
                blk = self.find_corresponding_text_block(rect_coords, 0.1)

            if not blk:
                min_dist = float('inf')
                closest = None
                rc_x = (rect_coords[0] + rect_coords[2]) / 2
                rc_y = (rect_coords[1] + rect_coords[3]) / 2
                for b in self.blk_list:
                    if b in matched_blks:
                        continue
                    bx = (b.xyxy[0] + b.xyxy[2]) / 2
                    by = (b.xyxy[1] + b.xyxy[3]) / 2
                    dist = ((rc_x - bx)**2 + (rc_y - by)**2)**0.5
                    if dist < BLOCK_MATCH_DIST_THRESHOLD and dist < min_dist:
                        min_dist = dist
                        closest = b
                blk = closest

            if blk and blk not in matched_blks:
                new_blk_list.append(blk)
                matched_blks.add(blk)
            else:
                logger.info(f"[SYNC] Creazione nuovo blocco per rettangolo a {rect_coords}")
                # Le coordinate scena sono float: normalizza a int una sola volta.
                # Con float, img[y1:y2, x1:x2] solleva TypeError e l'OCR del
                # blocco disegnato a mano falliva sempre (testo "" -> '...').
                ix1, iy1, ix2, iy2 = (int(round(rect_coords[0])), int(round(rect_coords[1])),
                                      int(round(rect_coords[2])), int(round(rect_coords[3])))
                if ix2 < ix1:
                    ix1, ix2 = ix2, ix1
                if iy2 < iy1:
                    iy1, iy2 = iy2, iy1
                int_rect = (ix1, iy1, ix2, iy2)
                region_blk = blk if blk is not None else None
                # Cache image outside loop to avoid repeated expensive calls
                if image is None:
                    image = self.image_viewer.get_cv2_image()
                bubble_bbox = (
                    region_blk.get_active_inpaint_bbox()
                    if region_blk is not None and hasattr(region_blk, "get_active_inpaint_bbox")
                    else getattr(region_blk, 'bubble_xyxy', None)
                )
                bubble_polygon = (
                    region_blk.get_active_inpaint_polygon()
                    if region_blk is not None and hasattr(region_blk, "get_active_inpaint_polygon")
                    else getattr(region_blk, 'polygon_points', None)
                )
                # Blocco disegnato a mano senza corrispondente: usa il rettangolo
                # stesso come bubble/poligono (come handle_rectangle_creation),
                # altrimenti bubble=None impedisce il crop OCR corretto.
                if bubble_bbox is None:
                    bubble_bbox = np.array(int_rect, dtype=np.int32)
                if bubble_polygon is None:
                    bubble_polygon = np.array([
                        [ix1, iy1], [ix2, iy1], [ix2, iy2], [ix1, iy2]
                    ], dtype=np.int32)
                inpaint = get_inpaint_bboxes(
                    int_rect,
                    image,
                    bubble_bbox,
                    bubble_polygon,
                )
                new_blk = TextBlock(
                    text_bbox=np.array(int_rect),
                    bubble_bbox=np.array(bubble_bbox, dtype=np.int32),
                    inpaint_bboxes=inpaint,
                    text_segm_points=np.array(bubble_polygon, dtype=np.int32),
                    text_class=getattr(region_blk, 'text_class', ''),
                )
                new_blk_list.append(new_blk)

        self.blk_list = new_blk_list
        if 0 <= self.curr_img_idx < len(self.image_files):
            current_file = self.image_files[self.curr_img_idx]
            if current_file in self.image_states:
                self.save_current_image_state()
        logger.info(f"[SYNC] Completata. Nuova lista: {len(self.blk_list)} blocchi")
