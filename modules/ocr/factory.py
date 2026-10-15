import gc
import threading
import logging

# torch and all OCR engine classes are imported lazily inside methods to avoid cold-start delay
from .base import OCREngine
from ..utils.model_manager import model_manager

logger = logging.getLogger(__name__)

class OCREngineFactory:
    """Factory for creating appropriate OCR engines based on settings."""
    
    _engines = {}  # Cache of created engines
    _cache_lock = threading.Lock()  # Thread-safety for cache operations
    
    @classmethod
    def create_engine(cls, settings, source_lang_english: str, ocr_model: str) -> OCREngine:
        """Create or retrieve an appropriate OCR engine based on settings."""
        print(f"Creating OCR engine for model: {ocr_model}")
        
        # Create a cache key based on model and language
        cache_key = f"{ocr_model}_{source_lang_english}"
        
        # Return cached engine if available
        if cache_key in cls._engines:
            return cls._engines[cache_key]
        
        # Create engine based on model or language
        engine = cls._create_new_engine(settings, source_lang_english, ocr_model)
        cls._engines[cache_key] = engine
        return engine
    
    @classmethod
    def _create_new_engine(cls, settings, source_lang_english: str, ocr_model: str) -> OCREngine:
        """Create a new OCR engine instance based on model and language."""
        
        # Motori OCR locali (nessuna API coinvolta)
        local_ocr_models = {
            'PP-OCRv5': cls._create_ppocr_v5,
            'MangaOCR': cls._create_manga_ocr,
        }

        if ocr_model in local_ocr_models:
            return local_ocr_models[ocr_model](settings)

        # Modelli dinamici dal Model Manager (oggi solo geminiamo)
        ocr_engines = model_manager.get_ocr_engines()

        if ocr_model in ocr_engines:
            return cls._create_dynamic_engine(settings, ocr_model, ocr_engines[ocr_model])
        
        # Gestione speciale per "Default" - usa modelli specifici per lingua
        if ocr_model == 'Default':
            language_factories = {
                'Japanese': cls._create_manga_ocr,
                'Korean': cls._create_pororo_ocr,
                'Chinese': cls._create_paddle_ocr,
                # Per il russo resta il fallback locale DocTR: non c'e'
                # piu' alcun engine online che copra questa lingua.
                'Russian': cls._create_doctr_ocr,
            }

            if source_lang_english in language_factories:
                return language_factories[source_lang_english](settings)

            # Fallback per Default: usa DocTR
            return cls._create_doctr_ocr(settings)
        
        # Se il modello non è trovato, genera errore informativo
        raise ValueError(f"OCR model '{ocr_model}' not found. Available models: {list(ocr_engines.keys())}")
    
    @classmethod
    def _create_dynamic_engine(cls, settings, model_name: str, engine_info: dict) -> OCREngine:
        """Create engine dynamically based on Model Manager info."""
        engine_type = engine_info['engine_type']

        # Unico engine online rimasto: Geminiamo. Usa i cookie del browser,
        # quindi non ha bisogno di credenziali ne' di get_llm_client().
        if engine_type == 'geminiamo':
            return cls._create_geminiamo_ocr(settings)

        raise ValueError(
            f"OCR engine_type '{engine_type}' non supportato. "
            f"Unico engine online disponibile: 'geminiamo'."
        )

    @staticmethod
    def _create_geminiamo_ocr(settings) -> OCREngine:
        """Create Geminiamo OCR engine."""
        from .geminiamo_ocr import GeminiamoOCR
        engine = GeminiamoOCR()
        engine.initialize(settings)
        return engine

    
    
    @staticmethod
    def _create_manga_ocr(settings) -> OCREngine:
        from .manga_ocr.engine import MangaOCREngine
        device = 'cuda' if settings.is_gpu_enabled() else 'cpu'
        engine = MangaOCREngine()
        engine.initialize(device=device)
        return engine
    
    @staticmethod
    def _create_pororo_ocr(settings) -> OCREngine:
        from .pororo.engine import PororoOCREngine
        engine = PororoOCREngine()
        engine.initialize()
        return engine
    
    @staticmethod
    def _create_ppocr_v5(settings) -> OCREngine:
        """Create PP-OCRv5 engine."""
        from .ppocr.engine import PPOCRv5Engine
        device = 'cuda' if settings.is_gpu_enabled() else 'cpu'
        engine = PPOCRv5Engine()
        engine.initialize(device=device)
        return engine

    @staticmethod
    def _create_paddle_ocr(settings) -> OCREngine:
        from .paddle_ocr import PaddleOCREngine
        engine = PaddleOCREngine()
        engine.initialize()
        return engine
        
    
    
    @staticmethod
    def _create_doctr_ocr(settings) -> OCREngine:
        from .doctr_ocr import DocTROCREngine
        device = 'cuda' if settings.is_gpu_enabled() else 'cpu'
        engine = DocTROCREngine()
        engine.initialize(device=device)
        return engine
    
    
    
    
    

    @classmethod
    def clear_cache(cls):
        """Clear the engine cache and release GPU memory safely."""
        with cls._cache_lock:
            for cache_key, engine in list(cls._engines.items()):
                if hasattr(engine, 'cleanup') and callable(getattr(engine, 'cleanup')):
                    try:
                        engine.cleanup()
                        logger.debug(f"[OCR_CACHE] cleanup() chiamato per {cache_key}")
                    except Exception as e:
                        logger.warning(f"[OCR_CACHE] Errore durante cleanup() per {cache_key}: {e}")
                
                model_attrs = ['model', 'ocr', 'reader', '_model']
                for attr in model_attrs:
                    if hasattr(engine, attr):
                        try:
                            model_obj = getattr(engine, attr)
                            if model_obj is not None:
                                if hasattr(model_obj, 'cpu'):
                                    setattr(engine, attr, model_obj.cpu())
                                del model_obj
                        except Exception as e:
                            logger.warning(f"[OCR_CACHE] Errore durante cleanup {attr} per {cache_key}: {e}")
            
            cls._engines.clear()
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                    logger.info("[OCR_CACHE] Cache OCR svuotata e memoria GPU rilasciata")
            except ImportError:
                pass
