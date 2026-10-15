"""
State Machine per gestire lo stato delle operazioni batch in KomicTranslate.

Centralizza la gestione dei flag per evitare conflitti tra operazioni:
- Rileva Tutto
- Traduci Tutto

Stati per immagine:
- detection_completed: Rileva Tutto ha rilevato le caselle
- ocr_done: OCR già eseguito (testo disponibile nei blocchi)
"""
import copy
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from modules.utils.textblock import TextBlock

logger = logging.getLogger(__name__)


class ImageStateManager:
    """Gestisce lo stato di tutte le immagini nel batch in modo centralizzato."""
    
    # Chiavi degli stati per ogni immagine
    STATE_KEYS = {
        'detection_completed': False,
        'ocr_done': False,
        'blk_list': [],
        'text_blocks': [],
        'viewer_state': {},
    }
    
    def __init__(self, image_states: Dict[str, Dict[str, Any]]):
        """
        Args:
            image_states: Dizionario condiviso degli stati delle immagini (main_page.image_states)
        """
        self.image_states = image_states
    
    def get_state(self, image_path: str) -> Dict[str, Any]:
        """Restituisce lo stato completo per un'immagine, creandolo se non esiste."""
        if image_path not in self.image_states:
            # deepcopy OBBLIGATORIA: dict.copy() e' superficiale, quindi ogni
            # stato auto-creato condividerebbe gli STESSI oggetti list/dict di
            # STATE_KEYS (e degli altri stati), corrompendo lo stato delle altre
            # immagini e della classe stessa.
            self.image_states[image_path] = copy.deepcopy(self.STATE_KEYS)
            # Le lingue NON vengono inventate: se mancano, restano vuote e saranno
            # valorizzate dal chiamante (che conosce la UI). Hardcodare 'Italian'
            # faceva tradurre tutto in italiano indipendentemente dalla scelta utente.
            self.image_states[image_path].setdefault('source_lang', '')
            self.image_states[image_path].setdefault('target_lang', '')
        return self.image_states[image_path]
    
    def set_flag(self, image_path: str, flag_name: str, value: bool) -> None:
        """Imposta un flag di stato specifico per un'immagine."""
        state = self.get_state(image_path)
        state[flag_name] = value
        logger.debug(f"[STATE] {image_path}: {flag_name} = {value}")
    
    def get_flag(self, image_path: str, flag_name: str) -> bool:
        """Legge un flag di stato specifico."""
        state = self.get_state(image_path)
        return state.get(flag_name, False)
    
    def get_blocks(self, image_path: str) -> List[TextBlock]:
        """Restituisce i blocchi di testo (priorità a blk_list)."""
        state = self.get_state(image_path)
        if 'blk_list' in state and state['blk_list']:
            return state['blk_list']
        return state.get('text_blocks', [])
    
    def set_blocks(self, image_path: str, blocks: List[TextBlock], is_blk_list: bool = True) -> None:
        """Imposta i blocchi di testo."""
        state = self.get_state(image_path)
        if is_blk_list:
            state['blk_list'] = blocks
            state['text_blocks'] = blocks  # Sincronizza
        else:
            state['text_blocks'] = blocks
    
    def has_valid_detection(self, image_path: str) -> bool:
        """Verifica se esiste un rilevamento valido (blocchi con coordinate)."""
        blocks = self.get_blocks(image_path)
        if not blocks:
            return False
        valid_count = sum(
            1 for b in blocks 
            if hasattr(b, 'xyxy') and b.xyxy is not None and len(b.xyxy) >= 4
        )
        return valid_count > 0 and valid_count / len(blocks) >= 0.5
    
    def mark_detection_completed(self, image_path: str, blocks: List[TextBlock]) -> None:
        """Marca il rilevamento come completato."""
        state = self.get_state(image_path)
        state['blk_list'] = blocks
        state['text_blocks'] = blocks
        state['detection_completed'] = True
        state['detection_timestamp'] = datetime.now().isoformat()
        state['detection_method'] = 'detect_all_text_boxes'
        logger.info(f"[STATE] {image_path}: detection_completed = True ({len(blocks)} blocchi)")

    def mark_ocr_done(self, image_path: str) -> None:
        """Marca OCR come completato."""
        self.set_flag(image_path, 'ocr_done', True)
    
    def mark_translation_completed(self, image_path: str) -> None:
        """Marca la traduzione come completata."""
        state = self.get_state(image_path)
        state['translation_completed'] = True
        state['translation_timestamp'] = datetime.now().isoformat()
        logger.info(f"[STATE] {image_path}: translation_completed = True")
    
    def should_skip_detection(self, image_path: str) -> bool:
        """Verifica se saltare il rilevamento (esiste già rilevamento valido)."""
        return self.get_flag(image_path, 'detection_completed') and self.has_valid_detection(image_path)
    
    def should_skip_ocr(self, image_path: str) -> bool:
        """Verifica se saltare OCR (già fatto o testo già presente)."""
        state = self.get_state(image_path)
        if state.get('ocr_done', False):
            return True
        # Controlla se i blocchi hanno già testo
        blocks = self.get_blocks(image_path)
        return all(getattr(b, 'text', '').strip() for b in blocks if b is not None)

    def should_skip_translation(self, image_path: str) -> bool:
        """Verifica se saltare la traduzione (già completata)."""
        state = self.get_state(image_path)
        return state.get('translation_completed', False)
    
    def can_skip_to_rendering(self, image_path: str) -> bool:
        """
        Verifica se si può saltare direttamente al rendering.
        True se: rilevamento fatto + OCR fatto
        """
        return (self.get_flag(image_path, 'detection_completed') and
                self.get_flag(image_path, 'ocr_done'))

    def get_operation_status(self, image_path: str) -> Dict[str, bool]:
        """Restituisce lo stato di tutte le operazioni per debug."""
        state = self.get_state(image_path)
        return {
            'detection_completed': state.get('detection_completed', False),
            'ocr_done': state.get('ocr_done', False),
            'translation_completed': state.get('translation_completed', False),
            'has_blocks': len(self.get_blocks(image_path)) > 0,
            'blocks_count': len(self.get_blocks(image_path)),
        }


def get_state_manager(image_states: Dict[str, Dict[str, Any]]) -> ImageStateManager:
    """Factory function per ottenere l'ImageStateManager."""
    return ImageStateManager(image_states)