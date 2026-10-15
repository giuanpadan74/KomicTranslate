
from PySide6 import QtWidgets, QtCore, QtGui, QtWebEngineWidgets
from PySide6.QtCore import QUrl, Qt, QSize

class MiniBrowser(QtWidgets.QWidget):
    def __init__(self, parent=None, url="https://gemini.google.com/"):
        super().__init__(parent)
        self.setMinimumHeight(200)
        
        # Layout principale
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Toolbar
        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setContentsMargins(5, 5, 5, 5)
        toolbar.setSpacing(5)
        
        # Stile dei pulsanti
        btn_style = """
            QPushButton {
                background-color: #444;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 2px;
            }
            QPushButton:hover {
                background-color: #666;
            }
            QPushButton:pressed {
                background-color: #333;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                color: #555;
            }
        """
        
        # Pulsanti di navigazione
        self.btn_back = QtWidgets.QPushButton("◀")
        self.btn_back.setFixedSize(24, 24)
        self.btn_back.setStyleSheet(btn_style)
        self.btn_back.setToolTip("Indietro")
        self.btn_back.clicked.connect(self.go_back)
        
        self.btn_forward = QtWidgets.QPushButton("▶")
        self.btn_forward.setFixedSize(24, 24)
        self.btn_forward.setStyleSheet(btn_style)
        self.btn_forward.setToolTip("Avanti")
        self.btn_forward.clicked.connect(self.go_forward)
        
        self.btn_refresh = QtWidgets.QPushButton("↻")
        self.btn_refresh.setFixedSize(24, 24)
        self.btn_refresh.setStyleSheet(btn_style)
        self.btn_refresh.setToolTip("Aggiorna")
        self.btn_refresh.clicked.connect(self.reload)
        
        self.btn_expand = QtWidgets.QPushButton("⛶")
        self.btn_expand.setFixedSize(24, 24)
        self.btn_expand.setStyleSheet(btn_style)
        self.btn_expand.setToolTip("Schermo intero")
        self.btn_expand.clicked.connect(self.toggle_expand)

        self.btn_external = QtWidgets.QPushButton("↗")
        self.btn_external.setFixedSize(24, 24)
        self.btn_external.setStyleSheet(btn_style)
        self.btn_external.setToolTip("Apri nel browser predefinito")
        self.btn_external.clicked.connect(self.open_external)
        
        toolbar.addWidget(self.btn_back)
        toolbar.addWidget(self.btn_forward)
        toolbar.addWidget(self.btn_refresh)
        toolbar.addStretch()
        toolbar.addWidget(self.btn_external)
        
        # Widget contenitore per la toolbar per avere lo sfondo
        toolbar_widget = QtWidgets.QWidget()
        toolbar_widget.setStyleSheet("background-color: #222; border-top-left-radius: 8px; border-top-right-radius: 8px;")
        toolbar_widget.setLayout(toolbar)
        layout.addWidget(toolbar_widget)
        
        # Browser View
        self.webview = QtWebEngineWidgets.QWebEngineView()
        self.webview.setFocusPolicy(Qt.StrongFocus)
        
        # Ottimizzazioni Performance e Settings
        settings = self.webview.settings()
        settings.setAttribute(settings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(settings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(settings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(settings.WebAttribute.Accelerated2dCanvasEnabled, True)
        settings.setAttribute(settings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(settings.WebAttribute.ScrollAnimatorEnabled, True)
        
        # User Agent Linux per evitare prompt Windows Hello/Passkey
        profile = self.webview.page().profile()
        profile.setHttpUserAgent("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        self.webview.setUrl(QUrl(url))
        self.webview.setStyleSheet("background-color: white;") # Fallback
        layout.addWidget(self.webview)
        
        # Loading Indicator (Overlay)
        self.loading_label = QtWidgets.QLabel(self)
        self.loading_label.setAlignment(Qt.AlignCenter)
        self.loading_label.setStyleSheet("background-color: rgba(0, 0, 0, 150); color: white; font-weight: bold; border-radius: 4px;")
        self.loading_label.setText("Caricamento...")
        self.loading_label.hide()
        
        # Signals
        self.webview.loadStarted.connect(self.on_load_started)
        self.webview.loadFinished.connect(self.on_load_finished)
        self.webview.urlChanged.connect(self.update_buttons)
        
        self.update_buttons()
        
        # Stile generale del widget
        self.setStyleSheet("""
            MiniBrowser {
                border: 1px solid #444;
                border-radius: 8px;
            }
        """)
        
        # Shadow effect
        shadow = QtWidgets.QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(15)
        shadow.setColor(QtGui.QColor(0, 0, 0, 100))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

    def go_back(self):
        self.webview.back()

    def go_forward(self):
        self.webview.forward()

    def reload(self):
        self.webview.reload()

    def open_external(self):
        QtGui.QDesktopServices.openUrl(self.webview.url())

    def on_load_started(self):
        self.loading_label.show()
        self.loading_label.raise_()
        self._update_loading_pos()

    def on_load_finished(self, success):
        self.loading_label.hide()
        self.update_buttons()

    def update_buttons(self):
        self.btn_back.setEnabled(self.webview.history().canGoBack())
        self.btn_forward.setEnabled(self.webview.history().canGoForward())

    def resizeEvent(self, event):
        self._update_loading_pos()
        super().resizeEvent(event)
        
    def _update_loading_pos(self):
        if self.loading_label.isVisible():
            # Posiziona il loading al centro della webview
            webview_geo = self.webview.geometry()
            # Converti coordinate se necessario, ma qui sono relative a self
            self.loading_label.setGeometry(webview_geo)

    def toggle_expand(self):
        if not self.is_expanded:
            # Save state
            self._original_parent = self.parent()
            if self._original_parent:
                self._original_layout = self._original_parent.layout()
                if self._original_layout:
                    self._original_index = self._original_layout.indexOf(self)
            
            # Detach and maximize
            self.setParent(None)
            self.setWindowFlags(Qt.Window)
            self.showMaximized()
            self.is_expanded = True
            self.btn_expand.setText("↙")
            self.btn_expand.setToolTip("Ripristina")
        else:
            # Restore state
            self.setWindowFlags(Qt.Widget)
            if self._original_parent:
                self.setParent(self._original_parent)
                if self._original_layout and self._original_index >= 0:
                    self._original_layout.insertWidget(self._original_index, self)
            
            self.show()
            self.is_expanded = False
            self.btn_expand.setText("⛶")
            self.btn_expand.setToolTip("Schermo intero")

    def closeEvent(self, event):
        if self.is_expanded:
            event.ignore()
            self.toggle_expand()
        else:
            super().closeEvent(event)

    def eventFilter(self, source, event):
        if event.type() == QtCore.QEvent.MouseButtonPress:
            if source == self:
                self.webview.setFocus()
        return super().eventFilter(source, event)


