from typing import List

from PySide6 import QtWidgets, QtCore
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl

from ...dayu_widgets.check_box import MCheckBox
from ...dayu_widgets.combo_box import MComboBox
from ...dayu_widgets.spin_box import MSpinBox
from ...dayu_widgets.label import MLabel
from ...dayu_widgets.text_edit import MTextEdit
from modules.utils.model_manager import model_manager
from modules.utils.translator_utils import refresh_model_map


class ToolsPage:
    
    def _create_tools_widget(self) -> QtWidgets.QWidget:
        tools_widget = QtWidgets.QWidget()
        tools_layout = QtWidgets.QVBoxLayout(tools_widget)
        tools_layout.setContentsMargins(5, 5, 5, 5)
        tools_layout.setSpacing(15)

        self.inpainters = ['LaMa', 'AOT', 'MI-GAN']
        self.inpaint_strategy = [self.tr('Resize'), self.tr('Original'), self.tr('Crop')]

        current_translators = self.get_supported_translators()
        current_ocr_engines = self.get_supported_ocr_engines()
        
        ocr_widget, self.ocr_combo = self._create_title_and_combo_with_highlights(self.tr("OCR"), current_ocr_engines)
        self.ocr_combo.setFixedWidth(200)
        ocr_section = self._create_section_container(self.tr("OCR"), ocr_widget)

        translator_widget, self.translator_combo = self._create_title_and_combo_with_highlights(self.tr("Translator"), current_translators)
        self.translator_combo.setFixedWidth(200)
        # Il prompt TXT sta sotto il dropdown Translator: e' l'unico prompt
        # ancora necessario, dato che TXT e' l'unico traduttore supportato.
        translator_widget_layout = translator_widget.layout()
        translator_widget_layout.addWidget(self._create_txt_prompt_section())
        translator_section = self._create_section_container(self.tr("Traduttore"), translator_widget)

        inpainting_container = QtWidgets.QWidget()
        inpainting_v_layout = QtWidgets.QVBoxLayout(inpainting_container)
        inpainting_v_layout.setContentsMargins(0, 0, 0, 0)
        inpainting_v_layout.setSpacing(10)

        current_inpainters = self.get_supported_inpainters()
        inpainter_widget, self.inpainter_combo = self._create_title_and_combo(self.tr("Inpainter"), current_inpainters)
        self.inpainter_combo.setFixedWidth(200)

        self.inpainting_standard_controls = self._create_inpainting_controls()
        self.inpainting_standard_controls.setContentsMargins(20, 0, 0, 0)

        inpainting_v_layout.addWidget(inpainter_widget)
        inpainting_v_layout.addWidget(self.inpainting_standard_controls)
        
        inpainting_section = self._create_section_container(self.tr("Inpainting"), inpainting_container)

        hd_strategy_container = QtWidgets.QWidget()
        hd_strategy_v_layout = QtWidgets.QVBoxLayout(hd_strategy_container)
        hd_strategy_v_layout.setContentsMargins(0, 0, 0, 0)
        hd_strategy_v_layout.setSpacing(10)

        inpaint_strategy_widget, self.inpaint_strategy_combo = self._create_title_and_combo(self.tr("HD Strategy"), self.inpaint_strategy)
        self.inpaint_strategy_combo.setFixedWidth(200)
        self.inpaint_strategy_combo.setCurrentText(self.tr("Resize"))

        self.hd_strategy_widgets = QtWidgets.QWidget()
        self.hd_strategy_layout = QtWidgets.QVBoxLayout(self.hd_strategy_widgets)
        self.hd_strategy_layout.setContentsMargins(0, 0, 0, 0)

        self.resize_widget = QtWidgets.QWidget()
        about_resize_layout = QtWidgets.QVBoxLayout(self.resize_widget)
        about_resize_layout.setContentsMargins(0, 0, 0, 0)
        
        resize_layout = QtWidgets.QHBoxLayout()
        resize_label = MLabel(self.tr("Resize Limit:"))
        about_resize_label = MLabel(self.tr("Resize the longer side of the image to a specific size,\nthen do inpainting on the resized image."))
        self.resize_spinbox = MSpinBox().small()
        self.resize_spinbox.setFixedWidth(70)
        self.resize_spinbox.setMaximum(3000)
        self.resize_spinbox.setValue(960)
        resize_layout.addWidget(resize_label)
        resize_layout.addWidget(self.resize_spinbox)
        resize_layout.addStretch()
        
        about_resize_layout.addWidget(about_resize_label)
        about_resize_layout.addLayout(resize_layout)

        self.crop_widget = QtWidgets.QWidget()
        crop_layout = QtWidgets.QVBoxLayout(self.crop_widget)
        crop_layout.setContentsMargins(0, 0, 0, 0)
        
        ocr_cards_container = QtWidgets.QWidget()
        ocr_cards_layout = QtWidgets.QVBoxLayout(ocr_cards_container)
        ocr_cards_layout.setContentsMargins(0, 0, 0, 0)
        
        self.hd_strategy_layout.addWidget(self.resize_widget)
        self.hd_strategy_layout.addWidget(self.crop_widget)
        self.hd_strategy_layout.addWidget(ocr_cards_container)

        self.resize_widget.show()
        self.crop_widget.hide()

        self.inpaint_strategy_combo.currentIndexChanged.connect(self.update_hd_strategy_widgets)

        hd_strategy_v_layout.addWidget(inpaint_strategy_widget)
        hd_strategy_v_layout.addWidget(self.hd_strategy_widgets)
        
        resize_section = self._create_section_container(self.tr("Ridimensiona"), hd_strategy_container)

        self.use_rectangle_checkbox = MCheckBox(self.tr("Usa Rettangolo"))
        rectangle_section = self._create_section_container(self.tr("Forma predefinita per Rileva"), self.use_rectangle_checkbox)

        self.use_gpu_checkbox = MCheckBox(self.tr("Use GPU"))

        fit_mode_container = QtWidgets.QWidget()
        fit_mode_layout = QtWidgets.QHBoxLayout(fit_mode_container)
        fit_mode_layout.setContentsMargins(0, 0, 0, 0)
        fit_mode_label = MLabel(self.tr("Modalità adattamento immagine:"))
        self.fit_mode_combo = MComboBox()
        self.fit_mode_combo.addItems([
            self.tr("Adatta all'altezza"),
            self.tr("Adatta alla larghezza"),
            self.tr("Adatta alla pagina"),
        ])
        self.fit_mode_combo.setFixedWidth(200)
        self.fit_mode_combo.setToolTip(self.tr("Modalità di adattamento automatico dell'immagine all'apertura"))
        fit_mode_layout.addWidget(fit_mode_label)
        fit_mode_layout.addWidget(self.fit_mode_combo)
        fit_mode_layout.addStretch()

        options_container = QtWidgets.QWidget()
        options_layout = QtWidgets.QVBoxLayout(options_container)
        options_layout.addWidget(self.use_gpu_checkbox)
        options_layout.addWidget(fit_mode_container)
        
        gpu_section = self._create_section_container(self.tr("Opzioni Avanzate"), options_container)

        if hasattr(model_manager, 'models_changed'):
            model_manager.models_changed.connect(self.refresh_translator_options)
            model_manager.models_changed.connect(self.refresh_ocr_options)
        
        try:
            refresh_model_map.connect(self.refresh_translator_options)
        except AttributeError:
            pass

        tools_layout.addWidget(ocr_section)
        tools_layout.addWidget(translator_section)
        tools_layout.addWidget(inpainting_section)
        tools_layout.addWidget(resize_section)
        tools_layout.addWidget(rectangle_section)
        tools_layout.addWidget(gpu_section)
        tools_layout.addStretch(1)

        # Widget legacy non mostrati: senza lo strato LLM non hanno piu' un
        # uso funzionale, ma settings_page.get_llm_settings() li legge durante
        # il salvataggio della configurazione. Senza questi attributi il
        # salvataggio del config solleverebbe AttributeError, quindi restano
        # vivi ma fuori da ogni layout.
        self.extra_context = MTextEdit()
        self.image_checkbox = MCheckBox(self.tr("Provide Image as input to multimodal LLMs"))
        self.image_checkbox.setChecked(True)

        self.update_hd_strategy_widgets(self.inpaint_strategy_combo.currentIndex())
        self.refresh_all_options()

        return tools_widget
    
    def is_gpu_enabled(self):
        return self.use_gpu_checkbox.isChecked()
    
    def is_rectangle_enabled(self):
        return self.use_rectangle_checkbox.isChecked()
    
    def update_hd_strategy_widgets(self, index: int):
        if index == 0:
            self.resize_widget.setVisible(True)
            self.crop_widget.setVisible(False)
        elif index == 1:
            self.resize_widget.setVisible(False)
            self.crop_widget.setVisible(False)
        else:
            self.resize_widget.setVisible(False)
            self.crop_widget.setVisible(True)
    
    def _create_section_container(self, title: str, widget: QtWidgets.QWidget) -> QtWidgets.QGroupBox:
        container = QtWidgets.QGroupBox(title)
        container.setStyleSheet("""
            QGroupBox {
                border: 1px solid #3a3a3a;
                border-radius: 8px;
                margin-top: 15px;
                padding: 15px;
                background-color: #252525;
                font-weight: bold;
                color: #e0e0e0;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(5, 15, 5, 5)
        layout.setSpacing(10)
        layout.addWidget(widget)
        return container
    
    def _create_inpainting_controls(self) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 5, 0, 5)
        layout.setSpacing(20)

        res_container = QtWidgets.QWidget()
        res_layout = QtWidgets.QVBoxLayout(res_container)
        res_layout.setContentsMargins(0, 0, 0, 0)
        res_label = MLabel(self.tr("Max Resolution"))
        self.inpaint_max_res_combo = MComboBox().small()
        self.inpaint_max_res_combo.addItems(["256", "512", "1024", "2048"])
        self.inpaint_max_res_combo.setFixedWidth(100)
        res_layout.addWidget(res_label)
        res_layout.addWidget(self.inpaint_max_res_combo)

        merge_container = QtWidgets.QWidget()
        merge_layout = QtWidgets.QVBoxLayout(merge_container)
        merge_layout.setContentsMargins(0, 0, 0, 0)
        merge_label = MLabel(self.tr("Merge Distance"))
        self.inpaint_merge_combo = MComboBox().small()
        self.inpaint_merge_combo.addItems(["64", "128", "256", "512", "1024"])
        self.inpaint_merge_combo.setFixedWidth(100)
        merge_layout.addWidget(merge_label)
        merge_layout.addWidget(self.inpaint_merge_combo)

        layout.addWidget(res_container)
        layout.addWidget(merge_container)
        layout.addStretch()

        return widget
