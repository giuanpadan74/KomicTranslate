# Lazy import: InpainterFactory is imported on demand to avoid loading torch at startup.
# from .factory import InpainterFactory  # <- rimosso dall'avvio (cold-start fix)

# Available inpainting models
INPAINTING_MODELS = {
}

# Export all models
__all__ = ['INPAINTING_MODELS']