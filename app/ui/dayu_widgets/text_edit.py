#!/usr/bin/env python
# -*- coding: utf-8 -*-
###################################################################
# Author: Mu yanru
# Date  : 2019.6
# Email : muyanru345@163.com
###################################################################

# Import future modules
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

# Import third-party modules
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets


class MSizeGrip(QtWidgets.QSizeGrip):
    def __init__(self, parent=None):
        super(MSizeGrip, self).__init__(parent)


def _has_foreground(fmt):
    """True se il char format ha un foreground esplicito."""
    try:
        return fmt.foreground().style() != QtCore.Qt.BrushStyle.NoBrush
    except Exception:
        try:
            return fmt.hasProperty(QtGui.QTextFormat.Property.ForegroundBrush)
        except Exception:
            return False


class MTextEdit(QtWidgets.QTextEdit):
    def __init__(self, parent=None):
        super(MTextEdit, self).__init__(parent)
        self.setWindowFlags(QtCore.Qt.SubWindow)
        self._size_grip = MSizeGrip(self)
        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._size_grip, 0, 0, QtCore.Qt.AlignBottom | QtCore.Qt.AlignRight)
        self.setLayout(layout)
        self._size_grip.setVisible(False)
        self._is_focused_by_click = False

    def focusInEvent(self, event):
        """Override per gestire l'evento di focus in entrata"""
        super(MTextEdit, self).focusInEvent(event)
        self._is_focused_by_click = True
        # Normalizza eventuali frammenti incollati in precedenza con colore
        # nero (formattazione rich-text dagli appunti) che in dark mode
        # risultano illeggibili.
        try:
            self._normalize_document_colors()
        except Exception:
            pass
        # Applica uno stylesheet per mantenere l'aspetto attivo.
        # Il colore del testo segue il tema (bianco in dark mode) cosi`
        # il testo digitato resta sempre leggibile. Lo stylesheet da solo
        # non basta per il testo incollato (cfr. insertFromMimeData), che
        # porta con se` il proprio QTextCharFormat con foreground nero.
        try:
            text_color = "#ffffff" if self._is_dark_mode() else "#262626"
        except Exception:
            text_color = "#ffffff"
        self.setStyleSheet("""
            MTextEdit {{
                border: 2px solid #fadb14;
                border-radius: 4px;
                color: {color};
            }}
        """.format(color=text_color))
        # Allinea anche il formato corrente cosi` la digitazione usa il
        # colore del tema e non un eventuale nero residuo.
        try:
            self._reset_current_char_format()
        except Exception:
            pass

    def _is_dark_mode(self):
        """Rileva la modalita` scura dallo sfondo effettivo del widget."""
        try:
            bg = self.palette().color(QtGui.QPalette.ColorRole.Base)
            if not bg.isValid():
                bg = self.palette().color(QtGui.QPalette.ColorRole.Window)
            if not bg.isValid():
                return True
            return bg.lightness() < 128
        except Exception:
            return True

    def _theme_text_color(self):
        return QtGui.QColor("#ffffff") if self._is_dark_mode() else QtGui.QColor("#262626")

    def _reset_current_char_format(self):
        """Pulisce il foreground del formato corrente (eredita dal tema)."""
        cursor = self.textCursor()
        fmt = cursor.charFormat()
        if _has_foreground(fmt):
            fmt.clearForeground()
            cursor.setCharFormat(fmt)
            self.setTextCursor(cursor)
        self.setTextColor(self._theme_text_color())

    def _normalize_document_colors(self):
        """Forza un foreground leggibile sul tema corrente.

        Dark mode: i frammenti con testo scuro (es. nero incollato da
        appunti rich-text) diventano bianchi. Light mode: i frammenti
        quasi bianchi diventano scuri. Preserva grassetto/corsivo/ecc.:
        cambia solo il foreground.
        """
        doc = self.document()
        if doc is None or doc.isEmpty():
            return
        dark = self._is_dark_mode()
        target = QtGui.QColor("#ffffff") if dark else QtGui.QColor("#262626")
        target_fmt = QtGui.QTextCharFormat()
        target_fmt.setForeground(QtGui.QBrush(target))
        self.blockSignals(True)
        try:
            block = doc.begin()
            while block.isValid():
                it = block.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    if frag.isValid():
                        fmt = frag.charFormat()
                        if _has_foreground(fmt):
                            try:
                                c = fmt.foreground().color()
                            except Exception:
                                c = None
                            if c is not None and c.isValid():
                                bad = c.lightness() < 100 if dark else c.lightness() > 200
                                if bad:
                                    tmp = QtGui.QTextCursor(doc)
                                    tmp.setPosition(frag.position())
                                    tmp.setPosition(frag.position() + frag.length(),
                                                    QtGui.QTextCursor.MoveMode.KeepAnchor)
                                    tmp.mergeCharFormat(target_fmt)
                    it += 1
                block = block.next()
            # Allinea anche il formato di digitazione corrente.
            cursor = self.textCursor()
            cur_fmt = cursor.charFormat()
            try:
                cur_color = cur_fmt.foreground().color() if _has_foreground(cur_fmt) else None
            except Exception:
                cur_color = None
            if cur_color is not None and cur_color.isValid():
                bad = cur_color.lightness() < 100 if dark else cur_color.lightness() > 200
                if bad:
                    cursor.mergeCharFormat(target_fmt)
                    self.mergeCurrentCharFormat(target_fmt)
                    return
            self.setTextColor(target)
        finally:
            self.blockSignals(False)

    def insertFromMimeData(self, source):
        """Incolla sempre come testo semplice (niente colori dagli appunti).

        QTextEdit incolla di default l'HTML degli appunti, incluso
        <span style="color:#000000">: lo stylesheet con color:white non puo`
        sovrascriverlo perche' il formato del carattere ha precedenza.
        Inserendo solo source.text() il testo incollato eredita il colore
        del tema (bianco in dark mode) e resta sempre leggibile.
        """
        try:
            if source is not None and source.hasText():
                text = source.text()
                if text:
                    cursor = self.textCursor()
                    # Rimuove un eventuale foreground nero residuo dal cursore.
                    fmt = cursor.charFormat()
                    if _has_foreground(fmt):
                        try:
                            c = fmt.foreground().color()
                        except Exception:
                            c = None
                        if c is None or (c.isValid() and c.lightness() < 100 and self._is_dark_mode()):
                            fmt.clearForeground()
                            cursor.setCharFormat(fmt)
                            self.setTextCursor(cursor)
                    cursor.insertText(text)
                    self.setTextCursor(cursor)
                    # Garantisce che la digitazione successiva resti bianca.
                    try:
                        if self._is_dark_mode():
                            self.setTextColor(QtGui.QColor("#ffffff"))
                    except Exception:
                        pass
                    return
        except Exception:
            pass
        super(MTextEdit, self).insertFromMimeData(source)

    def setHtml(self, text):
        super(MTextEdit, self).setHtml(text)
        try:
            self._normalize_document_colors()
        except Exception:
            pass

    def focusOutEvent(self, event):
        """Override per gestire l'evento di focus in uscita.

        Il focus deve essere rilasciato solo quando l'utente clicca fuori dalla
        casella (ad esempio su un pulsante, un menu o un'area della UI non
        modificabile). Se il focus viene rubato dal graphics view o dalla scena
        (ad esempio perché il mouse passa sopra il canvas), lo manteniamo qui
        per evitare di interrompere la modifica del testo.
        """
        # Ottieni il widget che sta ricevendo il focus.
        # In alcune build di PySide6 QtWidgets.QApplication.focusWidget() può
        # restituire None se l'evento viene propagato durante la chiusura di
        # un popup; in tal caso accettiamo la normale perdita di focus.
        try:
            new_focus = QtWidgets.QApplication.focusWidget()
        except Exception:
            new_focus = None

        # Se il nuovo focus è nullo (chiusura di popup/menu), accetta la perdita.
        if new_focus is None:
            super(MTextEdit, self).focusOutEvent(event)
            self._is_focused_by_click = False
            self.setStyleSheet("")
            return

        # Se il focus resta sul widget stesso o passa a un discendente, accetta.
        if new_focus is self or self.isAncestorOf(new_focus):
            super(MTextEdit, self).focusOutEvent(event)
            return

        # Se il focus va a un widget che vive sul graphics view / canvas
        # (QGraphicsView, QGraphicsScene, o un loro discendente), intercettiamo
        # e manteniamo il focus sulla casella di testo.
        from PySide6 import QtGui
        graphics_view = None
        parent = self.parent()
        while parent is not None:
            if isinstance(parent, QtWidgets.QGraphicsView):
                graphics_view = parent
                break
            parent = parent.parent()

        if graphics_view is not None:
            # Risaliamo la catena del nuovo focus widget per capire se appartiene
            # al graphics view: in tal caso l'utente non ha cliccato "fuori" ma
            # ha solo spostato il mouse sopra il canvas, quindi ignoriamo la
            # perdita di focus.
            ancestor = new_focus
            while ancestor is not None:
                if ancestor is graphics_view:
                    event.ignore()
                    # Re-assertiamo il focus per evitare che il cursore scompaia.
                    self.setFocus(QtCore.Qt.FocusReason.OtherFocusReason)
                    return
                parent = ancestor.parent()
                ancestor = parent if isinstance(parent, QtWidgets.QWidget) else None

        # Altrimenti il focus è andato a un widget "valido" della UI: accetta.
        super(MTextEdit, self).focusOutEvent(event)
        self._is_focused_by_click = False
        # Rimuovi lo stylesheet personalizzato quando perde il focus
        self.setStyleSheet("")

    def mousePressEvent(self, event):
        """Override per intercettare i click del mouse"""
        self._is_focused_by_click = True
        super(MTextEdit, self).mousePressEvent(event)

    def autosize(self):
        self.textChanged.connect(self._autosize_text_edit)
        return self

    def _autosize_text_edit(self):
        # w = self.width()
        doc = self.document()
        print(self.width(), doc.lineCount(), doc.idealWidth())

    def resizeable(self):
        """Show the size grip on bottom right. User can use it to resize MTextEdit"""
        self._size_grip.setVisible(True)
        return self
