import logging
import numpy as np
from .base import BaseLLMTranslation
from ...api_clients.geminiamo_client import geminiamo_client

# Configura il logger
logger = logging.getLogger(__name__)

class GeminiamoTranslation(BaseLLMTranslation):
    """Gemini Translation engine using Geminiamo (cookies)."""
    
    def __init__(self):
        super().__init__()
        self.client = geminiamo_client

    def initialize(self, settings, source_lang: str, target_lang: str, **kwargs) -> None:
        super().initialize(settings, source_lang, target_lang, **kwargs)
        self.img_as_llm_input = False

    def _perform_translation(self, user_prompt: str, system_prompt: str, image: np.ndarray) -> str:
        """
        Perform translation using Geminiamo.
        
        Args:
            user_prompt: User prompt for LLM
            system_prompt: System prompt for LLM
            image: Image as numpy array (optional)
            
        Returns:
            Translated JSON text
        """
        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        try:
            logger.info("Sending request to Geminiamo...")
            response_text = self.client.generate_content(full_prompt, image_path=None)
            
            # Extract JSON from response if needed (Gemini often wraps in markdown)
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
                
            return response_text
            
        except Exception as e:
            logger.error(f"Geminiamo translation error: {e}")
            raise

