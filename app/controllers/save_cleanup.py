from PySide6 import QtWidgets


def deactivate_viewer_selections(image_viewer) -> None:
    """Disattiva editing e selezioni del canvas prima di un salvataggio."""
    if image_viewer is None:
        return

    for text_item in list(getattr(image_viewer, "text_items", [])):
        if getattr(text_item, "editing_mode", False) and hasattr(text_item, "exit_editing_mode"):
            text_item.exit_editing_mode()

        if hasattr(text_item, "textCursor") and hasattr(text_item, "setTextCursor"):
            cursor = text_item.textCursor()
            if cursor.hasSelection():
                cursor.clearSelection()
                text_item.setTextCursor(cursor)

        if hasattr(text_item, "set_multi_selected"):
            text_item.set_multi_selected(False)

        if hasattr(text_item, "update_outlines"):
            try:
                # Mantiene il contorno persistente del testo, rimuovendo solo
                # eventuali selezioni transienti prima del rendering/salvataggio.
                text_item.update_outlines()
            except RuntimeError:
                pass

        if hasattr(text_item, "handleDeselection"):
            text_item.handleDeselection()
        elif hasattr(text_item, "setSelected"):
            text_item.setSelected(False)

    if hasattr(image_viewer, "deselect_all"):
        image_viewer.deselect_all()

    scene = getattr(image_viewer, "_scene", None)
    if scene is not None:
        scene.clearSelection()
        scene.clearFocus()

    image_viewer.clearFocus()

    focus_widget = QtWidgets.QApplication.focusWidget()
    if focus_widget is not None:
        focus_widget.clearFocus()
