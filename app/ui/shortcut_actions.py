from PySide6 import QtWidgets

from app.ui.dayu_widgets.message import MMessage


def trigger_save_loaded_images(window) -> None:
    image_files = getattr(window, "image_files", None)
    if not image_files:
        QtWidgets.QApplication.beep()
        MMessage.warning(
            text=window.tr("Nessuna immagine caricata da salvare."),
            parent=window,
            duration=3,
            closable=True,
        )
        return

    save_browser = getattr(window, "save_browser", None)
    if save_browser is not None:
        save_browser.click()
