from PySide6 import QtCore, QtGui


def apply_patch_to_qimage(source: QtGui.QImage, rect: QtCore.QRect, patch: QtGui.QImage) -> QtGui.QImage:
    if source.isNull() or patch.isNull():
        return QtGui.QImage()
    result = source.copy()
    image_rect = QtCore.QRect(0, 0, result.width(), result.height())
    target_rect = rect.normalized().intersected(image_rect)
    if target_rect.width() <= 1 or target_rect.height() <= 1:
        return QtGui.QImage()
    target_size = target_rect.size()
    patch_image = patch
    if patch.size() != target_size:
        dw = patch.width() - target_size.width()
        dh = patch.height() - target_size.height()
        # Differenza di pochi pixel: taglia/estendi la patch SENZA scaling,
        # così i bordi source restano completamente coperti. Quando la patch
        # è più piccola, estendiamo ripetendo l'ultimo pixel (edge-extend),
        # non con trasparenza, per evitare di lasciare vedere la source.
        if abs(dw) <= 2 and abs(dh) <= 2:
            if dw >= 0 and dh >= 0:
                # Patch più grande o uguale in entrambe le dimensioni:
                # tagliamo dall'angolo in alto-a-sinistra.
                patch_image = patch.copy(0, 0, target_size.width(), target_size.height())
            else:
                # Patch più piccola in almeno una dimensione: creiamo un
                # canvas opaco delle dimensioni target riempiendolo con il
                # primo pixel della patch, poi incolliamo la patch a (0,0).
                canvas_format = (
                    patch.format()
                    if not patch.format() in (QtGui.QImage.Format.Format_Invalid,)
                    else QtGui.QImage.Format.Format_ARGB32
                )
                canvas = QtGui.QImage(target_size, canvas_format)
                # Edge-extend: riempi il canvas con il colore del primo
                # pixel della patch. Così non si vede la source sotto.
                edge_color = QtGui.QColor(patch.pixel(0, 0))
                canvas.fill(edge_color)
                painter = QtGui.QPainter(canvas)
                painter.drawImage(0, 0, patch)
                painter.end()
                patch_image = canvas
        else:
            # Differenza consistente (Gemini ha restituito una patch con
            # risoluzione diversa): scaling necessario per coprire l'area.
            patch_image = patch.scaled(
                target_size,
                QtCore.Qt.IgnoreAspectRatio,
                QtCore.Qt.SmoothTransformation,
            )
    painter = QtGui.QPainter(result)
    painter.drawImage(target_rect.topLeft(), patch_image)
    painter.end()
    return result
