import os, shutil, json
import logging
from typing import List

from PySide6 import QtWidgets, QtGui
from PySide6.QtCore import Signal, QSettings
from PySide6.QtGui import QFont, QFontDatabase

logger = logging.getLogger(__name__)

from . import SettingsPageUI
from .tooltip_manager import TooltipManager
from .shortcut_manager import ShortcutManager

from dataclasses import dataclass, asdict, is_dataclass

# Dictionary to map old model names to the newest versions in settings
OCR_MIGRATIONS = {
    "GPT-4o": "GPT-4.1-mini",
    "Gemini-2.5-Flash": "Gemini-2.0-Flash",
}

TRANSLATOR_MIGRATIONS = {
    "GPT-4o": "GPT-4.1",
    "GPT-4o mini": "GPT-4.1-mini",
    "Gemini-2.0-Flash": "Gemini-2.5-Flash",
    "Gemini-2.0-Pro": "Gemini-2.5-Flash",
    "Gemini-2.5-Pro": "Gemini-2.5-Flash",
    "Claude-3-Opus": "Claude-3.7-Sonnet",
}

class SettingsPage(QtWidgets.QWidget):
    theme_changed = Signal(str)
    font_imported = Signal(str)
    selected_fonts_changed = Signal()  # Nuovo segnale per la modifica dei font selezionati
    settings_saved = Signal() # Segnale emesso dopo il salvataggio

    def __init__(self, parent=None):
        super(SettingsPage, self).__init__(parent)

        self.tooltip_manager = TooltipManager()
        self.shortcut_manager = ShortcutManager()
        self.ui = SettingsPageUI(self)
        self._setup_connections()
        self._loading_settings = False

        layout = QtWidgets.QVBoxLayout()
        layout.addWidget(self.ui)
        self.setLayout(layout)

    def _setup_connections(self):
        # Connect signals to slots
        self.ui.theme_combo.currentTextChanged.connect(self.on_theme_changed)
        self.ui.lang_combo.currentTextChanged.connect(self.on_language_changed)
        self.ui.font_browser.sig_files_changed.connect(self.import_font)
        self.selected_fonts_changed.connect(self._on_selected_fonts_changed)  # Connetti il segnale selected_fonts_changed

    def on_theme_changed(self, theme: str):
        self.theme_changed.emit(theme)

    def get_txt_prompt(self, t_lang='English') -> str:
        """Delega all'editor del prompt (TxtPromptMixin su SettingsPageUI).

        Senza questa delega, i chiamanti che usano
        `settings_page.get_txt_prompt(...)` (es. ui_controller.show_txt_modal)
        non troverebbero il metodo — vive su `settings_page.ui` — e
        ripiegherebbero sempre sul default hardcoded, ignorando il prompt
        personalizzato dall'utente.
        """
        try:
            return self.ui.get_txt_prompt(t_lang)
        except Exception:
            from .pages.txt_prompt_mixin import TXT_PROMPT_DEFAULT
            if '{t_lang}' in TXT_PROMPT_DEFAULT:
                return TXT_PROMPT_DEFAULT.replace('{t_lang}', t_lang)
            return TXT_PROMPT_DEFAULT

    def get_theme(self):
        return self.ui.theme_combo.currentText()

    def get_tool_selection(self, tool_type):
        tool_combos = {
            'translator': self.ui.translator_combo,
            'ocr': self.ui.ocr_combo,
            'inpainter': self.ui.inpainter_combo
        }
        current_text = tool_combos[tool_type].currentText()
        
        # Estrai solo il nome del modello rimuovendo lo status (es. "MI-GAN (available)" -> "MI-GAN")
        if ' (' in current_text and current_text.endswith(')'):
            model_name = current_text.split(' (')[0]
            return model_name
        
        return current_text
    


    def is_gpu_enabled(self):
        return self.ui.use_gpu_checkbox.isChecked()
    
    def is_rectangle_enabled(self):
        return self.ui.use_rectangle_checkbox.isChecked()

    def is_pre_ocr_filter_enabled(self):
        return getattr(self.ui, 'pre_ocr_filter_checkbox', None) is not None and self.ui.pre_ocr_filter_checkbox.isChecked()

    def get_llm_settings(self):
        return {
            'extra_context': self.ui.extra_context.toPlainText(),
            'image_input_enabled': self.ui.image_checkbox.isChecked()
        }



    def get_export_settings(self):
        settings = {
            'export_raw_text': self.ui.raw_text_checkbox.isChecked(),
            'export_translated_text': self.ui.translated_text_checkbox.isChecked(),
            'export_inpainted_image': self.ui.inpainted_image_checkbox.isChecked(),
            'save_as': {}
        }
        for file_type in self.ui.from_file_types:
            settings['save_as'][f'.{file_type}'] = self.ui.export_widgets[f'.{file_type}_save_as'].currentText()
        return settings

    def get_hd_strategy_settings(self):
        strategy = self.ui.inpaint_strategy_combo.currentText()
        settings = {
            'strategy': strategy
        }

        if strategy == self.ui.tr("Resize"):
            settings['resize_limit'] = str(self.ui.resize_spinbox.value())
        elif strategy == self.ui.tr("Crop"):
            settings['crop_margin'] = str(self.ui.crop_margin_spinbox.value())
            settings['crop_trigger_size'] = str(self.ui.crop_trigger_spinbox.value())

        # Standardized controls
        settings['inpaint_max_res'] = int(self.ui.inpaint_max_res_combo.currentText())
        settings['inpaint_merge_distance'] = int(self.ui.inpaint_merge_combo.currentText())

        return settings

    def get_all_settings(self):
        return {
            'language': self.ui.lang_combo.currentText(),
            'theme': self.get_theme(),
            'tools': {
                'translator': self.get_tool_selection('translator'),
                'ocr': self.get_tool_selection('ocr'),
                'inpainter': self.get_tool_selection('inpainter'),
                'use_gpu': self.is_gpu_enabled(),
                'fit_mode': self.ui.fit_mode_combo.currentIndex(),
                'use_rectangle': self.is_rectangle_enabled(),
                'hd_strategy': self.get_hd_strategy_settings(),

            },
            'llm': self.get_llm_settings(),
            'export': self.get_export_settings(),
        }

    def import_font(self, file_paths: List[str]):

        file_paths = [f for f in file_paths 
                      if f.endswith((".ttf", ".ttc", ".otf", ".woff", ".woff2"))]

        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_file_dir, '..', '..', '..'))
        font_folder_path = os.path.join(project_root, 'fonts')

        if not os.path.exists(font_folder_path):
            os.makedirs(font_folder_path)

        if file_paths:
            for file in file_paths:
                shutil.copy(file, font_folder_path)
                
            font_files = [os.path.join(font_folder_path, f) for f in os.listdir(font_folder_path) 
                      if f.endswith((".ttf", ".ttc", ".otf", ".woff", ".woff2"))]
            
            font_families = []
            for font in font_files:
                font_family = self.add_font_family(font)
                font_families.append(font_family)
            
            if font_families:
                self.font_imported.emit(font_families[0])

    def select_color(self, outline = False):
        default_color = QtGui.QColor('#000000') if not outline else QtGui.QColor('#FFFFFF')
        color_dialog = QtWidgets.QColorDialog()
        color_dialog.setCurrentColor(default_color)
        
        if color_dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            color = color_dialog.selectedColor()
            if color.isValid():
                # Check if the buttons exist before accessing them
                if hasattr(self.ui, 'color_button') and hasattr(self.ui, 'outline_color_button'):
                    button = self.ui.color_button if not outline else self.ui.outline_color_button
                    button.setStyleSheet(
                        f"background-color: {color.name()}; border: none; border-radius: 5px;"
                    )
                    button.setProperty('selected_color', color.name())

    # With the mappings, settings are saved with English values and loaded in the selected language
    def save_settings(self):
        settings = QSettings("ComicLabs", "KomicTranslate")
        all_settings = self.get_all_settings()

        def process_group(group_key: str, group_value, settings_obj: QSettings):
            """Helper function to process a group and its nested values."""
            if is_dataclass(group_value) and not isinstance(group_value, type):
                group_value = asdict(group_value)
            if isinstance(group_value, dict):
                settings_obj.beginGroup(str(group_key))
                for sub_key, sub_value in group_value.items():
                    process_group(str(sub_key), sub_value, settings_obj)
                settings_obj.endGroup()
            else:
                # Convert value to English using mappings if available
                mapped_value = self.ui.value_mappings.get(str(group_value), group_value)
                settings_obj.setValue(str(group_key), mapped_value)

        for key, value in all_settings.items():
            process_group(key, value, settings)

        self.settings_saved.emit()

        # Save selected fonts
        selected_fonts = self.get_selected_fonts()
        settings.beginGroup('text_rendering')
        settings.setValue('selected_fonts', selected_fonts)
        settings.setValue('pre_ocr_filter', self.is_pre_ocr_filter_enabled())
        settings.endGroup()

        # Save tooltips
        if hasattr(self, 'tooltip_manager') and hasattr(self.ui, 'tooltip_inputs'):
            for key, edit in self.ui.tooltip_inputs.items():
                self.tooltip_manager.set(key, edit.text())
            self.tooltip_manager.save()

        # Save shortcuts
        if hasattr(self, 'shortcut_manager') and hasattr(self.ui, 'shortcut_inputs'):
            for key, edit in self.ui.shortcut_inputs.items():
                self.shortcut_manager.set(key, edit.text())
            self.shortcut_manager.save()

    def load_settings(self):
        self._loading_settings = True
        settings = QSettings("ComicLabs", "KomicTranslate")

        # Load language
        language = settings.value('language', 'English', type=str)
        translated_language = self.ui.reverse_mappings.get(str(language), language)
        self.ui.lang_combo.setCurrentText(str(translated_language))

        # Load theme
        theme = settings.value('theme', 'Dark', type=str)
        translated_theme = self.ui.reverse_mappings.get(str(theme), theme)
        self.ui.theme_combo.setCurrentText(str(translated_theme))
        self.theme_changed.emit(str(translated_theme))

        # Load tools settings
        settings.beginGroup('tools')

        # Il default era 'GPT-4o', un traduttore dello strato LLM rimosso:
        # su un config nuovo o senza la chiave, setCurrentText su una voce
        # inesistente non fa nulla e il dropdown restava senza selezione
        # valida, con la validazione che falliva subito dopo.
        # Ora si sceglie il primo sito browser del registro, che e' la
        # categoria di traduzione predefinita dell'app.
        from modules.browser_sites import site_keys
        _siti = site_keys()
        _default_tr = _siti[0] if _siti else 'geminiamo'
        translator = settings.value('translator', _default_tr, type=str)
        translated_translator = self.ui.reverse_mappings.get(str(translator), translator)

        # Se la chiave salvata non corrisponde piu' a nessuna voce del
        # dropdown (traduttore rimosso, config di una versione vecchia),
        # ripiega sul default invece di lasciare il combo vuoto.
        combo = self.ui.translator_combo
        if combo.findText(str(translated_translator)) < 0:
            logger.warning(
                f"Traduttore salvato non valido: {translator!r}. "
                f"Ripiego su {_default_tr!r}."
            )
            translated_translator = _default_tr
        combo.setCurrentText(str(translated_translator))

        ocr = settings.value('ocr', 'Default', type=str)
        translated_ocr = self.ui.reverse_mappings.get(str(ocr), ocr)
        self.ui.ocr_combo.setCurrentText(str(translated_ocr))

        inpainter = settings.value('inpainter', 'LaMa', type=str)
        translated_inpainter = self.ui.reverse_mappings.get(str(inpainter), inpainter)
        self.ui.inpainter_combo.setCurrentText(str(translated_inpainter))

        # Explicitly convert settings value to bool to avoid type mismatch
        use_gpu = bool(settings.value('use_gpu', False, type=bool))
        self.ui.use_gpu_checkbox.setChecked(use_gpu)

        # fit_mode: 0=altezza (default), 1=larghezza, 2=pagina
        # La vecchia chiave auto_fit_width viene ignorata intenzionalmente.
        fit_mode = int(settings.value('fit_mode', 0, type=int))
        self.ui.fit_mode_combo.setCurrentIndex(fit_mode)

        use_rectangle = bool(settings.value('use_rectangle', False, type=bool))
        self.ui.use_rectangle_checkbox.setChecked(use_rectangle)



        # Load HD strategy settings
        settings.beginGroup('hd_strategy')
        strategy = settings.value('strategy', 'Resize', type=str)
        translated_strategy = self.ui.reverse_mappings.get(str(strategy), strategy)
        self.ui.inpaint_strategy_combo.setCurrentText(str(translated_strategy))
        if strategy == 'Resize':
            # type=int forza la conversione: i valori venivano salvati come str
            # (settings.value() li serializza cosi'), quindi isinstance(..., int)
            # era sempre False e l'impostazione tornava sempre al default.
            self.ui.resize_spinbox.setValue(settings.value('resize_limit', 960, type=int))
        elif strategy == 'Crop':
            self.ui.crop_margin_spinbox.setValue(settings.value('crop_margin', 64, type=int))
            self.ui.crop_trigger_spinbox.setValue(settings.value('crop_trigger_size', 1024, type=int))
        
        # Load standardized controls
        inpaint_max_res = settings.value('inpaint_max_res', 1024)
        self.ui.inpaint_max_res_combo.setCurrentText(str(inpaint_max_res))
        
        inpaint_merge_dist = settings.value('inpaint_merge_distance', 512)
        self.ui.inpaint_merge_combo.setCurrentText(str(inpaint_merge_dist))
        
        settings.endGroup()  # hd_strategy
        settings.endGroup()  # tools

        # Load LLM settings
        settings.beginGroup('llm')
        extra_context = settings.value('extra_context', '', type=str)
        if extra_context is not None:
            self.ui.extra_context.setPlainText(str(extra_context))
        else:
            self.ui.extra_context.setPlainText('')
        image_input_enabled = bool(settings.value('image_input_enabled', True, type=bool))
        self.ui.image_checkbox.setChecked(image_input_enabled)
        settings.endGroup()



        # Load export settings
        settings.beginGroup('export')
        self.ui.raw_text_checkbox.setChecked(bool(settings.value('export_raw_text', False, type=bool)))
        self.ui.translated_text_checkbox.setChecked(bool(settings.value('export_translated_text', False, type=bool)))
        self.ui.inpainted_image_checkbox.setChecked(bool(settings.value('export_inpainted_image', False, type=bool)))
        settings.beginGroup('save_as')
        for file_type in ['.pdf', '.epub', '.cbr', '.cbz', '.cb7', '.cbt']:
            self.ui.export_widgets[f'{file_type}_save_as'].setCurrentText(settings.value(file_type, file_type[1:]))
        settings.endGroup()  # save_as
        settings.endGroup()  # export

        # Load selected fonts
        settings.beginGroup('text_rendering')
        selected_fonts = settings.value('selected_fonts', [], type=list)
        pre_ocr_filter = settings.value('pre_ocr_filter', False, type=bool)
        settings.endGroup()
        self.set_selected_fonts(selected_fonts)
        if hasattr(self.ui, 'pre_ocr_filter_checkbox'):
            self.ui.pre_ocr_filter_checkbox.setChecked(bool(pre_ocr_filter))

        if hasattr(self, 'tooltip_manager'):
            self.tooltip_manager.load()
            if hasattr(self.ui, 'tooltip_inputs'):
                for key, edit in self.ui.tooltip_inputs.items():
                    edit.setText(self.tooltip_manager.get(key))

        if hasattr(self, 'shortcut_manager'):
            self.shortcut_manager.load()
            if hasattr(self.ui, 'shortcut_inputs'):
                for key, edit in self.ui.shortcut_inputs.items():
                    edit.setText(self.shortcut_manager.get(key))

        self._loading_settings = False

    def on_language_changed(self, new_language):
        if not self._loading_settings:  
            self.show_restart_dialog()

    def show_restart_dialog(self):
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle(self.tr("Restart Required"))
        msg_box.setText(self.tr("Please restart the application for the language changes to take effect."))
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Information)
        msg_box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
        msg_box.exec()

    def get_min_font_size(self):
        return int(self.ui.min_font_spinbox.value())
    
    def get_max_font_size(self):
        return int(self.ui.max_font_spinbox.value())

    def add_font_family(self, font_input: str) -> str:
        # Check if font_input is a file path
        if os.path.splitext(font_input)[1].lower() in [".ttf", ".ttc", ".otf", ".woff", ".woff2"]:
            font_id = QFontDatabase.addApplicationFont(font_input)
            if font_id != -1:
                font_families = QFontDatabase.applicationFontFamilies(font_id)
                if font_families:
                    return font_families[0]
        
        # If not a file path or loading failed, treat as font family name
        return font_input

    def get_value(self, key: str, default_value=None):
        """Get a value from settings with a default fallback.
        
        Args:
            key: The settings key to retrieve
            default_value: Default value if key not found
            
        Returns:
            The value if found, otherwise the default value
        """
        # Handle other settings
        settings = self.get_all_settings()
        
        # Navigate nested dictionaries using dot notation
        try:
            value = settings
            for part in key.split('.'):
                value = value[part]
            return value
        except (KeyError, TypeError):
            return default_value

    # Removed duplicate get_theme method

    def get_qwen_ocr_prompt(self):
        """Gets the custom prompt for Qwen OCR."""
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_file_dir, '..', '..', '..'))
        prompts_path = os.path.join(project_root, 'config', 'prompts.json')
        
        try:
            with open(prompts_path, 'r', encoding='utf-8') as f:
                prompts = json.load(f)
                return prompts.get('qwen_ocr_prompt', 'Recognize the text in the image. Write exactly what appears, DO NOT translate.')
        except Exception as e:
            print(f"Error loading prompts: {e}")
            return 'Recognize the text in the image. Write exactly what appears, DO NOT translate.'

    def get_qwen_translate_prompt(self):
        """Ottiene il prompt personalizzato per il traduttore Qwen."""
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_file_dir, '..', '..', '..'))
        prompts_path = os.path.join(project_root, 'config', 'prompts.json')

        try:
            with open(prompts_path, 'r', encoding='utf-8') as f:
                prompts = json.load(f)
                return prompts.get('qwen_translate_prompt', '')
        except Exception as e:
            print(f"Error loading prompts: {e}")
            return ''

    def get_deepseek_translate_prompt(self):
        """Ottiene il prompt personalizzato per il traduttore DeepSeek."""
        current_file_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_file_dir, '..', '..', '..'))
        prompts_path = os.path.join(project_root, 'config', 'prompts.json')

        try:
            with open(prompts_path, 'r', encoding='utf-8') as f:
                prompts = json.load(f)
                return prompts.get('deepseek_translate_prompt', '')
        except Exception as e:
            print(f"Error loading prompts: {e}")
            return ''

    def get_translate_prompt_for_model(self, model_name: str) -> str:
        """
        Restituisce il prompt di traduzione personalizzato per il modello specificato.
        Se il modello è DeepSeek, usa il prompt dedicato. Altrimenti ricade sull'extra_context generico.
        """
        if not model_name:
            return self.get_llm_settings().get('extra_context', '')

        model_lower = model_name.lower()
        if 'deepseek' in model_lower:
            deepseek_prompt = self.get_deepseek_translate_prompt()
            if deepseek_prompt:
                return deepseek_prompt
        elif 'qwen' in model_lower:
            qwen_prompt = self.get_qwen_translate_prompt()
            if qwen_prompt:
                return qwen_prompt

        return self.get_llm_settings().get('extra_context', '')

    def get_selected_fonts(self):
        """Restituisce la lista dei font selezionati nelle impostazioni"""
        selected_fonts = []
        for font_family, checkbox in self.ui.font_checkboxes.items():
            if checkbox.isChecked():
                selected_fonts.append(font_family)
        return selected_fonts

    def set_selected_fonts(self, selected_fonts):
        """Imposta i checkbox dei font"""
        # Se non ci sono font selezionati, seleziona tutti i font come default
        if not selected_fonts:
            for checkbox in self.ui.font_checkboxes.values():
                checkbox.setChecked(True)
        else:
            for font_family, checkbox in self.ui.font_checkboxes.items():
                checkbox.setChecked(font_family in selected_fonts)
        self.selected_fonts_changed.emit()  # Emit the signal when fonts are changed

    # Handler del segnale selected_fonts_changed
    def _on_selected_fonts_changed(self):
        # Salva le impostazioni quando i font selezionati cambiano
        self.save_font_settings()
        # Non emettiamo di nuovo il segnale qui per evitare un loop infinito

    def save_font_settings(self):
        # Salva solo le impostazioni dei font
        settings = QSettings("ComicLabs", "KomicTranslate")
        settings.beginGroup('text_rendering')
        selected_fonts = self.get_selected_fonts()
        settings.setValue('selected_fonts', selected_fonts)
        settings.endGroup()
    
    def get_cache_stats(self):
        """Ottiene le statistiche della cache"""
        return {"total_items": 0, "total_size_mb": 0, "cache_dir": "N/A"}
    
    def clear_cache(self, max_age_hours=None):
        """Pulisce la cache"""
        pass
        
    def show_cache_stats_dialog(self):
        """Mostra un dialogo con le statistiche della cache"""
        stats = self.get_cache_stats()
        
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle(self.tr("Statistiche Cache"))
        
        stats_text = f"""{self.tr("File totali")}: {stats.get('total_files', 0)}
{self.tr("Dimensione totale")}: {stats.get('total_size_mb', 0):.2f} MB
{self.tr("Directory cache")}: {stats.get('cache_dir', 'N/A')}
{self.tr("Voci metadati")}: {stats.get('metadata_entries', 0)}"""
        
        msg_box.setText(stats_text)
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Information)
        msg_box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
        msg_box.exec()
    
    def show_clear_cache_dialog(self):
        """Mostra un dialogo per pulire la cache"""
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle(self.tr("Pulisci Cache"))
        msg_box.setText(self.tr("Vuoi pulire la cache dell'inpainting?"))
        msg_box.setInformativeText(self.tr("Questo rimuoverà tutti i risultati salvati in cache."))
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Question)
        
        # Aggiungi pulsanti personalizzati
        clear_all_button = msg_box.addButton(self.tr("Pulisci Tutto"), QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        clear_old_button = msg_box.addButton(self.tr("Pulisci Solo Vecchi (24h+)"), QtWidgets.QMessageBox.ButtonRole.AcceptRole)
        cancel_button = msg_box.addButton(self.tr("Annulla"), QtWidgets.QMessageBox.ButtonRole.RejectRole)
        
        msg_box.exec()
        
        clicked_button = msg_box.clickedButton()
        if clicked_button == clear_all_button:
            self.clear_cache()
            self._show_cache_cleared_message(self.tr("Cache completamente pulita."))
        elif clicked_button == clear_old_button:
            self.clear_cache(max_age_hours=24)
            self._show_cache_cleared_message(self.tr("File di cache più vecchi di 24 ore rimossi."))
    
    def _show_cache_cleared_message(self, message):
        """Mostra un messaggio di conferma dopo la pulizia della cache"""
        msg_box = QtWidgets.QMessageBox(self)
        msg_box.setWindowTitle(self.tr("Cache Pulita"))
        msg_box.setText(message)
        msg_box.setIcon(QtWidgets.QMessageBox.Icon.Information)
        msg_box.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Ok)
        msg_box.exec()
