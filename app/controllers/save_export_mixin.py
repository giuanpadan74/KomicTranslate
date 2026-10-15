"""Mixin di salvataggio ed esportazione con cleanup obbligatorio e
controllo preventivo Boxes.

Override dei 4 metodi di salvataggio / esportazione di ``ProjectMixin``
per garantire che, prima di ogni operazione:

  1. Venga eseguito un controllo obbligatorio che verifica l'assenza
     di elementi grafici "Boxes" sovrapposti all'immagine.
  2. Se rilevati, vengano rimossi automaticamente.
  3. Il salvataggio proceda SOLO dopo che non ci sono piu' Boxes.
  4. Venga registrato un log per tracciabilita' interna.
  5. Venga verificata l'integrita' del file salvato.

I 4 metodi overridati sono:

  1. ``thread_save_as_project()``  - "Salva come" in formato .ctpr
  2. ``save_current_image()``      - salva l'immagine attualmente caricata
  3. ``export_to_pdf()``           - esporta il progetto corrente in PDF
  4. ``save_and_make()``           - esporta tutte le immagini in archivio
"""

import logging
from typing import Optional

from app.controllers.save_cleanup import deactivate_viewer_selections
from app.controllers.save_export_cleanup import (
    prohibited_elements_hidden,
    verify_prohibited_count,
)
from app.controllers.save_boxes_check import (
    auto_remove_boxes,
    log_save_operation,
    verify_image_integrity,
)

logger = logging.getLogger(__name__)


def _basename(path: str) -> str:
    """Restituisce il basename di un path (o stringa vuota)."""
    import os as _os
    return _os.path.basename(path) if path else ""


class SaveExportMixin:
    """Mixin che aggiunge cleanup obbligatorio e controllo Boxes a
    save / export."""

    # --- Controllo preventivo Boxes obbligatorio -------------------- #

    def _enforce_no_boxes(self, operation_name: str) -> bool:
        """Verifica obbligatoria: se Boxes sono presenti, li rimuove
        automaticamente. Ritorna True se si puo' procedere."""
        viewer = getattr(self, "image_viewer", None)
        can_proceed = auto_remove_boxes(viewer, operation_name)

        if not can_proceed:
            logger.error(
                "[BOXES_CHECK] Boxes residui dopo rimozione per %s - "
                "possibile interferenza con salvataggio",
                operation_name,
            )

        return can_proceed

    # --- Hook diagnostici ------------------------------------------ #

    def _pre_save_check(self, operation_name: str):
        viewer = getattr(self, "image_viewer", None)
        return verify_prohibited_count(viewer, operation_name)

    def _post_save_check(self, operation_name: str):
        viewer = getattr(self, "image_viewer", None)
        return verify_prohibited_count(viewer, f"{operation_name} [post]")

    # 1. "Salva come" .ctpr ----------------------------------------- #

    def thread_save_as_project(self):
        """Salva il progetto in formato .ctpr senza rimozione distruttiva dei boxes."""
        op = "thread_save_as_project"
        self._pre_save_check(op)
        with prohibited_elements_hidden(getattr(self, "image_viewer", None)):
            deactivate_viewer_selections(self.image_viewer)
            super().thread_save_as_project()
        self._post_save_check(op)

    # 2. Salva immagine attualmente caricata ------------------------- #

    def save_current_image(self, file_path: str):
        """Salva l'immagine corrente con controllo obbligatorio Boxes."""
        op = f"save_current_image({_basename(file_path)})"
        if not self._enforce_no_boxes(op):
            return
        self._pre_save_check(op)
        try:
            with prohibited_elements_hidden(getattr(self, "image_viewer", None)):
                deactivate_viewer_selections(self.image_viewer)
                super().save_current_image(file_path)
            log_save_operation(op, file_path, success=True)
            if file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp', '.webp')):
                verify_image_integrity(file_path)
        except Exception as exc:
            log_save_operation(op, file_path, success=False, extra_info=str(exc))
            raise
        self._post_save_check(op)

    # 3. Esporta progetto corrente in PDF ----------------------------- #

    def export_to_pdf(self):
        """Esporta l'immagine corrente in PDF con controllo obbligatorio."""
        op = "export_to_pdf"
        if not self._enforce_no_boxes(op):
            return
        self._pre_save_check(op)
        with prohibited_elements_hidden(getattr(self, "image_viewer", None)):
            deactivate_viewer_selections(self.image_viewer)
            super().export_to_pdf()
        self._post_save_check(op)

    # 4. Esporta tutte le immagini in archivio ------------------------ #

    def save_and_make(self, output_path: str):
        """Esporta tutte le immagini con controllo obbligatorio Boxes."""
        op = f"save_and_make({_basename(output_path)})"
        if not self._enforce_no_boxes(op):
            return
        self._pre_save_check(op)
        try:
            with prohibited_elements_hidden(getattr(self, "image_viewer", None)):
                deactivate_viewer_selections(self.image_viewer)
                super().save_and_make(output_path)
            log_save_operation(op, output_path, success=True)
        except Exception as exc:
            log_save_operation(op, output_path, success=False, extra_info=str(exc))
            raise
        self._post_save_check(op)
