from typing import List

from PySide6 import QtWidgets

from ...dayu_widgets.combo_box import MComboBox
from ...dayu_widgets.label import MLabel


class GeneralPage:
    
    def _create_personalization_widget(self) -> QtWidgets.QWidget:
        personalization_widget = QtWidgets.QWidget()
        personalization_layout = QtWidgets.QVBoxLayout(personalization_widget)
        
        self.languages = ['English', '한국어', 'Français', '日本語', 
                         '简体中文', '繁體中文', 'русский', 'Deutsch', 
                         'Nederlands', 'Español', 'Italiano', 'Türkçe']
        self.themes = [self.tr('Dark'), self.tr('Light')]
        
        language_widget, self.lang_combo = self._create_title_and_combo(self.tr("Language"), self.languages)
        self.set_combo_box_width(self.lang_combo, self.languages)
        theme_widget, self.theme_combo = self._create_title_and_combo(self.tr("Theme"), self.themes)
        self.set_combo_box_width(self.theme_combo, self.themes)

        personalization_layout.addWidget(language_widget) 
        personalization_layout.addWidget(theme_widget) 
        personalization_layout.addStretch()

        return personalization_widget
    
    def _create_title_and_combo(self, title: str, options: List[str]):
        combo_widget = QtWidgets.QWidget()
        combo_layout = QtWidgets.QVBoxLayout(combo_widget)

        if title in [self.tr("Inpainter"), self.tr("HD Strategy")]:
            label = MLabel(title)
        else:
            label = MLabel(title).h4()
        combo = MComboBox().small()
        combo.addItems(options)

        combo_layout.addWidget(label)
        combo_layout.addWidget(combo)

        return combo_widget, combo
    
    def _create_title_and_combo_with_highlights(self, title: str, options: List[str]):
        combo_widget = QtWidgets.QWidget()
        combo_layout = QtWidgets.QVBoxLayout(combo_widget)

        if title in [self.tr("Inpainter"), self.tr("HD Strategy")]:
            label = MLabel(title)
        else:
            label = MLabel(title).h4()
        
        combo = MComboBox().small()
        combo.addItems(options)
        
        tooltip_text = (
            "Indicatori:\n"
            "⭐ = Migliore della famiglia\n"
            "⚡ = Veloce\n"
            "👁️ = Ottimo per OCR/Vision\n"
            "🧠 = Ottimo per ragionamento\n"
            "💰 = Economico\n"
            "🔄 = Stabile\n"
            "🔬 = Sperimentale"
        )
        combo.setToolTip(tooltip_text)
        
        combo_layout.addWidget(label)
        combo_layout.addWidget(combo)

        return combo_widget, combo
