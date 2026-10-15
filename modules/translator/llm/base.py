from typing import Any
import numpy as np
import logging
from abc import abstractmethod
import cv2
import traceback

from ..base import LLMTranslation
from ...utils.textblock import TextBlock
from ...utils.translator_utils import get_raw_text, set_texts_from_json, is_there_text
from ...utils.image_utils import create_blocks_collage

# Configura il logger per BaseLLMTranslation
logger = logging.getLogger(__name__)


class BaseLLMTranslation(LLMTranslation):
    """Base class for LLM-based translation engines with shared functionality."""
    
    def __init__(self):
        """Initialize LLM translation engine."""
        self.source_lang = None
        self.target_lang = None
        self.api_key = None
        self.api_url = None
        self.client = None
        self.model = None
        self.img_as_llm_input = False
    
    def initialize(self, settings: Any, source_lang: str, target_lang: str, **kwargs) -> None:
        """
        Initialize the LLM translation engine.
        
        Args:
            settings: Settings object with credentials
            source_lang: Source language name
            target_lang: Target language name
            **kwargs: Engine-specific initialization parameters
        """
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.img_as_llm_input = settings.get_llm_settings()['image_input_enabled']
        
    def translate(self, blk_list: list[TextBlock], image: np.ndarray, extra_context: str) -> list[TextBlock]:
        """
        Translate text blocks using LLM.
        
        Args:
            blk_list: List of TextBlock objects to translate
            image: Image as numpy array
            extra_context: Additional context information for translation
            
        Returns:
            List of updated TextBlock objects with translations
        """
        logger.info(f"=== INIZIO TRADUZIONE {type(self).__name__} ===")
        logger.info(f"Lingue: {self.source_lang} -> {self.target_lang}")
        logger.info(f"Numero di TextBlock da tradurre: {len(blk_list)}")
        
        try:
            # Estrai il testo sorgente dai TextBlock
            entire_raw_text = get_raw_text(blk_list)
            
            # Decide se usare la modalità Collage o Immagine Intera
            # Se abbiamo un'immagine e l'input immagine è attivo, usiamo il COLLAGE
            # per dare al modello ritagli ad alta risoluzione dei singoli blocchi.
            final_image = image
            use_collage = False
            
            if image is not None and self.img_as_llm_input:
                use_collage = True
                logger.info("Modalità COLLAGE attivata per la traduzione Vision LLM")
                
                crops = []
                indices = []
                for i, blk in enumerate(blk_list):
                    try:
                        # Espansione minima per sicurezza
                        padding = 10
                        if blk.bubble_xyxy is not None:
                            x1, y1, x2, y2 = blk.bubble_xyxy
                        else:
                            x1, y1, x2, y2 = blk.xyxy
                        
                        # Aggiungi padding e clamp alle dimensioni immagine
                        img_h, img_w = image.shape[:2]
                        x1 = max(0, int(x1) - padding)
                        y1 = max(0, int(y1) - padding)
                        x2 = min(img_w, int(x2) + padding)
                        y2 = min(img_h, int(y2) + padding)
                        
                        if x2 > x1 and y2 > y1:
                            crop = image[y1:y2, x1:x2]
                            if crop.size > 0:
                                crops.append(crop)
                                indices.append(i)
                    except Exception as e:
                        logger.error(f"Errore estrazione crop per blocco {i}: {e}")
                
                if crops:
                    # Crea il collage
                    final_image, id_map = create_blocks_collage(crops, indices, show_labels=True)
                    logger.info(f"Collage creato con {len(crops)} blocchi")
                else:
                    use_collage = False
                    logger.warning("Impossibile creare collage, ripiego su immagine intera")

            system_prompt = self.get_system_prompt(self.source_lang, self.target_lang)
            
            # Check if we need to use Vision-based OCR+Translation (only if blocks have no text)
            use_vision_ocr = False
            if image is not None and self.img_as_llm_input and not is_there_text(blk_list):
                 use_vision_ocr = True
                 logger.info("Rilevato testo vuoto con immagine disponibile: Attivazione modalità OCR+Traduzione via Vision LLM")
            
            if use_collage:
                # Prompt specifico per Collage (modelli vision)
                user_prompt = (
                    f"{extra_context}\n"
                    f"The provided image is a COLLAGE of text blocks from a comic/manga. Each block is numbered.\n"
                    f"Translate the text from each numbered block to {self.target_lang}.\n"
                    f"Maintain the context and flow between blocks.\n"
                )

                if not use_vision_ocr:
                    user_prompt += f"\nSource text for reference:\n{entire_raw_text}\n"

                user_prompt += (
                    f"\nReturn ONLY a JSON object where keys are the numbers from the image (\"1\", \"2\", etc.) "
                    f"and values are the translated text in {self.target_lang}.\n"
                    f"Example format: {{\"1\": \"translated text in {self.target_lang}\", \"2\": \"...\"}}\n"
                    f"CRITICAL: You MUST translate every value into {self.target_lang}. "
                    f"Do NOT copy the source text. Do NOT output the source language."
                )
            elif use_vision_ocr:
                # Construct a prompt that includes coordinates for the blocks (Full Image)
                coords_text = []
                img_h, img_w = image.shape[:2]
                for i, blk in enumerate(blk_list):
                    x1, y1, x2, y2 = blk.xyxy
                    coords_text.append(f"block_{i}: [{int(x1)}, {int(y1)}, {int(x2)}, {int(y2)}]")

                coords_str = "\n".join(coords_text)
                user_prompt = (
                    f"{extra_context}\n"
                    f"The provided image contains text blocks that need to be recognized and translated to {self.target_lang}.\n"
                    f"Here are the coordinates of the text blocks (x1, y1, x2, y2) in the image (Size: {img_w}x{img_h}):\n{coords_str}\n\n"
                    f"Please transcribe the text from each block and provide the translation in {self.target_lang}.\n"
                    f"Return ONLY a JSON object where keys are 'block_0', 'block_1', etc. and values are the translated text in {self.target_lang}.\n"
                    f"Example format: {{\"block_0\": \"translated text in {self.target_lang}\", \"block_1\": \"...\"}}\n"
                    f"CRITICAL: You MUST translate every value into {self.target_lang}. "
                    f"Do NOT copy the source text. Do NOT output the source language."
                )
            else:
                # Testo puro (modelli text-only come Aya). Prompt più diretto e aggressivo
                # per evitare che il modello ricopi il testo sorgente invece di tradurlo.
                user_prompt = (
                    f"{extra_context}\n"
                    f"### TASK ###\n"
                    f"Translate the following JSON values from {self.source_lang} to {self.target_lang}.\n\n"
                    f"### TARGET LANGUAGE ###\n"
                    f"{self.target_lang}\n\n"
                    f"### MANDATORY RULES ###\n"
                    f"1. Output language: {self.target_lang} (not {self.source_lang}, not English).\n"
                    f"2. You MUST translate every value. NEVER copy the source text as-is.\n"
                    f"3. Keep the JSON keys exactly as provided (e.g. \"block_0\", \"block_1\").\n"
                    f"4. Translate ONLY the values, never the keys.\n"
                    f"5. If a value is already in {self.target_lang}, keep it as-is; otherwise translate it.\n"
                    f"6. If a value is empty, return an empty string for that key. NEVER return \"...\" or placeholders.\n"
                    f"7. Be natural and fluent in {self.target_lang}.\n"
                    f"8. Return ONLY a valid JSON object. No markdown, no explanations, no preamble.\n\n"
                    f"### INPUT JSON ###\n"
                    f"{entire_raw_text}\n\n"
                    f"### OUTPUT (valid JSON, all values in {self.target_lang}) ###\n"
                )
            
            logger.info(f"Chiamata a _perform_translation con {len(user_prompt)} caratteri di prompt")

            # Chiamata alla traduzione specifica del modello
            entire_translated_text = self._perform_translation(user_prompt, system_prompt, final_image)

            # FIX: Verifica che la traduzione sia effettivamente avvenuta. Se l'output
            # coincide con il source, il modello (es. Aya) potrebbe non aver tradotto.
            # In tal caso ritentiamo con un prompt più aggressivo.
            if entire_translated_text and not use_collage and not use_vision_ocr:
                if self._is_response_unchanged(entire_translated_text, entire_raw_text):
                    logger.warning(
                        "Output identico al source: il modello potrebbe non aver tradotto. "
                        "Ritento con prompt rinforzato."
                    )
                    retry_system_prompt = (
                        f"You are a strict translation engine. "
                        f"You MUST convert every input value from {self.source_lang} "
                        f"into {self.target_lang}. The previous attempt failed because "
                        f"the output was identical to the input. "
                        f"NEVER copy the source text. Output a JSON object whose values "
                        f"are the {self.target_lang} translation of each input value."
                    )
                    retry_user_prompt = (
                        f"Translate every value in the following JSON from "
                        f"{self.source_lang} to {self.target_lang}.\n"
                        f"Output language: {self.target_lang}.\n"
                        f"Return ONLY a JSON object, no markdown.\n\n"
                        f"{entire_raw_text}\n"
                    )
                    entire_translated_text = self._perform_translation(
                        retry_user_prompt, retry_system_prompt, final_image
                    )

            # Log del risultato della traduzione
            if entire_translated_text:
                logger.debug(f"Risposta raw ricevuta (primi 200 char): {entire_translated_text[:200]}...")
            else:
                logger.error("ERRORE: Traduzione vuota o None ricevuta!")
            
            # Applica le traduzioni ai TextBlock
            # Se abbiamo usato il collage, dobbiamo mappare gli ID numerici "1", "2" back to block_0, block_1
            if use_collage and entire_translated_text:
                try:
                    import json
                    from ...utils.translator_utils import _extract_json_object
                    raw_json = _extract_json_object(entire_translated_text)
                    if raw_json:
                        data = json.loads(raw_json)
                        normalized_data = {}
                        # Se id_map è disponibile (modalità collage), mappa gli ID numerici agli indici originali
                        for k, v in data.items():
                            if k in id_map:
                                # Mapping local ID (str "1", "2"...) to original block index
                                orig_idx = id_map[k]
                                normalized_data[f"block_{orig_idx}"] = v
                            elif k.isdigit():
                                # Fallback se id_map fallisce ma la chiave è numerica
                                idx = int(k) - 1
                                if 0 <= idx < len(blk_list):
                                    normalized_data[f"block_{idx}"] = v
                            else:
                                normalized_data[k] = v
                        entire_translated_text = json.dumps(normalized_data)
                except Exception as e:
                    logger.warning(f"Errore nella normalizzazione degli ID del collage: {e}")

            logger.info("Applicazione traduzioni ai TextBlock...")
            set_texts_from_json(blk_list, entire_translated_text, self.img_as_llm_input)
            # Blocchi con sorgente vuota (OCR mancato, es. casella manuale non
            # ancora processata): il modello tende a copiare il placeholder
            # dell'esempio ("..."). Forza stringa vuota cosi' il rendering li
            # salta invece di stampare '...'.
            _PLACEHOLDERS = {'...', '…', '..', '.', '--', '-', 'null', 'none', 'n/a'}
            for _blk in blk_list:
                _src = (getattr(_blk, 'text', '') or '').strip()
                _tr = (getattr(_blk, 'translation', '') or '').strip()
                if not _src:
                    _blk.translation = ""
                elif _tr.lower() in _PLACEHOLDERS:
                    _blk.translation = ""

            translated_count = 0
            for i, blk in enumerate(blk_list):
                if hasattr(blk, 'translation') and blk.translation:
                    translated_count += 1
            
            logger.info(f"Traduzione completata: {translated_count}/{len(blk_list)} TextBlock tradotti")
        
        except Exception as e:
            logger.error(f"ERRORE durante la traduzione {type(self).__name__}: {str(e)}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            print(f"{type(self).__name__} translation error: {str(e)}")
            
        logger.info(f"=== FINE TRADUZIONE {type(self).__name__} ===")
        return blk_list

    def _is_response_unchanged(self, response: str, source_text_json: str) -> bool:
        """
        Verifica se la risposta del modello è sostanzialmente identica al source.
        Usato per rilevare i casi in cui il modello (es. Aya) non traduce e ricopia
        il testo sorgente. La logica è volutamente conservativa: ritorna True
        solo se la similarità è molto alta, per evitare falsi positivi su testi
        brevi o coincidenti (es. nomi propri, espressioni universali).

        Args:
            response: testo restituito dal modello
            source_text_json: JSON con i testi sorgenti

        Returns:
            True se l'output sembra coincidere con il source (nessuna traduzione)
        """
        import json as _json
        try:
            from ...utils.translator_utils import _extract_json_object as _extract
        except Exception:
            return False

        try:
            resp_json_str = _extract(response) or response
            src_json_str = _extract(source_text_json) or source_text_json
            resp_data = _json.loads(resp_json_str)
            src_data = _json.loads(src_json_str)
        except Exception:
            return False

        if not isinstance(resp_data, dict) or not isinstance(src_data, dict):
            return False

        src_items = []
        resp_items = []
        for k, v in src_data.items():
            if isinstance(v, str):
                src_items.append(v.strip().lower())
        for k, v in resp_data.items():
            if isinstance(v, str):
                resp_items.append(v.strip().lower())

        if not src_items:
            return False

        # Se il numero di item differisce significativamente, non considerarlo "unchanged"
        if abs(len(src_items) - len(resp_items)) > max(1, len(src_items) // 4):
            return False

        # Calcola quanto del source è stato copiato pari-pari nel response
        copied = 0
        for s in src_items:
            if not s:
                continue
            for r in resp_items:
                # Confronto esatto o substring molto forte
                if s == r or (len(s) >= 6 and (s in r or r in s)):
                    copied += 1
                    break

        ratio = copied / max(1, len(src_items))
        # Se più dell'85% del source è stato ricopiato, consideralo "non tradotto"
        return ratio >= 0.85

    def get_system_prompt(self, source_lang: str, target_lang: str) -> str:
        """
        Get system prompt for LLM translation.

        Args:
            source_lang: Source language
            target_lang: Target language

        Returns:
            Formatted system prompt
        """
        return f"""You are an expert translator. Your sole task is to translate text from {source_lang} to {target_lang}.

ABSOLUTE RULES (non-negotiable):
1. The TARGET LANGUAGE for your output is {target_lang}. Every value in the returned JSON MUST be in {target_lang}.
2. NEVER copy the source text as-is. You MUST translate every value, even short words, exclamations, onomatopoeias and proper nouns, unless the input is already in {target_lang}.
3. If the input is already in {target_lang}, return it unchanged for that block. Otherwise, translate it.
4. Return ONLY a valid JSON object. No markdown code fences, no explanations, no preamble, no trailing text.
5. Keep the JSON keys EXACTLY as provided (e.g. "block_0", "block_1" or numeric "1", "2"). Translate ONLY the values.
6. Sound natural and fluent, as a native {target_lang} speaker would write. Pay attention to style, formality, idioms, and slang.
7. The source text may come from OCR of a comic, so it may contain typos; use context to translate correctly.
8. NEVER use honorifics such as 당신, 그녀, 그 or their Japanese equivalents.

Do your best — the quality of the translation depends entirely on you.
"""

    @abstractmethod
    def _perform_translation(self, user_prompt: str, system_prompt: str, image: np.ndarray) -> str:
        """
        Perform translation using specific LLM.
        
        Args:
            user_prompt: User prompt for LLM
            system_prompt: System prompt for LLM
            image: Image as numpy array
            
        Returns:
            Translated JSON text
        """
        pass