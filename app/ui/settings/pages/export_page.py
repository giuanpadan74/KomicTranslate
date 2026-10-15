from typing import List

from PySide6 import QtWidgets
from PySide6.QtGui import QFontMetrics

from ...dayu_widgets.label import MLabel
from ...dayu_widgets.combo_box import MComboBox
from ...dayu_widgets.check_box import MCheckBox


class ExportPage:
    
    def _create_export_widget(self) -> QtWidgets.QWidget:
        export_widget = QtWidgets.QWidget()
        export_layout = QtWidgets.QVBoxLayout(export_widget)
        batch_label = MLabel(self.tr("Automatic Mode")).h4()

        self.raw_text_checkbox = MCheckBox(self.tr("Export Raw Text"))
        self.translated_text_checkbox = MCheckBox(self.tr("Export Translated text"))
        self.inpainted_image_checkbox = MCheckBox(self.tr("Export Inpainted Image"))

        export_layout.addWidget(batch_label)
        export_layout.addWidget(self.raw_text_checkbox)
        export_layout.addWidget(self.translated_text_checkbox)
        export_layout.addWidget(self.inpainted_image_checkbox)

        self.from_file_types = ['pdf', 'epub', 'cbr', 'cbz', 'cb7', 'cbt', 'zip', 'rar']
        available_file_types = ['pdf', 'epub', 'cbr', 'cbz', 'cb7', 'cbt', 'zip', 'rar']

        for file_type in self.from_file_types:
            save_layout = QtWidgets.QHBoxLayout()
            save_label = MLabel(self.tr("Save {file_type} as:").format(file_type=file_type))
            save_combo = MComboBox().small()
            save_combo.addItems(available_file_types)
            self.set_combo_box_width(save_combo, available_file_types)

            if file_type in ['cbr', 'cbt']:
                save_combo.setCurrentText('cbz')
            elif file_type == 'rar':
                save_combo.setCurrentText('zip')
            elif file_type == 'epub':
                save_combo.setCurrentText('pdf')
            elif file_type in available_file_types:
                save_combo.setCurrentText(file_type)

            self.export_widgets[f'.{file_type.lower()}_save_as'] = save_combo

            save_layout.addWidget(save_label)
            save_layout.addWidget(save_combo)
            save_layout.addStretch(1)

            export_layout.addLayout(save_layout)

        export_layout.addStretch(1)

        return export_widget
    
    def set_combo_box_width(self, combo_box: MComboBox, items: List[str], padding: int = 40):
        font_metrics = QFontMetrics(combo_box.font())
        max_width = max(font_metrics.horizontalAdvance(item) for item in items)
        combo_box.setFixedWidth(max_width + padding)
