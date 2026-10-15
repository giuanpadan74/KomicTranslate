from PySide6 import QtCore, QtWidgets
from .header_toolbar_frames import make_bordered_frame
def _clear_layout(widget: QtWidgets.QWidget) -> None:
    layout = widget.layout()
    if layout is None:
        return

    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            continue
        child = item.widget()
        if child is not None:
            child.setParent(widget)

    dummy = QtWidgets.QWidget()
    dummy.setLayout(layout)
class HeaderToolbarLayoutApplier:
    def __init__(
        self,
        scroll_area: QtWidgets.QScrollArea,
        container: QtWidgets.QWidget,
        visible_main_buttons: list[QtWidgets.QAbstractButton],
        undo_tool_group: QtWidgets.QWidget,
        ocr_dropdown: QtWidgets.QWidget,
        translate_dropdown: QtWidgets.QWidget,
        inpainter_dropdown: QtWidgets.QWidget,
        original_button: QtWidgets.QWidget,
        detect_font_button: QtWidgets.QWidget,
        auto_center_button: QtWidgets.QWidget,
        batch_separator: QtWidgets.QWidget,
        detect_batch_button: QtWidgets.QWidget,
        translate_button: QtWidgets.QWidget,
        sbianchetta_button: QtWidgets.QWidget,
        markers_button: QtWidgets.QWidget,
        polygons_button: QtWidgets.QWidget,
        rect_boxes_button: QtWidgets.QWidget,
        toggle_text_boxes_button: QtWidgets.QWidget,
        cancel_batch_button: QtWidgets.QWidget,
        loading: QtWidgets.QWidget,
        mode_selector_group: QtWidgets.QWidget,
    ):
        self._scroll_area = scroll_area
        self._container = container
        self._visible_main_buttons = visible_main_buttons
        self._undo_tool_group = undo_tool_group
        self._ocr_dropdown = ocr_dropdown
        self._translate_dropdown = translate_dropdown
        self._inpainter_dropdown = inpainter_dropdown
        self._original_button = original_button
        self._detect_font_button = detect_font_button
        self._auto_center_button = auto_center_button
        self._batch_separator = batch_separator
        self._detect_batch_button = detect_batch_button
        self._translate_button = translate_button
        self._sbianchetta_button = sbianchetta_button
        self._markers_button = markers_button
        self._polygons_button = polygons_button
        self._rect_boxes_button = rect_boxes_button
        self._toggle_text_boxes_button = toggle_text_boxes_button
        self._cancel_batch_button = cancel_batch_button
        self._loading = loading
        self._mode_selector_group = mode_selector_group

    def apply_top(self) -> None:
        _clear_layout(self._container)
        header_layout = QtWidgets.QHBoxLayout()
        manual_frame = make_bordered_frame()
        manual_layout = QtWidgets.QHBoxLayout(manual_frame)
        manual_layout.setContentsMargins(6, 6, 6, 6)
        manual_layout.setSpacing(6)

        left_tools_widget = QtWidgets.QWidget()
        left_tools_layout = QtWidgets.QGridLayout(left_tools_widget)
        left_tools_layout.setContentsMargins(0, 0, 0, 0)
        left_tools_layout.setHorizontalSpacing(6)
        left_tools_layout.setVerticalSpacing(4)

        if len(self._visible_main_buttons) >= 6:
            left_tools_layout.addWidget(self._visible_main_buttons[0], 0, 0)
            left_tools_layout.addWidget(self._visible_main_buttons[1], 0, 1)
            left_tools_layout.addWidget(self._visible_main_buttons[2], 0, 2)
            left_tools_layout.addWidget(self._visible_main_buttons[3], 0, 3)
            left_tools_layout.addWidget(self._visible_main_buttons[4], 0, 4)
            left_tools_layout.addWidget(self._visible_main_buttons[5], 0, 5)

        left_tools_layout.addWidget(
            self._ocr_dropdown,
            1,
            1,
            alignment=QtCore.Qt.AlignmentFlag.AlignCenter,
        )
        left_tools_layout.addWidget(
            self._translate_dropdown,
            1,
            2,
            alignment=QtCore.Qt.AlignmentFlag.AlignCenter,
        )
        left_tools_layout.addWidget(
            self._inpainter_dropdown,
            1,
            4,
            alignment=QtCore.Qt.AlignmentFlag.AlignCenter,
        )

        manual_layout.addWidget(left_tools_widget, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        manual_layout.addWidget(self._undo_tool_group, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        manual_layout.addWidget(self._original_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        manual_layout.addWidget(self._detect_font_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        manual_layout.addWidget(self._auto_center_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(manual_frame, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        batch_frame = make_bordered_frame()
        batch_layout = QtWidgets.QHBoxLayout(batch_frame)
        batch_layout.setContentsMargins(6, 6, 6, 6)
        batch_layout.setSpacing(6)
        batch_layout.addWidget(self._detect_batch_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        batch_layout.addWidget(self._translate_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        batch_layout.addWidget(self._sbianchetta_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(batch_frame, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        header_layout.addWidget(self._markers_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(self._polygons_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(self._rect_boxes_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(self._toggle_text_boxes_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(self._cancel_batch_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self._batch_separator.setVisible(False)

        header_layout.addWidget(self._loading, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        header_layout.addStretch()
        header_layout.addWidget(self._mode_selector_group, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        self._container.setLayout(header_layout)

        self._scroll_area.setWidgetResizable(False)
        self._scroll_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._scroll_area.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

    def apply_sidebar(self) -> None:
        _clear_layout(self._container)
        root = QtWidgets.QVBoxLayout()
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        manual_frame = make_bordered_frame()
        manual_grid = QtWidgets.QGridLayout(manual_frame)
        manual_grid.setContentsMargins(6, 6, 6, 6)
        manual_grid.setHorizontalSpacing(6)
        manual_grid.setVerticalSpacing(6)
        for i in range(3):
            manual_grid.setColumnStretch(i, 1)

        if len(self._visible_main_buttons) >= 3:
            manual_grid.addWidget(self._visible_main_buttons[0], 0, 0)
            manual_grid.addWidget(self._visible_main_buttons[1], 0, 1)
            manual_grid.addWidget(self._visible_main_buttons[2], 0, 2)
        manual_grid.addWidget(self._undo_tool_group, 1, 0, alignment=QtCore.Qt.AlignmentFlag.AlignLeft)
        manual_grid.addWidget(self._ocr_dropdown, 1, 1, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        manual_grid.addWidget(self._translate_dropdown, 1, 2, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        if len(self._visible_main_buttons) >= 6:
            manual_grid.addWidget(self._visible_main_buttons[3], 2, 0)
            manual_grid.addWidget(self._visible_main_buttons[4], 2, 1)
            manual_grid.addWidget(self._visible_main_buttons[5], 2, 2)
        manual_grid.addWidget(self._original_button, 3, 0)
        manual_grid.addWidget(self._inpainter_dropdown, 3, 1, alignment=QtCore.Qt.AlignmentFlag.AlignCenter)
        manual_grid.addWidget(self._detect_font_button, 4, 0)
        manual_grid.addWidget(self._auto_center_button, 4, 1)
        batch_frame = make_bordered_frame()
        batch_grid = QtWidgets.QGridLayout(batch_frame)
        batch_grid.setContentsMargins(6, 6, 6, 6)
        batch_grid.setHorizontalSpacing(6)
        batch_grid.setVerticalSpacing(6)
        for i in range(3):
            batch_grid.setColumnStretch(i, 1)

        batch_grid.addWidget(self._detect_batch_button, 0, 0)
        batch_grid.addWidget(self._translate_button, 0, 1)
        batch_grid.addWidget(self._sbianchetta_button, 0, 2)

        self._batch_separator.setVisible(False)

        root.addWidget(manual_frame)
        root.addWidget(batch_frame)
        markers_row = QtWidgets.QWidget(); markers_grid = QtWidgets.QGridLayout(markers_row); markers_grid.setContentsMargins(0, 0, 0, 0); markers_grid.setHorizontalSpacing(4); markers_grid.setVerticalSpacing(4); markers_grid.setColumnStretch(0, 1); markers_grid.setColumnStretch(1, 1); markers_grid.setColumnStretch(2, 1)
        markers_grid.addWidget(self._markers_button, 0, 0)
        markers_grid.addWidget(self._polygons_button, 0, 1)
        markers_grid.addWidget(self._rect_boxes_button, 0, 2)
        markers_grid.addWidget(self._toggle_text_boxes_button, 1, 0, 1, 3)
        root.addWidget(markers_row)
        if self._cancel_batch_button.isVisible():
            root.addWidget(self._cancel_batch_button)

        self._container.setLayout(root)

        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self._scroll_area.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
