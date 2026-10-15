"""
ImageUpdateHandler - Gestione dell'aggiornamento delle immagini processate.

Estratto da controller.py per migliorare la manutenibilità e supportare il vibe coding.
"""
import logging
import numpy as np

logger = logging.getLogger(__name__)


class ImageUpdateHandler:
    """Mixin per la gestione dell'aggiornamento delle immagini nella UI."""

    def __init__(self, parent=None):
        super().__init__(parent)

    def on_image_processed(self, index: int, image: np.ndarray, image_path: str):
        """
        Callback quando un'immagine è stata processata.
        """
        if index == self.curr_img_idx:
            self.set_cv2_image(image)
        else:
            from app.ui.commands.image import SetImageCommand
            command = SetImageCommand(self, image_path, image, False)
            self.undo_group.activeStack().push(command)
            self.image_data[image_path] = image

    def on_image_skipped(self, image_path: str, skip_reason: str, error: str):
        """Callback quando un'immagine viene saltata durante il processing."""
        from PySide6.QtCore import QCoreApplication
        message = {
            "Text Blocks": QCoreApplication.translate('Messages', 'No Text Blocks Detected.\nSkipping:') + f" {image_path}\n{error}",
            "OCR": QCoreApplication.translate('Messages', 'Could not OCR detected text.\nSkipping:') + f" {image_path}\n{error}",
            "Translator": QCoreApplication.translate('Messages', 'Could not get translations.\nSkipping:') + f" {image_path}\n{error}"
        }

        text = message.get(skip_reason, f"Unknown skip reason: {skip_reason}. Error: {error}")

        from app.ui.dayu_widgets.message import MMessage
        MMessage.info(
            text=text,
            parent=self,
            duration=5,
            closable=True
        )