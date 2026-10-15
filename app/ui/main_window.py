import os
import json
import subprocess
from PySide6 import QtWidgets, QtGui
from PySide6 import QtCore
from PySide6.QtGui import QIntValidator, QIcon, QDoubleValidator
from PySide6.QtCore import QSettings, QSize, QCoreApplication
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout, QLabel, QScrollArea

from .dayu_widgets import dayu_theme
from .dayu_widgets.divider import MDivider
from .dayu_widgets.combo_box import MComboBox, MFontComboBox
from .dayu_widgets.check_box import MCheckBox
from .dayu_widgets.text_edit import MTextEdit
from .dayu_widgets.line_edit import MLineEdit
from .dayu_widgets.browser import MDragFileButton, MClickBrowserFileToolButton, MClickSaveFileToolButton
from .dayu_widgets.push_button import MPushButton
from .dayu_widgets.tool_button import MToolButton
from .dayu_widgets.radio_button import MRadioButton
from .dayu_widgets.button_group import MPushButtonGroup, MToolButtonGroup
from .dayu_widgets.slider import MSlider
from .dayu_widgets.spin_box import MSpinBox
from .dayu_widgets.qt import MPixmap, MIcon
from .dayu_widgets.progress_bar import MProgressBar
from .dayu_widgets.loading import MLoading
from .dayu_widgets.theme import MTheme
from .dayu_widgets.menu import MMenu
from .dayu_widgets.collapse import MSectionItem

from .canvas.image_viewer import ImageViewer
from .canvas.text_item import TextBlockItem
from .translation_editor_dialog import TranslationEditorDialog
# Rimosso import balloon_tool - funzionalità eliminata
from .canvas.svg_tool import SvgTool
from .settings.settings_page import SettingsPage
from .settings.shortcut_manager import ShortcutManager
from .list_view import PageListView
from .shortcut_actions import trigger_save_loaded_images
from .gvb_prompt_dialog import GvbPromptDialog
from constants import (
    DEFAULT_FONT_COLOR,
    DEFAULT_OUTLINE_COLOR,
    DEFAULT_FONT_FAMILY,
    DEFAULT_FONT_SIZE,
    DEFAULT_LINE_SPACING,
    HEADER_TOOLBAR_WIDTH_SCALE,
    HEADER_TOOLBAR_HEIGHT_SCALE,
)
from .header_toolbar_layout import HeaderToolbarLayoutApplier
from .operativa_layout_controller import (
    OperativaLayoutController,
    SETTINGS_APP,
    SETTINGS_ORG,
)
from .sidebar_dock_title_bar import SidebarDockTitleBar
from .sidebar_sections import SidebarSectionsWidget
from modules.gvb_prompt_store import load_gvb_prompt_text, save_gvb_prompt_text



current_file_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_file_dir, '..', '..'))
font_folder_path = os.path.join(project_root, 'fonts')

supported_source_languages = [
"Korean", "Japanese", "French", "Chinese", "English",
"Russian", "German", "Dutch", "Spanish", "Italian"
]

supported_target_languages = [
"English", "Korean", "Japanese", "French", "Simplified Chinese",
"Traditional Chinese", "Russian", "German", "Dutch", "Spanish", 
"Italian", "Turkish", "Polish", "Portuguese", "Brazilian Portuguese",
"Thai", "Vietnamese", "Hungarian", "Indonesian",  "Finnish",
"Arabic"]


class ComicTranslateUI(QtWidgets.QMainWindow):
    log_message_signal = QtCore.Signal(str)  # Segnale per messaggi di log (thread-safe)

    def __init__(self, parent=None):
        super(ComicTranslateUI, self).__init__(parent)
        self.setWindowTitle("KomicTranslate")
        
        # Set window icon with multiple sizes for better compatibility
        self._set_window_icon()
        
        screen = QtWidgets.QApplication.primaryScreen()
        geo = screen.geometry()
        
        width = float(geo.width())
        height = float(geo.height())
        x = 50
        y = 50
        w = int(width / 1.2)
        h = int(height / 1.2)
        self.setGeometry(x, y, w, h)

        self.image_viewer = ImageViewer(self)
        self.image_viewer._scene.selectionChanged.connect(self._on_scene_selection_changed)
        self._current_svg_item = None
        
        # Crea un'istanza persistente di SvgTool
        self.svg_tool = SvgTool(self.image_viewer)
        
        # Connetti il segnale per l'eyedropper del pennello avanzato
        self.image_viewer.eyedropperColorPicked.connect(self._on_eyedropper_color_picked)
        
        self.settings_page = SettingsPage(self)
        self.settings_page.theme_changed.connect(self.apply_theme)
        self.settings_page.font_imported.connect(self.set_font)
        self.settings_page.selected_fonts_changed.connect(self.update_font_dropdown)
        self.settings_page.settings_saved.connect(self.refresh_ui_texts)
        self.main_content_widget = None
        self.tool_buttons = {}  # Dictionary to store mutually exclusive tool names and their corresponding buttons
        self.page_list = PageListView()

        self.grabGesture(QtCore.Qt.GestureType.PanGesture)
        self.grabGesture(QtCore.Qt.GestureType.PinchGesture)

        self._shortcuts = {}
        self._setup_shortcuts()
        
        self.lang_mapping = {
            self.tr("English"): "English",
            self.tr("Korean"): "Korean",
            self.tr("Japanese"): "Japanese",
            self.tr("French"): "French",
            self.tr("Simplified Chinese"): "Simplified Chinese",
            self.tr("Traditional Chinese"): "Traditional Chinese",
            self.tr("Chinese"): "Chinese",
            self.tr("Russian"): "Russian",
            self.tr("German"): "German",
            self.tr("Dutch"): "Dutch",
            self.tr("Spanish"): "Spanish",
            self.tr("Italian"): "Italian",
            self.tr("Turkish"): "Turkish",
            self.tr("Polish"): "Polish",
            self.tr("Portuguese"): "Portuguese",
            self.tr("Brazilian Portuguese"): "Brazilian Portuguese",
            self.tr("Thai"): "Thai",
            self.tr("Vietnamese"): "Vietnamese",
            self.tr("Indonesian"): "Indonesian",
            self.tr("Hungarian"): "Hungarian",
            self.tr("Finnish"): "Finnish",
            self.tr("Arabic"): "Arabic",
        }
        # Create reverse mapping
        self.reverse_lang_mapping = {v: k for k, v in self.lang_mapping.items()}

        self.button_to_alignment = {
            0: QtCore.Qt.AlignmentFlag.AlignLeft,
            1: QtCore.Qt.AlignmentFlag.AlignCenter,
            2: QtCore.Qt.AlignmentFlag.AlignRight,
            3: QtCore.Qt.AlignmentFlag.AlignJustify,
        }

        # Connetti il segnale di log (prima di _init_ui)
        self.log_message_signal.connect(self._on_log_message)
        
        self._init_ui()
        
        # Carica i modelli di font salvati all'avvio
        self.load_font_models_list()
        
        # Aggiorna i testi dell'interfaccia con la traduzione caricata
        self.refresh_ui_texts()

    def _init_ui(self):
        main_widget = QtWidgets.QWidget(self)
        self.main_layout = QtWidgets.QHBoxLayout()
        main_widget.setLayout(self.main_layout)
        self.setCentralWidget(main_widget)

        # Navigation rail
        nav_rail_layout = self._create_nav_rail()
        self.main_layout.addLayout(nav_rail_layout)
        self.main_layout.addWidget(MDivider(orientation=QtCore.Qt.Vertical))

        # Create main content
        self.main_content_widget = self._create_main_content()
        self.main_layout.addWidget(self.main_content_widget)

    def resizeEvent(self, event):
        """Quando la finestra cambia dimensione, riallinea l'altezza della
        scroll area della toolbar in modo che mostri i pulsanti senza tagliarli
        e senza lasciare strisce vuote verticali."""
        super().resizeEvent(event)
        if hasattr(self, "_update_header_scroll_height"):
            self._update_header_scroll_height()
        if hasattr(self, "_update_log_section_width"):
            self._update_log_section_width()

    def _update_header_scroll_height(self):
        """Calcola l'altezza naturale del container della toolbar e la applica
        alla QScrollArea. Chiamato dopo il setup, ad ogni resize e dopo
        cambi di lingua (refresh_ui_texts)."""
        scroll_area = getattr(self, "_header_scroll_area", None)
        container = getattr(self, "_header_container", None)
        if scroll_area is None or container is None:
            return
        # Forza il ricalcolo del sizeHint del container
        container.adjustSize()
        hint = container.sizeHint()
        if hint.height() <= 0:
            return
        # Aggiungi spazio per la scrollbar SOLO se è visibile, altrimenti
        # crea una fascia vuota sotto la toolbar.
        sb = scroll_area.horizontalScrollBar()
        sb_h = sb.sizeHint().height() if sb is not None and sb.isVisible() else 0
        new_h = hint.height() + sb_h + 2
        if scroll_area.height() != new_h:
            scroll_area.setFixedHeight(new_h)

    def _update_log_section_width(self):
        scroll_area = getattr(self, "right_panel_scroll_area", None)
        log_inner = getattr(self, "_log_inner_widget", None)
        if scroll_area is None or log_inner is None:
            return
        viewport_w = scroll_area.viewport().width()
        if viewport_w <= 0:
            return
        target_w = max(160, int(viewport_w * 0.5))
        if log_inner.width() != target_w:
            log_inner.setFixedWidth(target_w)

    def event(self, ev):
        """Intercetta LanguageChange e altre notifiche per riallineare la
        toolbar quando i testi cambiano (es. cambio lingua)."""
        result = super().event(ev)
        if ev.type() == QtCore.QEvent.Type.LanguageChange and \
                hasattr(self, "_update_header_scroll_height"):
            # Rimanda al prossimo tick per dare tempo al layout di assestarsi
            QtCore.QTimer.singleShot(0, self._update_header_scroll_height)
        if ev.type() == QtCore.QEvent.Type.LanguageChange and \
                hasattr(self, "_update_log_section_width"):
            QtCore.QTimer.singleShot(0, self._update_log_section_width)
        return result

    def _create_nav_rail(self):
        nav_rail_layout = QtWidgets.QVBoxLayout()
        nav_divider = MDivider()
        nav_divider.setFixedWidth(30)

        # Create the tool browser button
        self.tool_browser = MToolButton()
        self.tool_browser.set_dayu_svg("upload-file.svg")
        self.tool_browser.setToolTip(self.settings_page.tooltip_manager.get("tool_browser"))
        self.tool_browser.clicked.connect(self.show_tool_menu)

        self.image_browser_button = MClickBrowserFileToolButton(multiple=True)
        self.image_browser_button.set_dayu_filters([".png", ".jpg", ".jpeg", ".webp", ".bmp"])
        
        self.document_browser_button = MClickBrowserFileToolButton(multiple=True)
        self.document_browser_button.set_dayu_filters([".pdf", ".epub"])
        
        self.archive_browser_button = MClickBrowserFileToolButton(multiple=True)
        self.archive_browser_button.set_dayu_filters([".zip", ".rar", ".7z", ".tar"])
        
        self.comic_browser_button = MClickBrowserFileToolButton(multiple=True)
        self.comic_browser_button.set_dayu_filters([".cbz", ".cbr", ".cb7", ".cbt"])

        self.project_browser_button = MClickBrowserFileToolButton(multiple=False)
        self.project_browser_button.set_dayu_filters([".ctpr"])

        self.tool_menu = MMenu(parent=self)
        
        # Add actions to the menu and connect them to the browser buttons
        image_action = self.tool_menu.addAction(MIcon("ion--image-outline.svg"), self.tr("Images"))
        image_action.triggered.connect(self.image_browser_button.clicked)
        
        document_action = self.tool_menu.addAction(MIcon("mingcute--document-line.svg"), self.tr("Document"))
        document_action.triggered.connect(self.document_browser_button.clicked)
        
        archive_action = self.tool_menu.addAction(MIcon("flowbite--file-zip-outline.svg"), self.tr("Archive"))
        archive_action.triggered.connect(self.archive_browser_button.clicked)
        
        comic_action = self.tool_menu.addAction(MIcon("mdi--comic-thought-bubble-outline.svg"), self.tr("Comic Book Archive"))
        comic_action.triggered.connect(self.comic_browser_button.clicked)

        project_action = self.tool_menu.addAction(MIcon("ct-file-icon.svg"), self.tr("Project File"))
        project_action.triggered.connect(self.project_browser_button.clicked)

        # Rest of the code remains the same
        self.save_browser = MClickSaveFileToolButton()
        save_file_types = [("Images", ["png", "jpg", "jpeg", "webp", "bmp"])]
        self.save_browser.set_file_types(save_file_types)
        self.save_browser.set_dayu_svg("save.svg")
        self.save_browser.setToolTip(self.settings_page.tooltip_manager.get("save_browser"))

        # Nuovo pulsante per esportazione PDF
        self.export_pdf_button = MToolButton()
        self.export_pdf_button.set_dayu_svg("mingcute--document-line.svg")  # Icona documento PDF
        self.export_pdf_button.setToolTip(self.settings_page.tooltip_manager.get("export_pdf"))
        # Il collegamento ora viene fatto nel controller

        self.save_project_button = MToolButton()
        self.save_project_button.set_dayu_svg("fluent--save-16-regular.svg")
        self.save_project_button.setToolTip(self.settings_page.tooltip_manager.get("save_project"))

        self.save_as_project_button = MToolButton()
        self.save_as_project_button.set_dayu_svg("fluent--save-as-24-regular.svg")
        self.save_as_project_button.setToolTip(self.settings_page.tooltip_manager.get("save_as_project"))

        # Nuovo pulsante per unire file CTPR
        self.join_ctpr_button = MToolButton()
        self.join_ctpr_button.set_dayu_svg("tabler--files.svg")  # Icona file multipli
        self.join_ctpr_button.setToolTip(self.settings_page.tooltip_manager.get("join_ctpr"))

        save_all_file_types = [
            ("ZIP files", "zip"),
            ("CBZ files", "cbz"),
            ("CB7 files", "cb7"),
            ("PDF files", "pdf"),
        ]

        self.save_all_browser = MClickSaveFileToolButton()
        self.save_all_browser.set_dayu_svg("tabler--file-export.svg")
        self.save_all_browser.set_file_types(save_all_file_types)
        self.save_all_browser.setToolTip(self.settings_page.tooltip_manager.get("save_all_browser"))

        self.nav_tool_group = MToolButtonGroup(orientation=QtCore.Qt.Vertical, exclusive=True)
        nav_tools = [
            {"svg": "home_line.svg", "checkable": True, "tooltip": self.tr("Home"), "clicked": self.show_main_page},
            {"svg": "info_line.svg", "checkable": False, "tooltip": self.tr("Scheda fumetto"), "clicked": self.open_comic_info_dialog},
            {"svg": "settings.svg", "checkable": True, "tooltip": self.tr("Settings"), "clicked": self.show_settings_page},
            {"svg": "history_icon.svg", "checkable": False, "tooltip": self.tr("History"), "clicked": self.show_history_page},
        ]
        self.nav_tool_group.set_button_list(nav_tools)
        self.nav_tool_group.get_button_group().buttons()[0].setChecked(True)

        # Aggiungere il pulsante al layout nella sezione nav_rail_layout
        
        nav_rail_layout.addWidget(self.tool_browser)
        # nav_rail_layout.addWidget(self.save_project_button)  # Nascosto
        nav_rail_layout.addWidget(self.save_as_project_button)
        nav_rail_layout.addWidget(self.join_ctpr_button)  # Nuovo pulsante
        nav_rail_layout.addWidget(self.save_browser)
        nav_rail_layout.addWidget(self.export_pdf_button)  # Nuovo pulsante PDF
        nav_rail_layout.addWidget(self.save_all_browser)
        nav_rail_layout.addWidget(nav_divider)
        nav_rail_layout.addWidget(self.nav_tool_group)
        nav_rail_layout.addStretch()

        nav_rail_layout.setContentsMargins(0, 0, 0, 0)

        return nav_rail_layout

    def show_tool_menu(self):
        # Show the tool menu at the appropriate position
        self.tool_menu.exec_(self.tool_browser.mapToGlobal(self.tool_browser.rect().bottomLeft()))
    
    def create_tool_button(self, text: str = "", svg: str = "", checkable: bool = False):
        if text:
            button = MToolButton()
            button.set_dayu_svg(svg)
            button.text_beside_icon()
            button.setText(text)
        else:
            button = MToolButton()
            button.set_dayu_svg(svg)

        button.setCheckable(checkable)
        
        # Applica stile CSS per rendere le icone bianche
        button.setStyleSheet("""
            MToolButton {
                color: white;
            }
            MToolButton:hover {
                color: #f0f0f0;
            }
            MToolButton:pressed {
                color: #e0e0e0;
            }
            MToolButton:checked {
                color: white;
                background-color: rgba(255, 255, 255, 0.35);
                border: 1px solid rgba(255, 255, 255, 0.45);
                border-radius: 4px;
            }
        """)

        return button

    def _create_main_content(self):
        content_widget = QtWidgets.QWidget()

        self._init_gvb_controls()

        # 1. Setup Progress and Loading widgets (needed for header)
        self._setup_progress_widgets()

        # 2. Page List (Left)
        left_widget = self._setup_left_panel()

        # 3. Stacked View (File Loader / Viewer) (Central)
        central_widget = self._setup_central_view()

        # 4. Right Panel (Settings and Tools)
        self._ui_layout_settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        right_widget = self._setup_right_panel()

        # 5. Header / Toolbar
        # Note: Must be after right panel because of update_buttons_visibility
        header_widget = self._setup_header_toolbar()

        header_host_widget = QtWidgets.QWidget()
        header_host_layout = QtWidgets.QVBoxLayout(header_host_widget)
        header_host_layout.setContentsMargins(0, 0, 0, 0)
        header_host_layout.setSpacing(0)
        header_host_layout.addWidget(header_widget)
        self._header_host_widget = header_host_widget

        self._ensure_right_dock()
        self._operativa_layout_controller = OperativaLayoutController(
            settings=self._ui_layout_settings,
            header_toolbar_widget=header_widget,
            header_host_widget=header_host_widget,
            header_host_layout=header_host_layout,
            sidebar_host_widget=self._operativa_host_widget,
            sidebar_host_layout=self._operativa_host_layout,
            toggle_button=self._right_dock_title_bar.layout_button,
            on_mode_changed=self._on_operativa_layout_mode_changed,
            parent=self,
        )
        self._right_dock_title_bar.layout_toggle_requested.connect(
            self._operativa_layout_controller.toggle
        )
        self._right_dock_title_bar.float_toggle_requested.connect(
            self._toggle_right_dock_floating
        )
        self._operativa_layout_controller.apply(self._operativa_layout_controller.load_preference())

        # 6. Assemble everything
        self._assemble_main_layout(content_widget, header_host_widget, left_widget, central_widget, right_widget)

        # 7. Final Initializations
        font_files = [os.path.join(font_folder_path, f) for f in os.listdir(font_folder_path) 
                      if f.endswith((".ttf", ".ttc", ".otf", ".woff", ".woff2"))]
        for font in font_files:
            self.add_custom_font(font)
        self.update_font_dropdown()

        return content_widget

    def _on_operativa_layout_mode_changed(self, show_in_sidebar: bool) -> None:
        applier = getattr(self, "_header_toolbar_layout_applier", None)
        if applier is None:
            return
        if hasattr(self, "_right_dock_title_bar"):
            self._right_dock_title_bar.set_operativa_in_sidebar(show_in_sidebar)
        if show_in_sidebar:
            applier.apply_sidebar()
        else:
            applier.apply_top()
        QtCore.QTimer.singleShot(0, self._update_header_scroll_height)

    def _init_gvb_controls(self):
        if hasattr(self, 'gvb_region_button'):
            return

        icon_size = QtCore.QSize(26, 26)
        side_button_height = 30

        prompt_button_style = """
            QPushButton {
                background-color: #007bff;
                border: 1px solid #007bff;
                color: white;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0069d9;
                border: 1px solid #0062cc;
            }
            QPushButton:pressed {
                background-color: #0062cc;
                border: 1px solid #005cbf;
            }
        """

        self.prompt_button = MPushButton(self.tr("PROMPT"))
        self.prompt_button.setEnabled(True)
        self.prompt_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.prompt_button.setFixedHeight(side_button_height)
        self.prompt_button.setToolTip("Modifica e salva il prompt da inviare a Gemini insieme all'immagine selezionata")
        self.prompt_button.setStyleSheet(prompt_button_style)

        self.prompt_side_button = MPushButton(self.tr("PROMPT"))
        self.prompt_side_button.setEnabled(True)
        self.prompt_side_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.prompt_side_button.setFixedHeight(side_button_height)
        self.prompt_side_button.setMinimumWidth(48)
        self.prompt_side_button.setToolTip("Modifica e salva il prompt da inviare a Gemini insieme all'immagine selezionata")
        self.prompt_side_button.setStyleSheet(prompt_button_style)

        self.gvb_simple_button = MPushButton(self.tr("GVB"))
        self.gvb_simple_button.setEnabled(True)
        self.gvb_simple_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.gvb_simple_button.setFixedHeight(side_button_height)
        self.gvb_simple_button.setToolTip("Apri Gemini in browser")
        self.gvb_simple_button.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                border: 1px solid #28a745;
                color: white;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #218838;
                border: 1px solid #218838;
            }
        """)

        self.gvb_region_button = self.create_tool_button(svg="magic-select.svg", checkable=False)
        self.gvb_region_button.setToolTip("Seleziona una porzione dell'immagine, copiala negli appunti e apri GVB")
        self.gvb_region_button.setIconSize(icon_size)
        self.gvb_region_button.setFixedSize(30, 30)

        self.gvb_apply_region_button = self.create_tool_button(svg="stamp-post.svg", checkable=False)
        self.gvb_apply_region_button.setToolTip("Applica alla tavola l'immagine finale copiata da Gemini")
        self.gvb_apply_region_button.setIconSize(icon_size)
        self.gvb_apply_region_button.setFixedSize(30, 30)

        self.gvb_simple_side_button = MPushButton(self.tr("GVB"))
        self.gvb_simple_side_button.setEnabled(True)
        self.gvb_simple_side_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.gvb_simple_side_button.setFixedHeight(side_button_height)
        self.gvb_simple_side_button.setMinimumWidth(48)
        self.gvb_simple_side_button.setToolTip("Apri Gemini in browser")
        self.gvb_simple_side_button.setStyleSheet(self.gvb_simple_button.styleSheet())

        self.prompt_button.clicked.connect(self.open_prompt_editor_dialog)
        self.prompt_side_button.clicked.connect(self.open_prompt_editor_dialog)
        self.gvb_simple_button.clicked.connect(self.open_simple_gemini_browser)
        self.gvb_simple_side_button.clicked.connect(self.open_simple_gemini_browser)
        self.gvb_region_button.clicked.connect(self.start_region_gvb_selection)
        self.gvb_apply_region_button.clicked.connect(self.apply_region_from_gvb_clipboard)

    def open_prompt_editor_dialog(self):
        current_text = load_gvb_prompt_text("")
        dialog = GvbPromptDialog(initial_text=current_text, parent=self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            new_text = dialog.prompt_text()
            save_gvb_prompt_text(new_text)
            from app.ui.messages import Messages
            if new_text and new_text.strip():
                Messages.show_info(
                    self,
                    'Prompt salvato',
                    'Il prompt è stato salvato e verrà usato automaticamente insieme alla selezione dell\'immagine.',
                    duration=4,
                )
            else:
                Messages.show_info(
                    self,
                    'Prompt rimosso',
                    'Il prompt è stato cancellato. Non verrà inviato alcun testo automatico a Gemini.',
                    duration=4,
                )


    def show_settings_page(self):
        if not self.settings_page:
            self.settings_page = SettingsPage(self)
        
        # Remove the main content widget
        self.main_layout.removeWidget(self.main_content_widget)
        self.main_content_widget.hide()
        
        # Add the settings page
        self.main_layout.addWidget(self.settings_page)
        self.settings_page.show()

    def show_main_page(self):
        if self.settings_page:
            # Remove the settings page
            self.main_layout.removeWidget(self.settings_page)
            self.settings_page.hide()
        
        # Add back the main content widget
        self.main_layout.addWidget(self.main_content_widget)
        self.main_content_widget.show()
    
    def show_history_page(self):
        """Mostra un dialog popup con il contenuto del file history.txt come mini editor"""
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr("History"))
        dialog.setModal(True)
        dialog.resize(700, 500)
        
        layout = QVBoxLayout(dialog)
        
        # Toolbar per i pulsanti di formattazione (inizialmente nascosta)
        toolbar_layout = QHBoxLayout()
        
        bold_button = QPushButton(self.tr("Grassetto"))
        bold_button.setCheckable(True)
        bold_button.setVisible(False)
        
        italic_button = QPushButton(self.tr("Corsivo"))
        italic_button.setCheckable(True)
        italic_button.setVisible(False)
        
        underline_button = QPushButton(self.tr("Sottolineato"))
        underline_button.setCheckable(True)
        underline_button.setVisible(False)
        
        toolbar_layout.addWidget(bold_button)
        toolbar_layout.addWidget(italic_button)
        toolbar_layout.addWidget(underline_button)
        toolbar_layout.addStretch()
        
        layout.addLayout(toolbar_layout)
        
        # Text area per mostrare/modificare il contenuto del file
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setFont(QFont("Consolas", 10))  # Font monospace per migliore leggibilità
        
        # Leggi il contenuto del file history.txt
        history_file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'history.txt')
        try:
            with open(history_file_path, 'r', encoding='utf-8') as file:
                content = file.read()
                text_edit.setPlainText(content)
        except FileNotFoundError:
            text_edit.setPlainText(self.tr("File history.txt non trovato."))
        except Exception as e:
            text_edit.setPlainText(self.tr(f"Errore nella lettura del file: {str(e)}"))
        
        layout.addWidget(text_edit)
        
        # Variabile per tracciare la modalità edit
        edit_mode = False
        
        def toggle_edit_mode():
            nonlocal edit_mode
            if not edit_mode:
                # Richiedi password
                password, ok = QtWidgets.QInputDialog.getText(
                    dialog, 
                    self.tr("Password richiesta"), 
                    self.tr("Inserisci la password per modificare:"), 
                    QtWidgets.QLineEdit.Password
                )
                
                if ok and password == "kiffone":
                    edit_mode = True
                    text_edit.setReadOnly(False)
                    edit_button.setText(self.tr("Salva"))
                    
                    # Mostra i pulsanti di formattazione
                    bold_button.setVisible(True)
                    italic_button.setVisible(True)
                    underline_button.setVisible(True)
                    
                elif ok:
                    QtWidgets.QMessageBox.warning(dialog, self.tr("Errore"), self.tr("Password errata!"))
            else:
                # Salva le modifiche
                try:
                    with open(history_file_path, 'w', encoding='utf-8') as file:
                        file.write(text_edit.toPlainText())
                    QtWidgets.QMessageBox.information(dialog, self.tr("Successo"), self.tr("File salvato con successo!"))
                except Exception as e:
                    QtWidgets.QMessageBox.critical(dialog, self.tr("Errore"), self.tr(f"Errore nel salvataggio: {str(e)}"))
                
                edit_mode = False
                text_edit.setReadOnly(True)
                edit_button.setText(self.tr("Modifica"))
                
                # Nascondi i pulsanti di formattazione
                bold_button.setVisible(False)
                italic_button.setVisible(False)
                underline_button.setVisible(False)
        
        def apply_bold():
            if edit_mode:
                cursor = text_edit.textCursor()
                if cursor.hasSelection():
                    char_format = cursor.charFormat()
                    char_format.setFontWeight(QFont.Bold if not char_format.fontWeight() == QFont.Bold else QFont.Normal)
                    cursor.mergeCharFormat(char_format)
                    text_edit.setTextCursor(cursor)
        
        def apply_italic():
            if edit_mode:
                cursor = text_edit.textCursor()
                if cursor.hasSelection():
                    char_format = cursor.charFormat()
                    char_format.setFontItalic(not char_format.fontItalic())
                    cursor.mergeCharFormat(char_format)
                    text_edit.setTextCursor(cursor)
        
        def apply_underline():
            if edit_mode:
                cursor = text_edit.textCursor()
                if cursor.hasSelection():
                    char_format = cursor.charFormat()
                    char_format.setFontUnderline(not char_format.fontUnderline())
                    cursor.mergeCharFormat(char_format)
                    text_edit.setTextCursor(cursor)
        
        # Connetti i pulsanti di formattazione
        bold_button.clicked.connect(apply_bold)
        italic_button.clicked.connect(apply_italic)
        underline_button.clicked.connect(apply_underline)
        
        # Pulsanti in basso
        button_layout = QHBoxLayout()
        
        edit_button = QPushButton(self.tr("Modifica"))
        edit_button.clicked.connect(toggle_edit_mode)
        button_layout.addWidget(edit_button)
        
        button_layout.addStretch()
        
        close_button = QPushButton(self.tr("Chiudi"))
        close_button.clicked.connect(dialog.accept)
        button_layout.addWidget(close_button)
        
        layout.addLayout(button_layout)
        
        dialog.exec()

    def apply_theme(self, theme: str):
        if theme == self.settings_page.ui.tr("Light"):
            new_theme = MTheme("light", primary_color=MTheme.blue)
        else:
            new_theme = MTheme("dark", primary_color=MTheme.yellow)

        new_theme.apply(self)
        # Refresh the UI to apply the new theme
        self.repaint()

    def open_comic_info_dialog(self):
        """Apre la Scheda fumetto (ComicInfo.xml). Implementazione reale nel
        controller (app/controllers/comic_info_controller.py). Fallback base."""
        try:
            from app.controllers.comic_info_controller import open_comic_info_dialog
            open_comic_info_dialog(self)
        except Exception:
            from app.ui.comic_info_dialog import ComicInfoDialog
            dlg = ComicInfoDialog(getattr(self, "comic_info", None), None, self)
            if dlg.exec() == QtWidgets.QDialog.Accepted:
                self.comic_info = dlg.result()

    def toggle_pan_tool(self):
        if self.pan_button.isChecked():
            self.set_tool('pan')
        else:
            self.set_tool(None)


    def toggle_box_tool(self):
        if self.box_button.isChecked():
            self.set_tool('box')
        else:
            self.set_tool(None)

    def toggle_brush_tool(self):
        if self.brush_button.isChecked():
            self.set_tool('brush')
            size = self.image_viewer.brush_size
            if hasattr(self, "brush_eraser_spinbox"):
                self.brush_eraser_spinbox.blockSignals(True)
                self.brush_eraser_spinbox.setValue(size)
                self.brush_eraser_spinbox.blockSignals(False)
            elif hasattr(self, "brush_eraser_slider"):
                self.brush_eraser_slider.setValue(size)
        else:
            self.set_tool(None)
    def toggle_eraser_tool(self):
        if self.eraser_button.isChecked():
            self.set_tool('eraser')
            size = self.image_viewer.eraser_size
            if hasattr(self, "brush_eraser_spinbox"):
                self.brush_eraser_spinbox.blockSignals(True)
                self.brush_eraser_spinbox.setValue(size)
                self.brush_eraser_spinbox.blockSignals(False)
            elif hasattr(self, "brush_eraser_slider"):
                self.brush_eraser_slider.setValue(size)
        else:
            self.set_tool(None)
    
    def toggle_pen_tool(self):
        if self.pen_button.isChecked():
            self.set_tool('pen')
            size = self.image_viewer.pen_size
            if hasattr(self, "pen_size_spinbox"):
                self.pen_size_spinbox.blockSignals(True)
                self.pen_size_spinbox.setValue(size)
                self.pen_size_spinbox.blockSignals(False)
            elif hasattr(self, "pen_size_slider"):
                self.pen_size_slider.setValue(size)
        else:
            self.set_tool(None)

    def toggle_bucket_tool(self):
        if self.bucket_button.isChecked():
            self.set_tool('bucket')
        else:
            self.set_tool(None)
    
    def toggle_svg_tool(self):
        if self.svg_button.isChecked():
            self.set_tool('svg')
            self.image_viewer.svg_tool = self.svg_tool
        else:
            self.set_tool(None)
            self.image_viewer.svg_tool = None
    
    def set_slider_size(self, size: int):
        if hasattr(self, "brush_eraser_slider"):
            self.brush_eraser_slider.blockSignals(True)
            self.brush_eraser_slider.setValue(size)
            self.brush_eraser_slider.blockSignals(False)
        if hasattr(self, "brush_eraser_spinbox"):
            self.brush_eraser_spinbox.blockSignals(True)
            self.brush_eraser_spinbox.setValue(size)
            self.brush_eraser_spinbox.blockSignals(False)

    def set_tool(self, tool_name: str):
        self.image_viewer.unsetCursor()
        self.image_viewer.set_tool(tool_name)
        for name, button in self.tool_buttons.items():
            if name != tool_name:
                button.setChecked(False)
            elif tool_name is not None:
                button.setChecked(True)
        # If tool_name is None, uncheck all buttons
        if not tool_name:
            for button in self.tool_buttons.values():
                button.setChecked(False)
            self.image_viewer.setDragMode(QtWidgets.QGraphicsView.DragMode.ScrollHandDrag)

    def set_brush_eraser_size(self, size: int):
        # Aggiorna il viewer per entrambi gli strumenti di inpainting
        self.image_viewer.set_br_er_size(size, size, tool_type='brush')
        self.image_viewer.set_br_er_size(size, size, tool_type='eraser')
        if hasattr(self, "brush_eraser_spinbox"):
            self.brush_eraser_spinbox.blockSignals(True)
            self.brush_eraser_spinbox.setValue(size)
            self.brush_eraser_spinbox.blockSignals(False)
        if hasattr(self, "brush_eraser_slider"):
            self.brush_eraser_slider.blockSignals(True)
            self.brush_eraser_slider.setValue(size)
            self.brush_eraser_slider.blockSignals(False)

    def scale_size(self, base_size, image_width, image_height):
        # Calculate the diagonal of the image
        image_diagonal = (image_width**2 + image_height**2)**0.5
        
        # Use a reference diagonal (e.g., 1000 pixels) to calculate scaling factor
        reference_diagonal = 1000
        scaling_factor = image_diagonal / reference_diagonal
        
        # Scale the diameter and pen width
        scaled_size = base_size * scaling_factor
        
        return scaled_size

    def get_font_family(self, font_input: str) -> QFont:
        # Check if font_input is a file path
        if os.path.splitext(font_input)[1].lower() in [".ttf", ".ttc", ".otf", ".woff", ".woff2"]:
            font_id = QFontDatabase.addApplicationFont(font_input)
            if font_id != -1:
                font_families = QFontDatabase.applicationFontFamilies(font_id)
                if font_families:
                    return font_families[0]
        
        # If not a file path or loading failed, treat as font family name
        return font_input
    
    def add_custom_font(self, font_input: str):
        # Check if font_input is a file path
        if os.path.splitext(font_input)[1].lower() in [".ttf", ".ttc", ".otf", ".woff", ".woff2"]:
            QFontDatabase.addApplicationFont(font_input)

    def get_color(self):
        default_color = QtGui.QColor('#000000')
        color_dialog = QtWidgets.QColorDialog()
        color_dialog.setCurrentColor(default_color)
        if color_dialog.exec() == QtWidgets.QDialog.Accepted:
            color = color_dialog.selectedColor()
            return color
        
    def _setup_shortcuts(self):
        """Inizializza le scorciatoie da tastiera basate sulle impostazioni."""
        # Pulisci scorciatoie esistenti se presenti
        for s in self._shortcuts.values():
            s.setEnabled(False)
            s.deleteLater()
        self._shortcuts.clear()

        manager = self.settings_page.shortcut_manager
        
        # Mapping Azione -> (Metodo, Tab ShortcutManager)
        mappings = {
            "open_file": lambda: self.image_browser_button.clicked.emit(),
            "save_image": lambda: trigger_save_loaded_images(self),
            "save_project": lambda: self.save_project_button.click(),
            "export_pdf": lambda: self.export_pdf_button.click(),
            "save_all": lambda: self.save_all_browser.click(),
            "redo": lambda: self.undo_tool_group.get_button_group().buttons()[1].click(),
            "detect_text": lambda: self.hbutton_group.get_button_group().buttons()[0].click(),
            "ocr_text": lambda: self.hbutton_group.get_button_group().buttons()[1].click(),
            "translate_text": lambda: self.hbutton_group.get_button_group().buttons()[2].click(),
            "render_text": lambda: self.hbutton_group.get_button_group().buttons()[6].click(),
            "original_view": lambda: self.original_button.click(),
            "detect_font": lambda: self.detect_font_button.click(),
            "auto_center": lambda: self.auto_center_button.click(),
            "detect_all": lambda: self.detect_batch_button.click(),
            "translate_all": lambda: self.translate_button.click(),
            "sbianchetta": lambda: self.sbianchetta_button.click() if hasattr(self, "sbianchetta_button") else None,
            "toggle_markers": lambda: self.markers_button.click(),
            "toggle_polygons": lambda: self.polygons_button.click(),
            "toggle_rect_boxes": lambda: self.rect_boxes_button.click(),
            "fit_width": lambda: self.fit_width_button.click(),
            "fit_height": lambda: self.fit_height_button.click(),
            "save_as_project": lambda: self.save_as_project_button.click(),
            "comic_info": lambda: self.open_comic_info_dialog(),
            
            "toggle_box": self.toggle_box_tool,
            "delete_box": lambda: self.delete_button.click(),
            "clear_boxes": lambda: self.clear_rectangles_button.click(),
            "pan_tool": self.toggle_pan_tool,
            "undo": lambda: self.undo_tool_group.get_button_group().buttons()[0].click(),
            
            "inpaint_brush": self.toggle_brush_tool,
            "inpaint_eraser": self.toggle_eraser_tool,
            "clear_inpaint": lambda: self.clear_brush_strokes_button.click(),
            
            "paint_pen": self.toggle_pen_tool,
            "paint_bucket": self.toggle_bucket_tool,
            "color_picker": lambda: self.color_button.click() if hasattr(self, "color_button") else None,
            
            "svg_tool": self.toggle_svg_tool,
            "delete_shape": self._on_delete_shape_clicked,
            "bring_to_front": self._on_bring_to_front_clicked,
            "send_to_back": self._on_send_to_back_clicked,
        }

        delete_box_seq = manager.get_sequence("delete_box")
        delete_shape_seq = manager.get_sequence("delete_shape")
        shared_delete_shortcut = (
            not delete_box_seq.isEmpty()
            and not delete_shape_seq.isEmpty()
            and delete_box_seq == delete_shape_seq
        )

        for key, callback in mappings.items():
            if key == "delete_shape" and shared_delete_shortcut:
                continue
            seq = manager.get_sequence(key)
            if not seq.isEmpty():
                shortcut = QtGui.QShortcut(seq, self)
                shortcut.activated.connect(callback)
                shortcut.setContext(QtCore.Qt.ShortcutContext.ApplicationShortcut)
                self._shortcuts[key] = shortcut

    def _update_ui_texts(self):
        """Aggiorna i testi dei pulsanti e delle label per la lingua corrente."""
        # Aggiorna pulsanti toolbar principale
        buttons = self.hbutton_group.get_button_group().buttons()
        # Assumendo l'ordine: Rileva, OCR, Traduci, Gemini, Segmenta, Pulisci, Render.
        if len(buttons) >= 7:
            buttons[0].setText(QCoreApplication.translate("ComicTranslateUI", "Rileva"))
            buttons[1].setText(QCoreApplication.translate("ComicTranslateUI", "OCR"))
            buttons[2].setText(QCoreApplication.translate("ComicTranslateUI", "Traduci"))
            buttons[3].setText(QCoreApplication.translate("ComicTranslateUI", "Gemini"))
            buttons[4].setText(QCoreApplication.translate("ComicTranslateUI", "Segmenta"))
            buttons[5].setText(QCoreApplication.translate("ComicTranslateUI", "Pulisci"))
            buttons[6].setText(QCoreApplication.translate("ComicTranslateUI", "Render."))

        # Aggiorna altri pulsanti header
        if hasattr(self, 'original_button'):
            self.original_button.setText(QCoreApplication.translate("ComicTranslateUI", "Original"))
        if hasattr(self, 'detect_font_button'):
            self.detect_font_button.setText(QCoreApplication.translate("ComicTranslateUI", "Font"))
        if hasattr(self, 'auto_center_button'):
            self.auto_center_button.setText(QCoreApplication.translate("ComicTranslateUI", "Center"))
        
        # Aggiorna pulsanti Batch
        if hasattr(self, 'detect_batch_button'):
            self.detect_batch_button.setText(QCoreApplication.translate("ComicTranslateUI", "Rileva Tutto"))
        if hasattr(self, 'translate_button'):
            self.translate_button.setText(QCoreApplication.translate("ComicTranslateUI", "Traduci Tutto"))
        if hasattr(self, 'sbianchetta_button'):
            self.sbianchetta_button.setText(QCoreApplication.translate("ComicTranslateUI", "Sbianchetta"))
        if hasattr(self, 'markers_button'):
            self.markers_button.setText(QCoreApplication.translate("ComicTranslateUI", "Marcatori"))
        if hasattr(self, 'polygons_button'):
            self.polygons_button.setText(QCoreApplication.translate("ComicTranslateUI", "Poligoni"))
        if hasattr(self, 'rect_boxes_button'):
            self.rect_boxes_button.setText(QCoreApplication.translate("ComicTranslateUI", "Caselle OCR"))
        if hasattr(self, 'cancel_batch_button'):
            self.cancel_batch_button.setText(QCoreApplication.translate("ComicTranslateUI", "Cancel"))

        # Aggiorna selettore modalità
        mode_buttons = self.mode_selector_group.get_button_group().buttons()
        if len(mode_buttons) >= 2:
            mode_buttons[0].setText(QCoreApplication.translate("ComicTranslateUI", "Gemini"))
            mode_buttons[0].setToolTip(QCoreApplication.translate("ComicTranslateUI", "Modalità Manuale"))
            mode_buttons[1].setText(QCoreApplication.translate("ComicTranslateUI", "Classic"))
            mode_buttons[1].setToolTip(QCoreApplication.translate("ComicTranslateUI", "Modalità API KEY"))

        # Aggiorna tooltip undo/redo
        undo_buttons = self.undo_tool_group.get_button_group().buttons()
        if len(undo_buttons) >= 2:
            undo_buttons[0].setToolTip(QCoreApplication.translate("ComicTranslateUI", "Undo"))
            undo_buttons[1].setToolTip(QCoreApplication.translate("ComicTranslateUI", "Redo"))
        
        # Aggiorna tool menu
        if hasattr(self, 'tool_menu'):
            actions = self.tool_menu.actions()
            # L'ordine delle azioni è: Images, Document, Archive, Comic Book Archive, Project File
            if len(actions) >= 5:
                actions[0].setText(QCoreApplication.translate("ComicTranslateUI", "Images"))
                actions[1].setText(QCoreApplication.translate("ComicTranslateUI", "Document"))
                actions[2].setText(QCoreApplication.translate("ComicTranslateUI", "Archive"))
                actions[3].setText(QCoreApplication.translate("ComicTranslateUI", "Comic Book Archive"))
                actions[4].setText(QCoreApplication.translate("ComicTranslateUI", "Project File"))
                
        # Aggiorna nav tool group tooltip
        if hasattr(self, 'nav_tool_group'):
            nav_buttons = self.nav_tool_group.get_button_group().buttons()
            if len(nav_buttons) >= 4:
                 nav_buttons[0].setToolTip(QCoreApplication.translate("ComicTranslateUI", "Home"))
                 nav_buttons[1].setToolTip(QCoreApplication.translate("ComicTranslateUI", "Scheda fumetto"))
                 nav_buttons[2].setToolTip(QCoreApplication.translate("ComicTranslateUI", "Settings"))
                 nav_buttons[3].setToolTip(QCoreApplication.translate("ComicTranslateUI", "History"))
        if hasattr(self, "right_dock"):
            dock_title = QCoreApplication.translate("ComicTranslateUI", "Barra Laterale")
            self.right_dock.setWindowTitle(dock_title)
            if hasattr(self, "_right_dock_title_bar"):
                self._right_dock_title_bar.set_title(dock_title)

    def refresh_ui_texts(self):
        """Aggiorna tutti i testi della UI (es. dopo cambio impostazioni)."""
        self._setup_shortcuts()
        # Aggiorna i tooltip che ora potrebbero contenere scorciatoie diverse
        # Nota: La migrazione precedente usava self.settings_page.tooltip_manager.get()
        # Se modifichiamo quel metodo o richiamiamo i setToolTip, l'utente vedrà i tasti aggiornati.
        self._update_all_tooltips()
        
        # Aggiorna i testi statici dei pulsanti
        self._update_ui_texts()

    def _update_all_tooltips(self):
        """Riapplica tutti i tooltip per riflettere le scorciatoie correnti."""
        tm = self.settings_page.tooltip_manager
        sm = self.settings_page.shortcut_manager

        # Helper per prendere il tooltip con shortcut
        def get_tt(tt_key, sc_key=None):
            sc_text = sm.get(sc_key) if sc_key else None
            return tm.get(tt_key, sc_text)

        # Pulsanteti toolbar
        buttons = self.hbutton_group.get_button_group().buttons()
        if len(buttons) >= 7:
            # Aggiorna i tooltip con le nuove scorciatoie
            buttons[0].setToolTip(get_tt(f"tool_hbutton_rileva", "detect_text"))  # Rileva
            buttons[1].setToolTip(get_tt(f"tool_hbutton_ocr", "ocr_text"))        # OCR
            buttons[2].setToolTip(get_tt(f"tool_hbutton_traduci", "translate_text"))  # Traduci
            buttons[3].setToolTip(get_tt(f"tool_hbutton_txt", "none"))             # Gemini (nascosto)
            buttons[4].setToolTip(get_tt(f"tool_hbutton_segmenta", "none"))          # Segmenta (nascosto)
            buttons[5].setToolTip(get_tt(f"tool_hbutton_pulisci", "clear_boxes"))      # Pulisci
            buttons[6].setToolTip(get_tt(f"tool_hbutton_render", "render_text"))     # Render
            
        # Aggiorna tooltip dove possibile
        self.original_button.setToolTip(get_tt("tool_original", "original_view"))
        self.detect_font_button.setToolTip(get_tt("tool_detect_font", "detect_font"))
        self.auto_center_button.setToolTip(get_tt("tool_center", "auto_center"))
        self.detect_batch_button.setToolTip(get_tt("tool_detect_all", "detect_all"))
        self.translate_button.setToolTip(get_tt("tool_translate_all", "translate_all"))
        if hasattr(self, "sbianchetta_button"):
            sbianchetta_tt = tm.get("tool_sbianchetta", None)
            if sbianchetta_tt:
                self.sbianchetta_button.setToolTip(sbianchetta_tt)
        self.markers_button.setToolTip(get_tt("tool_markers", "toggle_markers"))
        if hasattr(self, "polygons_button"):
            self.polygons_button.setToolTip(get_tt("polygons", "toggle_polygons"))
        if hasattr(self, "rect_boxes_button"):
            self.rect_boxes_button.setToolTip(get_tt("rect_boxes", "toggle_rect_boxes"))
        if hasattr(self, "toggle_text_boxes_button"):
            self.toggle_text_boxes_button.setToolTip(
                QCoreApplication.translate(
                    "ComicTranslateUI",
                    "Nasconde o mostra le caselle di testo create da 'Traduci Tutto'",
                )
            )
        self.fit_width_button.setToolTip(get_tt("tool_fit_width", "fit_width"))
        self.fit_height_button.setToolTip(get_tt("tool_fit_height", "fit_height"))
        self.save_as_project_button.setToolTip(get_tt("tool_save_as_project", "save_as_project"))
        
    def set_font(self, font_family: str):
        """
        Sets the font for the application
        """
        self.font_dropdown.setCurrentText(font_family)
        self.settings_page.font_imported.disconnect(self.set_font)
        self.settings_page.font_imported.connect(self.set_font)
        
        # Aggiorna il dropdown dopo l'importazione dei font
        self.update_font_dropdown()
        
        # Carica i modelli font salvati
        self.load_font_models_list()
    
    def save_font_model(self):
        """Salva le impostazioni font correnti come modello"""
        # Chiedi il nome del modello
        name, ok = QtWidgets.QInputDialog.getText(
            self, 
            self.tr("Salva modello font"), 
            self.tr("Inserisci il nome del modello:")
        )
        
        if ok and name.strip():
            # Raccogli le impostazioni correnti
            model_data = {
                'font_family': self.font_dropdown.currentText(),
                'font_size': self.font_size_dropdown.currentText(),
                'line_spacing': self.line_spacing_dropdown.currentText(),
                'alignment': self.alignment_tool_group.get_dayu_checked(),
                'bold': self.bold_button.isChecked(),
                'italic': self.italic_button.isChecked(),
                'underline': self.underline_button.isChecked(),
                'font_color': self.block_font_color_button.property('selected_color'),
                'outline': self.outline_checkbox.isChecked(),
                'outline_color': self.outline_font_color_button.property('selected_color'),
                'outline_width': self.outline_width_dropdown.currentText(),
                'remove_newlines': self.remove_newlines_button.isChecked()
            }
            
            # Carica i modelli esistenti
            models_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'font_models.json')
            models = {}
            
            if os.path.exists(models_file):
                try:
                    with open(models_file, 'r', encoding='utf-8') as f:
                        models = json.load(f)
                    if not isinstance(models, dict):
                        raise ValueError(f"Formato inatteso: {type(models).__name__}")
                except Exception as e:
                    # Non sovrascrivere: se il file e' corrotto, salvare qui avrebbe
                    # distrutto TUTTI i modelli font gia' salvati dall'utente.
                    print(f"Errore nel caricamento dei modelli: {e}")
                    QtWidgets.QMessageBox.warning(
                        self,
                        self.tr("Errore"),
                        self.tr(f"Impossibile leggere i modelli salvati: {e}\n"
                                "Il file non e' stato modificato per evitare perdita di dati.")
                    )
                    return

            # Aggiungi il nuovo modello
            models[name.strip()] = model_data
            
            # Salva i modelli (scrittura atomica: .tmp + replace)
            try:
                tmp_models_file = models_file + ".tmp"
                with open(tmp_models_file, 'w', encoding='utf-8') as f:
                    json.dump(models, f, indent=2, ensure_ascii=False)
                os.replace(tmp_models_file, models_file)
                
                # Aggiorna la lista dei modelli
                self.load_font_models_list()
                
                # Seleziona il modello appena salvato
                self.model_selector.setCurrentText(name.strip())
                
                QtWidgets.QMessageBox.information(
                    self, 
                    self.tr("Modello salvato"), 
                    self.tr(f"Il modello '{name.strip()}' è stato salvato con successo.")
                )
            except Exception as e:
                QtWidgets.QMessageBox.warning(
                    self, 
                    self.tr("Errore"), 
                    self.tr(f"Errore nel salvataggio del modello: {e}")
                )
    
    def load_font_models_list(self):
        """Carica la lista dei modelli font salvati nel dropdown"""
        models_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'font_models.json')
        
        # Pulisci il dropdown
        self.model_selector.clear()
        self.model_selector.addItem("")
        
        if os.path.exists(models_file):
            try:
                with open(models_file, 'r', encoding='utf-8') as f:
                    models = json.load(f)
                
                # Aggiungi i modelli al dropdown
                for model_name in sorted(models.keys()):
                    self.model_selector.addItem(model_name)
                    
            except Exception as e:
                print(f"Errore nel caricamento della lista modelli: {e}")
    
    def load_selected_font_model(self, model_name):
        """Carica il modello font selezionato"""
        if not model_name.strip():
            return
            
        models_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'font_models.json')
        
        if os.path.exists(models_file):
            try:
                with open(models_file, 'r', encoding='utf-8') as f:
                    models = json.load(f)
                
                if model_name in models:
                    self.apply_font_model(models[model_name])
                    
            except Exception as e:
                QtWidgets.QMessageBox.warning(
                    self, 
                    self.tr("Errore"), 
                    self.tr(f"Errore nel caricamento del modello: {e}")
                )
    
    def load_default_font_model(self):
        """Carica il modello font DEFAULT se esiste"""
        models_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'font_models.json')
        
        if os.path.exists(models_file):
            try:
                with open(models_file, 'r', encoding='utf-8') as f:
                    models = json.load(f)
                
                if 'DEFAULT' in models:
                    self.apply_font_model(models['DEFAULT'])
                    self.model_selector.setCurrentText('DEFAULT')
                else:
                    QtWidgets.QMessageBox.information(
                        self, 
                        self.tr("Modello non trovato"), 
                        self.tr("Il modello DEFAULT non esiste. Salvane uno con il nome 'DEFAULT'.")
                    )
                    
            except Exception as e:
                QtWidgets.QMessageBox.warning(
                    self, 
                    self.tr("Errore"), 
                    self.tr(f"Errore nel caricamento del modello DEFAULT: {e}")
                )
        else:
            QtWidgets.QMessageBox.information(
                self, 
                self.tr("Nessun modello salvato"), 
                self.tr("Non ci sono modelli font salvati.")
            )
    
    def delete_font_model(self):
        """Cancella il modello font selezionato"""
        current_model = self.model_selector.currentText().strip()
        
        if not current_model:
            QtWidgets.QMessageBox.information(
                self, 
                self.tr("Nessun modello selezionato"), 
                self.tr("Seleziona un modello da cancellare.")
            )
            return
        
        # Conferma di cancellazione
        reply = QtWidgets.QMessageBox.question(
            self, 
            self.tr("Conferma cancellazione"), 
            self.tr(f"Sei sicuro di voler cancellare il modello '{current_model}'?\nQuesta azione non può essere annullata."),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            models_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'font_models.json')
            
            try:
                if os.path.exists(models_file):
                    with open(models_file, 'r', encoding='utf-8') as f:
                        models = json.load(f)
                    if not isinstance(models, dict):
                        raise ValueError(f"Formato inatteso: {type(models).__name__}")
                    
                    if current_model in models:
                        del models[current_model]
                        
                        # Salva il file aggiornato (atomico: .tmp + replace)
                        tmp_models_file = models_file + ".tmp"
                        with open(tmp_models_file, 'w', encoding='utf-8') as f:
                            json.dump(models, f, indent=2, ensure_ascii=False)
                        os.replace(tmp_models_file, models_file)
                        
                        # Aggiorna il dropdown
                        self.load_font_models_list()
                        
                        QtWidgets.QMessageBox.information(
                            self, 
                            self.tr("Modello cancellato"), 
                            self.tr(f"Il modello '{current_model}' è stato cancellato con successo.")
                        )
                    else:
                        QtWidgets.QMessageBox.warning(
                            self, 
                            self.tr("Modello non trovato"), 
                            self.tr(f"Il modello '{current_model}' non esiste nel file.")
                        )
                else:
                    QtWidgets.QMessageBox.warning(
                        self, 
                        self.tr("File non trovato"), 
                        self.tr("Il file dei modelli non esiste.")
                    )
                    
            except Exception as e:
                QtWidgets.QMessageBox.warning(
                    self, 
                    self.tr("Errore"), 
                    self.tr(f"Errore nella cancellazione del modello: {e}")
                )
    
    def apply_font_model(self, model_data):
        """Applica le impostazioni del modello font ai controlli"""
        try:
            # Applica le impostazioni
            if 'font_family' in model_data:
                self.font_dropdown.setCurrentText(model_data['font_family'])
            
            if 'font_size' in model_data:
                self.font_size_dropdown.setCurrentText(str(model_data['font_size']))
            
            if 'line_spacing' in model_data:
                self.line_spacing_dropdown.setCurrentText(str(model_data['line_spacing']))
            
            if 'alignment' in model_data:
                self.alignment_tool_group.set_dayu_checked(model_data['alignment'])
            
            if 'bold' in model_data:
                self.bold_button.setChecked(model_data['bold'])
            
            if 'italic' in model_data:
                self.italic_button.setChecked(model_data['italic'])
            
            if 'underline' in model_data:
                self.underline_button.setChecked(model_data['underline'])
            
            if 'font_color' in model_data:
                color = model_data['font_color']
                self.block_font_color_button.setStyleSheet(f"background-color: {color}; border: none; border-radius: 5px;")
                self.block_font_color_button.setProperty('selected_color', color)
            
            if 'outline' in model_data:
                self.outline_enabled = model_data['outline']
            
            if 'outline_color' in model_data:
                color = model_data['outline_color']
                self.outline_font_color_button.setStyleSheet(f"background-color: {color}; border: none; border-radius: 5px;")
                self.outline_font_color_button.setProperty('selected_color', color)
            
            if 'outline_width' in model_data:
                self.outline_width_dropdown.setCurrentText(str(model_data['outline_width']))
            
            if 'remove_newlines' in model_data:
                self.remove_newlines_button.setChecked(model_data['remove_newlines'])
                
        except Exception as e:
            print(f"Errore nell'applicazione del modello: {e}")
        
    def update_font_dropdown(self):
        """
        Aggiorna il dropdown dei font mostrando solo quelli selezionati nelle impostazioni
        """
        # Salva la selezione corrente
        current_font = self.font_dropdown.currentText()
        
        # Ottieni i font selezionati dalle impostazioni
        selected_fonts = self.settings_page.get_selected_fonts()
        
        # Svuota il dropdown
        self.font_dropdown.clear()
        
        # Aggiungi solo i font selezionati
        for font_family in QtGui.QFontDatabase().families():
            if font_family in selected_fonts:
                self.font_dropdown.addItem(font_family)
                
        # Ripristina la selezione precedente se possibile
        index = self.font_dropdown.findText(current_font)
        if index >= 0:
            self.font_dropdown.setCurrentIndex(index)
        elif self.font_dropdown.count() > 0:
            self.font_dropdown.setCurrentIndex(0)
    
    def deselect_tool_buttons(self, except_for=None):
        """Deseleziona tutti i pulsanti degli strumenti tranne quello specificato."""
        for key, button in self.tool_buttons.items():
            if key != except_for:
                button.setChecked(False)

    def _on_svg_border_color_changed(self, color):
        """Imposta il colore del bordo per l'SVG selezionato."""
        self.image_viewer.set_svg_border_color(color)
        
    def _on_svg_fill_color_changed(self, color):
        """Imposta il colore di riempimento per l'SVG selezionato."""
        self.image_viewer.set_svg_fill_color(color)
    
    def _on_reset_styles_clicked(self):
        """Ripristina gli stili originali per gli SVG selezionati."""
        self.image_viewer.reset_selected_svg_styles()
        
    def _on_save_svg_clicked(self):
        """Salva l'SVG modificato su file."""
        from app.ui.canvas.svg_item import SvgItem
        
        # Trova l'SVG selezionato
        selected_svg = None
        for item in self.image_viewer._scene.items():
            if isinstance(item, SvgItem) and item.isSelected():
                selected_svg = item
                break
        
        if not selected_svg:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, self.tr("Nessuna selezione"), 
                               self.tr("Seleziona un'immagine SVG da salvare."))
            return
            
        # Chiedi dove salvare
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, 
            self.tr("Salva SVG"), 
            selected_svg.get_filename(), 
            "SVG Files (*.svg)"
        )
        
        if file_path:
            if selected_svg.save_to_file(file_path):
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.information(self, self.tr("Salvataggio completato"), 
                                      self.tr("File SVG salvato con successo."))
            else:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.critical(self, self.tr("Errore"), 
                                   self.tr("Impossibile salvare il file SVG."))
    

        
    def _on_svg_border_width_changed(self, width_text):
        """Imposta lo spessore del bordo per l'SVG selezionato."""
        try:
            width = float(width_text)
            self.image_viewer.set_svg_border_width(width)
        except ValueError:
            pass  # Ignora valori non validi
    
    def _set_window_icon(self):
        """Imposta l'icona della finestra con multiple dimensioni per migliore compatibilità"""
        import logging
        logger = logging.getLogger('KomicTranslate.Icon')
        
        # Percorso base per le icone
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        icons_path = os.path.join(base_path, "assets", "icons")
        
        # Crea un QIcon con multiple dimensioni
        icon = QIcon()
        
        # Prima prova con il file .ico (migliore per Windows)
        ico_path = os.path.join(icons_path, "komictranslate_icon.ico")
        if os.path.exists(ico_path):
            icon.addFile(ico_path)
            logger.debug(f"Icona .ico caricata da: {ico_path}")
        
        # Aggiungi le icone PNG di diverse dimensioni
        png_sizes = [16, 32, 48, 64, 128, 256]
        for size in png_sizes:
            png_path = os.path.join(icons_path, f"komictranslate_icon_{size}.png")
            if os.path.exists(png_path):
                icon.addFile(png_path, QSize(size, size))
                logger.debug(f"Icona PNG {size}x{size} aggiunta da: {png_path}")
        
        # Fallback to SVG if no other icons found
        if icon.isNull():
            svg_path = os.path.join(icons_path, "komictranslate_icon.svg")
            if os.path.exists(svg_path):
                icon.addFile(svg_path)
                logger.debug(f"Icona SVG caricata da: {svg_path}")
        
        # Imposta l'icona della finestra
        if not icon.isNull():
            self.setWindowIcon(icon)
            logger.info("Icona della finestra impostata con successo")
        else:
            logger.error("Impossibile caricare l'icona della finestra")
    
    def sync_shape_controls(self, shape):
        """Sincronizza i controlli della toolbar con le proprietà della forma selezionata."""
        # Gestione connessione segnale dimensione
        from app.ui.canvas.svg_item import SvgItem
        
        if self._current_svg_item and self._current_svg_item != shape:
            try:
                self._current_svg_item.sizeChanged.disconnect(self._update_size_inputs)
            except:
                pass
        
        self._current_svg_item = shape
        
        if shape:
            # Sincronizza input dimensioni
            if isinstance(shape, SvgItem):
                size = shape.get_scaled_size()
                if size:
                    self.width_input.setText(f"{size.width():.1f}")
                    self.height_input.setText(f"{size.height():.1f}")
                
                try:
                    shape.sizeChanged.connect(self._update_size_inputs)
                except:
                    pass
            
            # Sincronizza colori e bordi
            if isinstance(shape, SvgItem) and hasattr(shape, 'fill_color'):
                self.fill_color_button.blockSignals(True)
                try:
                    self.fill_color_button.set_color(shape.fill_color())
                finally:
                    self.fill_color_button.blockSignals(False)
            
            if isinstance(shape, SvgItem) and hasattr(shape, 'border_color'):
                self.border_color_button.blockSignals(True)
                try:
                    self.border_color_button.set_color(shape.border_color())
                finally:
                    self.border_color_button.blockSignals(False)
                
            if isinstance(shape, SvgItem) and hasattr(shape, 'border_width'):
                width = shape.border_width()
                # Aggiorna il selettore senza triggerare il segnale
                self.svg_border_width_selector.blockSignals(True)
                val_str = str(width).rstrip('0').rstrip('.') if width % 1 != 0 else str(int(width))
                self.svg_border_width_selector.setCurrentText(val_str)
                self.svg_border_width_selector.blockSignals(False)
        else:
            self.width_input.clear()
            self.height_input.clear()

    def _on_scene_selection_changed(self):
        """Gestisce il cambio di selezione nella scena"""
        # Salta durante rimozione batch (delete) per non bloccare l'UI
        scene = self.image_viewer._scene
        if getattr(scene, '_batch_removing', False):
            return
        from app.ui.canvas.svg_item import SvgItem
        selected_items = scene.selectedItems()
        selected_shape = None
        for item in selected_items:
            if isinstance(item, SvgItem):
                selected_shape = item
                break
        
        self.sync_shape_controls(selected_shape)
        self._refresh_toggle_shape_button_state()

    def _refresh_toggle_shape_button_state(self):
        """Aggiorna stato e tooltip del pulsante Toggle in base alla selezione."""
        has_selection = len(self.image_viewer.get_selected_rectangles()) > 0
        self.toggle_shape_button.setEnabled(has_selection)
        if has_selection:
            self.toggle_shape_button.setToolTip(
                self.tr("Toggle: commuta la forma del box selezionato tra Rettangolo ed Ellisse")
            )
        else:
            self.toggle_shape_button.setToolTip(
                self.tr("Toggle: seleziona una casella di testo per passare tra Rettangolo ed Ellisse")
            )

    def update_size_inputs_from_tool(self, w, h):
        """Aggiorna i campi input quando l'SVG viene selezionato dal tool"""
        self.width_input.setText(f"{w:.1f}")
        self.height_input.setText(f"{h:.1f}")

    def _on_width_input_changed(self):
        """Aggiorna la larghezza dell'SVG dall'input"""
        try:
            w = float(self.width_input.text())
            if w <= 0: return
            
            if self._current_svg_item:
                base_w = self._current_svg_item.svg_size.width()
                new_scale_x = w / base_w
                self._current_svg_item.set_scale(scale_x=new_scale_x)
            elif hasattr(self, 'svg_tool') and self.svg_tool.is_placing:
                self.svg_tool.set_target_width(w)
        except ValueError:
            pass

    def _on_height_input_changed(self):
        """Aggiorna l'altezza dell'SVG dall'input"""
        try:
            h = float(self.height_input.text())
            if h <= 0: return
            
            if self._current_svg_item:
                base_h = self._current_svg_item.svg_size.height()
                new_scale_y = h / base_h
                self._current_svg_item.set_scale(scale_y=new_scale_y)
            elif hasattr(self, 'svg_tool') and self.svg_tool.is_placing:
                self.svg_tool.set_target_height(h)
        except ValueError:
            pass
    
    def _on_painting_color_changed(self, color):
        """Gestisce il cambio di colore per Penna e Secchiello."""
        self.image_viewer.set_painting_color(color)
        # Disattiva eyedropper se era attivo
        if hasattr(self.image_viewer, 'eyedropper_mode') and self.image_viewer.eyedropper_mode:
            self.image_viewer.toggle_eyedropper()
            self.eyedropper_button.setChecked(False)
    
    def _on_pen_size_changed(self, value):
        """Gestisce il cambio di dimensione della penna."""
        self.image_viewer.set_br_er_size(value, value, tool_type='pen')
        if hasattr(self, "pen_size_spinbox"):
            if self.pen_size_spinbox.value() != value:
                self.pen_size_spinbox.blockSignals(True)
                self.pen_size_spinbox.setValue(value)
                self.pen_size_spinbox.blockSignals(False)
        if hasattr(self, "pen_size_value_label"):
            self.pen_size_value_label.setText(str(value))

    def _on_pen_opacity_changed(self, value):
        """Gestisce il cambio di opacità della penna."""
        self.image_viewer.set_pen_opacity(value)
        self.pen_opacity_value_label.setText(f"{value}%")
    
    def _on_opacity_changed(self, value):
        """Metodo mantenuto per compatibilità, ora non più usato nell'inpainting standard."""
        pass
    
    def _on_advanced_brush_toggled(self, checked):
        """Gestisce l'abilitazione/disabilitazione del pennello avanzato."""
        self.image_viewer.enable_advanced_brush(checked)
        
        # Abilita/disabilita i controlli correlati
        self.brush_color_button.setEnabled(checked)
        self.opacity_slider.setEnabled(checked)
        
        if checked:
            # Imposta il colore e l'opacità iniziali
            color = self.brush_color_button.color()
            self.image_viewer.set_brush_color(color)
            opacity = self.opacity_slider.value()
            self.image_viewer.set_brush_opacity(opacity)
    

    
    def _on_brush_color_changed(self, color):
        """Gestisce il cambio di colore del pennello avanzato."""
        self.image_viewer.set_brush_color(color)
        # Disattiva eyedropper se era attivo
        if hasattr(self.image_viewer, 'eyedropper_mode') and self.image_viewer.eyedropper_mode:
            self.image_viewer.toggle_eyedropper()
    
    def _on_bucket_tolerance_changed(self, value):
        """Gestisce il cambio di tolleranza del secchiello."""
        self.image_viewer.bucket_fill_tolerance = value
        if hasattr(self, "bucket_tolerance_spinbox"):
            if self.bucket_tolerance_spinbox.value() != value:
                self.bucket_tolerance_spinbox.blockSignals(True)
                self.bucket_tolerance_spinbox.setValue(value)
                self.bucket_tolerance_spinbox.blockSignals(False)
        if hasattr(self, "bucket_tolerance_value"):
            self.bucket_tolerance_value.setText(str(value))

    def _on_eyedropper_color_picked(self, color):
        """Gestisce il colore prelevato dall'eyedropper."""
        self.painting_color_button.set_color(color)
        self._on_painting_color_changed(color)

    def _on_polygon_add_clicked(self):
        """Gestisce il click sul pulsante + per aggiungere vertice al poligono."""
        selected_rects = self.image_viewer.get_selected_rectangles()
        if selected_rects:
            rect_item = selected_rects[0]
            if hasattr(rect_item, 'polygon_overlay') and rect_item.polygon_overlay:
                rect_item.polygon_overlay.add_vertex_after_selected()

    def _on_polygon_delete_clicked(self):
        """Gestisce il click sul pulsante Canc per eliminare vertice del poligono."""
        selected_rects = self.image_viewer.get_selected_rectangles()
        if selected_rects:
            rect_item = selected_rects[0]
            if hasattr(rect_item, 'polygon_overlay') and rect_item.polygon_overlay:
                rect_item.polygon_overlay.delete_selected_vertex()

    def _on_delete_shape_clicked(self):
        """Gestisce il click sul pulsante elimina forma."""
        self.image_viewer.delete_selected_svgs()

    def _on_bring_to_front_clicked(self):
        """Porta la forma selezionata in primo piano."""
        self.image_viewer.bring_shape_to_front()
        
    def _on_send_to_back_clicked(self):
        """Porta la forma selezionata in secondo piano."""
        self.image_viewer.send_shape_to_back()

    def copy_source_to_target(self):
        """Copia il contenuto di Source in Target per tutti i blocchi rilevati"""
        
        # 1. Copia per il blocco attualmente selezionato (se esiste) nell'editor di testo
        source_text = self.s_text_edit.toPlainText()
        if source_text:
            self.t_text_edit.setPlainText(source_text)
            
        # 2. Copia massiva per tutti i blocchi (logica da controller)
        # Verifica se siamo nel contesto del controller (self.blk_list esiste)
        if hasattr(self, 'blk_list') and self.blk_list:
            count = 0
            for blk in self.blk_list:
                if hasattr(blk, 'text') and blk.text:
                    blk.translation = blk.text
                    count += 1
            
            # Aggiorna gli elementi visivi nel canvas
            if hasattr(self, 'image_viewer') and self.image_viewer and hasattr(self.image_viewer, '_scene'):
                # Itera sugli elementi della scena per aggiornare quelli visibili
                for item in self.image_viewer._scene.items():
                    if isinstance(item, TextBlockItem) and hasattr(item, 'blk') and item.blk:
                        # Aggiorna il testo visualizzato nell'item se corrisponde a un blocco
                        if item.blk.text:
                            # Usa set_plain_text se disponibile, altrimenti setHtml o setPlainText
                            if hasattr(item, 'set_plain_text'):
                                item.set_plain_text(item.blk.text)
                            elif hasattr(item, 'setPlainText'):
                                item.setPlainText(item.blk.text)
                            
            # Feedback all'utente tramite status bar se disponibile
            if hasattr(self, 'statusBar') and self.statusBar():
                self.statusBar().showMessage(self.tr(f"Copiato testo Source -> Target per {count} blocchi"), 3000)
            
            print(f"Copiato testo Source -> Target per {count} blocchi")
    
    def _open_translation_editor(self):
        """Apre la finestra di dialogo per modificare tutte le traduzioni"""
        blocks = []
        
        if hasattr(self, 'image_viewer') and self.image_viewer and hasattr(self.image_viewer, 'text_items'):
            ordered_blocks = []
            seen_ids = set()
            for item in self.image_viewer.text_items:
                blk = getattr(item, 'blk', None)
                if blk is None:
                    continue
                blk_id = id(blk)
                if blk_id in seen_ids:
                    continue
                ordered_blocks.append(blk)
                seen_ids.add(blk_id)
            if ordered_blocks:
                if hasattr(self, 'blk_list') and self.blk_list:
                    for blk in self.blk_list:
                        blk_id = id(blk)
                        if blk_id in seen_ids:
                            continue
                        ordered_blocks.append(blk)
                        seen_ids.add(blk_id)
                blocks = ordered_blocks
        
        if not blocks and hasattr(self, 'blk_list') and self.blk_list:
            blocks = self.blk_list

        if (not blocks and hasattr(self, 'curr_img_idx') and hasattr(self, 'image_files') and
                hasattr(self, 'image_states') and self.curr_img_idx is not None and
                isinstance(self.curr_img_idx, int) and 0 <= self.curr_img_idx < len(self.image_files)):
            current_file = self.image_files[self.curr_img_idx]
            state = self.image_states.get(current_file, {}) if isinstance(self.image_states, dict) else {}
            state_blocks = state.get('blk_list') or state.get('text_blocks') or []
            if state_blocks:
                blocks = state_blocks
        
        if not blocks and hasattr(self, 'image_viewer') and self.image_viewer and hasattr(self.image_viewer, '_scene'):
            for item in self.image_viewer._scene.items():
                if isinstance(item, TextBlockItem) and hasattr(item, 'blk') and item.blk:
                    blocks.append(item.blk)

        if not blocks:
            QtWidgets.QMessageBox.information(
                self,
                self.tr("Nessun blocco"),
                self.tr("Nessun blocco di testo rilevato.")
            )
            return
        
        # Crea il dialogo
        dialog = TranslationEditorDialog(blocks, self)
        
        # Se l'utente ha premuto OK
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            # Ottieni i blocchi aggiornati
            updated_blocks = dialog.get_updated_translations()
            
            # Aggiorna gli elementi visivi nel canvas
            if hasattr(self, 'image_viewer') and self.image_viewer and hasattr(self.image_viewer, '_scene'):
                for item in self.image_viewer._scene.items():
                    if isinstance(item, TextBlockItem) and hasattr(item, 'blk') and item.blk:
                        # Aggiorna il testo visualizzato con la traduzione
                        if hasattr(item.blk, 'translation'):
                            if hasattr(item, 'set_plain_text'):
                                item.set_plain_text(item.blk.translation)
                            elif hasattr(item, 'setPlainText'):
                                item.setPlainText(item.blk.translation)
            
            # Feedback all'utente
            if hasattr(self, 'statusBar') and self.statusBar:
                self.statusBar().showMessage(self.tr("Traduzioni aggiornate con successo"), 3000)
            # Aggiungiamo al log
            self.add_log_message("Modificate tutte le traduzioni completate")
    
    def add_log_message(self, message):
        """Aggiunge un messaggio al log con timestamp (thread-safe)"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        self.log_message_signal.emit(log_line)
    
    def _on_log_message(self, log_line):
        """Slot per aggiungere il messaggio al log (eseguito nel thread principale)"""
        print(f"[DEBUG] _on_log_message called with: {log_line}")
        if hasattr(self, 'log_text_edit'):
            self.log_text_edit.append(log_line)
            # Scrolliamo verso il basso per mostrare l'ultimo messaggio
            self.log_text_edit.verticalScrollBar().setValue(
                self.log_text_edit.verticalScrollBar().maximum()
            )
            print(f"[DEBUG] Added log line: {log_line}")

    # Metodi per la gestione dei controlli SVG avanzati rimossi



    def save_settings(self):
        # Salva le impostazioni
        self.settings_page.save_settings()
        # Aggiorna i font nel dropdown
        self.update_font_dropdown()
    
    def _on_inpainter_model_changed(self, index):
        """Gestisce il cambio di modello inpainter selezionato."""
        if index >= 0 and hasattr(self, 'controller') and self.controller:
            # Recupera il nome del modello dal data associato all'item
            model_name = self.inpainter_model_dropdown.itemData(index)
            if model_name:
                self.controller.set_inpainter_model(model_name)
    
    def _on_refresh_models_clicked(self):
        """Aggiorna la lista dei modelli disponibili."""
        if hasattr(self, 'controller') and self.controller:
            self.controller.refresh_inpainter_models()
    
    def _on_mode_changed(self, button):
        """Gestisce il cambio di modalità (Manuale / API KEY)"""
        # Trova l'indice del pulsante premuto
        buttons = self.mode_selector_group.get_button_group().buttons()
        index = buttons.index(button)
        self._update_buttons_visibility(index)

    def _update_buttons_visibility(self, mode_index):
        """
        Aggiorna la visibilità dei pulsanti in base alla modalità selezionata.
        """
        # Lista pulsanti (ordine aggiornato):
        # 0: Detect Text Boxes
        # 1: OCR
        # 2: Translate
        # 3: Gemini OUT (NASCOSTO - VETUSTO)
        # 4: Segment Text
        # 5: Clean Image
        # 6: Render
        
        buttons = self.hbutton_group.get_button_group().buttons()
        
        # Sempre visibili: Detect, OCR, Translate, Segment, Clean, Render
        # Sempre nascosto: Gemini OUT (index 3)
        visible_indices = [0, 1, 2, 4, 5, 6]
            
        for i, btn in enumerate(buttons):
            btn.setVisible(i in visible_indices)

    def update_inpainter_models(self, models):
        """Aggiorna il dropdown con i modelli disponibili."""
        current_selection = self.inpainter_model_dropdown.currentText()
        self.inpainter_model_dropdown.clear()
        
        # models è una lista di ModelInfo, non un dizionario
        for model_info in models:
            display_name = f"{model_info.name} ({model_info.status.value})"
            self.inpainter_model_dropdown.addItem(display_name, model_info.name)
        
        # Ripristina la selezione precedente se possibile
        index = self.inpainter_model_dropdown.findData(current_selection)
        if index >= 0:
            self.inpainter_model_dropdown.setCurrentIndex(index)
        elif self.inpainter_model_dropdown.count() > 0:
            self.inpainter_model_dropdown.setCurrentIndex(0)

    def _setup_dropdown_bar(self):
        dropdown_style = """
            QComboBox {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                color: #e0e0e0;
                border-radius: 4px;
                padding: 4px 8px;
                min-height: 24px;
            }
            QComboBox:hover {
                background-color: #3d3d3d;
                border: 1px solid #4d4d4d;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #888;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: #e0e0e0;
                border: 1px solid #3d3d3d;
                selection-background-color: #4d4d4d;
            }
        """

        self.ocr_dropdown = MComboBox()
        self.ocr_dropdown.setStyleSheet(dropdown_style)
        self.ocr_dropdown.addItems(self.settings_page.ui.get_supported_ocr_engines())
        current_ocr = self.settings_page.get_tool_selection('ocr')
        if current_ocr:
            self.ocr_dropdown.setCurrentText(current_ocr)

        self.translate_dropdown = MComboBox()
        self.translate_dropdown.setStyleSheet(dropdown_style)
        self.settings_page.ui.populate_grouped_combo(
            self.translate_dropdown,
            self.settings_page.ui.get_supported_translators_grouped()
        )
        current_translator = self.settings_page.get_tool_selection('translator')
        if current_translator:
            idx = self.translate_dropdown.findText(current_translator)
            if idx >= 0:
                self.translate_dropdown.setCurrentIndex(idx)

        self.inpainter_dropdown = MComboBox()
        self.inpainter_dropdown.setStyleSheet(dropdown_style)
        self.inpainter_dropdown.addItems(self.settings_page.ui.get_supported_inpainters())
        current_inpainter = self.settings_page.get_tool_selection('inpainter')
        if current_inpainter:
            self.inpainter_dropdown.setCurrentText(current_inpainter)
        
        return (self.ocr_dropdown, self.translate_dropdown, self.inpainter_dropdown)

    def _setup_header_toolbar(self):
        header_layout = QtWidgets.QHBoxLayout()

        self.undo_tool_group = MToolButtonGroup(orientation=QtCore.Qt.Horizontal, exclusive=True)
        undo_tools = [
            {"svg": "undo.svg", "checkable": False, "tooltip": self.tr("Undo")},
            {"svg": "redo.svg", "checkable": False, "tooltip": self.tr("Redo")},
        ]
        self.undo_tool_group.set_button_list(undo_tools)
        undo_buttons = self.undo_tool_group.get_button_group().buttons()
        for b in undo_buttons:
            b.small().icon_only()
            b.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        # Selettore modalità (Manuale / API KEY) - NASCOSTO (VETUSTO)
        self.mode_selector_group = MToolButtonGroup(orientation=QtCore.Qt.Horizontal, exclusive=True)
        mode_tools = [
            {"text": self.tr("Gemini"), "checkable": True, "tooltip": self.tr("Modalità Manuale")},
            {"text": self.tr("Classic"), "checkable": True, "tooltip": self.tr("Modalità API KEY")},
        ]
        self.mode_selector_group.set_button_list(mode_tools)
        self.mode_selector_group.get_button_group().buttons()[1].setChecked(True)
        self.mode_selector_group.get_button_group().buttonClicked.connect(self._on_mode_changed)
        self.mode_selector_group.setVisible(False)

        # ==== DROPDOWN BAR - Nuova sezione per i dropdown sotto i pulsanti ====
        self._setup_dropdown_bar()
        
        button_config_list = [
            {"text": self.tr("Rileva"), "dayu_type": MPushButton.DefaultType, "enabled": True},
            {"text": self.tr("OCR"), "dayu_type": MPushButton.DefaultType, "enabled": True},
            {"text": self.tr("Traduci"), "dayu_type": MPushButton.DefaultType, "enabled": True},
            {"text": self.tr("Gemini"), "dayu_type": MPushButton.DefaultType, "enabled": True},
            {"text": self.tr("Segmenta"), "dayu_type": MPushButton.DefaultType, "enabled": True},
            {"text": self.tr("Pulisci"), "dayu_type": MPushButton.DefaultType, "enabled": True},
            {"text": self.tr("Render."), "dayu_type": MPushButton.DefaultType, "enabled": True},
        ]

        self.hbutton_group = MPushButtonGroup()
        self.hbutton_group.set_dayu_size(dayu_theme.small)
        self.hbutton_group.set_button_list(button_config_list)
        self.hbutton_group.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)

        left_tools_widget = QtWidgets.QWidget()
        left_tools_layout = QtWidgets.QGridLayout(left_tools_widget)
        left_tools_layout.setContentsMargins(0, 0, 0, 0)
        left_tools_layout.setHorizontalSpacing(6)
        left_tools_layout.setVerticalSpacing(4)

        main_buttons = self.hbutton_group.get_button_group().buttons()
        visible_main_buttons = []
        for i, btn in enumerate(main_buttons):
            if i == 3:
                continue
            col = i if i < 3 else i - 1
            visible_main_buttons.append(btn)
            left_tools_layout.addWidget(btn, 0, col)

        left_tools_layout.addWidget(
            self.ocr_dropdown,
            1,
            1,
            alignment=QtCore.Qt.AlignmentFlag.AlignCenter,
        )
        left_tools_layout.addWidget(
            self.translate_dropdown,
            1,
            2,
            alignment=QtCore.Qt.AlignmentFlag.AlignCenter,
        )
        left_tools_layout.addWidget(
            self.inpainter_dropdown,
            1,
            4,
            alignment=QtCore.Qt.AlignmentFlag.AlignCenter,
        )

        header_layout.addWidget(left_tools_widget, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addSpacing(4)
        header_layout.addWidget(self.undo_tool_group, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addSpacing(4)
        
        # Applica la visibilità corretta dei pulsanti per la modalità Classic predefinita
        self._update_buttons_visibility(1)



        self.original_button = MPushButton(self.tr("Original"))
        self.original_button.setEnabled(False)
        self.original_button.setCheckable(True)
        self.original_button.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #4d4d4d;
                color: #e0e0e0;
                border-radius: 4px;
            }
            QPushButton:hover:!checked {
                background-color: #4d4d4d;
            }
            QPushButton:checked {
                background-color: #b03030;
                border: 1px solid #d05050;
                color: #ffffff;
            }
            QPushButton:checked:hover {
                background-color: #c04040;
            }
            QPushButton:disabled {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                color: #808080;
            }
        """)
        self.original_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.original_button.set_dayu_size(dayu_theme.small)
        
        self.detect_font_button = MPushButton(self.tr("Font"))
        self.detect_font_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.detect_font_button.set_dayu_size(dayu_theme.small)
        self.detect_font_button.setToolTip(self.settings_page.tooltip_manager.get("detect_font"))
        self.detect_font_button.setVisible(True)

        self.auto_center_button = MPushButton(self.tr("Center"))
        self.auto_center_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.auto_center_button.set_dayu_size(dayu_theme.small)
        self.auto_center_button.setToolTip(self.settings_page.tooltip_manager.get("auto_center"))
        self.auto_center_button.setEnabled(True)
        self.auto_center_button.setVisible(True)



        # Separator for batch section
        self.batch_separator = MDivider(orientation=QtCore.Qt.Vertical)

        # Batch buttons with distinct styling
        batch_style = """
            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                color: #e0e0e0;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
                border: 1px solid #4d4d4d;
            }
            QPushButton:pressed {
                background-color: #1d1d1d;
            }
        """

        self.detect_batch_button = MPushButton(self.tr("Rileva Tutto"))
        self.detect_batch_button.setEnabled(True)
        self.detect_batch_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.detect_batch_button.set_dayu_size(dayu_theme.small)
        self.detect_batch_button.setStyleSheet(batch_style)

        self.translate_button = MPushButton(self.tr("Traduci Tutto"))
        self.translate_button.setEnabled(True)
        self.translate_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.translate_button.set_dayu_size(dayu_theme.small)
        self.translate_button.setStyleSheet(batch_style)

        self.sbianchetta_button = MPushButton(self.tr("Sbianchetta"))
        self.sbianchetta_button.setEnabled(True)
        self.sbianchetta_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.sbianchetta_button.set_dayu_size(dayu_theme.small)
        self.sbianchetta_button.setStyleSheet(batch_style)

        self.markers_button = MPushButton(self.tr("Marcatori"))
        self.markers_button.setEnabled(True)
        self.markers_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.markers_button.set_dayu_size(dayu_theme.small)
        self.markers_button.setCheckable(True)
        self.markers_button.setChecked(True)
        self.markers_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                border: 1px solid #5a6268;
                color: white;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a6268;
                border: 1px solid #545b62;
            }
            QPushButton:pressed {
                background-color: #545b62;
            }
            QPushButton:checked {
                background-color: #dc3545;
                border: 1px solid #c82333;
                color: white;
            }
        """)

        self.polygons_button = MPushButton(self.tr("Poligoni"))
        self.polygons_button.setEnabled(True)
        self.polygons_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.polygons_button.set_dayu_size(dayu_theme.small)
        self.polygons_button.setCheckable(True)
        self.polygons_button.setChecked(True)
        self.polygons_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                border: 1px solid #5a6268;
                color: white;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a6268;
                border: 1px solid #545b62;
            }
            QPushButton:pressed {
                background-color: #545b62;
            }
            QPushButton:checked {
                background-color: #dc3545;
                border: 1px solid #c82333;
                color: white;
            }
        """)

        self.rect_boxes_button = MPushButton(self.tr("Caselle OCR"))
        self.rect_boxes_button.setEnabled(True)
        self.rect_boxes_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.rect_boxes_button.set_dayu_size(dayu_theme.small)
        self.rect_boxes_button.setCheckable(True)
        self.rect_boxes_button.setChecked(True)
        self.rect_boxes_button.setStyleSheet("""
            QPushButton {
                background-color: #6c757d;
                border: 1px solid #5a6268;
                color: white;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a6268;
                border: 1px solid #545b62;
            }
            QPushButton:pressed {
                background-color: #545b62;
            }
            QPushButton:checked {
                background-color: #dc3545;
                border: 1px solid #c82333;
                color: white;
            }
        """)

        # Pulsante toggle per nascondere/mostrare le caselle di testo create da "Traduci Tutto".
        # Stato iniziale: disabilitato; viene abilitato automaticamente in on_blk_rendered()
        # quando "Traduci Tutto" genera le caselle di testo.
        self.toggle_text_boxes_button = MPushButton(self.tr("Nascondi\nTesto"))
        self.toggle_text_boxes_button.setEnabled(False)
        self.toggle_text_boxes_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.toggle_text_boxes_button.set_dayu_size(dayu_theme.small)
        self.toggle_text_boxes_button.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                border: 1px solid #c82333;
                color: white;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c82333;
                border: 1px solid #bd2130;
            }
            QPushButton:pressed {
                background-color: #bd2130;
            }
            QPushButton:disabled {
                background-color: #6c757d;
                border: 1px solid #5a6268;
                color: #adb5bd;
            }
        """)

        self.cancel_batch_button = MPushButton(self.tr("Cancel"))
        self.cancel_batch_button.setEnabled(False)
        self.cancel_batch_button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.cancel_batch_button.set_dayu_size(dayu_theme.small)
        self.cancel_batch_button.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                border: 1px solid #c82333;
                color: white;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #c82333;
                border: 1px solid #bd2130;
            }
            QPushButton:pressed {
                background-color: #bd2130;
            }
            QPushButton:disabled {
                background-color: #6c757d;
                border: 1px solid #5a6268;
                color: #adb5bd;
            }
        """)
        self.cancel_batch_button.setVisible(False)


        header_layout.addWidget(self.original_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(self.detect_font_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(self.auto_center_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        
        # Add visual separator
        header_layout.addSpacing(6)
        header_layout.addWidget(self.batch_separator, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addSpacing(6)
        
        # Batch section
        header_layout.addWidget(self.detect_batch_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(self.translate_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(self.sbianchetta_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(self.markers_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(self.polygons_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(self.rect_boxes_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(self.toggle_text_boxes_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(self.cancel_batch_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        
        header_layout.addWidget(self.loading, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addStretch()
        header_layout.addWidget(self.mode_selector_group, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        uniform_widgets = [
            self.ocr_dropdown,
            self.translate_dropdown,
            self.inpainter_dropdown,
            *visible_main_buttons,
            self.original_button,
            self.detect_font_button,
            self.auto_center_button,
            self.detect_batch_button,
            self.translate_button,
            self.sbianchetta_button,
            self.markers_button,
            self.polygons_button,
            self.rect_boxes_button,
            self.toggle_text_boxes_button,
        ]
        max_width = max(w.sizeHint().width() for w in uniform_widgets)
        max_width = min(max_width, 85)
        max_width = int(max_width * HEADER_TOOLBAR_WIDTH_SCALE)
        for w in uniform_widgets:
            w.setFixedWidth(max_width)

        header_buttons = [
            *visible_main_buttons,
            self.original_button,
            self.detect_font_button,
            self.auto_center_button,
            self.detect_batch_button,
            self.translate_button,
            self.sbianchetta_button,
            self.markers_button,
            self.polygons_button,
            self.rect_boxes_button,
            self.toggle_text_boxes_button,
            self.cancel_batch_button,
        ]
        target_h = min(w.sizeHint().height() for w in header_buttons)
        target_h = int(target_h * HEADER_TOOLBAR_HEIGHT_SCALE)
        for w in header_buttons:
            w.setFixedHeight(target_h)
        for b in undo_buttons:
            b.setFixedSize(QtCore.QSize(target_h, target_h))

        # Avvolgi la header_layout in una QScrollArea orizzontale per gestire
        # schermi piccoli (es. 1280x800) in cui i pulsanti non entrano tutti.
        container = QtWidgets.QWidget()
        container.setObjectName("headerToolbarContainer")
        container.setLayout(header_layout)
        # Lascia che il container mantenga la propria altezza naturale
        container.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
        # Piccolo padding estetico
        container.setContentsMargins(2, 2, 2, 2)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("headerToolbarScrollArea")
        scroll_area.setWidgetResizable(False)
        scroll_area.setWidget(container)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_area.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        # Altezza fissa iniziale, verrà riallineata da _update_header_scroll_height
        scroll_area.setFixedHeight(container.sizeHint().height() + 2)

        self._header_scroll_area = scroll_area
        self._header_container = container
        self._header_toolbar_layout_applier = HeaderToolbarLayoutApplier(
            scroll_area=scroll_area,
            container=container,
            visible_main_buttons=visible_main_buttons,
            undo_tool_group=self.undo_tool_group,
            ocr_dropdown=self.ocr_dropdown,
            translate_dropdown=self.translate_dropdown,
            inpainter_dropdown=self.inpainter_dropdown,
            original_button=self.original_button,
            detect_font_button=self.detect_font_button,
            auto_center_button=self.auto_center_button,
            batch_separator=self.batch_separator,
            detect_batch_button=self.detect_batch_button,
            translate_button=self.translate_button,
            sbianchetta_button=self.sbianchetta_button,
            markers_button=self.markers_button,
            polygons_button=self.polygons_button,
            rect_boxes_button=self.rect_boxes_button,
            toggle_text_boxes_button=self.toggle_text_boxes_button,
            cancel_batch_button=self.cancel_batch_button,
            loading=self.loading,
            mode_selector_group=self.mode_selector_group,
        )
        # Ricalcola l'altezza dopo che il layout è stato effettivamente calcolato
        QtCore.QTimer.singleShot(0, self._update_header_scroll_height)

        return scroll_area

    def _setup_progress_widgets(self):
        self.progress_bar = MProgressBar().auto_color()
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)

        self.loading = MLoading().small()
        self.loading.setVisible(False)
        
        # Radios (nascosti nel codice originale)
        self.manual_radio = MRadioButton(self.tr("Manual"))
        self.manual_radio.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.manual_radio.setVisible(False)
        self.automatic_radio = MRadioButton(self.tr("Automatic"))
        self.automatic_radio.setChecked(True)
        self.automatic_radio.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        self.automatic_radio.setVisible(False)

    def _setup_left_panel(self):
        left_layout = QtWidgets.QVBoxLayout()
        left_layout.addWidget(MDivider())

        self.image_card_layout = QtWidgets.QVBoxLayout()
        self.image_card_layout.addStretch(1)

        self.page_list.setLayout(self.image_card_layout)
        left_layout.addWidget(self.page_list)
        left_widget = QtWidgets.QWidget()
        left_widget.setLayout(left_layout)
        return left_widget

    def _setup_central_view(self):
        self.central_stack = QtWidgets.QStackedWidget()
        
        self.drag_browser = MDragFileButton(text=self.tr("Click or drag files here"), multiple=True)
        self.drag_browser.set_dayu_svg("attachment_line.svg")
        self.drag_browser.set_dayu_filters([".png", ".jpg", ".jpeg", ".webp", ".bmp",
                                            ".zip", ".cbz", ".cbr", ".cb7", ".cbt",
                                            ".pdf", ".epub", ".ctpr"])
        self.drag_browser.setToolTip(self.settings_page.tooltip_manager.get("drag_browser"))
        
        self.central_stack.addWidget(self.drag_browser)
        self.central_stack.addWidget(self.image_viewer)
        
        central_widget = QtWidgets.QWidget()
        central_layout = QtWidgets.QVBoxLayout(central_widget)
        central_layout.addWidget(self.central_stack)
        central_layout.setContentsMargins(10, 10, 10, 10)
        return central_widget

    def _setup_text_input_area(self):
        main_layout = QtWidgets.QVBoxLayout()
        
        # Source and Target in HBox
        input_layout = QtWidgets.QHBoxLayout()
       
        # Source Language (dropdown + campo di testo sorgente)
        s_combo_text_layout = QtWidgets.QVBoxLayout()
        self.s_combo = MComboBox().medium()
        self.s_combo.addItems([self.tr(lang) for lang in supported_source_languages])
        self.s_combo.setToolTip(self.settings_page.tooltip_manager.get("s_combo"))
        s_combo_text_layout.addWidget(self.s_combo)
        self.s_text_edit = MTextEdit()
        self.s_text_edit.setFixedHeight(150)
        s_combo_text_layout.addWidget(self.s_text_edit)
        # Mostriamo il campo di testo sorgente
        self.s_text_edit.setVisible(True)
        input_layout.addLayout(s_combo_text_layout)

        # Target Language (dropdown + campo di testo target)
        t_combo_text_layout = QtWidgets.QVBoxLayout()
        self.t_combo = MComboBox().medium()
        self.t_combo.addItems([self.tr(lang) for lang in supported_target_languages])
        self.t_combo.setToolTip(self.settings_page.tooltip_manager.get("t_combo"))
        t_combo_text_layout.addWidget(self.t_combo)
        
        self.t_text_edit = MTextEdit()
        self.t_text_edit.setFixedHeight(150)
        t_combo_text_layout.addWidget(self.t_text_edit)
        # Mostriamo il campo di testo target
        self.t_text_edit.setVisible(True)

        input_layout.addLayout(t_combo_text_layout)
        
        main_layout.addLayout(input_layout)
        
        # Add "La Traduzione" button
        self.open_translation_editor_button = MPushButton(self.tr("La Traduzione"))
        self.open_translation_editor_button.setToolTip(self.tr("Modifica tutte le traduzioni in una finestra"))
        self.open_translation_editor_button.setStyleSheet("text-align: left; padding-left: 10px;")
        self.open_translation_editor_button.clicked.connect(self._open_translation_editor)
        main_layout.addWidget(self.open_translation_editor_button)
        
        return main_layout

    def _on_select_all_boxes_clicked(self):
        """Callback del pulsante 'Seleziona tutte'."""
        try:
            count = self.select_all_text_items()
        except Exception as e:
            print(f"[MULTI-SELECT] 'Seleziona tutte' non riuscito: {e}")
            return
        if count <= 0:
            from app.ui.messages import Messages
            Messages.show_info(
                self,
                self.tr("Nessuna casella"),
                self.tr("Non ci sono caselle di testo rilevate da selezionare."),
            )

    def _setup_text_render_settings(self):
        text_render_layout = QtWidgets.QVBoxLayout()
        font_settings_layout = QtWidgets.QHBoxLayout()

        self.font_dropdown = MFontComboBox().small()
        self.font_dropdown.setToolTip(self.settings_page.tooltip_manager.get("font_dropdown"))
        
        # Note: fonts are handled in update_font_dropdown called later
            
        self.font_size_dropdown = MComboBox().small()
        self.font_size_dropdown.setToolTip(self.settings_page.tooltip_manager.get("font_size_dropdown"))
        # I valori non sono hardcoded: vengono generati dal range
        # [min, max] con passo 0.5 in refresh_font_size_dropdown().
        self.font_size_dropdown.setFixedWidth(60)
        self.font_size_dropdown.set_editable(True)

        self.line_spacing_dropdown = MComboBox().small()
        self.line_spacing_dropdown.setToolTip(self.settings_page.tooltip_manager.get("line_spacing_dropdown"))
        self.line_spacing_dropdown.addItems(['0.8', '0.9', '1.0', '1.1', '1.2', '1.3', '1.4', '1.5'])
        self.line_spacing_dropdown.setFixedWidth(60)
        self.line_spacing_dropdown.set_editable(True)

        self.remove_newlines_button = self.create_tool_button(svg="enter-crossed.svg", checkable=False)
        self.remove_newlines_button.setText('↵̸')
        self.remove_newlines_button.setToolTip(self.settings_page.tooltip_manager.get("remove_newlines"))
        self.remove_newlines_button.setFixedSize(30, 30)

        self.polygon_text_button = self.create_tool_button(
            svg="pentagon-outline.svg", checkable=True
        )
        self.polygon_text_button.setToolTip(
            self.settings_page.tooltip_manager.get("polygon_text")
        )
        self.polygon_text_button.setFixedSize(30, 30)
        self.polygon_text_button.setVisible(False)
        
        font_settings_layout.addWidget(self.font_dropdown)
        font_settings_layout.addWidget(self.font_size_dropdown)
        font_settings_layout.addWidget(self.line_spacing_dropdown)
        font_settings_layout.addStretch()

        # Duplicato di Minimum/Maximum Font Size nella barra laterale
        # (etichette abbreviate "Min:" / "Max:").
        min_max_layout = QtWidgets.QHBoxLayout()
        min_max_layout.setContentsMargins(0, 0, 0, 0)
        min_max_layout.setSpacing(4)
        try:
            _init_min = int(self.settings_page.ui.min_font_spinbox.value())
        except Exception:
            _init_min = 9
        try:
            _init_max = int(self.settings_page.ui.max_font_spinbox.value())
        except Exception:
            _init_max = 40
        self.min_font_label_sidebar = QtWidgets.QLabel(self.tr("Min:"))
        self.min_font_label_sidebar.setToolTip(self.tr("Minimum Font Size"))
        self.min_font_sidebar_spinbox = MSpinBox().small()
        self.min_font_sidebar_spinbox.setMinimum(1)
        self.min_font_sidebar_spinbox.setMaximum(100)
        self.min_font_sidebar_spinbox.setFixedWidth(55)
        self.min_font_sidebar_spinbox.setToolTip(self.tr("Minimum Font Size"))
        self.min_font_sidebar_spinbox.setValue(_init_min)
        self.max_font_label_sidebar = QtWidgets.QLabel(self.tr("Max:"))
        self.max_font_label_sidebar.setToolTip(self.tr("Maximum Font Size"))
        self.max_font_sidebar_spinbox = MSpinBox().small()
        self.max_font_sidebar_spinbox.setMinimum(1)
        self.max_font_sidebar_spinbox.setMaximum(100)
        self.max_font_sidebar_spinbox.setFixedWidth(55)
        self.max_font_sidebar_spinbox.setToolTip(self.tr("Maximum Font Size"))
        self.max_font_sidebar_spinbox.setValue(_init_max)
        min_max_layout.addWidget(self.min_font_label_sidebar)
        min_max_layout.addWidget(self.min_font_sidebar_spinbox)
        min_max_layout.addSpacing(8)
        min_max_layout.addWidget(self.max_font_label_sidebar)
        min_max_layout.addWidget(self.max_font_sidebar_spinbox)
        min_max_layout.addStretch()
        self._syncing_min_max = False
        try:
            self.min_font_sidebar_spinbox.valueChanged.connect(self._on_sidebar_min_font_changed)
            self.max_font_sidebar_spinbox.valueChanged.connect(self._on_sidebar_max_font_changed)
            self.settings_page.ui.min_font_spinbox.valueChanged.connect(self._on_settings_min_font_changed)
            self.settings_page.ui.max_font_spinbox.valueChanged.connect(self._on_settings_max_font_changed)
        except Exception:
            pass
        self.refresh_font_size_dropdown()

        main_text_settings_layout = QtWidgets.QHBoxLayout()

        settings = QSettings("ComicLabs", "KomicTranslate")
        settings.beginGroup('text_rendering')
        dflt_clr = settings.value('color', DEFAULT_FONT_COLOR)
        dflt_outline_check = settings.value('outline', True, type=bool)
        settings.endGroup()
        
        self.block_font_color_button = QtWidgets.QPushButton()
        self.block_font_color_button.setToolTip(self.settings_page.tooltip_manager.get("block_font_color"))
        self.block_font_color_button.setFixedSize(30, 30)
        self.block_font_color_button.setStyleSheet(
            f"background-color: {dflt_clr}; border: none; border-radius: 5px;"
        )
        self.block_font_color_button.setProperty('selected_color', dflt_clr)

        self.alignment_tool_group = MToolButtonGroup(orientation=QtCore.Qt.Horizontal, exclusive=False)
        alignment_tools = [
            {"svg": "tabler--align-left.svg", "checkable": False, "tooltip": "Align Left"},
            {"svg": "tabler--align-center.svg", "checkable": False, "tooltip": "Align Center"},
            {"svg": "tabler--align-right.svg", "checkable": False, "tooltip": "Align Right"},
            {"svg": "tabler--align-justify.svg", "checkable": False, "tooltip": "Align Justify"},
        ]
        self.alignment_tool_group.set_button_list(alignment_tools)

        # Set center alignment as default
        self.alignment_tool_group.get_button_group().buttons()[1].setChecked(True)

        self.bold_button = self.create_tool_button(svg = "bold.svg", checkable=False)
        self.bold_button.setToolTip(self.settings_page.tooltip_manager.get("bold"))
        self.italic_button = self.create_tool_button(svg = "italic.svg", checkable=False)
        self.italic_button.setToolTip(self.settings_page.tooltip_manager.get("italic"))
        self.underline_button = self.create_tool_button(svg = "underline.svg", checkable=False)
        self.underline_button.setToolTip(self.settings_page.tooltip_manager.get("underline"))

        self.outline_button = MPushButton(self.tr("Contorno"))
        self.outline_button.setToolTip(self.settings_page.tooltip_manager.get("outline"))
        
        self.outline_font_color_button = QtWidgets.QPushButton()
        self.outline_font_color_button.setToolTip(self.settings_page.tooltip_manager.get("outline_font_color"))
        self.outline_font_color_button.setFixedSize(30, 30)
        self.outline_font_color_button.setStyleSheet(
            f"background-color: {DEFAULT_OUTLINE_COLOR}; border: none; border-radius: 5px;"
        )
        self.outline_font_color_button.setProperty('selected_color', DEFAULT_OUTLINE_COLOR)

        self.outline_width_dropdown = MComboBox().small()
        self.outline_width_dropdown.setToolTip(self.settings_page.tooltip_manager.get("outline_width"))
        self.outline_width_dropdown.addItems(['1.0', '1.15', '1.3', '1.4', '1.5'])
        self.outline_width_dropdown.setFixedWidth(60)
        self.outline_width_dropdown.set_editable(True)

        style_buttons_layout = QtWidgets.QHBoxLayout()
        style_buttons_layout.addWidget(self.block_font_color_button)
        style_buttons_layout.addWidget(self.alignment_tool_group)
        style_buttons_layout.addWidget(self.bold_button)
        style_buttons_layout.addWidget(self.italic_button)
        style_buttons_layout.addWidget(self.underline_button)
        style_buttons_layout.addStretch()

        outline_controls_layout = QtWidgets.QHBoxLayout()
        outline_controls_layout.addWidget(self.outline_button)
        outline_controls_layout.addWidget(self.outline_font_color_button)
        outline_controls_layout.addWidget(self.outline_width_dropdown)
        outline_controls_layout.addWidget(self.remove_newlines_button)
        outline_controls_layout.addSpacing(6)
        outline_controls_layout.addWidget(self.polygon_text_button)
        outline_controls_layout.addStretch()

        font_models_layout = QtWidgets.QHBoxLayout()
        self.save_model_button = MPushButton(self.tr("Salva modelli"))
        self.save_model_button.setToolTip(self.settings_page.tooltip_manager.get("save_model"))
        self.save_model_button.set_dayu_size(dayu_theme.small)
        self.save_model_button.clicked.connect(self.save_font_model)
        
        self.model_selector = MComboBox().small()
        self.model_selector.setToolTip(self.settings_page.tooltip_manager.get("model_selector"))
        self.model_selector.setFixedWidth(120)
        self.model_selector.currentTextChanged.connect(self.load_selected_font_model)
        
        self.delete_model_button = MPushButton("❌")
        self.delete_model_button.setToolTip(self.settings_page.tooltip_manager.get("delete_model"))
        self.delete_model_button.clicked.connect(self.delete_font_model)
        self.delete_model_button.setFixedSize(20, 20)
        self.delete_model_button.setStyleSheet("""
            QPushButton {
                color: #dc3545;
                background-color: transparent;
                border: 1px solid #dc3545;
                border-radius: 10px;
                font-weight: bold;
                font-size: 14px;
                font-family: Arial, sans-serif;
            }
            QPushButton:hover {
                color: white;
                background-color: #dc3545;
            }
            QPushButton:pressed {
                background-color: #c82333;
            }
        """)
        
        self.default_model_button = MPushButton(self.tr("DEF"))
        self.default_model_button.setToolTip(self.settings_page.tooltip_manager.get("default_model"))
        self.default_model_button.set_dayu_size(dayu_theme.small)
        self.default_model_button.setFixedWidth(60)
        self.default_model_button.clicked.connect(self.load_default_font_model)
        
        self.copy_to_target_button = MPushButton(self.tr("Src→Tgt"))
        self.copy_to_target_button.setToolTip(self.settings_page.tooltip_manager.get("copy_to_target"))
        self.copy_to_target_button.set_dayu_size(dayu_theme.small)
        self.copy_to_target_button.setFixedWidth(90)
        self.copy_to_target_button.clicked.connect(self.copy_source_to_target)

        target_h = self.model_selector.sizeHint().height()
        self.save_model_button.setFixedHeight(target_h)
        self.default_model_button.setFixedHeight(target_h)
        self.copy_to_target_button.setFixedHeight(target_h)
        self.delete_model_button.setFixedSize(target_h, target_h)
        
        font_models_layout.addWidget(self.save_model_button)
        font_models_layout.addWidget(self.model_selector)
        font_models_layout.addWidget(self.delete_model_button)
        font_models_layout.addWidget(self.default_model_button)
        font_models_layout.addWidget(self.copy_to_target_button)
        font_models_layout.addStretch()

        text_render_layout.addWidget(MDivider())
        text_render_layout.addLayout(font_settings_layout)
        text_render_layout.addLayout(min_max_layout)
        text_render_layout.addLayout(style_buttons_layout)
        text_render_layout.addLayout(outline_controls_layout)
        text_render_layout.addLayout(font_models_layout)
        text_render_layout.addWidget(MDivider())
        
        return text_render_layout

    def get_sidebar_min_font_size(self):
        try:
            return int(self.min_font_sidebar_spinbox.value())
        except Exception:
            return int(self.settings_page.get_min_font_size())

    def get_sidebar_max_font_size(self):
        try:
            return int(self.max_font_sidebar_spinbox.value())
        except Exception:
            return int(self.settings_page.get_max_font_size())

    def refresh_font_size_dropdown(self):
        """Ricostruisce il dropdown dai valori min/max con passo 0.5."""
        from .font_size_utils import font_size_range, parse_font_size, format_font_size
        try:
            min_v = self.get_sidebar_min_font_size()
        except Exception:
            try:
                min_v = int(self.settings_page.get_min_font_size())
            except Exception:
                min_v = 9
        try:
            max_v = self.get_sidebar_max_font_size()
        except Exception:
            try:
                max_v = int(self.settings_page.get_max_font_size())
            except Exception:
                max_v = 40
        if min_v > max_v:
            min_v, max_v = max_v, min_v
        items = font_size_range(min_v, max_v, 0.5)
        try:
            current = self.font_size_dropdown.currentText()
        except Exception:
            current = ''
        current_val = parse_font_size(current, default=min_v)
        # Clamp nel range
        if current_val < min(min_v, max_v):
            current_val = float(min(min_v, max_v))
        if current_val > max(min_v, max_v):
            current_val = float(max(min_v, max_v))
        self.font_size_dropdown.blockSignals(True)
        try:
            self.font_size_dropdown.clear()
            self.font_size_dropdown.addItems(items)
            target = format_font_size(current_val)
            idx = self.font_size_dropdown.findText(target)
            if idx >= 0:
                self.font_size_dropdown.setCurrentIndex(idx)
            else:
                # Fallback: valore piu' vicino
                best_idx, best_dist = 0, None
                for i, it in enumerate(items):
                    d = abs(parse_font_size(it, default=current_val) - current_val)
                    if best_dist is None or d < best_dist:
                        best_dist, best_idx = d, i
                self.font_size_dropdown.setCurrentIndex(best_idx)
        finally:
            self.font_size_dropdown.blockSignals(False)

    def _set_min_max_no_signal(self, min_v, max_v):
        self._syncing_min_max = True
        try:
            for spin, val in (
                (self.settings_page.ui.min_font_spinbox, min_v),
                (self.settings_page.ui.max_font_spinbox, max_v),
                (self.min_font_sidebar_spinbox, min_v),
                (self.max_font_sidebar_spinbox, max_v),
            ):
                try:
                    spin.blockSignals(True)
                    spin.setValue(int(val))
                except Exception:
                    pass
                finally:
                    try:
                        spin.blockSignals(False)
                    except Exception:
                        pass
        finally:
            self._syncing_min_max = False
        self.refresh_font_size_dropdown()

    def _on_sidebar_min_font_changed(self, value):
        if getattr(self, '_syncing_min_max', False):
            return
        try:
            max_v = int(self.max_font_sidebar_spinbox.value())
        except Exception:
            max_v = int(value)
        min_v = int(value)
        if min_v > max_v:
            max_v = min_v
        self._set_min_max_no_signal(min_v, max_v)

    def _on_sidebar_max_font_changed(self, value):
        if getattr(self, '_syncing_min_max', False):
            return
        try:
            min_v = int(self.min_font_sidebar_spinbox.value())
        except Exception:
            min_v = int(value)
        max_v = int(value)
        if max_v < min_v:
            min_v = max_v
        self._set_min_max_no_signal(min_v, max_v)

    def _on_settings_min_font_changed(self, value):
        if getattr(self, '_syncing_min_max', False):
            return
        try:
            max_v = int(self.settings_page.ui.max_font_spinbox.value())
        except Exception:
            max_v = int(value)
        min_v = int(value)
        if min_v > max_v:
            max_v = min_v
        self._set_min_max_no_signal(min_v, max_v)

    def _on_settings_max_font_changed(self, value):
        if getattr(self, '_syncing_min_max', False):
            return
        try:
            min_v = int(self.settings_page.ui.min_font_spinbox.value())
        except Exception:
            min_v = int(value)
        max_v = int(value)
        if max_v < min_v:
            min_v = max_v
        self._set_min_max_no_signal(min_v, max_v)

    def _create_sidebar_section(self, title, widget, expand=False):
        section = MSectionItem(title=title, expand=expand, widget=widget)
        section.header_widget.setMinimumHeight(26)
        section.header_widget.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Preferred,
        )
        section.title_label.setMinimumHeight(18)
        return section

    def _build_tool_sections(self):
        sections = [
            ("selection", self._create_sidebar_section(self.tr("Selezione"), self._setup_selection_tools(), True)),
            ("box", self._create_sidebar_section(self.tr("Box"), self._setup_box_size_tools(), True)),
            ("gvb", self._create_sidebar_section(self.tr("GVB"), self._setup_gvb_tools())),
            ("inpainting", self._create_sidebar_section(self.tr("Inpainting"), self._setup_inpainting_tools())),
            ("painting", self._create_sidebar_section(self.tr("Painting"), self._setup_painting_tools())),
            ("polygons", self._create_sidebar_section(self.tr("Poligoni"), self._setup_polygon_tools())),
            ("canvas_svg", self._create_sidebar_section(self.tr("Canvas & SVG"), self._setup_canvas_tools())),
            ("navigation", self._create_sidebar_section(self.tr("Navigazione Immagine"), self._setup_image_navigation_tools())),
            ("operations", self._create_sidebar_section(self.tr("Stato Operazioni"), self._create_log_widget())),
            ("operativa", self._create_sidebar_section(self.tr("Operativa"), self._create_operativa_widget(), True)),
        ]

        # Timer per il monitoraggio GPU (1500 ms)
        self.gpu_monitor_timer = QtCore.QTimer(self)
        self.gpu_monitor_timer.setInterval(1500)
        self.gpu_monitor_timer.timeout.connect(self._update_gpu_stats)
        self._gpu_monitor_active = False

        # Aggiungi un messaggio di test
        self.add_log_message("Stato operazioni inizializzato")
        return sections

    def _create_log_widget(self):
        log_widget = QtWidgets.QWidget()
        log_outer_lay = QtWidgets.QHBoxLayout(log_widget)
        log_outer_lay.setContentsMargins(0, 0, 0, 0)
        log_outer_lay.setSpacing(0)

        log_inner = QtWidgets.QWidget()
        self._log_inner_widget = log_inner
        log_lay = QtWidgets.QVBoxLayout(log_inner)
        log_lay.setContentsMargins(4, 4, 4, 4)
        log_lay.setSpacing(4)

        gpu_row = QtWidgets.QHBoxLayout()
        gpu_row.setContentsMargins(0, 0, 0, 0)
        gpu_row.setSpacing(8)
        self.gpu_stats_label = QtWidgets.QLabel(self.tr("GPU: --"))
        self.gpu_stats_label.setStyleSheet("color: #4FC3F7; font-family: Consolas, monospace; font-weight: bold;")
        gpu_row.addWidget(self.gpu_stats_label)
        gpu_row.addStretch()
        log_lay.addLayout(gpu_row)

        self.log_text_edit = MTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setFixedHeight(120)
        log_lay.addWidget(self.log_text_edit)

        log_outer_lay.addWidget(log_inner)
        log_outer_lay.addStretch()
        return log_widget

    def _create_operativa_widget(self):
        operativa_widget = QtWidgets.QWidget()
        operativa_layout = QtWidgets.QVBoxLayout(operativa_widget)
        operativa_layout.setContentsMargins(4, 4, 4, 4)
        operativa_layout.setSpacing(6)

        self._operativa_host_widget = QtWidgets.QWidget()
        self._operativa_host_layout = QtWidgets.QVBoxLayout(self._operativa_host_widget)
        self._operativa_host_layout.setContentsMargins(0, 0, 0, 0)
        self._operativa_host_layout.setSpacing(0)
        operativa_layout.addWidget(self._operativa_host_widget)
        return operativa_widget

    def _update_gpu_stats(self):
        """Aggiorna la label con l'utilizzo GPU/VRAM corrente tramite nvidia-smi."""
        if not self._gpu_monitor_active:
            return
        try:
            # Su Windows l'app gira --noconsole: senza CREATE_NO_WINDOW ogni
            # nvidia-smi apre una console nera lampo (una ogni 1.5s col monitor
            # attivo). Stessa convenzione gia' usata in gvb_image_clipboard.
            hidden_kwargs = {}
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                hidden_kwargs = {
                    'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000),
                    'startupinfo': startupinfo,
                }
            result = subprocess.run(
                ['nvidia-smi',
                 '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu',
                 '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=1,
                **hidden_kwargs
            )
            if result.returncode == 0 and result.stdout.strip():
                line = result.stdout.strip().split('\n')[0]
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 3:
                    util, mem_used, mem_total = parts[0], parts[1], parts[2]
                    temp = parts[3] if len(parts) >= 4 else None
                    text = f"GPU: {util}%  |  VRAM: {mem_used}/{mem_total} MB"
                    if temp:
                        text += f"  |  {temp}°C"
                    self.gpu_stats_label.setText(text)
                    return
            self.gpu_stats_label.setText(self.tr("GPU: N/A"))
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            self.gpu_stats_label.setText(self.tr("GPU: N/A (nvidia-smi non disponibile)"))

    def start_gpu_monitor(self):
        """Avvia il monitoraggio GPU (chiamato all'inizio di una traduzione batch)."""
        self._gpu_monitor_active = True
        self._update_gpu_stats()  # primo aggiornamento immediato
        self.gpu_monitor_timer.start()

    def stop_gpu_monitor(self):
        """Ferma il monitoraggio GPU (chiamato a fine traduzione batch)."""
        self._gpu_monitor_active = False
        self.gpu_monitor_timer.stop()

    def _setup_selection_tools(self):
        selection_widget = QtWidgets.QWidget()
        selection_layout = QtWidgets.QVBoxLayout(selection_widget)
        selection_layout.setContentsMargins(0, 0, 0, 0)
        selection_layout.setSpacing(0)

        box_row1 = QtWidgets.QHBoxLayout()
        box_row1.setContentsMargins(0, 0, 0, 0)
        box_row1.setSpacing(1)

        self.box_button = self.create_tool_button(svg = "select.svg", checkable=True)
        self.box_button.setToolTip(self.settings_page.tooltip_manager.get("box_button"))
        self.box_button.clicked.connect(self.toggle_box_tool)
        self.tool_buttons['box'] = self.box_button

        self.delete_button = self.create_tool_button(svg = "trash_line.svg", checkable=False)
        self.delete_button.setToolTip(self.settings_page.tooltip_manager.get("delete_button"))

        self.clear_rectangles_button = self.create_tool_button(svg = "clear-outlined.svg")
        self.clear_rectangles_button.setToolTip(self.settings_page.tooltip_manager.get("clear_rectangles"))

        self.toggle_shape_button = self.create_tool_button(svg = "shape-outline.svg", checkable=False)
        self.toggle_shape_button.setToolTip(
            self.tr("Toggle: seleziona una casella di testo per passare tra Rettangolo ed Ellisse")
        )
        self.toggle_shape_button.setEnabled(False)

        self.draw_blklist_blks = self.create_tool_button(svg="gridicons--create.svg")
        self.draw_blklist_blks.setToolTip(self.settings_page.tooltip_manager.get("draw_blklist_blks"))

        self.pan_button = self.create_tool_button(svg = "pan_tool.svg", checkable = True)
        self.pan_button.setToolTip(self.settings_page.tooltip_manager.get("pan_button"))
        self.pan_button.clicked.connect(self.toggle_pan_tool)
        self.tool_buttons['pan'] = self.pan_button

        # Pulsante per commutare modalità poligono/rettangolo per inpainting
        self.polygon_inpaint_button = self.create_tool_button(
            svg="square-pentagon-outline.svg", checkable=True
        )
        self.polygon_inpaint_button.setToolTip(
            self.tr("Commuta: seleziona una casella di testo per passare tra Rettangolo e Poligono")
        )
        self.polygon_inpaint_button.setFixedSize(30, 30)
        self.polygon_inpaint_button.setVisible(True)
        self.polygon_inpaint_button.setEnabled(False)
        self.polygon_inpaint_button.setChecked(False)

        # Selezione multipla: seleziona tutte le caselle di testo rilevate,
        # come se si facesse CTRL+click su ognuna.
        self.select_all_boxes_button = self.create_tool_button(svg="check.svg")
        self.select_all_boxes_button.setToolTip(
            self.tr("Seleziona tutte le caselle di testo rilevate (come CTRL+click)")
        )
        self.select_all_boxes_button.clicked.connect(self._on_select_all_boxes_clicked)

        box_row1.addWidget(self.box_button)
        box_row1.addWidget(self.pan_button)
        box_row1.addWidget(self.delete_button)
        box_row1.addWidget(self.clear_rectangles_button)
        box_row1.addWidget(self.draw_blklist_blks)
        box_row1.addWidget(self.toggle_shape_button)
        box_row1.addWidget(self.polygon_inpaint_button)
        box_row1.addWidget(self.select_all_boxes_button)
        box_row1.addStretch()
        selection_layout.addLayout(box_row1)

        return selection_widget

    def _setup_box_size_tools(self):
        box_widget = QtWidgets.QWidget()
        box_tools_lay = QtWidgets.QVBoxLayout(box_widget)
        box_tools_lay.setContentsMargins(0, 0, 0, 0)
        box_tools_lay.setSpacing(0)

        box_row2 = QtWidgets.QHBoxLayout()
        box_row2.setContentsMargins(0, 0, 0, 0)
        box_row2.setSpacing(1)

        self.change_all_blocks_size_dec = self.create_tool_button(svg="minus_line.svg")
        self.change_all_blocks_size_dec.setToolTip(self.settings_page.tooltip_manager.get("change_all_blocks_size_dec"))
        
        self.change_all_blocks_size_diff = MLineEdit()
        self.change_all_blocks_size_diff.setFixedWidth(30)
        self.change_all_blocks_size_diff.setText("3")
        self.change_all_blocks_size_diff.setValidator(QIntValidator())
        self.change_all_blocks_size_diff.setAlignment(QtCore.Qt.AlignCenter)
        
        self.change_all_blocks_size_inc = self.create_tool_button(svg="add_line.svg")
        self.change_all_blocks_size_inc.setToolTip(self.settings_page.tooltip_manager.get("change_all_blocks_size_inc"))

        self.set_all_button = MPushButton(self.tr("Set for all"))
        self.set_all_button.setToolTip(self.settings_page.tooltip_manager.get("set_all_button"))

        box_row2.addWidget(self.change_all_blocks_size_dec)
        box_row2.addWidget(self.change_all_blocks_size_diff)
        box_row2.addWidget(self.change_all_blocks_size_inc)
        box_row2.addWidget(self.set_all_button)
        box_row2.addStretch()
        
        box_tools_lay.addLayout(box_row2)
        return box_widget

    def _setup_gvb_tools(self):
        gvb_widget = QtWidgets.QWidget()
        gvb_tools_lay = QtWidgets.QHBoxLayout(gvb_widget)
        gvb_tools_lay.setContentsMargins(0, 0, 0, 0)
        gvb_tools_lay.setSpacing(4)
        gvb_tools_lay.addWidget(self.gvb_region_button)
        gvb_tools_lay.addWidget(self.gvb_apply_region_button)
        gvb_tools_lay.addWidget(self.prompt_side_button)
        gvb_tools_lay.addWidget(self.gvb_simple_side_button)
        gvb_tools_lay.addStretch()
        return gvb_widget

    def _setup_inpainting_tools(self):
        inp_widget = QtWidgets.QWidget()
        inp_tools_lay = QtWidgets.QVBoxLayout(inp_widget)
        inp_tools_lay.setContentsMargins(0, 0, 0, 0)
        inp_tools_lay.setSpacing(2)
        
        row1 = QtWidgets.QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(1)
        
        self.brush_button = self.create_tool_button(svg = "brush-fill.svg", checkable=True)
        self.brush_button.setToolTip(self.settings_page.tooltip_manager.get("brush_button"))
        self.brush_button.clicked.connect(self.toggle_brush_tool)
        self.tool_buttons['brush'] = self.brush_button

        self.eraser_button = self.create_tool_button(svg = "eraser_fill.svg", checkable=True)
        self.eraser_button.setToolTip(self.settings_page.tooltip_manager.get("eraser_button"))
        self.eraser_button.clicked.connect(self.toggle_eraser_tool)
        self.tool_buttons['eraser'] = self.eraser_button

        self.clear_brush_strokes_button = self.create_tool_button(svg = "clear-outlined.svg")
        self.clear_brush_strokes_button.setToolTip(self.settings_page.tooltip_manager.get("clear_brush_strokes"))
        
        row1.addWidget(self.brush_button)
        row1.addWidget(self.eraser_button)
        row1.addWidget(self.clear_brush_strokes_button)

        size_label = QtWidgets.QLabel(self.tr("Dim Inpaint:"))
        self.brush_eraser_spinbox = MSpinBox().small()
        self.brush_eraser_spinbox.setMinimum(1)
        self.brush_eraser_spinbox.setMaximum(100)
        self.brush_eraser_spinbox.setFixedWidth(60)
        self.brush_eraser_spinbox.valueChanged.connect(self.set_brush_eraser_size)
        self.brush_eraser_spinbox.setValue(20)
        row1.addSpacing(6)
        row1.addWidget(size_label)
        row1.addWidget(self.brush_eraser_spinbox)
        row1.addStretch()
        
        inp_tools_lay.addLayout(row1)
        
        # Inpainter models components (required by controller)
        self.inpainter_model_dropdown = MComboBox()
        self.refresh_models_button = self.create_tool_button(svg="refresh.svg")
        self.refresh_models_button.setVisible(False)
        
        return inp_widget

    def _setup_polygon_tools(self):
        polygon_widget = QtWidgets.QWidget()
        polygon_tools_lay = QtWidgets.QVBoxLayout(polygon_widget)
        polygon_tools_lay.setContentsMargins(0, 0, 0, 0)
        polygon_tools_lay.setSpacing(2)

        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(1)

        self.polygon_add_button = MPushButton(self.tr("+"))
        self.polygon_add_button.setMinimumWidth(40)
        self.polygon_add_button.clicked.connect(self._on_polygon_add_clicked)
        self.polygon_add_button.setToolTip(self.tr("Aggiungi nuovo vertice al poligono selezionato"))

        self.polygon_delete_button = MPushButton(self.tr("Canc"))
        self.polygon_delete_button.setMinimumWidth(40)
        self.polygon_delete_button.clicked.connect(self._on_polygon_delete_clicked)
        self.polygon_delete_button.setToolTip(self.tr("Elimina il vertice selezionato del poligono"))

        row.addWidget(self.polygon_add_button)
        row.addWidget(self.polygon_delete_button)
        row.addStretch()

        polygon_tools_lay.addLayout(row)

        return polygon_widget

    def _setup_painting_tools(self):
        paint_widget = QtWidgets.QWidget()
        paint_tools_lay = QtWidgets.QVBoxLayout(paint_widget)
        paint_tools_lay.setContentsMargins(0, 0, 0, 0)
        paint_tools_lay.setSpacing(2)
        
        row1 = QtWidgets.QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(1)
        
        self.pen_button = self.create_tool_button(svg = "pen-line.svg", checkable=True)
        self.pen_button.setToolTip(self.settings_page.tooltip_manager.get("pen_button"))
        self.pen_button.clicked.connect(self.toggle_pen_tool)
        self.tool_buttons['pen'] = self.pen_button

        self.bucket_button = self.create_tool_button(svg = "paint-bucket.svg", checkable=True)
        self.bucket_button.setToolTip(self.settings_page.tooltip_manager.get("bucket_button"))
        self.bucket_button.clicked.connect(self.toggle_bucket_tool)
        self.tool_buttons['bucket'] = self.bucket_button

        from app.ui.widgets.color_button import MColorToolButton
        self.painting_color_button = MColorToolButton(self.tr("Colore Penna/Secchiello"))
        self.painting_color_button.set_color(QtGui.QColor(0, 0, 0))
        self.painting_color_button.colorChanged.connect(self._on_painting_color_changed)
        
        row1.addWidget(self.pen_button)
        row1.addWidget(self.bucket_button)
        row1.addWidget(self.painting_color_button)

        pen_size_label = QtWidgets.QLabel(self.tr("Dim Penna:"))
        self.pen_size_spinbox = MSpinBox().small()
        self.pen_size_spinbox.setMinimum(1)
        self.pen_size_spinbox.setMaximum(50)
        self.pen_size_spinbox.setFixedWidth(60)
        self.pen_size_spinbox.valueChanged.connect(self._on_pen_size_changed)
        self.pen_size_spinbox.setValue(5)

        tol_label = QtWidgets.QLabel(self.tr("Tol Secchiello:"))
        self.bucket_tolerance_spinbox = MSpinBox().small()
        self.bucket_tolerance_spinbox.setMinimum(0)
        self.bucket_tolerance_spinbox.setMaximum(100)
        self.bucket_tolerance_spinbox.setFixedWidth(60)
        self.bucket_tolerance_spinbox.valueChanged.connect(self._on_bucket_tolerance_changed)
        self.bucket_tolerance_spinbox.setValue(32)

        row1.addSpacing(6)
        row1.addWidget(pen_size_label)
        row1.addWidget(self.pen_size_spinbox)
        row1.addSpacing(6)
        row1.addWidget(tol_label)
        row1.addWidget(self.bucket_tolerance_spinbox)
        row1.addStretch()
        
        paint_tools_lay.addLayout(row1)

        return paint_widget
        
        # Inpainter models dropdown (nascosto o usato in background)
        self.inpainter_model_dropdown = MComboBox()
        self.inpainter_model_dropdown.setToolTip(self.settings_page.tooltip_manager.get("inpainter_model"))
        self.inpainter_model_dropdown.currentIndexChanged.connect(self._on_inpainter_model_changed)
        self.refresh_models_button = self.create_tool_button(svg="refresh.svg")
        self.refresh_models_button.setVisible(False)
        
        return inp_widget

    def _setup_opacity_controls(self):
        opacity_widget = QtWidgets.QWidget()
        opacity_layout = QtWidgets.QHBoxLayout(opacity_widget)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        opacity_layout.setSpacing(1)
        
        opacity_label = QtWidgets.QLabel(self.tr("Opacità:"))
        self.opacity_slider = MSlider()
        self.opacity_slider.setMinimum(1)
        self.opacity_slider.setMaximum(100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setToolTip(self.settings_page.tooltip_manager.get("opacity_slider"))
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        self.opacity_slider.setEnabled(False)
        
        self.opacity_value_label = QtWidgets.QLabel("100%")
        self.opacity_value_label.setMinimumWidth(35)
        
        opacity_layout.addWidget(opacity_label)
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_value_label)
        return opacity_widget

    def _setup_canvas_tools(self):
        canvas_tools_widget = QtWidgets.QWidget()
        canvas_tools_lay = QtWidgets.QVBoxLayout(canvas_tools_widget)
        canvas_tools_lay.setContentsMargins(0, 0, 0, 0)
        canvas_tools_lay.setSpacing(1)
        top_row = QtWidgets.QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(1)
        bottom_row = QtWidgets.QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(1)
        
        self.svg_button = self.create_tool_button(svg="ion--image-outline.svg", checkable=True)
        self.svg_button.setToolTip(self.settings_page.tooltip_manager.get("svg_button"))
        self.svg_button.clicked.connect(self.toggle_svg_tool)
        self.tool_buttons['svg'] = self.svg_button
        
        self.svg_delete_button = self.create_tool_button(svg="delete.svg")
        self.svg_delete_button.setToolTip(self.settings_page.tooltip_manager.get("delete_shape"))
        self.svg_delete_button.clicked.connect(self._on_delete_shape_clicked)
        
        from app.ui.widgets.color_button import MColorToolButton
        self.border_color_button = MColorToolButton(self.tr("Colore bordo"))
        self.border_color_button.set_color(QtGui.QColor(0, 0, 0))
        self.border_color_button.colorChanged.connect(self._on_svg_border_color_changed)
        
        self.svg_border_width_selector = MComboBox().small()
        self.svg_border_width_selector.addItems([str(i) for i in range(0, 11)])
        self.svg_border_width_selector.setEditable(True)
        self.svg_border_width_selector.setCurrentText("2")
        self.svg_border_width_selector.setToolTip(self.settings_page.tooltip_manager.get("border_width_selector"))
        self.svg_border_width_selector.setFixedWidth(46)
        self.svg_border_width_selector.currentTextChanged.connect(self._on_svg_border_width_changed)
        
        self.fill_color_button = MColorToolButton(self.tr("Colore riempimento"))
        self.fill_color_button.set_color(QtGui.QColor(255, 255, 255, 180))
        self.fill_color_button.colorChanged.connect(self._on_svg_fill_color_changed)
        
        self.reset_styles_button = self.create_tool_button(svg="undo.svg")
        self.reset_styles_button.setToolTip(self.settings_page.tooltip_manager.get("reset_styles"))
        self.reset_styles_button.clicked.connect(self._on_reset_styles_clicked)
        
        self.save_svg_button = self.create_tool_button(svg="save.svg")
        self.save_svg_button.setToolTip(self.settings_page.tooltip_manager.get("save_svg"))
        self.save_svg_button.clicked.connect(self._on_save_svg_clicked)
        
        self.width_input = MLineEdit().small()
        self.width_input.setFixedWidth(44)
        self.width_input.setPlaceholderText("W")
        self.width_input.setValidator(QDoubleValidator(0.1, 10000.0, 1))
        self.width_input.editingFinished.connect(self._on_width_input_changed)
        
        self.height_input = MLineEdit().small()
        self.height_input.setFixedWidth(44)
        self.height_input.setPlaceholderText("H")
        self.height_input.setValidator(QDoubleValidator(0.1, 10000.0, 1))
        self.height_input.editingFinished.connect(self._on_height_input_changed)
        
        self.bring_front_button = self.create_tool_button(svg="bring_to_front.svg")
        self.bring_front_button.setToolTip(self.settings_page.tooltip_manager.get("bring_front"))
        self.bring_front_button.clicked.connect(self._on_bring_to_front_clicked)
        
        self.send_back_button = self.create_tool_button(svg="send_to_back.svg")
        self.send_back_button.setToolTip(self.settings_page.tooltip_manager.get("send_back"))
        self.send_back_button.clicked.connect(self._on_send_to_back_clicked)
        
        top_row.addWidget(self.svg_button)
        top_row.addWidget(self.fill_color_button)
        top_row.addWidget(self.border_color_button)
        top_row.addWidget(self.svg_border_width_selector)
        top_row.addWidget(self.reset_styles_button)
        top_row.addWidget(QtWidgets.QLabel("W:"))
        top_row.addWidget(self.width_input)
        top_row.addWidget(QtWidgets.QLabel("H:"))
        top_row.addWidget(self.height_input)
        top_row.addStretch()

        bottom_row.addWidget(self.send_back_button)
        bottom_row.addWidget(self.bring_front_button)
        bottom_row.addWidget(self.save_svg_button)
        bottom_row.addWidget(self.svg_delete_button)
        bottom_row.addStretch()

        canvas_tools_lay.addLayout(top_row)
        canvas_tools_lay.addLayout(bottom_row)
        return canvas_tools_widget

    def _setup_image_navigation_tools(self):
        nav_widget = QtWidgets.QWidget()
        nav_lay = QtWidgets.QHBoxLayout(nav_widget)
        nav_lay.setContentsMargins(0, 0, 0, 0)
        nav_lay.setSpacing(4)

        # Pulsante Adatta Larghezza
        self.fit_width_button = self.create_tool_button(svg="fit-width-max.svg")
        self.fit_width_button.setToolTip(self.tr("Adatta immagine alla massima larghezza possibile"))
        self.fit_width_button.large().icon_only()
        self.fit_width_button.clicked.connect(self.image_viewer.fit_to_width)

        # Pulsante Adatta Altezza
        self.fit_height_button = self.create_tool_button(svg="fit-height-max.svg")
        self.fit_height_button.setToolTip(self.tr("Adatta immagine alla massima altezza possibile"))
        self.fit_height_button.large().icon_only()
        self.fit_height_button.clicked.connect(self.image_viewer.fit_to_height)

        # Pulsante Scorri Su
        self.scroll_up_button = self.create_tool_button(svg="up_fill.svg")
        self.scroll_up_button.setToolTip(self.tr("Scorri immagine su"))
        self.scroll_up_button.large().icon_only()
        self.scroll_up_button.clicked.connect(self.image_viewer.scroll_up)

        # Pulsante Scorri Giù
        self.scroll_down_button = self.create_tool_button(svg="down_fill.svg")
        self.scroll_down_button.setToolTip(self.tr("Scorri immagine giù"))
        self.scroll_down_button.large().icon_only()
        self.scroll_down_button.clicked.connect(self.image_viewer.scroll_down)

        nav_lay.addWidget(self.fit_width_button)
        nav_lay.addWidget(self.fit_height_button)
        nav_lay.addWidget(self.scroll_down_button)
        nav_lay.addWidget(self.scroll_up_button)
        nav_lay.addStretch()
        
        return nav_widget

    def _setup_right_panel(self):
        right_layout = QtWidgets.QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        sections_widget = SidebarSectionsWidget(self._ui_layout_settings, self)
        for section_key, section_widget in self._build_right_panel_sections():
            sections_widget.add_section(section_key, section_widget)
        sections_widget.restore_order()
        self._sidebar_sections_widget = sections_widget
        right_layout.addWidget(sections_widget)

        # Wrappa il contenuto in un container inserito in una QScrollArea
        # verticale, così a risoluzioni piccole (es. 1280x720) l'utente può
        # scorrere per raggiungere tutti i controlli.
        right_widget = QtWidgets.QWidget()
        right_widget.setLayout(right_layout)

        scroll_area = QScrollArea()
        scroll_area.setObjectName("rightPanelScrollArea")
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(right_widget)
        scroll_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setFrameShape(QScrollArea.NoFrame)
        scroll_area.setMinimumWidth(240)
        # Disabilita l'horizontal scroll per non rompere il layout fluido
        scroll_area.setSizePolicy(
            QtWidgets.QSizePolicy.Preferred,
            QtWidgets.QSizePolicy.Expanding)
        self.right_panel_scroll_area = scroll_area
        QtCore.QTimer.singleShot(0, self._update_log_section_width)
        return scroll_area

    def _build_right_panel_sections(self):
        input_layout = self._setup_text_input_area()
        text_widget = QtWidgets.QWidget()
        text_lay = QtWidgets.QVBoxLayout(text_widget)
        text_lay.setContentsMargins(0, 0, 0, 0)
        text_lay.setSpacing(4)
        text_lay.addLayout(input_layout)

        text_render_layout = self._setup_text_render_settings()
        font_widget = QtWidgets.QWidget()
        font_lay = QtWidgets.QVBoxLayout(font_widget)
        font_lay.setContentsMargins(0, 0, 0, 0)
        font_lay.setSpacing(4)
        font_lay.addLayout(text_render_layout)

        sections = [
            ("text", self._create_sidebar_section(self.tr("Testo"), text_widget, True)),
            ("font", self._create_sidebar_section(self.tr("Carattere"), font_widget, True)),
        ]
        sections.extend(self._build_tool_sections())
        return sections

    def _assemble_main_layout(self, content_widget, header_layout, left_widget, central_widget, right_widget):
        splitter = QtWidgets.QSplitter()
        splitter.addWidget(left_widget)
        splitter.addWidget(central_widget)
        self.main_splitter = splitter

        self._ensure_right_dock()
        self.right_dock.setWidget(right_widget)

        # Rapporti iniziali all'avvio:
        # - colonna file sinistra circa al 70% della larghezza precedente
        # - pannello destro circa al 130% della larghezza precedente
        # - area centrale invariata
        splitter.setStretchFactor(0, 28)
        splitter.setStretchFactor(1, 80)

        content_layout = QtWidgets.QVBoxLayout()
        # header_layout può essere un QLayout legacy o un QWidget (QScrollArea)
        # se la versione responsive è attiva. Supportiamo entrambi per
        # compatibilità con eventuali subclass.
        if isinstance(header_layout, QtWidgets.QLayout):
            content_layout.addLayout(header_layout)
            header_factor = header_layout
        else:
            content_layout.addWidget(header_layout)
            header_factor = header_layout
        content_layout.addWidget(self.progress_bar)
        content_layout.addWidget(splitter)

        content_layout.setStretchFactor(header_factor, 0)
        content_layout.setStretchFactor(splitter, 1)

        content_widget.setLayout(content_layout)

    def _ensure_right_dock(self):
        if hasattr(self, "right_dock") and self.right_dock is not None:
            return
        self.right_dock = QtWidgets.QDockWidget(self.tr("Barra Laterale"), self)
        self.right_dock.setObjectName("RightSideDock")
        self.right_dock.setAllowedAreas(
            QtCore.Qt.DockWidgetArea.RightDockWidgetArea
            | QtCore.Qt.DockWidgetArea.LeftDockWidgetArea
        )
        self.right_dock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self._right_dock_title_bar = SidebarDockTitleBar(self.tr("Barra Laterale"), self.right_dock)
        self.right_dock.setTitleBarWidget(self._right_dock_title_bar)
        self.right_dock.topLevelChanged.connect(
            self._right_dock_title_bar.set_dock_floating
        )
        self._right_dock_title_bar.set_dock_floating(self.right_dock.isFloating())
        self.addDockWidget(QtCore.Qt.DockWidgetArea.RightDockWidgetArea, self.right_dock)

    def _toggle_right_dock_floating(self):
        if not hasattr(self, "right_dock") or self.right_dock is None:
            return
        self.right_dock.setFloating(not self.right_dock.isFloating())
