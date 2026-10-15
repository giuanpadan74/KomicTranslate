from typing import List, Dict, Optional

from modules.utils.model_manager import model_manager


class ServiceMixin:
    
    def get_credential_services_dynamic(self):
        supported_providers = [
            "OpenAI", "Anthropic", "Google", "DeepSeek", "Cerebras",
            "DeepL", "Alibaba", "Geminiamo"
        ]
        return supported_providers

    def get_service_definitions(self):
        return {
            "ocr_services": {"Default": {"type": "traditional", "category": "ocr"}},
            "translation_services": {},
            "multimodal_keywords": ["gpt", "claude-3", "claude-4", "gemini", "qwen", "vision", "vl"],
            "recommended_models": {
                "DeepL": {"icon": "⭐", "label": "Migliore", "families": ["deepl"], "category": "translation"},
                "Google Translate": {"icon": "⚡", "label": "Veloce", "families": ["google"], "category": "translation"},
                "GPT-4.1": {"icon": "⭐", "label": "Migliore", "families": ["openai", "gpt"]},
                "GPT-4o": {"icon": "⚡", "label": "Veloce", "families": ["openai", "gpt"]},
                "GPT-4o mini": {"icon": "💰", "label": "Economico", "families": ["openai", "gpt"]},
                "GPT-4.1-mini": {"icon": "💰", "label": "Economico", "families": ["openai", "gpt"]},
                "Claude-4-Opus": {"icon": "⭐", "label": "Migliore", "families": ["anthropic", "claude"]},
                "Claude-3.7-Sonnet": {"icon": "⚡", "label": "Veloce", "families": ["anthropic", "claude"]},
                "Claude-3.5-Haiku": {"icon": "💰", "label": "Economico", "families": ["anthropic", "claude"]},
                "Claude-3-Opus": {"icon": "🔄", "label": "Stabile", "families": ["anthropic", "claude"]},
                "Gemini-2.5-Pro": {"icon": "⭐", "label": "Migliore", "families": ["google", "gemini"]},
                "Gemini-2.5-Flash": {"icon": "⚡", "label": "Veloce", "families": ["google", "gemini"]},
                "Qwen2.5-Max": {"icon": "⭐", "label": "Migliore", "families": ["alibaba", "qwen"]},
                "Qwen2.5-VL-72B": {"icon": "👁️", "label": "Vision", "families": ["alibaba", "qwen"], "best_for": "ocr"},
                "Qwen3-32B": {"icon": "🧠", "label": "Ragionamento", "families": ["alibaba", "qwen"]},
                "QwQ-32B-Preview": {"icon": "🔬", "label": "Sperimentale", "families": ["alibaba", "qwen"]},
                "Deepseek-v3": {"icon": "⭐", "label": "Migliore", "families": ["deepseek"]},
            }
        }

    def get_all_services_dynamic(self, category: str) -> List[str]:
        try:
            services = []
            service_defs = self.get_service_definitions()
            
            if category == "ocr":
                services.extend(list(service_defs["ocr_services"].keys()))
                try:
                    ocr_engines = model_manager.get_ocr_engines()
                    for engine_name in ocr_engines.keys():
                        if engine_name.lower() not in [s.lower() for s in services]:
                            services.append(engine_name)
                except Exception as e:
                    print(f"Error getting dynamic OCR engines: {e}")
                    
            elif category == "translation":
                services.extend(list(service_defs["translation_services"].keys()))
                try:
                    translation_engines = model_manager.get_translation_engines()
                    for engine_name in translation_engines.keys():
                        if engine_name.lower() not in [s.lower() for s in services]:
                            services.append(engine_name)
                except Exception as e:
                    print(f"Error getting dynamic translation engines: {e}")
                    
            elif category == "inpainting":
                try:
                    from modules.inpainting.factory import InpainterFactory
                    static_models = InpainterFactory.get_available_models()
                    services.extend(list(static_models.keys()))
                except Exception as e:
                    print(f"Error getting static inpainters: {e}")
                
                try:
                    inpainting_engines = model_manager.get_inpainting_engines()
                    for engine_name in inpainting_engines.keys():
                        if engine_name.lower() not in [s.lower() for s in services]:
                            services.append(engine_name)
                except Exception as e:
                    print(f"Error getting dynamic inpainters: {e}")
                        
            return services
            
        except Exception as e:
            print(f"Error getting dynamic services for {category}: {e}")
            return []

    def is_multimodal_model(self, model_name: str, model_data: Optional[dict] = None) -> bool:
        service_defs = self.get_service_definitions()
        keywords = service_defs["multimodal_keywords"]
        model_lower = model_name.lower()
        for keyword in keywords:
            if keyword in model_lower:
                return True
        if model_data:
            description = model_data.get("description", "").lower()
            for keyword in keywords:
                if keyword in description:
                    return True
        return False

    def is_ocr_service(self, service_name: str) -> bool:
        try:
            ocr_engines = model_manager.get_ocr_engines()
            if service_name in ocr_engines:
                return True
            model_data = model_manager.get_model_data(service_name) if hasattr(model_manager, 'get_model_data') else None
            if model_data:
                provider = model_data.get("provider", "")
                description = model_data.get("description", "").lower()
                return ("ocr" in description or "vision" in description or
                       provider in ["google"] and "ocr" in service_name.lower())
        except:
            pass
        ocr_services = ["Default"]
        return service_name in ocr_services

    def format_service_name(self, service_name: str, category: str) -> str:
        return service_name

    def get_supported_translators(self) -> List[str]:
        from modules.browser_sites import site_labels
        services = self.get_all_services_dynamic("translation")
        services.sort(key=str.lower)
        formatted_services = [self.format_service_name(s, "translation") for s in services]
        # I siti browser (Gemini, Dola...) vengono dal registro, non da qui:
        # aggiungerne uno significa creare il file in modules/browser_sites/.
        base_list = [self.tr(l) for l in site_labels()]
        base_list += [self.tr(s) for s in formatted_services]
        return base_list

    def get_supported_translators_grouped(self) -> Dict[str, List[str]]:
        """Traduttori raggruppati: siti browser da un lato, engine veri dall'altro."""
        from modules.browser_sites import site_labels, GROUP_LABEL
        services = self.get_all_services_dynamic("translation")
        services.sort(key=str.lower)

        browser_group = [self.tr(l) for l in site_labels()]
        txt_group = list(browser_group)

        for service_name in services:
            formatted_tr = self.tr(self.format_service_name(service_name, "translation"))
            provider = ""
            try:
                engines = model_manager.get_translation_engines()
                if service_name in engines:
                    provider = (engines[service_name].get('provider') or '').lower()
            except Exception:
                pass
            if not provider:
                try:
                    model_data = model_manager.get_model_data(service_name) if hasattr(model_manager, 'get_model_data') else None
                    if model_data:
                        provider = (model_data.get('provider') or '').lower()
                except Exception:
                    pass

            # Rimane solo geminiamo (cookie del browser, nessuna API key)
            if provider == 'geminiamo':
                txt_group.append(formatted_tr)

        return {
            self.tr(GROUP_LABEL): browser_group,
            self.tr("── Geminiamo (cookie Firefox) ──"): txt_group[len(browser_group):],
        }
    
    def get_supported_ocr_engines(self) -> List[str]:
        services = self.get_all_services_dynamic("ocr")
        services.sort(key=str.lower)
        formatted_services = [self.format_service_name(s, "ocr") for s in services]
        return [self.tr(s) for s in formatted_services]
    
    def get_supported_inpainters(self) -> List[str]:
        services = self.get_all_services_dynamic("inpainting")
        services.sort(key=str.lower)
        formatted_services = [self.format_service_name(s, "inpainting") for s in services]
        return [self.tr(s) for s in formatted_services]

    def get_value_mappings_dynamic(self) -> Dict:
        from modules.browser_sites import SITES, LEGACY_KEYS
        # Chiavi dei siti browser + le chiavi legacy (es. 'TXT' -> 'Gemini'),
        # cosi' un config salvato prima della rinomina continua a risolversi.
        mappings = dict(LEGACY_KEYS)
        for _k in SITES:
            mappings[_k] = _k
        mappings.update({
            "English": "English", "한국어": "한국어", "Français": "Français",
            "日本語": "日本語", "简体中文": "简体中文", "繁體中文": "繁體中文",
            "русский": "русский", "Deutsch": "Deutsch", "Nederlands": "Nederlands",
            "Español": "Español", "Italiano": "Italiano", "Türkçe": "Türkçe",
            self.tr("Dark"): "Dark", self.tr("Light"): "Light",
            "LaMa": "LaMa", "AOT": "AOT",
            self.tr("Resize"): "Resize", self.tr("Original"): "Original", self.tr("Crop"): "Crop",
            self.tr("Left"): "Left", self.tr("Center"): "Center", self.tr("Right"): "Right",
        })
        
        for service in self.get_all_services_dynamic("translation"):
            if ':free' in service:
                mappings[self.tr(service)] = service
                mappings[service] = service
            else:
                normalized_service = service.replace(':free', '')
                mappings[self.tr(service)] = normalized_service
                mappings[service] = normalized_service
        
        for service in self.get_all_services_dynamic("ocr"):
            if ':free' in service:
                mappings[self.tr(service)] = service
                mappings[service] = service
            else:
                normalized_service = service.replace(':free', '')
                mappings[self.tr(service)] = normalized_service
                mappings[service] = normalized_service
        
        for service in self.get_all_services_dynamic("inpainting"):
            mappings[self.tr(service)] = service
            mappings[service] = service
        
        return mappings

    def get_service_metadata(self, service_name: str) -> dict:
        service_defs = self.get_service_definitions()
        for category in ["ocr_services", "translation_services"]:
            if service_name in service_defs[category]:
                return service_defs[category][service_name]
        if service_name in service_defs["recommended_models"]:
            return service_defs["recommended_models"][service_name]
        try:
            if hasattr(model_manager, 'get_model_data'):
                return model_manager.get_model_data(service_name)
        except:
            pass
        return {"type": "unknown", "category": "unknown"}
    
    def get_provider_from_service(self, service: str) -> Optional[str]:
        try:
            model_data = model_manager.get_model_data(service) if hasattr(model_manager, 'get_model_data') else None
            if model_data and 'provider' in model_data:
                provider = model_data['provider'].lower()
                provider_mapping = {
                    "openai": "OpenAI", "anthropic": "Anthropic", "google": "Google",
                    "alibaba": "Alibaba", "deepseek": "DeepSeek", "deepl": "DeepL",
                }
                return provider_mapping.get(provider)
        except:
            pass
        
        service_lower = service.lower()
        if "openai" in service_lower or "gpt" in service_lower:
            return "OpenAI"
        elif "claude" in service_lower or "anthropic" in service_lower:
            return "Anthropic"
        elif "gemini" in service_lower or "google" in service_lower:
            return "Google"
        elif "qwen" in service_lower or "alibaba" in service_lower:
            return "Alibaba"
        elif "deepseek" in service_lower:
            return "DeepSeek"
        elif "deepl" in service_lower:
            return "DeepL"
        return None

    def _normalize_service_name(self, service: str) -> str:
        provider_mapping = {
            "openai": "OpenAI", "anthropic": "Anthropic", "google": "Google",
            "alibaba": "Alibaba", "deepseek": "DeepSeek", "deepl": "DeepL",
        }
        if service in provider_mapping.values():
            return service
        service_mapping = {"Qwen": "Alibaba"}
        return service_mapping.get(service, service)

    def _get_service_url(self, service: str) -> str:
        dynamic_url = self._get_service_url_dynamic(service)
        if dynamic_url != "https://openrouter.ai/settings/keys":
            return dynamic_url
        service_urls = {
            "OpenAI": "https://openrouter.ai/settings/keys",
            "Anthropic": "https://openrouter.ai/settings/keys",
            "Alibaba": "https://openrouter.ai/settings/keys",
            "DeepSeek": "https://openrouter.ai/settings/keys",
            "DeepL": "https://www.deepl.com/pro-api",
            "Google": "https://aistudio.google.com/app/apikey",
            self.tr("DeepL"): "https://www.deepl.com/pro-api",
            self.tr("Google Gemini"): "https://aistudio.google.com/app/apikey",
        }
        return service_urls.get(service, "https://openrouter.ai/settings/keys")
    
    def _get_service_url_dynamic(self, service: str) -> str:
        try:
            provider_urls = {
                "OpenAI": "https://openrouter.ai/settings/keys",
                "Anthropic": "https://openrouter.ai/settings/keys",
                "Alibaba": "https://openrouter.ai/settings/keys",
                "DeepSeek": "https://openrouter.ai/settings/keys",
                "Google": "https://aistudio.google.com/app/apikey",
                "DeepL": "https://www.deepl.com/pro-api",
                "Cerebras": "https://cloud.cerebras.ai/",
            }
            if service in provider_urls:
                return provider_urls[service]
            model_data = model_manager.get_model_data(service)
            if model_data:
                provider = model_data.get("provider", "")
                openrouter_providers = {
                    "openai": "https://openrouter.ai/settings/keys",
                    "anthropic": "https://openrouter.ai/settings/keys",
                    "alibaba": "https://openrouter.ai/settings/keys",
                    "deepseek": "https://openrouter.ai/settings/keys"
                }
                direct_providers = {
                    "google": "https://aistudio.google.com/app/apikey",
                    "deepl": "https://www.deepl.com/pro-api",
                }
                if provider.lower() in openrouter_providers:
                    return openrouter_providers[provider.lower()]
                elif provider.lower() in direct_providers:
                    return direct_providers[provider.lower()]
        except Exception as e:
            print(f"Error getting service URL for {service}: {e}")
        return "https://openrouter.ai/settings/keys"
