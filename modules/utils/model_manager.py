import json
from modules.utils.secret_utils import mask_key
import os
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from pathlib import Path

current_file_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(current_file_dir, '..', '..'))

class ModelStatus(Enum):
    """Stato di disponibilita' di un modello (UI dropdown inpainter)."""
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"
    ERROR = "error"

@dataclass
class ModelInfo:
    """Info modello per la UI (usata da update_inpainter_models)."""
    name: str
    version: str
    description: str
    status: ModelStatus
    last_checked: float
    error_message: Optional[str] = None
    capabilities: Optional[Dict[str, Any]] = None

class ModelManager:
    _instance = None
    _initialized = False
    
    def __new__(cls, config_path: str = None):
        """Singleton pattern per garantire una sola istanza."""
        if cls._instance is None:
            cls._instance = super(ModelManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, config_path: str = None):
        if ModelManager._initialized:
            return
        
        if config_path is None:
            config_path = os.path.join(PROJECT_ROOT, 'config', 'models.json')
        elif not os.path.isabs(config_path):
            config_path = os.path.join(PROJECT_ROOT, config_path)
        
        self.config_path = Path(config_path)
        self.models = {}
        self.metadata = {}
        self._synced = False
        self._models_loaded = False
        ModelManager._initialized = True
    
    def load_models(self) -> None:
        """Load models from configuration file (lazy initialization)."""
        # Evita caricamenti multipli
        if self._models_loaded:
            return
            
        self._models_loaded = True
        
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.models = data.get('models', {})
                    self.metadata = data.get('metadata', {})
            else:
                self._create_default_config()
            
            # Ensure Geminiamo is present
            if 'geminiamo' not in self.models:
                self.models['geminiamo'] = {
                    'api_name': 'geminiamo',
                    'provider': 'geminiamo',
                    'status': 'active',
                    'description': 'Geminiamo - Free Gemini integration via browser cookies',
                    'capabilities': ['ocr', 'translation', 'chat'],
                    'context_length': 8192
                }
        except Exception as e:
            print(f"Error loading models: {e}")
            self._create_default_config()
    
    def _ensure_loaded(self) -> None:
        """Ensure models are loaded before accessing them."""
        if not self._models_loaded:
            self.load_models()
    
    def save_models(self) -> None:
        """Save models to configuration file."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                'models': self.models,
                'metadata': {
                    **self.metadata,
                    'last_updated': datetime.now().isoformat()[:10]
                }
            }
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving models: {e}")
    
    def get_model_map(self) -> Dict[str, str]:
        """Get the current model mapping for translator_utils."""
        self._ensure_loaded()  # Lazy load
        model_map = {}
        for name, info in self.models.items():
            if info.get('status') == 'active':
                # Usa 'api_name' se disponibile, altrimenti usa il nome del modello come fallback
                if 'api_name' in info:
                    model_map[name] = info['api_name']
                else:
                    print(f"[WARNING] Modello '{name}' non ha 'api_name', uso il nome come fallback")
                    model_map[name] = name
        return model_map
    
    def get_active_models(self) -> List[str]:
        """Get list of active model names."""
        self._ensure_loaded()  # Lazy load
        # Non sincronizza automaticamente - restituisce solo i modelli già caricati
        return [
            name for name, info in self.models.items() 
            if info.get('status') == 'active'
        ]

    def check_models_availability(self, model_names: List[str]) -> List[str]:
        """
        Checks if the specified models are still available from providers.
        Returns a list of model names (display names) that are no longer available.
        """
        if not model_names:
            return []
            
        unavailable = []
        providers_to_check = set()
        model_to_api_name = {}
        model_to_provider = {}
        
        # Identify models and their providers
        for display_name in model_names:
            if not display_name:
                continue
                
            model_info = self.models.get(display_name)
            
            # If not found by name, try to find by api_name
            if not model_info:
                for name, info in self.models.items():
                    if info.get('api_name') == display_name:
                        display_name = name
                        model_info = info
                        break
            
            if model_info:
                provider = model_info.get('provider')
                api_name = model_info.get('api_name')
                
                # We only check online providers
                if provider and provider not in ['local', 'custom', 'unknown']:
                    providers_to_check.add(provider)
                    model_to_api_name[display_name] = api_name
                    model_to_provider[display_name] = provider
                elif provider == 'local':
                    # Local models are always considered available if they are in the config
                    pass
            else:
                # Model not found in local configuration at all
                unavailable.append(display_name)

        # For each provider involved, fetch currently available models
        all_available_api_names = set()
        for provider in providers_to_check:
            try:
                # Reuse existing fetch logic
                available_models = self._fetch_provider_models(provider)
                if available_models:
                    for m_info in available_models.values():
                        api_id = m_info.get('api_name') or m_info.get('id')
                        if api_id:
                            all_available_api_names.add(api_id)
                else:
                    print(f"[MODEL CHECK] Could not fetch models for provider {provider}, skipping check for this provider")
                    # If we can't fetch models (network error, auth error), we don't mark as unavailable
                    # to avoid false positives during offline starts.
                    for name, p in model_to_provider.items():
                        if p == provider:
                            if name in model_to_api_name:
                                del model_to_api_name[name]
            except Exception as e:
                print(f"[MODEL CHECK] Error verifying provider {provider}: {e}")
                continue

        # Final check: is the api_name in the list of available models from the provider?
        for display_name, api_name in model_to_api_name.items():
            if api_name not in all_available_api_names:
                # Special case: if it's a known model but prefix changed (e.g. google/ vs no prefix)
                found_with_variant = False
                for available_api in all_available_api_names:
                    if api_name in available_api or available_api in api_name:
                        found_with_variant = True
                        break
                
                if not found_with_variant:
                    unavailable.append(display_name)
                
        return sorted(list(set(unavailable)))
    
    
    def force_sync(self) -> Dict[str, List[str]]:
        """Forza la sincronizzazione manuale dei modelli (chiamata dal pulsante refresh)."""
        print("[DEBUG] Eseguendo sincronizzazione manuale dei modelli...")
        try:
            results = self.sync_and_check_models()
            self._synced = True
            return results
        except Exception as e:
            print(f"Errore durante la sincronizzazione manuale: {e}")
            return {'new_models': [], 'updated_models': [], 'deprecated_models': [], 'provider_details': {}}
    
    def get_models_by_provider(self, provider: str) -> List[str]:
        """Get models by provider."""
        self._ensure_loaded()  # Lazy load
        # Non sincronizza automaticamente - restituisce solo i modelli già caricati
        return [
            name for name, info in self.models.items() 
            if info.get('provider') == provider and info.get('status') == 'active'
        ]
    
    def get_model_data(self, model_name: str) -> Optional[Dict]:
        """Get complete data for a specific model."""
        self._ensure_loaded()  # Lazy load
        return self.models.get(model_name)

    def get_max_output_tokens(self, model_name: str, fallback: int = 4000) -> int:
        """
        Restituisce il limite di token di OUTPUT per un modello.

        Sorgenti consultate nell'ordine:
        1. Campo 'max_output_tokens' in models.json (impostato dall'utente o dal sync)
        2. Tabella built-in per i modelli hardcoded nell'app
        3. Fallback conservativo (default 4000)

        Args:
            model_name: Nome del modello (translator_key)
            fallback:   Valore usato se il modello è sconosciuto

        Returns:
            int: max token di output da usare per il budget dello Smart Batching
        """
        self._ensure_loaded()

        # 1. Cerca in models.json (include modelli aggiunti dall'utente)
        model_data = self.models.get(model_name)
        if model_data and 'max_output_tokens' in model_data:
            value = model_data['max_output_tokens']
            if isinstance(value, int) and value > 0:
                return value

        # 2. Tabella built-in per i modelli hardcoded nel codice dell'app
        #    (nomi usati come translator_key in processor.py)
        BUILTIN_LIMITS = {
            # ── Gemini (via API Key) ──────────────────────────────────────
            "Gemini-2.0-Flash":         8192,
            "Gemini-2.5-Flash":         65536,
            "Gemini-2.0-Pro":           8192,
            # ── Geminiamo (reverse-engineered, stima conservativa) ────────
            "Geminiamo":                2000,
            "geminiamo":                2000,
            # ── OpenAI ────────────────────────────────────────────────────
            "GPT-4o":                   4096,
            "GPT-4o mini":              4096,
            # ── Anthropic ─────────────────────────────────────────────────
            "Claude-3-Opus":            4096,
            "Claude-3.7-Sonnet":        8192,
            "Claude-3.5-Haiku":         8192,
            # ── DeepSeek ──────────────────────────────────────────────────
            "Deepseek-v3":              8192,
            # ── Alibaba / OpenRouter ──────────────────────────────────────
            "Qwen2.5 VL 72B Instruct (free)": 8192,
        }
        if model_name in BUILTIN_LIMITS:
            return BUILTIN_LIMITS[model_name]

        # 3. Fallback conservativo
        return fallback

    def add_model(self, name: str, api_name: str, provider: str, 
                  description: str = "", release_date: str = None) -> bool:
        """Add a new model."""
        try:
            self.models[name] = {
                'api_name': api_name,
                'provider': provider,
                'status': 'active',
                'release_date': release_date,
                'description': description
            }
            self.save_models()
            return True
        except Exception as e:
            print(f"Error adding model {name}: {e}")
            return False
    
    def remove_model(self, name: str) -> bool:
        """Remove a model."""
        print(f"[DEBUG] model_manager.remove_model called with name: {name}")
        print(f"[DEBUG] Current models in self.models: {list(self.models.keys())}")
        
        try:
            if name in self.models:
                print(f"[DEBUG] Model {name} found in models, removing...")
                del self.models[name]
                print(f"[DEBUG] Model {name} deleted from models dict")
                self.save_models()
                print(f"[DEBUG] Models saved successfully")
                return True
            else:
                print(f"[DEBUG] Model {name} NOT found in models")
                return False
        except Exception as e:
            print(f"[DEBUG] Exception in remove_model: {e}")
            print(f"Error removing model {name}: {e}")
            return False
    
    def update_model_status(self, name: str, status: str) -> bool:
        """Update model status (active, deprecated, removed)."""
        try:
            if name in self.models:
                self.models[name]['status'] = status
                self.save_models()
                return True
            return False
        except Exception as e:
            print(f"Error updating model {name}: {e}")
            return False
    
    def get_deprecated_models(self) -> List[str]:
        """Get list of deprecated models."""
        return [
            name for name, info in self.models.items() 
            if info.get('status') == 'deprecated'
        ]
    
    def cleanup_deprecated_models(self) -> int:
        """Remove deprecated models and return count of removed models."""
        deprecated = self.get_deprecated_models()
        for model in deprecated:
            del self.models[model]
        if deprecated:
            self.save_models()
        return len(deprecated)
    
    
    
    
    def get_ocr_engines(self):
        """Get available OCR engines from models."""
        self._ensure_loaded()  # Lazy load
        ocr_engines = {}
        
        for model_name, model_data in self.models.items():
            if self.is_ocr_capable(model_data):
                ocr_engines[model_name] = {
                    'provider': model_data.get('provider'),
                    'model_id': model_data.get('api_name'),  # Corretto: usa api_name invece di model_id
                    'engine_type': self.determine_ocr_engine_type(model_data),
                    'api_base': model_data.get('api_base', ''),
                    'capabilities': model_data.get('capabilities', []),
                    'max_tokens': model_data.get('max_tokens', 4096)
                }
        
        return ocr_engines
    
    def is_ocr_capable(self, model_data):
        """Check if model supports OCR/vision tasks."""
        description = model_data.get('description', '').lower()
        capabilities = model_data.get('capabilities', [])
        # Usa 'api_name' invece di 'model_id' che non esiste
        api_name = model_data.get('api_name', '').lower()
        provider = model_data.get('provider', '').lower()
        
        # Criteri per identificare modelli OCR
        vision_keywords = ['vision', 'ocr', 'multimodal', 'image']
        model_keywords = ['gpt-4', 'claude-3', 'claude-4', 'gemini', 'gpt-4o']
        
        # Geminiamo support
        if provider == 'geminiamo':
            return True
        
        # Check specifico per Qwen/Alibaba per evitare falsi positivi con modelli solo testo
        # Richiede esplicitamente 'vl', 'vision' o 'ocr' nel nome se è un modello Qwen
        is_qwen_multimodal = 'qwen' in api_name and ('vl' in api_name or 'vision' in api_name or 'ocr' in api_name)
        
        # DISABLED: Replicate support removed - using only offline models
        # Replicate models no longer supported for OCR/inpainting
        
        return (any(keyword in description for keyword in vision_keywords) or
                'vision' in capabilities or
                'multimodal' in capabilities or
                'ocr' in capabilities or
                is_qwen_multimodal or
                any(keyword in api_name for keyword in model_keywords))
    
    def determine_ocr_engine_type(self, model_data):
        """Determine which OCR engine to use for this model.

        Rimangono solo engine locali (identificati a parte dalla factory)
        e geminiamo. Gli altri engine_type non esistono piu'.
        """
        provider = model_data.get('provider', '').lower()
        if provider == 'geminiamo':
            return 'geminiamo'
        return 'local'
    
    def get_ocr_credentials_key(self, model_name):
        """Chiave credenziali per un modello OCR: nessuna.

        Rimane solo geminiamo, che usa i cookie del browser; i modelli
        locali non hanno bisogno di credenziali. La funzione e' mantenuta
        per compatibilita' con i chiamanti esistenti.
        """
        return None
    
    def get_translation_engines(self):
        """Get available translation engines from models."""
        self._ensure_loaded()  # Lazy load
        translation_engines = {}
        
        for model_name, model_data in self.models.items():
            if self.is_translation_capable(model_data):
                translation_engines[model_name] = {
                    'provider': model_data.get('provider'),
                    'api_name': model_data.get('api_name'),
                    'engine_type': self.determine_translation_engine_type(model_data),
                    'api_base': model_data.get('api_base', ''),
                    'capabilities': model_data.get('capabilities', []),
                    'max_tokens': model_data.get('max_tokens', 4096)
                }
        
        return translation_engines
    
    def get_inpainting_engines(self):
        """Get available inpainting engines from models."""
        self._ensure_loaded()  # Lazy load
        inpainting_engines = {}
        
        for model_name, model_data in self.models.items():
            if self.is_inpainting_capable(model_data):
                inpainting_engines[model_name] = {
                    'provider': model_data.get('provider'),
                    'api_name': model_data.get('api_name'),
                    'engine_type': self.determine_inpainting_engine_type(model_data),
                    'api_base': model_data.get('api_base', ''),
                    'capabilities': model_data.get('capabilities', []),
                    'max_tokens': model_data.get('max_tokens', 4096)
                }
        
        return inpainting_engines
    
    def is_translation_capable(self, model_data):
        """Check if model supports translation tasks.

        Unico modello di traduzione rimasto: geminiamo. I modelli locali
        (OCR, inpainting) non sono traduttori.
        """
        provider = model_data.get('provider', '').lower()
        if provider == 'geminiamo':
            return True

        capabilities = model_data.get('capabilities', []) or []
        if 'translation' in capabilities:
            return True

        return False
    
    def determine_translation_engine_type(self, model_data):
        """Determine which translation engine to use for this model.

        Rimane solo geminiamo (cookie del browser). Tutti gli altri engine
        online sono stati rimossi insieme allo strato LLM.
        """
        provider = model_data.get('provider', '').lower()
        if provider == 'geminiamo':
            return 'geminiamo'
        return 'custom'
    
    def get_translation_credentials_key(self, model_name):
        """Chiave credenziali per un modello di traduzione: nessuna.

        Rimane solo geminiamo, che usa i cookie del browser e non ha bisogno
        di API key. La funzione resta per compatibilita' con i chiamanti.
        """
        return None
    
    def is_inpainting_capable(self, model_data):
        """Check if model supports inpainting tasks - only local models."""
        provider = model_data.get('provider', '').lower()
        
        # Solo modelli locali supportano inpainting
        if provider != 'local':
            return False
        
        capabilities = model_data.get('capabilities', [])
        
        # Controlla se ha capability esplicita di inpainting
        if 'inpainting' in capabilities:
            return True
        
        # Controlla se ha capability di image generation (può fare inpainting)
        if 'image_generation' in capabilities:
            return True
        
        return False
    
    def determine_inpainting_engine_type(self, model_data):
        """Determine the type of inpainting engine based on model data - only local models."""
        provider = model_data.get('provider', '').lower()
        api_name = model_data.get('api_name', '').lower()
        
        # Solo modelli locali supportati
        if provider == 'local':
            if 'lama' in api_name:
                return 'lama'

            elif 'aot' in api_name:
                return 'aot'
            elif 'inpaint' in api_name:
                return 'inpainting_specialized'
            else:
                return 'local_image'
        else:
            return 'unsupported'
    
    def get_inpainting_credentials_key(self, model_data):
        """Get the credentials key for inpainting model - only local models supported."""
        provider = model_data.get('provider', '').lower()
        
        # Solo modelli locali supportati, non servono credenziali
        if provider == 'local':
            return None
        else:
            return None  # Nessun supporto per modelli online
    
    def _create_default_config(self) -> None:
        """Create default configuration with current models including local inpainting models."""
        # Includi sempre i modelli locali di inpainting per evitare dipendenze dalla sincronizzazione
        self.models = {
            'LaMa': {
                'api_name': 'LaMa',
                'provider': 'local',
                'status': 'active',
                'description': 'LaMa - Large Mask Inpainting model for local processing (offline)',
                'capabilities': ['inpainting', 'image_editing'],
                'context_length': 1024
            },

            # Removed 'lama' with 'replicate' provider - using only offline models

            'aot': {
                'api_name': 'aot',
                'provider': 'local',
                'status': 'active',
                'description': 'AOT - Aggregated Contextual Transformations for inpainting',
                'capabilities': ['inpainting', 'image_editing'],
                'context_length': 1024
            },

        }
        self.metadata = {
            "last_updated": datetime.now().isoformat()[:10],
            "version": "1.0.0"
        }
        self.save_models()

    
    
    
    def update_model_capabilities(self, compatibility_results: Dict) -> int:
        """Update model capabilities based on compatibility check."""
        updated_count = 0
        
        provider_analysis = compatibility_results.get('provider_analysis', {})
        
        # Gestisci il nuovo formato semplificato
        if 'ocr_compatible' in provider_analysis and 'translation_compatible' in provider_analysis:
            # Nuovo formato: provider_analysis contiene direttamente le liste
            ocr_models = provider_analysis.get('ocr_compatible', [])
            translation_models = provider_analysis.get('translation_compatible', [])
            
            # Aggiorna modelli OCR
            for model_name in ocr_models:
                if self._add_capability_if_missing(model_name, 'vision'):
                    updated_count += 1
                if self._add_capability_if_missing(model_name, 'multimodal'):
                    updated_count += 1
            
            # Aggiorna modelli traduzione
            for model_name in translation_models:
                if self._add_capability_if_missing(model_name, 'translation'):
                    updated_count += 1
        else:
            # Formato originale: provider_analysis contiene analisi per provider
            for provider, analysis in provider_analysis.items():
                if isinstance(analysis, dict):
                    # Aggiorna modelli OCR
                    ocr_compatible = analysis.get('ocr_compatible', [])
                    for model_name in ocr_compatible:
                        if self._add_capability_if_missing(model_name, 'vision'):
                            updated_count += 1
                        if self._add_capability_if_missing(model_name, 'multimodal'):
                            updated_count += 1
                    
                    # Aggiorna modelli traduzione
                    translation_compatible = analysis.get('translation_compatible', [])
                    for model_name in translation_compatible:
                        if self._add_capability_if_missing(model_name, 'translation'):
                            updated_count += 1
                    
                    # Rimuovi capabilities errate (es. vision da Claude-3.5-Haiku-20241022)
                    issues = analysis.get('issues', [])
                    for issue in issues:
                        if "Should support OCR but missing" not in issue:
                            # Questo è un modello che NON dovrebbe supportare OCR
                            model_name = issue.split(':')[0]
                            if self._remove_capability_if_present(model_name, 'vision'):
                                updated_count += 1
                            if self._remove_capability_if_present(model_name, 'multimodal'):
                                updated_count += 1
        
        if updated_count > 0:
            self.save_models()
        
        return updated_count
    
    def _add_capability_if_missing(self, model_name: str, capability: str) -> bool:
        """Add capability to model if missing."""
        if model_name in self.models:
            capabilities = self.models[model_name].get('capabilities', [])
            if capability not in capabilities:
                capabilities.append(capability)
                self.models[model_name]['capabilities'] = capabilities
                return True
        return False
    
    def _remove_capability_if_present(self, model_name: str, capability: str) -> bool:
        """Remove capability from model if present."""
        if model_name in self.models:
            capabilities = self.models[model_name].get('capabilities', [])
            if capability in capabilities:
                capabilities.remove(capability)
                self.models[model_name]['capabilities'] = capabilities
                return True
        return False
    
    
    
    
    

    
    
    
    
    
    
    
    
    # DISABLED: Replicate support removed - using only offline models
    # def _fetch_replicate_models(self) -> Dict[str, Dict]:
    #     """Fetch Replicate models - DISABLED for offline-only operation"""
    #     print("[INFO] Replicate model fetching disabled - using only offline models")
    #     return None
    
    # DISABLED: Replicate validation removed - using only offline models
    # def _validate_replicate_model(self, full_name: str, headers: dict, strict_validation: bool = False) -> bool:
    #     """Validate Replicate model - DISABLED for offline-only operation"""
    #     print(f"[INFO] Replicate model validation disabled for {full_name}")
    #     return False
    
    
    
    def _generate_model_name(self, provider: str, api_name: str, model_info: Dict) -> str:
        """Generate a suggested name for a new model."""
        # Rimuovi prefissi comuni
        clean_name = api_name
        if '/' in clean_name:
            clean_name = clean_name.split('/')[-1]
        
        # Aggiungi suffisso se necessario per evitare conflitti
        base_name = clean_name
        counter = 1
        while base_name in self.models:
            base_name = f"{clean_name}_{counter}"
            counter += 1
        
        return base_name
    
    def _model_needs_update(self, current_info: Dict, new_info: Dict) -> bool:
        """Check if a model needs updating based on metadata changes."""
        # Confronta campi chiave per determinare se serve un aggiornamento
        key_fields = ['context_length', 'pricing', 'api_name']
        
        for field in key_fields:
            current_value = current_info.get(field)
            new_value = new_info.get(field)
            
            try:
                # Gestione sicura del confronto per evitare errori con tipi non hashable
                if isinstance(current_value, dict) and isinstance(new_value, dict):
                    # Confronta dizionari convertendoli in stringhe ordinate
                    if str(sorted(current_value.items())) != str(sorted(new_value.items())):
                        return True
                elif current_value != new_value:
                    return True
            except TypeError:
                # Fallback per tipi non confrontabili - considera come diversi
                return True
        
        return False


# Global instance
model_manager = ModelManager()
