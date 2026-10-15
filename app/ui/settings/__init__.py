import os
from typing import List

from PySide6 import QtWidgets, QtCore, QtGui

from ..dayu_widgets.divider import MDivider
from ..dayu_widgets.qt import MPixmap
from ..dayu_widgets.clickable_card import ClickMeta
from .mixins.service_mixin import ServiceMixin
from .pages.general_page import GeneralPage
from .pages.tools_page import ToolsPage
from .pages.export_page import ExportPage
from .pages.text_rendering_page import TextRenderingPage
from .pages.txt_prompt_mixin import TxtPromptMixin
from .pages.tooltip_page import TooltipPage
from .pages.shortcut_page import ShortcutPage


current_file_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_file_dir, '..', '..', '..'))
font_folder_path = os.path.join(project_root, 'fonts')


class SettingsPageUI(QtWidgets.QWidget, ServiceMixin,
                     GeneralPage, ToolsPage, ExportPage,
                     TextRenderingPage, TxtPromptMixin, TooltipPage,
                     ShortcutPage):
    
    def __init__(self, parent=None):
        super().__init__(parent)

        self.export_widgets = {}

        self._credential_services = []
        
        self.nav_cards = []  
        self.current_highlighted_nav = None

        self.value_mappings = self.get_value_mappings_dynamic()
        self.reverse_mappings = {v: k for k, v in self.value_mappings.items()}

        self._load_saved_prompts()
        self._init_ui()

    def refresh_translator_options(self):
        from modules.translator.factory import TranslationEngineFactory
        TranslationEngineFactory.clear_cache()

        if hasattr(self, 'translator_combo'):
            categories = self.get_supported_translators_grouped()
            self.populate_grouped_combo(self.translator_combo, categories)
        self.refresh_all_mappings()

    def populate_grouped_combo(self, combo, categories: dict):
        """Popola una QComboBox con categorie (header non selezionabili + items raggruppati)."""
        combo.blockSignals(True)
        current_text = combo.currentText()
        combo.clear()
        model = QtGui.QStandardItemModel(combo)
        for header, items in categories.items():
            header_item = QtGui.QStandardItem(header)
            header_item.setFlags(QtCore.Qt.NoItemFlags)  # non selezionabile
            header_item.setTextAlignment(QtCore.Qt.AlignCenter)
            font = header_item.font()
            font.setBold(True)
            header_item.setFont(font)
            header_item.setForeground(QtGui.QBrush(QtGui.QColor("#4FC3F7")))
            model.appendRow(header_item)
            for item_text in items:
                item = QtGui.QStandardItem(item_text)
                item.setFlags(QtCore.Qt.ItemIsEnabled | QtCore.Qt.ItemIsSelectable)
                model.appendRow(item)
        combo.setModel(model)
        # Ripristina selezione precedente se ancora presente
        if current_text:
            idx = combo.findText(current_text)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        combo.blockSignals(False)
    
    def refresh_ocr_options(self):
        try:
            from modules.ocr.factory import OCREngineFactory
            OCREngineFactory.clear_cache()
        except ImportError:
            pass
        
        if hasattr(self, 'ocr_combo'):
            current_value = self.ocr_combo.currentText()
            new_values = self.get_supported_ocr_engines()
            self.ocr_combo.clear()
            self.ocr_combo.addItems(new_values)
            if current_value in new_values:
                self.ocr_combo.setCurrentText(current_value)
            else:
                self.ocr_combo.setCurrentIndex(0 if new_values else -1)
        self.refresh_all_mappings()
    
    def refresh_all_mappings(self):
        self.value_mappings = self.get_value_mappings_dynamic()
        self.reverse_mappings = {}
        for display_name, base_name in self.value_mappings.items():
            self.reverse_mappings[display_name] = base_name
            self.reverse_mappings[base_name] = base_name
    
    def refresh_inpainter_options(self):
        try:
            from modules.inpainting.factory import InpainterFactory
            InpainterFactory.clear_cache()
        except ImportError:
            pass
        
        if hasattr(self, 'inpainter_combo'):
            current_value = self.inpainter_combo.currentText()
            new_values = self.get_supported_inpainters()
            self.inpainter_combo.clear()
            self.inpainter_combo.addItems(new_values)
            if current_value in new_values:
                self.inpainter_combo.setCurrentText(current_value)
            else:
                self.inpainter_combo.setCurrentIndex(0 if new_values else -1)

    def refresh_all_options(self):
        self.refresh_translator_options()
        self.refresh_ocr_options()
        self.refresh_inpainter_options()
        self.refresh_all_mappings()

    def _init_ui(self):
        self.stacked_widget = QtWidgets.QStackedWidget()

        navbar_layout = self._create_navbar()
        personalization_widget = self._create_personalization_widget()
        tools_widget = self._create_tools_widget()
        text_rendering_widget = self._create_text_rendering_widget()
        export_widget = self._create_export_widget()
        tooltip_widget = self._create_tooltip_widget()
        shortcut_widget = self._create_shortcut_widget()

        self.stacked_widget.addWidget(personalization_widget)
        self.stacked_widget.addWidget(tools_widget)
        self.stacked_widget.addWidget(text_rendering_widget)
        self.stacked_widget.addWidget(export_widget)
        self.stacked_widget.addWidget(tooltip_widget)
        self.stacked_widget.addWidget(shortcut_widget)

        navbar_widget = QtWidgets.QWidget()
        navbar_widget.setLayout(navbar_layout)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.addWidget(navbar_widget)
        main_layout.addWidget(MDivider(orientation=QtCore.Qt.Orientation.Vertical))
        main_layout.addWidget(self.stacked_widget, 1)
        main_layout.setContentsMargins(3, 3, 3, 3)

    def _load_saved_prompts(self):
        try:
            import json
            prompts_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "config", "prompts.json")
            if os.path.exists(prompts_file):
                with open(prompts_file, "r", encoding="utf-8") as f:
                    prompts = json.load(f)
                self.saved_prompts = prompts
            else:
                self.saved_prompts = {
                    "extra_context": "",
                    "txt_prompt": "",
                    "txt_prompt_presets": {},
                    "txt_prompt_active": "Default",
                    "inpainting_prompt": "Remove the masked area and fill with appropriate background."
                }
        except Exception as e:
            print(f"Errore durante il caricamento dei prompt: {str(e)}")
            self.saved_prompts = {
                "extra_context": "",
                "txt_prompt": "",
                "txt_prompt_presets": {},
                "txt_prompt_active": "Default"
            }
    
    def _save_prompts(self):
        try:
            import json
            prompts_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "config", "prompts.json")
            config_dir = os.path.dirname(prompts_file)
            if not os.path.exists(config_dir):
                os.makedirs(config_dir)
            existing_prompts = {}
            if os.path.exists(prompts_file):
                try:
                    with open(prompts_file, "r", encoding="utf-8") as f:
                        existing_prompts = json.load(f)
                except:
                    pass
            prompts = existing_prompts.copy()
            prompts.update({
                "extra_context": self.extra_context.toPlainText(),
                "txt_prompt": self.txt_prompt_edit.toPlainText() if hasattr(self, 'txt_prompt_edit') else existing_prompts.get('txt_prompt', ''),
                "txt_prompt_presets": getattr(self, 'saved_prompts', {}).get('txt_prompt_presets', existing_prompts.get('txt_prompt_presets', {})),
                "txt_prompt_active": getattr(self, 'saved_prompts', {}).get('txt_prompt_active', existing_prompts.get('txt_prompt_active', 'Default'))
            })
            with open(prompts_file, "w", encoding="utf-8") as f:
                json.dump(prompts, f, ensure_ascii=False, indent=4)
            from ..dayu_widgets.message import MMessage
            MMessage.success(self.tr("Prompt salvato con successo!"), parent=self, duration=5, closable=True)
        except Exception as e:
            from ..dayu_widgets.message import MMessage
            MMessage.error(self.tr(f"Errore durante il salvataggio del prompt: {str(e)}"), parent=self, duration=5, closable=True)

    def _create_navbar(self) -> QtWidgets.QLayout:
        navbar_layout = QtWidgets.QVBoxLayout()

        # L'ordine delle voci DEVE corrispondere a quello dei widget aggiunti
        # in _init_ui(): on_nav_clicked usa l'indice posizionale.
        for index, setting in enumerate([
            {"title": self.tr("Personalization"), "avatar": MPixmap(".svg")},
            {"title": self.tr("Tools"), "avatar": MPixmap(".svg")},
            {"title": self.tr("Text Rendering"), "avatar": MPixmap(".svg")},
            {"title": self.tr("Export"), "avatar": MPixmap(".svg")},
            {"title": self.tr("Tooltip"), "avatar": MPixmap(".svg")},
            {"title": self.tr("Shortcuts"), "avatar": MPixmap(".svg")},
        ]):
            nav_card = ClickMeta(extra=False)
            nav_card.setup_data(setting)
            nav_card.clicked.connect(lambda i=index, c=nav_card: self.on_nav_clicked(i, c))
            navbar_layout.addWidget(nav_card)
            self.nav_cards.append(nav_card)

        navbar_layout.addStretch(1)
        return navbar_layout

    def on_nav_clicked(self, index: int, clicked_nav: ClickMeta):
        if self.current_highlighted_nav:
            self.current_highlighted_nav.set_highlight(False)
        clicked_nav.set_highlight(True)
        self.current_highlighted_nav = clicked_nav
        self.stacked_widget.setCurrentIndex(index)


__all__ = ['SettingsPageUI']
