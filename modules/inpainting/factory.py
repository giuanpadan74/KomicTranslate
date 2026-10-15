import os
import gc
from typing import TYPE_CHECKING, Dict, Optional

if TYPE_CHECKING:
    from .base import InpaintModel  # imported only for type checkers, not at runtime

# Lazy imports: torch and model classes are only loaded when first needed (cold-start fix)
def _get_static_models():
    from .lama import LaMa
    from .mi_gan import MIGAN
    from .aot import AOT
    from .fast_clean import FastClean
    return {
        'lama': LaMa,
        'mi-gan': MIGAN,
        'aot': AOT,
        'fast_clean': FastClean
    }

class InpainterFactory:
    """
    Factory class for creating inpainter instances
    Handles only static offline models (LaMa, MI-GAN, AOT, ZITS)
    """
    
    _cache = {}
    _static_models = None  # populated lazily on first access

    @classmethod
    def _get_models(cls):
        if cls._static_models is None:
            cls._static_models = _get_static_models()
        return cls._static_models
    
    @classmethod
    def get_inpainter(cls, model_name: str, device: str = 'cpu', **kwargs) -> 'InpaintModel':
        """
        Get inpainter instance for the specified model

        Args:
            model_name: Name of the inpainting model
            device: Device to run on ('cpu' or 'cuda')
            **kwargs: Additional parameters for model initialization

        Returns:
            InpaintModel instance
        """
        from loguru import logger
        from .lama import LaMa  # Import here to avoid circular imports
        cache_key = f"{model_name}_{device}"

        logger.info(f"[FACTORY] get_inpainter chiamato: model_name={model_name}, device={device}, cache_key={cache_key}")

        # Return cached instance if available
        if cache_key in cls._cache:
            instance = cls._cache[cache_key]
            logger.info(f"[FACTORY] Istanza in cache trovata: {type(instance).__name__}, hasattr model={hasattr(instance, 'model')}")
            # Verify LaMa instances have the model attribute
            if isinstance(instance, LaMa) and not hasattr(instance, 'model'):
                logger.warning(f"[FACTORY] WARNING: Cached LaMa instance is corrupted (no model), recreating")
                del cls._cache[cache_key]
                logger.info(f"[FACTORY] Istanza corrotta rimossa dalla cache")
            else:
                logger.info(f"[FACTORY] Ritorno istanza cached")
                return instance

        logger.info(f"[FACTORY] Nessuna istanza valida in cache, creo nuova istanza")

        # Normalize name: lowercase and spaces to underscores
        name_key = model_name.lower().replace(" ", "_")

        static_models = cls._get_models()
        # Check if it's a static offline model
        if name_key in static_models:
            inpainter_class = static_models[name_key]
            instance = inpainter_class(device, **kwargs)
            cls._cache[cache_key] = instance
            return instance

        # Fallback to LaMa if model not found
        logger.warning(f"[FACTORY] WARNING: Model {model_name} not found, falling back to LaMa")
        fallback_key = f"lama_{device}"
        if fallback_key not in cls._cache:
            cls._cache[fallback_key] = LaMa(device, **kwargs)
        return cls._cache[fallback_key]
    
    @classmethod
    def is_model_available(cls, model_name: str) -> bool:
        """
        Check if a model is available for inpainting
        
        Args:
            model_name: Name of the model to check
            
        Returns:
            True if model is available, False otherwise
        """
        # Normalize name key
        name_key = model_name.lower().replace(" ", "_")
        # Check only static offline models (use known names to avoid triggering torch load)
        return name_key in {'lama', 'mi-gan', 'aot', 'fast_clean'}
    
    @classmethod
    def get_available_models(cls) -> Dict[str, str]:
        """
        Get all available inpainting models
        
        Returns:
            Dictionary mapping model names to their types
        """
        nice_names = {
            'lama': 'LaMa',
            'aot': 'AOT',
            'mi-gan': 'MI-GAN',
            'fast_clean': 'Fast Clean'
        }
        return {display: 'static' for display in nice_names.values()}
    
    @classmethod
    def clear_cache(cls):
        """
        Clear the inpainter cache and release GPU memory
        """
        # Properly release model resources before clearing cache
        for cache_key, instance in cls._cache.items():
            if hasattr(instance, 'model'):
                try:
                    # Move model to CPU and delete to free GPU memory
                    if hasattr(instance.model, 'cpu'):
                        instance.model.cpu()
                    del instance.model
                except Exception:
                    pass
            if hasattr(instance, 'generator'):
                try:
                    if hasattr(instance.generator, 'cpu'):
                        instance.generator.cpu()
                    del instance.generator
                except Exception:
                    pass
        
        cls._cache.clear()
        # Force garbage collection to release GPU memory
        gc.collect()
        try:
            import torch
            if hasattr(torch, 'cuda') and torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass
        print("[INFO] Inpainter cache cleared and GPU memory released")