from PySide6 import QtWidgets

from ...dayu_widgets.divider import MDivider
from ...dayu_widgets.label import MLabel
from ...dayu_widgets.line_edit import MLineEdit
from ...dayu_widgets.push_button import MPushButton
from ...dayu_widgets.message import MMessage
from ..tooltip_manager import TOOLTIP_GROUPS, DEFAULT_TOOLTIPS


class TooltipPage:
    
    def _create_tooltip_widget(self) -> QtWidgets.QWidget:
        tooltip_widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tooltip_widget)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        header_layout = QtWidgets.QHBoxLayout()
        self.tooltip_search = MLineEdit().small()
        self.tooltip_search.setPlaceholderText(self.tr("Cerca tooltip..."))
        self.tooltip_search.set_prefix_widget(QtWidgets.QLabel("🔍"))
        
        reset_all_btn = MPushButton(self.tr("Ripristina tutti")).small()
        reset_all_btn.clicked.connect(self._reset_all_tooltips)
        
        header_layout.addWidget(self.tooltip_search, 1)
        header_layout.addWidget(reset_all_btn)
        layout.addLayout(header_layout)

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        
        scroll_content = QtWidgets.QWidget()
        self.tooltip_scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
        self.tooltip_scroll_layout.setContentsMargins(0, 0, 10, 0)
        self.tooltip_scroll_layout.setSpacing(15)

        self.tooltip_inputs = {}
        self.tooltip_sections = []

        for group_name, keys in TOOLTIP_GROUPS.items():
            section_widget = QtWidgets.QWidget()
            section_layout = QtWidgets.QVBoxLayout(section_widget)
            section_layout.setContentsMargins(0, 0, 0, 0)
            section_layout.setSpacing(8)

            title = MLabel(self.tr(group_name)).h4()
            section_layout.addWidget(title)
            
            group_items = []
            for key in keys:
                item_widget = QtWidgets.QWidget()
                item_layout = QtWidgets.QHBoxLayout(item_widget)
                item_layout.setContentsMargins(10, 0, 0, 0)
                
                label = MLabel(key).secondary()
                label.setFixedWidth(180)
                
                edit = MLineEdit()
                edit.setPlaceholderText(DEFAULT_TOOLTIPS.get(key, ""))
                
                manager = self.parent().tooltip_manager if hasattr(self.parent(), 'tooltip_manager') else None
                if manager:
                    edit.setText(manager.get(key))
                
                self.tooltip_inputs[key] = edit
                
                item_layout.addWidget(label)
                item_layout.addWidget(edit, 1)
                section_layout.addWidget(item_widget)
                group_items.append((key, item_widget))
            
            section_layout.addWidget(MDivider())
            self.tooltip_scroll_layout.addWidget(section_widget)
            self.tooltip_sections.append((section_widget, group_items))

        self.tooltip_scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)

        self.tooltip_search.textChanged.connect(self._filter_tooltips)

        return tooltip_widget
    
    def _filter_tooltips(self, text: str):
        text = text.lower()
        for section_widget, items in self.tooltip_sections:
            section_visible = False
            for key, widget in items:
                match = text in key.lower() or text in widget.findChild(QtWidgets.QLineEdit).text().lower() or \
                        text in widget.findChild(QtWidgets.QLineEdit).placeholderText().lower()
                widget.setVisible(match)
                if match:
                    section_visible = True
            section_widget.setVisible(section_visible)

    def _reset_all_tooltips(self):
        confirm = QtWidgets.QMessageBox.question(
            self, self.tr("Conferma"),
            self.tr("Vuoi ripristinare tutti i tooltip ai valori predefiniti?"),
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        if confirm == QtWidgets.QMessageBox.StandardButton.Yes:
            manager = self.parent().tooltip_manager if hasattr(self.parent(), 'tooltip_manager') else None
            if manager:
                manager.reset_all()
                for key, edit in self.tooltip_inputs.items():
                    edit.setText(manager.get_default(key))
                MMessage.success(self.tr("Tooltip ripristinati"), parent=self)
