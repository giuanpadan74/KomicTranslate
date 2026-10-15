from .base import TranslationEngine
from .llm.geminiamo import GeminiamoTranslation
from ..browser_sites import is_browser_site



class TranslationEngineFactory:
    """Factory for creating appropriate translation engines based on settings."""
    
    _engines = {}  # Cache of created engines
    
    @classmethod
    def create_engine(cls, settings, source_lang: str, target_lang: str, translator_key: str) -> TranslationEngine:
        """
        Create or retrieve an appropriate translation engine based on settings.
        
        Args:
            settings: Settings object with translation configuration
            source_lang: Source language name
            target_lang: Target language name
            translator_key: Key identifying which translator to use
            
        Returns:
            Appropriate translation engine instance
        """
        print(f"[DEBUG] Creating translation engine for {translator_key}")
        print(f"[DEBUG] Source language: {source_lang}, Target language: {target_lang}")
        
        # Create a cache key based on translator and language pair
        cache_key = f"{translator_key}_{source_lang}_{target_lang}"
        
        # I siti "browser" (Gemini, Dola) non hanno un engine Python: vengono
        # automatizzati da modules/gemini_automator.py aprendo il sito in una
        # webview e pilotandola via JS. Qui non si crea nulla.
        if is_browser_site(translator_key):
            return None

        # Return cached engine if available
        if cache_key in cls._engines:
            print(f"[DEBUG] Using cached engine for {cache_key}")
            return cls._engines[cache_key]
        
        # Check if it's a dynamic model from Model Manager
        try:
            from ..utils.model_manager import model_manager
            translation_engines = model_manager.get_translation_engines()
            
            if translator_key in translation_engines:
                print(f"[DEBUG] Creating dynamic translation engine for {translator_key}")
                engine = cls._create_dynamic_translation_engine(settings, translator_key, source_lang, target_lang)
                cls._engines[cache_key] = engine
                return engine
            else:
                # Se il modello non è trovato, genera errore informativo
                available_models = list(translation_engines.keys())
                raise ValueError(f"Translation model '{translator_key}' not found. Available models: {available_models}")
                
        except Exception as e:
            print(f"[ERROR] Error creating translation engine: {e}")
            raise
    
    @classmethod
    def _create_dynamic_translation_engine(cls, settings, model_name: str, source_lang: str, target_lang: str):
        """Create a dynamic translation engine based on model manager data."""
        from ..utils.model_manager import model_manager
        
        translation_engines = model_manager.get_translation_engines()
        engine_info = translation_engines.get(model_name)
        
        if not engine_info:
            raise ValueError(f"No engine info found for model: {model_name}")
        
        engine_type = engine_info['engine_type']
        api_name = engine_info['api_name']

        print(f"[DEBUG] Creating dynamic engine: {engine_type}")

        # Unico engine online rimasto: Geminiamo (cookie del browser)
        if engine_type != 'geminiamo':
            raise ValueError(
                f"Translation engine_type '{engine_type}' non supportato. "
                f"Unico engine online disponibile: 'geminiamo'."
            )

        engine = cls._create_geminiamo_translation_dynamic(settings, api_name)

        if hasattr(engine, 'initialize'):
            engine.initialize(settings, source_lang, target_lang, model_name=model_name)

        return engine
    
    @staticmethod
    
    @staticmethod
    
    @staticmethod
    
    @staticmethod
    def _create_geminiamo_translation_dynamic(settings, model_name):
        """Create Geminiamo translation engine dynamically."""
        engine = GeminiamoTranslation()
        return engine

    @classmethod
    def clear_cache(cls):
        """Clear the engine cache."""
        cls._engines.clear()