"""Dialog Scheda fumetto: ComicInfo.xml editabile + ricerca web."""

from PySide6 import QtWidgets, QtCore
from PySide6.QtCore import QCoreApplication

from modules.metadata.comic_info import FIELDS, diff_fields, normalize
from modules.metadata.providers import merge_candidates, search_all


class ComicInfoDialog(QtWidgets.QDialog):
    def __init__(self, base_info: dict | None = None,
                 existing_info: dict | None = None, parent=None):
        super().__init__(parent)
        self._base = normalize(base_info)
        self._existing = normalize(existing_info) if existing_info else None
        self._results: list[dict] = []
        self._picked: list[dict] = []
        self.setWindowTitle(QCoreApplication.translate("ComicInfoDialog", "Scheda fumetto"))
        self.setModal(True)
        self.resize(740, 760)
        self._build()
        self._fill(self._base)

    # --- UI --- #
    def _tr(self, text: str) -> str:
        return QCoreApplication.translate("ComicInfoDialog", text)

    def _build(self):
        layout = QtWidgets.QVBoxLayout(self)

        search_row = QtWidgets.QHBoxLayout()
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText(self._tr("Cerca titolo..."))
        self.mdx_check = QtWidgets.QCheckBox("MangaDex")
        self.mdx_check.setChecked(True)
        self.cb_check = QtWidgets.QCheckBox("ComicsBox")
        self.cb_check.setChecked(True)
        self.bdt_check = QtWidgets.QCheckBox("Bedetheque")
        self.bdt_check.setChecked(True)
        search_btn = QtWidgets.QPushButton(self._tr("Cerca"))
        search_btn.clicked.connect(self._on_search)
        self.search_btn = search_btn
        search_row.addWidget(self.search_edit, 1)
        search_row.addWidget(self.mdx_check)
        search_row.addWidget(self.cb_check)
        search_row.addWidget(self.bdt_check)
        search_row.addWidget(search_btn)
        layout.addLayout(search_row)

        self.search_progress = QtWidgets.QProgressBar()
        self.search_progress.setRange(0, 0)
        self.search_progress.setVisible(False)
        self.search_progress.setMaximumHeight(12)
        layout.addWidget(self.search_progress)

        self.results_list = QtWidgets.QListWidget()
        self.results_list.setMaximumHeight(150)
        self.results_list.setWordWrap(True)
        self.results_list.itemSelectionChanged.connect(self._on_pick)
        self.results_list.itemDoubleClicked.connect(lambda _item: self._on_pick())
        layout.addWidget(self.results_list)

        form = QtWidgets.QFormLayout()
        self.edits: dict[str, QtWidgets.QWidget] = {}
        for key in FIELDS:
            if key in ("Summary",):
                edit = QtWidgets.QPlainTextEdit()
                edit.setMinimumHeight(110)
                edit.setMaximumHeight(220)
            elif key in ("Manga", "LanguageISO"):
                edit = QtWidgets.QComboBox()
                if key == "Manga":
                    edit.addItems(["YesAndRightToLeft", "Yes", "No"])
                else:
                    edit.addItems(["it", "en", "ja", "fr", "es", "de"])
                edit.setEditable(True)
            else:
                edit = QtWidgets.QLineEdit()
            self.edits[key] = edit
        # Righe singole
        form.addRow("Series", self.edits["Series"])
        # Campi corti appaiati: Volume|Number, Year|PageCount
        form.addRow(self._pair_row("Volume", "Number"))
        form.addRow("Title", self.edits["Title"])
        form.addRow("Writer", self.edits["Writer"])
        form.addRow("Penciller", self.edits["Penciller"])
        form.addRow("CoverArtist", self.edits["CoverArtist"])
        form.addRow("Publisher", self.edits["Publisher"])
        form.addRow(self._pair_row("Year", "PageCount"))
        form.addRow("Genre", self.edits["Genre"])
        form.addRow("LanguageISO", self.edits["LanguageISO"])
        form.addRow("Summary", self.edits["Summary"])
        form.addRow("Manga", self.edits["Manga"])
        form.addRow("Translator", self.edits["Translator"])
        layout.addLayout(form)

        if self._existing:
            diff_btn = QtWidgets.QPushButton(
                self._tr("Confronta con esistente"))
            diff_btn.clicked.connect(self._show_diff)
            layout.addWidget(diff_btn)

        btns = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _pair_row(self, left_key: str, right_key: str) -> QtWidgets.QWidget:
        """Una riga con due campi corti affiancati (Volume|Number)."""
        row = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QtWidgets.QLabel(left_key))
        lay.addWidget(self.edits[left_key], 1)
        lay.addSpacing(12)
        lay.addWidget(QtWidgets.QLabel(right_key))
        lay.addWidget(self.edits[right_key], 1)
        return row

    @staticmethod
    def _candidate_label(cand: dict) -> str:
        """Etichetta lunga e chiara: albo vs serie, numero e titolo."""
        src = cand.get("source", "?")
        series = (cand.get("Series") or "?").strip()
        number = (cand.get("Number") or "").strip()
        title = (cand.get("Title") or "").strip()
        kind = "albo" if number else ("serie" if src in ("ComicsBox", "Bedetheque") else "manga")
        head = f"{series} #{number}" if number else series
        if title:
            head += f" — {title}"
        extras = " ".join(p for p in (
            (cand.get("Writer") or "").strip(),
            (cand.get("Publisher") or "").strip(),
            (cand.get("Year") or "").strip(),
        ) if p)
        label = f"[{src} · {kind}] {head}"
        if extras:
            label += f"  ({extras})"
        return label
    def _fill(self, info: dict):
        for key in FIELDS:
            edit = self.edits[key]
            val = (info or {}).get(key, "")
            if isinstance(edit, QtWidgets.QPlainTextEdit):
                edit.setPlainText(val)
            elif isinstance(edit, QtWidgets.QComboBox):
                idx = edit.findText(val)
                edit.setCurrentIndex(idx if idx >= 0 else -1)
                if idx < 0 and val:
                    edit.setCurrentText(val)
            else:
                edit.setText(val)
        if not self.search_edit.text() and info.get("Series"):
            self.search_edit.setText(info.get("Series", ""))

    def result(self) -> dict:
        out = {}
        for key in FIELDS:
            edit = self.edits[key]
            if isinstance(edit, QtWidgets.QPlainTextEdit):
                out[key] = edit.toPlainText().strip()
            elif isinstance(edit, QtWidgets.QComboBox):
                out[key] = edit.currentText().strip()
            else:
                out[key] = edit.text().strip()
        return normalize(out)

    def _on_search(self):
        query = self.search_edit.text().strip()
        if not query:
            return
        self.results_list.clear()
        self.search_progress.setVisible(True)
        self.search_btn.setEnabled(False)
        QtWidgets.QApplication.processEvents()
        try:
            self._results = search_all(
                query,
                use_mangadex=self.mdx_check.isChecked(),
                use_comicsbox=self.cb_check.isChecked(),
                use_bedetheque=self.bdt_check.isChecked(),
            )
        finally:
            self.search_progress.setVisible(False)
            self.search_btn.setEnabled(True)
        if not self._results:
            self.results_list.addItem(self._tr("Nessun risultato"))
            return
        for cand in self._results:
            label = self._candidate_label(cand)
            item = QtWidgets.QListWidgetItem(label)
            item.setData(QtCore.Qt.UserRole, cand)
            item.setToolTip(label)
            self.results_list.addItem(item)

    # Campi che identificano una scheda compilata (esclusi i default tecnici)
    _CONTENT_FIELDS = ("Series", "Volume", "Number", "Title", "Writer",
                       "Penciller", "CoverArtist", "Publisher", "Year",
                       "Genre", "PageCount", "Summary")
    _KEEP_FIELDS = ("LanguageISO", "Manga", "Translator")

    def _on_pick(self):
        items = self.results_list.selectedItems()
        if not items:
            return
        cand = items[0].data(QtCore.Qt.UserRole)
        if not isinstance(cand, dict):
            return
        self._picked = [cand]
        current = self.result()
        if any(current.get(k) for k in self._CONTENT_FIELDS):
            # La scheda contiene gia' un altro albo: sostituzione totale
            # o solo riempimento vuoti?
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle(self._tr("Sostituire scheda?"))
            box.setText(self._tr(
                "La scheda contiene già dei dati.\n"
                "Vuoi sostituirli con quelli di:\n{label}?").format(
                    label=self._candidate_label(cand)))
            replace_btn = box.addButton(
                self._tr("Sì, sostituisci tutto"),
                QtWidgets.QMessageBox.AcceptRole)
            fill_btn = box.addButton(
                self._tr("No, solo campi vuoti"),
                QtWidgets.QMessageBox.ActionRole)
            box.addButton(QtWidgets.QMessageBox.Cancel)
            box.exec()
            clicked = box.clickedButton()
            if clicked == replace_btn:
                fresh = {k: "" for k in FIELDS}
                for k in self._KEEP_FIELDS:
                    fresh[k] = current.get(k, "")
                current = normalize(fresh)
            elif clicked != fill_btn:
                return
        for key in FIELDS:
            val = (cand.get(key) or "").strip()
            if val:
                current[key] = val
        self._fill(current)

    def _show_diff(self):
        rows = diff_fields(self._existing or {}, self.result())
        dlg = QtWidgets.QDialog(self)
        dlg.setWindowTitle(self._tr("Vecchio / Nuovo"))
        dlg.resize(620, 440)
        layout = QtWidgets.QVBoxLayout(dlg)
        table = QtWidgets.QTableWidget(len(rows), 3)
        table.setHorizontalHeaderLabels(
            [self._tr("Campo"), self._tr("Vecchio"), self._tr("Nuovo")])
        table.horizontalHeader().setStretchLastSection(True)
        for i, (field, old, new, changed) in enumerate(rows):
            table.setItem(i, 0, QtWidgets.QTableWidgetItem(field))
            table.setItem(i, 1, QtWidgets.QTableWidgetItem(old))
            table.setItem(i, 2, QtWidgets.QTableWidgetItem(new))
            if changed:
                for c in range(3):
                    table.item(i, c).setBackground(QtCore.Qt.yellow)
        table.resizeColumnsToContents()
        layout.addWidget(table)
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok)
        btns.accepted.connect(dlg.accept)
        layout.addWidget(btns)
        dlg.exec()
