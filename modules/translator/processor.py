import numpy as np
import logging
import time

from ..utils.textblock import TextBlock
from .base import LLMTranslation
from .factory import TranslationEngineFactory
from ..browser_sites import is_browser_site, resolve_key

# Configura il logger per Translator
logger = logging.getLogger(__name__)


class Translator:
    """
    Main translator class that orchestrates the translation process.
    
    Supports multiple translation engines including:
    - Text-based translators (Google, DeepL)
    - LLM-based translators (GPT, Claude, Gemini, Deepseek)
    """
    
    def __init__(self, main_page, source_lang: str = "", target_lang: str = ""):
        """
        Initialize translator with settings and languages.
        
        Args:
            main_page: Main application page with settings
            source_lang: Source language name (localized)
            target_lang: Target language name (localized)
        """
        self.main_page = main_page
        self.settings = main_page.settings_page
        
        self.translator_key = self._get_translator_key(self.settings.get_tool_selection('translator'))
        
        self.source_lang = source_lang
        self.source_lang_en = self._get_english_lang(main_page, self.source_lang)
        self.target_lang = target_lang
        self.target_lang_en = self._get_english_lang(main_page, self.target_lang)
        
        # Create appropriate engine using factory
        self.engine = TranslationEngineFactory.create_engine(
            self.settings,
            self.source_lang_en,
            self.target_lang_en,
            self.translator_key
        )
        
        # Track engine type for method dispatching
        if is_browser_site(self.translator_key):
            self.is_llm_engine = True  # serve il prompt per i siti browser
        else:
            self.is_llm_engine = isinstance(self.engine, LLMTranslation)
    
    def _get_translator_key(self, localized_translator: str) -> str:
        """
        Map localized translator names to standard keys with dynamic model support.
        
        Args:
            localized_translator: Translator name in UI language
            
        Returns:
            Standard translator key
        """
        # Apply reverse mapping to convert formatted display names back to base names
        base_translator = self.settings.ui.reverse_mappings.get(localized_translator, localized_translator)
        
        # DEBUG: Aggiungi logging per diagnosticare il problema
        print(f"[DEBUG] Localized translator: '{localized_translator}'")
        print(f"[DEBUG] Base translator after reverse mapping: '{base_translator}'")
        print(f"[DEBUG] Available reverse mappings keys: {list(self.settings.ui.reverse_mappings.keys())[:10]}")
        
        # I siti browser hanno una chiave propria; risolve anche 'TXT' -> 'Gemini'
        if is_browser_site(base_translator):
            return resolve_key(base_translator)

        # First check if it's a dynamic model using the base name
        try:
            from ..utils.model_manager import model_manager
            translation_engines = model_manager.get_translation_engines()
            if base_translator in translation_engines:
                return base_translator
        except Exception as e:
            print(f"Error checking dynamic translation engines: {e}")
        
        # Fallback to traditional mapping
        translator_map = {
            self.settings.ui.tr("Deepseek-v3"): "Deepseek-v3",
            self.settings.ui.tr("GPT-4o"): "GPT-4o",
            self.settings.ui.tr("GPT-4o mini"): "GPT-4o mini",
            self.settings.ui.tr("Claude-3-Opus"): "Claude-3-Opus",
            self.settings.ui.tr("Claude-3.7-Sonnet"): "Claude-3.7-Sonnet",
            self.settings.ui.tr("Claude-3.5-Haiku"): "Claude-3.5-Haiku",
            self.settings.ui.tr("Gemini-2.0-Flash"): "Gemini-2.0-Flash",
            self.settings.ui.tr("Gemini-2.5-Flash"): "Gemini-2.5-Flash",
            self.settings.ui.tr("Gemini-2.0-Pro"): "Gemini-2.0-Pro",
            self.settings.ui.tr("Google Translate"): "Google Translate",
            self.settings.ui.tr("DeepL"): "DeepL",
            self.settings.ui.tr("Qwen2.5 VL 72B Instruct (free)"): "Qwen2.5 VL 72B Instruct (free)",
        }
        return translator_map.get(localized_translator, base_translator)
    
    def _get_english_lang(self, main_page, translated_lang: str) -> str:
        """
        Get English language name from localized language name.
        
        Args:
            main_page: Main application page with language mapping
            translated_lang: Language name in UI language
            
        Returns:
            Language name in English
        """
        return main_page.lang_mapping.get(translated_lang, translated_lang)
    
    def translate(self, blk_list: list[TextBlock], image: np.ndarray | None = None, extra_context: str = "") -> list[TextBlock]:
        """
        Translate text in text blocks using the configured translation engine.
        
        Args:
            blk_list: List of TextBlock objects to translate
            image: Image as numpy array (for context in LLM translators)
            extra_context: Additional context information for translation
            
        Returns:
            List of updated TextBlock objects with translations
        """
        logger.info(f"=== INIZIO TRADUZIONE TRANSLATOR ===")
        logger.info(f"Motore di traduzione: {self.translator_key}")
        logger.info(f"Lingua sorgente: {self.source_lang_en}, Lingua target: {self.target_lang_en}")
        logger.info(f"Numero di blocchi da tradurre: {len(blk_list)}")
        
        # Log del contenuto dei TextBlock prima della traduzione
        total_source_chars = 0
        for i, blk in enumerate(blk_list):
            if hasattr(blk, 'text') and blk.text:
                total_source_chars += len(blk.text)
                logger.debug(f"TextBlock {i} PRIMA: '{blk.text[:100]}...' (lunghezza: {len(blk.text)})")
            else:
                logger.warning(f"TextBlock {i} VUOTO o senza testo!")
        
        logger.info(f"Totale caratteri sorgente: {total_source_chars}")
        
        # Nei siti browser l'engine è None: la traduzione la fa
        # l'automator guidando la webview, non Python.
        if is_browser_site(self.translator_key):
            logger.info(
                f"Sito browser attivo ({self.translator_key}): saltata "
                "traduzione automatica (solo prompt)"
            )
            return blk_list

        start_total = time.perf_counter()
        try:
            if self.is_llm_engine:
                logger.info(f"Usando traduttore LLM con extra context: {bool(extra_context)}")
                
                # --- Costruzione del contesto degli strumenti (lingue, font, etc.) ---
                tools_parts = [
                    f"Source Language: {self.source_lang_en}",
                    f"Target Language: {self.target_lang_en}"
                ]
                
                try:
                    # Ottieni i font selezionati, filtrandoli a quelli effettivamente usati nei blocchi
                    if hasattr(self.settings, 'get_selected_fonts'):
                        selected_fonts = self.settings.get_selected_fonts()
                        if selected_fonts:
                            # Raccoglie i font rilevati nei TextBlock della batch corrente
                            used_fonts = set()
                            for blk in blk_list:
                                used_font = getattr(blk, 'detected_font_family', None)
                                if used_font and used_font in selected_fonts:
                                    used_fonts.add(used_font)

                            if used_fonts:
                                # Invia solo i font effettivamente rilevati (lista corta e utile)
                                tools_parts.append(f"Selected Font(s): {', '.join(sorted(used_fonts))}")
                            elif len(selected_fonts) <= 5:
                                # Pochi font selezionati: lista completa è accettabile
                                tools_parts.append(f"Selected Font(s): {', '.join(selected_fonts)}")
                            # Altrimenti: nessuna font detection e troppi font -> ometti la lista
                            # (non è utile al traduttore e appesantisce inutilmente il prompt)
                    
                    # Ottieni impostazione Maiuscolo
                    if hasattr(self.settings.ui, 'uppercase_checkbox'):
                        upper = self.settings.ui.uppercase_checkbox.isChecked()
                        tools_parts.append(f"Uppercase Output: {'Yes' if upper else 'No'}")
                        
                    # Ottieni l'allineamento predefinito se possibile
                    # (Nota: l'allineamento è spesso per blocco, ma qui mettiamo quello globale se utile)
                except Exception as e:
                    logger.warning(f"Errore durante la raccolta del contesto strumenti: {e}")

                tools_context = "### TRANSLATION TOOLS & SETTINGS ###\n" + "\n".join(tools_parts) + "\n####################################\n"
                
                # Combina con l'extra_context esistente
                augmented_extra_context = tools_context + "\n" + extra_context if extra_context else tools_context
                
                if extra_context:
                    logger.debug(f"Extra context: {extra_context[:200]}...")
                
                if image is not None and hasattr(image, 'shape'):
                    logger.info(f"Immagine fornita: shape={image.shape}")
                else:
                    logger.warning("Nessuna immagine fornita al traduttore LLM!")
                
                # LLM translators need image and extra context
                # Convert numpy array to image path if needed
                image_param = None
                if image is not None:
                    # Pass the numpy array directly - the engine handles it
                    image_param = image
                start_engine = time.perf_counter()

                # ── Smart Batching ────────────────────────────────────────────
                # Recupera il limite di token di output del modello corrente.
                # Priorità: models.json → tabella built-in → fallback 4000.
                try:
                    from ..utils.model_manager import model_manager as _mm
                    MAX_OUTPUT_TOKENS = _mm.get_max_output_tokens(self.translator_key, fallback=4000)
                except Exception:
                    MAX_OUTPUT_TOKENS = 4000

                SAFETY_RATIO    = 0.80          # margine di sicurezza 20%
                TOKEN_BUDGET    = int(MAX_OUTPUT_TOKENS * SAFETY_RATIO)
                CHARS_PER_TOKEN = 1.5           # espansione media sorgente→target
                JSON_OVERHEAD   = 30            # token fissi per chiave JSON

                logger.info(
                    f"[SmartBatch] Modello={self.translator_key} | "
                    f"max_output={MAX_OUTPUT_TOKENS} | budget={TOKEN_BUDGET} tok"
                )

                def _estimate_block_tokens(blk) -> int:
                    text = getattr(blk, 'text', '') or ''
                    return int(len(text) / CHARS_PER_TOKEN) + JSON_OVERHEAD

                # Raggruppa i blocchi in chunk che rispettano il budget
                chunks: list[list] = []
                current_chunk: list = []
                current_tokens: int = 0
                for blk in blk_list:
                    blk_tokens = _estimate_block_tokens(blk)
                    if blk_tokens >= TOKEN_BUDGET:
                        if current_chunk:
                            chunks.append(current_chunk)
                            current_chunk = []
                            current_tokens = 0
                        chunks.append([blk])
                    elif current_tokens + blk_tokens > TOKEN_BUDGET:
                        chunks.append(current_chunk)
                        current_chunk = [blk]
                        current_tokens = blk_tokens
                    else:
                        current_chunk.append(blk)
                        current_tokens += blk_tokens
                if current_chunk:
                    chunks.append(current_chunk)

                total_blocks = len(blk_list)
                n_chunks = len(chunks)
                logger.info(
                    f"[SmartBatch] {total_blocks} blocchi → {n_chunks} chunk(s) "
                    f"(espansione={CHARS_PER_TOKEN}×, json_overhead={JSON_OVERHEAD})"
                )

                result = []
                processed = 0
                for c_idx, chunk in enumerate(chunks):
                    chunk_chars = sum(len(getattr(b, 'text', '') or '') for b in chunk)
                    logger.info(
                        f"[SmartBatch] Chunk {c_idx+1}/{n_chunks}: "
                        f"{len(chunk)} blocchi, ~{chunk_chars} char sorgente"
                    )
                    chunk_start = time.perf_counter()
                    # Usa augmented_extra_context invece di extra_context
                    res = self.engine.translate(chunk, image_param, augmented_extra_context)
                    result.extend(res)
                    processed += len(chunk)
                    logger.debug(
                        f"[SmartBatch] Chunk {c_idx+1} completato in "
                        f"{time.perf_counter() - chunk_start:.3f}s "
                        f"({processed}/{total_blocks} blocchi totali)"
                    )

                logger.info(
                    f"[SmartBatch] Traduzione LLM completata in "
                    f"{time.perf_counter() - start_engine:.3f}s"
                )
                # ─────────────────────────────────────────────────────────────

            else:
                logger.info("Usando traduttore basato su testo")
                # Text-based translators only need the text blocks
                start_engine = time.perf_counter()
                result = self.engine.translate(blk_list)
                logger.debug(f"Tempo traduzione testo: {time.perf_counter() - start_engine:.3f}s")
            
            # Log del contenuto dei TextBlock dopo la traduzione
            total_translated_chars = 0
            translated_count = 0
            for i, blk in enumerate(result):
                if hasattr(blk, 'translation') and blk.translation:
                    total_translated_chars += len(blk.translation)
                    translated_count += 1
                    logger.debug(f"TextBlock {i} DOPO: '{blk.translation[:100]}...' (lunghezza: {len(blk.translation)})")
                else:
                    logger.warning(f"TextBlock {i} NON TRADOTTO!")
            
            logger.info(f"Traduzione completata: {translated_count}/{len(blk_list)} blocchi tradotti")
            logger.info(f"Totale caratteri tradotti: {total_translated_chars}")
            
            return result
            
        except Exception as e:
            logger.error(f"ERRORE durante la traduzione nel Translator: {str(e)}")
            logger.error(f"Tipo errore: {type(e).__name__}")
            logger.error(f"Dettagli: {repr(e)}")
            print(f"Translator error: {str(e)}")
            return blk_list
        
        finally:
            logger.debug(f"Tempo totale traduzione batch: {time.perf_counter() - start_total:.3f}s")
            logger.info(f"=== FINE TRADUZIONE TRANSLATOR ===")
