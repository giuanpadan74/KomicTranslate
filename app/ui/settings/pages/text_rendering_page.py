from PySide6 import QtWidgets, QtGui

from ...dayu_widgets.label import MLabel
from ...dayu_widgets.combo_box import MComboBox
from ...dayu_widgets.spin_box import MSpinBox
from ...dayu_widgets.check_box import MCheckBox
from ...dayu_widgets.push_button import MPushButton
from ...dayu_widgets.browser import MClickBrowserFileToolButton


class TextRenderingPage:
    
    def _create_text_rendering_widget(self) -> QtWidgets.QWidget:
        text_rendering_widget = QtWidgets.QWidget()
        text_rendering_layout = QtWidgets.QVBoxLayout(text_rendering_widget)

        font_layout = QtWidgets.QVBoxLayout()

        min_font_layout = QtWidgets.QHBoxLayout()
        max_font_layout = QtWidgets.QHBoxLayout()
        min_font_label = MLabel(self.tr("Minimum Font Size:"))
        max_font_label = MLabel(self.tr("Maximum Font Size:"))

        self.min_font_spinbox = MSpinBox().small()
        self.min_font_spinbox.setFixedWidth(60)
        self.min_font_spinbox.setMaximum(100)
        self.min_font_spinbox.setValue(9)

        self.max_font_spinbox = MSpinBox().small()
        self.max_font_spinbox.setFixedWidth(60)
        self.max_font_spinbox.setMaximum(100)
        self.max_font_spinbox.setValue(40)

        min_font_layout.addWidget(min_font_label)
        min_font_layout.addWidget(self.min_font_spinbox)
        min_font_layout.addStretch()

        max_font_layout.addWidget(max_font_label)
        max_font_layout.addWidget(self.max_font_spinbox)
        max_font_layout.addStretch()

        font_label = MLabel(self.tr("Font:")).h4()
        
        font_browser_layout = QtWidgets.QHBoxLayout()
        import_font_label = MLabel(self.tr("Import Font:"))
        self.font_browser = MClickBrowserFileToolButton(multiple=True)
        self.font_browser.set_dayu_filters([".ttf", ".ttc", ".otf", ".woff", ".woff2"])
        self.font_browser.setToolTip(self.tr("Import the Font to use for Rendering Text on Images"))
        
        font_browser_layout.addWidget(import_font_label)
        font_browser_layout.addWidget(self.font_browser)
        font_browser_layout.addStretch()

        color_layout = QtWidgets.QHBoxLayout()
        color_label = MLabel(self.tr("Text Color:"))
        self.color_button = QtWidgets.QPushButton()
        self.color_button.setFixedSize(30, 30)
        self.color_button.setStyleSheet("background-color: #000000; border: none; border-radius: 5px;")
        self.color_button.setProperty('selected_color', '#000000')
        
        outline_color_label = MLabel(self.tr("Outline Color:"))
        self.outline_color_button = QtWidgets.QPushButton()
        self.outline_color_button.setFixedSize(30, 30)
        self.outline_color_button.setStyleSheet("background-color: #FFFFFF; border: none; border-radius: 5px;")
        self.outline_color_button.setProperty('selected_color', '#FFFFFF')
        
        color_layout.addWidget(color_label)
        color_layout.addWidget(self.color_button)
        color_layout.addSpacing(20)
        color_layout.addWidget(outline_color_label)
        color_layout.addWidget(self.outline_color_button)
        color_layout.addStretch()

        self.system_fonts_label = MLabel(self.tr("Font disponibili:")).h4()
        self.system_fonts_container = QtWidgets.QWidget()
        self.system_fonts_layout = QtWidgets.QVBoxLayout(self.system_fonts_container)
        
        self.font_scroll_area = QtWidgets.QScrollArea()
        self.font_scroll_area.setWidgetResizable(True)
        self.font_scroll_area.setWidget(self.system_fonts_container)
        self.font_scroll_area.setMinimumHeight(200)
        
        self.font_checkboxes = {}
        for font_family in QtGui.QFontDatabase().families():
            checkbox = MCheckBox(font_family)
            checkbox.setStyleSheet(f"font-family: '{font_family}';")
            checkbox.stateChanged.connect(self._on_font_checkbox_changed)
            self.font_checkboxes[font_family] = checkbox
            self.system_fonts_layout.addWidget(checkbox)

        font_button_layout = QtWidgets.QHBoxLayout()
        self.select_all_fonts_button = MPushButton(self.tr("Seleziona tutti"))
        self.select_all_fonts_button.clicked.connect(self._select_all_fonts)
        self.deselect_all_fonts_button = MPushButton(self.tr("Deseleziona tutti"))
        self.deselect_all_fonts_button.clicked.connect(self._deselect_all_fonts)
        
        font_button_layout.addWidget(self.select_all_fonts_button)
        font_button_layout.addWidget(self.deselect_all_fonts_button)
        font_button_layout.addStretch()

        font_layout.addWidget(font_label)
        font_layout.addLayout(font_browser_layout)
        font_layout.addLayout(min_font_layout)
        font_layout.addLayout(max_font_layout)
        font_layout.addLayout(color_layout)
        font_layout.addWidget(self.system_fonts_label)
        font_layout.addLayout(font_button_layout)
        font_layout.addWidget(self.font_scroll_area)

        font_layout_widget = QtWidgets.QWidget()
        font_layout_widget.setLayout(font_layout)

        self.uppercase_checkbox = MCheckBox(self.tr("Render Text in UpperCase"))
        text_rendering_layout.addWidget(self.uppercase_checkbox)
        self.pre_ocr_filter_checkbox = MCheckBox(self.tr("Pre-OCR filtro"))
        self.pre_ocr_filter_checkbox.setToolTip(self.tr("Esegue OCR durante il rilevamento per rimuovere automaticamente caselle vuote e numeri di pagina"))
        text_rendering_layout.addWidget(self.pre_ocr_filter_checkbox)

        text_rendering_layout.addSpacing(10)
        text_rendering_layout.addWidget(font_layout_widget)
        text_rendering_layout.addSpacing(10)

        text_rendering_layout.addStretch(1)
        return text_rendering_widget
    
    def _select_all_fonts(self):
        for checkbox in self.font_checkboxes.values():
            checkbox.setChecked(True)
        parent = self.parent()
        if parent and hasattr(parent, 'selected_fonts_changed'):
            parent.selected_fonts_changed.emit()
            
    def _deselect_all_fonts(self):
        for checkbox in self.font_checkboxes.values():
            checkbox.setChecked(False)
        parent = self.parent()
        if parent and hasattr(parent, 'selected_fonts_changed'):
            parent.selected_fonts_changed.emit()
            
    def _on_font_checkbox_changed(self):
        parent = self.parent()
        if parent and hasattr(parent, 'selected_fonts_changed'):
            parent.selected_fonts_changed.emit()
