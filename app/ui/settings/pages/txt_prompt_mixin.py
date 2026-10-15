"""Mixin con l'editor del prompt di traduzione (usato dalla modalita' browser).

Il prompt e' stato spostato qui dalla vecchia pagina "LLMs": con la
rimozione dello strato LLM la pagina non ha piu' senso, ma il prompt e'
essenziale perche' Gemini e Dola passano da qui il loro prompt.
"""
import os
import json

from PySide6 import QtWidgets

from ...dayu_widgets.label import MLabel
from ...dayu_widgets.text_edit import MTextEdit
from ...dayu_widgets.push_button import MPushButton
from ...dayu_widgets.message import MMessage


TXT_PROMPT_DEFAULT = """You are a professional translator specialized in natural language.

Target language is {t_lang}. Use that.

You are translating OCR-extracted comic text. The input may contain errors, typos, or incomplete sentences. You must interpret and correct them when needed to produce a natural and fluent language translation.

You MUST return ONLY a valid JSON object.

- No explanations
- No extra text
- No markdown
- No code blocks
- No comments

If anything other than JSON is included, the response is INVALID.

You MUST use these keys:

"block_1"
"block_2"
"block_3"
etc.

All keys MUST be present.

Even if a block is empty, include it with this string "...".

- Translate into natural, fluent language
- Preserve tone, slang, and intent
- Adapt idioms naturally
- Fix OCR mistakes when necessary
- If already target language → return unchanged
- NEVER use Korean or Japanese pronouns (당신, 그녀, 그, etc.)
- Use SINGLE QUOTES for quoted speech inside translations (e.g., '他说 "你好"') or escape double quotes with backslash (\\")

- Do NOT rename keys
- Do NOT change structure
- Do NOT omit keys
- Do NOT add keys
- Do NOT output arrays
- Do NOT output anything outside the JSON object

Before responding, verify:

1. Is the output valid JSON?
2. Are all keys present?
3. Is there any text outside JSON? → If YES, REMOVE it

Only return the JSON object."""

# Nome interno (stabile, non tradotto) del preset di fabbrica.
# Non e' un file a parte: e' solo la voce fissa del combo che
# restituisce TXT_PROMPT_DEFAULT e non si puo' sovrascrivere/eliminare.
DEFAULT_PRESET_NAME = "Default"


class TxtPromptMixin:
    """UI e persistenza del prompt usato dalla modalita' browser.

    Nota: la chiave di persistenza resta 'txt_prompt' e la costante
    TXT_PROMPT_DEFAULT per compatibilita' con i config gia' salvati:
    rinominarle farebbe perdere il prompt personalizzato agli utenti.
    I preset nominati vivono in 'txt_prompt_presets' (dict nome->testo)
    e il preset attivo in 'txt_prompt_active'.
    """

    def _create_txt_prompt_section(self) -> QtWidgets.QWidget:
        container = QtWidgets.QWidget()
        container_layout = QtWidgets.QVBoxLayout(container)
        container_layout.setContentsMargins(0, 10, 0, 10)

        title_label = MLabel(self.tr("Prompt di traduzione:"))
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        container_layout.addWidget(title_label)

        desc_label = MLabel(self.tr("Prompt usato dalla traduzione via browser (Gemini, Dola). Salva i tuoi preset e ricaricali dal menu."))
        desc_label.setStyleSheet("color: gray; font-size: 11px;")
        desc_label.setWordWrap(True)
        container_layout.addWidget(desc_label)

        # --- Riga preset: combo per ricaricare + elimina ---
        preset_row = QtWidgets.QHBoxLayout()
        preset_label = MLabel(self.tr("Preset:"))
        self.txt_preset_combo = QtWidgets.QComboBox()
        self.txt_preset_combo.setMinimumWidth(200)
        self.txt_preset_combo.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.txt_preset_combo.setToolTip(
            self.tr("Seleziona un preset salvato per caricarlo nell'editor."))
        self.txt_preset_combo.currentTextChanged.connect(self._on_txt_preset_changed)
        preset_row.addWidget(preset_label)
        preset_row.addWidget(self.txt_preset_combo, 1)
        container_layout.addLayout(preset_row)

        self.txt_prompt_edit = MTextEdit()
        self.txt_prompt_edit.setMinimumHeight(200)
        self.txt_prompt_edit.textChanged.connect(self._on_txt_prompt_changed)
        container_layout.addWidget(self.txt_prompt_edit)

        # --- Riga stato: conteggio + validazione segnaposto ---
        self.txt_prompt_status = MLabel("")
        self.txt_prompt_status.setStyleSheet("color: gray; font-size: 11px;")
        self.txt_prompt_status.setWordWrap(True)
        container_layout.addWidget(self.txt_prompt_status)

        btn_layout = QtWidgets.QHBoxLayout()

        # "Salva con nome" PRIMA di "Salva", come richiesto.
        self.btn_save_as_txt = MPushButton(self.tr("Salva con nome"))
        self.btn_save_as_txt.setProperty("class", "default")
        self.btn_save_as_txt.setToolTip(
            self.tr("Salva il testo corrente come nuovo preset con un nome a scelta."))
        self.btn_save_as_txt.clicked.connect(self._on_save_as_txt_prompt)

        self.btn_save_txt = MPushButton(self.tr("Salva"))
        self.btn_save_txt.setProperty("class", "primary")
        self.btn_save_txt.setEnabled(False)
        self.btn_save_txt.setToolTip(
            self.tr("Sovrascrivi il preset selezionato con il testo corrente."))
        self.btn_save_txt.clicked.connect(self._on_save_txt_prompt)

        self.btn_delete_txt = MPushButton(self.tr("Elimina"))
        self.btn_delete_txt.setProperty("class", "danger")
        self.btn_delete_txt.setToolTip(
            self.tr("Elimina il preset selezionato (il Default di fabbrica non si puo' eliminare)."))
        self.btn_delete_txt.clicked.connect(self._on_delete_txt_preset)

        btn_layout.addWidget(self.btn_save_as_txt)
        btn_layout.addWidget(self.btn_save_txt)
        btn_layout.addWidget(self.btn_delete_txt)
        btn_layout.addStretch()

        container_layout.addLayout(btn_layout)

        self._loading_preset = False
        self._load_txt_prompt()

        return container

    # ------------------------------------------------------------------
    # Persistenza
    # ------------------------------------------------------------------
    def _prompts_file(self) -> str:
        # pages/ -> settings -> ui -> app -> root : servono 4 livelli.
        # (Il vecchio codice ne usava 3 e puntava ad app/config, inesistente:
        # il salvataggio falliva in silenzio.)
        return os.path.normpath(os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "..", "..", "..", "..", "config", "prompts.json"))

    def _get_presets(self) -> dict:
        if hasattr(self, 'saved_prompts'):
            presets = self.saved_prompts.get('txt_prompt_presets')
            if isinstance(presets, dict):
                return dict(presets)
        return {}

    def _get_active_preset_name(self) -> str:
        if hasattr(self, 'saved_prompts'):
            name = self.saved_prompts.get('txt_prompt_active')
            if isinstance(name, str) and name:
                return name
        return DEFAULT_PRESET_NAME

    def _preset_names_sorted(self) -> list:
        """Default sempre per primo, poi gli utenti in ordine alfabetico."""
        names = [n for n in self._get_presets() if n != DEFAULT_PRESET_NAME]
        return [DEFAULT_PRESET_NAME] + sorted(names, key=str.lower)

    def _save_all_txt_to_config(self, active_name: str, active_text: str, presets: dict):
        # Aggiorna prima lo stato in memoria (la UI resta coerente anche se
        # il disco fallisce), poi prova a persistere su prompts.json.
        if hasattr(self, 'saved_prompts'):
            self.saved_prompts['txt_prompt'] = active_text
            self.saved_prompts['txt_prompt_presets'] = dict(presets)
            self.saved_prompts['txt_prompt_active'] = active_name
        try:
            prompts_file = self._prompts_file()
            os.makedirs(os.path.dirname(prompts_file), exist_ok=True)
            existing_prompts = {}
            if os.path.exists(prompts_file):
                try:
                    with open(prompts_file, "r", encoding="utf-8") as f:
                        existing_prompts = json.load(f)
                except Exception:
                    existing_prompts = {}
            existing_prompts['txt_prompt'] = active_text
            existing_prompts['txt_prompt_presets'] = presets
            existing_prompts['txt_prompt_active'] = active_name
            with open(prompts_file, "w", encoding="utf-8") as f:
                json.dump(existing_prompts, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"Errore nel salvare il prompt: {str(e)}")

    def _refresh_preset_combo(self, select: str = None):
        combo = self.txt_preset_combo
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(self._preset_names_sorted())
        target = select or self._get_active_preset_name()
        idx = combo.findText(target)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Caricamento
    # ------------------------------------------------------------------
    def _load_txt_prompt(self):
        """Carica il preset attivo (migra il vecchio txt_prompt singolo)."""
        if hasattr(self, 'saved_prompts'):
            # Migrazione: chi aveva solo 'txt_prompt' personalizzato lo
            # ritrova come preset attivo senza perdere nulla.
            presets = self._get_presets()
            active = self.saved_prompts.get('txt_prompt_active')
            legacy = self.saved_prompts.get('txt_prompt')
            if (not active) and legacy:
                # legacy == default o vuoto -> resta sul Default
                if legacy != TXT_PROMPT_DEFAULT:
                    presets.setdefault(self.tr("Il mio prompt"), legacy)
                    self.saved_prompts['txt_prompt_presets'] = presets
                    self.saved_prompts['txt_prompt_active'] = self.tr("Il mio prompt")
            # Se l'attivo punta a un preset esistente, usa quello;
            # altrimenti usa txt_prompt (retrocompatibilita'), poi il default.
            active = self._get_active_preset_name()
            if active != DEFAULT_PRESET_NAME and active in self._get_presets():
                text = self._get_presets()[active]
            elif isinstance(legacy, str) and legacy:
                text = legacy
            else:
                text = TXT_PROMPT_DEFAULT
                if active != DEFAULT_PRESET_NAME and active not in self._get_presets():
                    # preset attivo orfano (file modificato a mano): ripiega
                    self.saved_prompts['txt_prompt_active'] = DEFAULT_PRESET_NAME
                    active = DEFAULT_PRESET_NAME
        else:
            text = TXT_PROMPT_DEFAULT
            active = DEFAULT_PRESET_NAME

        self._loading_preset = True
        try:
            self._refresh_preset_combo(select=active)
            self.txt_prompt_edit.setPlainText(text)
            self._original_txt_prompt = text
            self._active_preset = active
        finally:
            self._loading_preset = False
        self._update_txt_prompt_state()

    # ------------------------------------------------------------------
    # Stato UI (Salva abilitato, Elimina, status)
    # ------------------------------------------------------------------
    def _update_txt_prompt_state(self):
        if not hasattr(self, '_original_txt_prompt'):
            return
        current = self.txt_prompt_edit.toPlainText()
        dirty = current != self._original_txt_prompt
        active = getattr(self, '_active_preset', DEFAULT_PRESET_NAME)

        # Sul Default di fabbrica "Salva" e' disabilitato: il default non si
        # sovrascrive, bisogna usare "Salva con nome". Sugli altri preset
        # "Salva" sovrascrive solo se ci sono modifiche.
        if active == DEFAULT_PRESET_NAME:
            self.btn_save_txt.setEnabled(False)
            self.btn_save_txt.setToolTip(
                self.tr("Il preset Default non si puo' sovrascrivere: usa 'Salva con nome'."))
        else:
            self.btn_save_txt.setEnabled(dirty and bool(current.strip()))
            self.btn_save_txt.setToolTip(
                self.tr("Sovrascrivi il preset selezionato con il testo corrente."))

        self.btn_delete_txt.setEnabled(active != DEFAULT_PRESET_NAME)

        # Status: conteggio + controllo segnaposto {t_lang}.
        n = len(current)
        if "{t_lang}" in current:
            self.txt_prompt_status.setText(
                self.tr(f"{n} caratteri • segnaposto {{t_lang}} presente"))
            self.txt_prompt_status.setStyleSheet("color: gray; font-size: 11px;")
        else:
            self.txt_prompt_status.setText(
                self.tr(f"{n} caratteri • ATTENZIONE: manca {{t_lang}}, la lingua target non verra' inserita"))
            self.txt_prompt_status.setStyleSheet("color: #E6A23C; font-size: 11px;")

    def _on_txt_prompt_changed(self):
        if getattr(self, '_loading_preset', False):
            return
        self._update_txt_prompt_state()

    # ------------------------------------------------------------------
    # Cambio preset con guardia modifiche non salvate
    # ------------------------------------------------------------------
    def _on_txt_preset_changed(self, name: str):
        if getattr(self, '_loading_preset', False) or not name:
            return
        if name == getattr(self, '_active_preset', DEFAULT_PRESET_NAME):
            return
        current = self.txt_prompt_edit.toPlainText()
        if current != getattr(self, '_original_txt_prompt', current):
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle(self.tr("Modifiche non salvate"))
            box.setText(self.tr(f"Passare al preset '{name}' senza salvare?"))
            box.setIcon(QtWidgets.QMessageBox.Icon.Question)
            btn_save = box.addButton(self.tr("Salva prima"),
                                     QtWidgets.QMessageBox.ButtonRole.AcceptRole)
            btn_discard = box.addButton(self.tr("Scarta modifiche"),
                                        QtWidgets.QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = box.addButton(QtWidgets.QMessageBox.StandardButton.Cancel)
            box.exec()
            clicked = box.clickedButton()
            if clicked == btn_save:
                if not self._save_current_over_active():
                    # Salvataggio annullato/fallito: resta sul preset corrente
                    self._refresh_preset_combo(select=self._active_preset)
                    return
            elif clicked != btn_discard:
                self._refresh_preset_combo(select=self._active_preset)
                return

        presets = self._get_presets()
        text = presets.get(name, TXT_PROMPT_DEFAULT) if name != DEFAULT_PRESET_NAME else TXT_PROMPT_DEFAULT
        self._loading_preset = True
        try:
            self._active_preset = name
            self.txt_prompt_edit.setPlainText(text)
            self._original_txt_prompt = text
            self._save_all_txt_to_config(name, text, presets)
        finally:
            self._loading_preset = False
        self._update_txt_prompt_state()

    # ------------------------------------------------------------------
    # Azioni
    # ------------------------------------------------------------------
    def _save_current_over_active(self) -> bool:
        """Sovrascrive il preset attivo. Ritorna False se annullato."""
        active = getattr(self, '_active_preset', DEFAULT_PRESET_NAME)
        if active == DEFAULT_PRESET_NAME:
            MMessage.info(
                self.tr("Il preset Default non si puo' sovrascrivere: usa 'Salva con nome'."),
                parent=self)
            return False
        current = self.txt_prompt_edit.toPlainText().strip()
        if not current:
            MMessage.warning(self.tr("Il prompt non può essere vuoto!"), parent=self)
            return False
        presets = self._get_presets()
        presets[active] = self.txt_prompt_edit.toPlainText()
        self._save_all_txt_to_config(active, self.txt_prompt_edit.toPlainText(), presets)
        self._original_txt_prompt = self.txt_prompt_edit.toPlainText()
        self._update_txt_prompt_state()
        return True

    def _on_save_as_txt_prompt(self):
        current = self.txt_prompt_edit.toPlainText()
        if not current.strip():
            MMessage.warning(self.tr("Il prompt non può essere vuoto!"), parent=self)
            return
        active = getattr(self, '_active_preset', DEFAULT_PRESET_NAME)
        suggestion = "" if active == DEFAULT_PRESET_NAME else active
        name, ok = QtWidgets.QInputDialog.getText(
            self, self.tr("Salva con nome"),
            self.tr("Nome del preset:"),
            text=suggestion)
        if not ok:
            return
        name = name.strip()
        if not name:
            MMessage.warning(self.tr("Il nome non può essere vuoto!"), parent=self)
            return
        if name == DEFAULT_PRESET_NAME:
            MMessage.warning(
                self.tr("'Default' e' riservato al prompt di fabbrica: scegli un altro nome."),
                parent=self)
            return
        presets = self._get_presets()
        if name in presets and name != active:
            box = QtWidgets.QMessageBox(self)
            box.setWindowTitle(self.tr("Sovrascrivere?"))
            box.setText(self.tr(f"Il preset '{name}' esiste già. Sovrascriverlo?"))
            box.setIcon(QtWidgets.QMessageBox.Icon.Question)
            box.setStandardButtons(
                QtWidgets.QMessageBox.StandardButton.Yes |
                QtWidgets.QMessageBox.StandardButton.Cancel)
            if box.exec() != QtWidgets.QMessageBox.StandardButton.Yes:
                return
        presets[name] = current
        self._active_preset = name
        self._save_all_txt_to_config(name, current, presets)
        self._original_txt_prompt = current
        self._refresh_preset_combo(select=name)
        self._update_txt_prompt_state()
        MMessage.success(self.tr(f"Preset '{name}' salvato!"), parent=self)

    def _on_save_txt_prompt(self):
        if getattr(self, '_active_preset', DEFAULT_PRESET_NAME) == DEFAULT_PRESET_NAME:
            MMessage.info(
                self.tr("Il preset Default non si puo' sovrascrivere: usa 'Salva con nome'."),
                parent=self)
            return
        if self._save_current_over_active():
            MMessage.success(self.tr("Preset aggiornato!"), parent=self)

    def _on_delete_txt_preset(self):
        active = getattr(self, '_active_preset', DEFAULT_PRESET_NAME)
        if active == DEFAULT_PRESET_NAME:
            return
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(self.tr("Elimina preset"))
        box.setText(self.tr(f"Eliminare il preset '{active}'?"))
        box.setIcon(QtWidgets.QMessageBox.Icon.Question)
        box.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Yes |
            QtWidgets.QMessageBox.StandardButton.Cancel)
        if box.exec() != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        presets = self._get_presets()
        presets.pop(active, None)
        self._active_preset = DEFAULT_PRESET_NAME
        self._save_all_txt_to_config(
            DEFAULT_PRESET_NAME, TXT_PROMPT_DEFAULT, presets)
        self._loading_preset = True
        try:
            self._refresh_preset_combo(select=DEFAULT_PRESET_NAME)
            self.txt_prompt_edit.setPlainText(TXT_PROMPT_DEFAULT)
            self._original_txt_prompt = TXT_PROMPT_DEFAULT
        finally:
            self._loading_preset = False
        self._update_txt_prompt_state()
        MMessage.success(self.tr(f"Preset '{active}' eliminato."), parent=self)

    # Alias retrocompatibilita': i vecchi pulsanti non esistono piu'.
    def _on_duplicate_txt_prompt(self):
        self._on_save_as_txt_prompt()

    def _on_reset_txt_prompt(self):
        self._loading_preset = True
        try:
            self._active_preset = DEFAULT_PRESET_NAME
            self._refresh_preset_combo(select=DEFAULT_PRESET_NAME)
            self.txt_prompt_edit.setPlainText(TXT_PROMPT_DEFAULT)
            self._original_txt_prompt = TXT_PROMPT_DEFAULT
            self._save_all_txt_to_config(
                DEFAULT_PRESET_NAME, TXT_PROMPT_DEFAULT, self._get_presets())
        finally:
            self._loading_preset = False
        self._update_txt_prompt_state()

    def get_txt_prompt(self, t_lang='English') -> str:
        if hasattr(self, 'saved_prompts') and 'txt_prompt' in self.saved_prompts:
            prompt = self.saved_prompts['txt_prompt']
            if not prompt:
                prompt = TXT_PROMPT_DEFAULT
        else:
            prompt = TXT_PROMPT_DEFAULT
        # NON usare str.format(): i prompt personalizzati contengono spesso
        # "{...}" (esempi JSON), e format() sollevava KeyError/IndexError
        # durante la traduzione. Sostituzione letterale del solo segnaposto.
        if '{t_lang}' in prompt:
            return prompt.replace('{t_lang}', t_lang)
        return prompt
