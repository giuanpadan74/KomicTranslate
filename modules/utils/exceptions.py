#!/usr/bin/env python3
"""
Eccezioni personalizzate per KomicTranslate.
Definisce eccezioni specifiche per diversi tipi di errori nel sistema.
"""

class KomicTranslateException(Exception):
    """Classe base per tutte le eccezioni di KomicTranslate."""
    pass

class GeminiamoSaturationError(KomicTranslateException):
    """
    Eccezione sollevata quando Geminiamo (web scraping) è saturo dopo i tentativi.
    """
    def __init__(self, message="Geminiamo web interface saturated"):
        self.message = message
        super().__init__(self.message)

class QuotaExhaustedException(KomicTranslateException):
    """
    Eccezione sollevata quando le quote API sono esaurite.
    
    Attributes:
        provider: Nome del provider API
        api_key_hint: Hint della chiave API
        quota_type: Tipo di quota esaurita ('minute', 'day', 'month')
        reset_time: Timestamp quando la quota si resetterà
        message: Messaggio di errore
    """
    
    def __init__(self, provider: str, api_key_hint: str = None, 
                 quota_type: str = "unknown", reset_time: float = None, 
                 message: str = None):
        self.provider = provider
        self.api_key_hint = api_key_hint
        self.quota_type = quota_type
        self.reset_time = reset_time
        
        if message is None:
            message = f"Quota {quota_type} esaurita per {provider}"
            if api_key_hint:
                message += f" (key: {api_key_hint})"
            if reset_time:
                import datetime
                reset_dt = datetime.datetime.fromtimestamp(reset_time)
                message += f". Reset previsto: {reset_dt.strftime('%H:%M:%S')}"
        
        self.message = message
        super().__init__(self.message)

class APIKeyException(KomicTranslateException):
    """
    Eccezione sollevata per problemi con le chiavi API.
    
    Attributes:
        provider: Nome del provider API
        api_key_hint: Hint della chiave API
        error_type: Tipo di errore ('invalid', 'expired', 'suspended')
        message: Messaggio di errore
    """
    
    def __init__(self, provider: str, api_key_hint: str = None, 
                 error_type: str = "unknown", message: str = None):
        self.provider = provider
        self.api_key_hint = api_key_hint
        self.error_type = error_type
        
        if message is None:
            message = f"Errore chiave API {error_type} per {provider}"
            if api_key_hint:
                message += f" (key: {api_key_hint})"
        
        self.message = message
        super().__init__(self.message)

class OCRException(KomicTranslateException):
    """
    Eccezione sollevata per errori nell'OCR.
    
    Attributes:
        engine: Nome del motore OCR
        stage: Fase del processing dove è avvenuto l'errore
        image_info: Informazioni sull'immagine processata
        message: Messaggio di errore
    """
    
    def __init__(self, engine: str, stage: str = "unknown", 
                 image_info: dict = None, message: str = None):
        self.engine = engine
        self.stage = stage
        self.image_info = image_info or {}
        
        if message is None:
            message = f"Errore OCR in {engine} durante {stage}"
            if 'size' in self.image_info:
                message += f" (immagine: {self.image_info['size']})"
        
        self.message = message
        super().__init__(self.message)

class TranslationException(KomicTranslateException):
    """
    Eccezione sollevata per errori nella traduzione.
    
    Attributes:
        translator: Nome del traduttore
        source_lang: Lingua sorgente
        target_lang: Lingua di destinazione
        text_preview: Anteprima del testo che ha causato l'errore
        message: Messaggio di errore
    """
    
    def __init__(self, translator: str, source_lang: str = "unknown", 
                 target_lang: str = "unknown", text_preview: str = None, 
                 message: str = None):
        self.translator = translator
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.text_preview = text_preview
        
        if message is None:
            message = f"Errore traduzione in {translator} ({source_lang} -> {target_lang})"
            if text_preview:
                preview = text_preview[:50] + "..." if len(text_preview) > 50 else text_preview
                message += f": '{preview}'"
        
        self.message = message
        super().__init__(self.message)

class TextBlockException(KomicTranslateException):
    """
    Eccezione sollevata per errori nella gestione dei textblock.
    
    Attributes:
        textblock_id: ID del textblock
        operation: Operazione che stava sendo eseguita
        textblock_data: Dati del textblock
        message: Messaggio di errore
    """
    
    def __init__(self, textblock_id: str, operation: str = "unknown", 
                 textblock_data: dict = None, message: str = None):
        self.textblock_id = textblock_id
        self.operation = operation
        self.textblock_data = textblock_data or {}
        
        if message is None:
            message = f"Errore textblock {textblock_id} durante {operation}"
        
        self.message = message
        super().__init__(self.message)

class EncodingException(KomicTranslateException):
    """
    Eccezione sollevata per errori di encoding/decoding.
    
    Attributes:
        encoding: Encoding utilizzato
        operation: Tipo di operazione ('encode', 'decode')
        text_preview: Anteprima del testo che ha causato l'errore
        message: Messaggio di errore
    """
    
    def __init__(self, encoding: str, operation: str = "unknown", 
                 text_preview: str = None, message: str = None):
        self.encoding = encoding
        self.operation = operation
        self.text_preview = text_preview
        
        if message is None:
            message = f"Errore {operation} con encoding {encoding}"
            if text_preview:
                preview = text_preview[:50] + "..." if len(text_preview) > 50 else text_preview
                message += f": '{preview}'"
        
        self.message = message
        super().__init__(self.message)

class InpaintingException(KomicTranslateException):
    """
    Eccezione sollevata per errori nell'inpainting.
    
    Attributes:
        inpainter: Nome dell'inpainter utilizzato
        stage: Fase dell'inpainting dove è avvenuto l'errore
        image_info: Informazioni sull'immagine
        message: Messaggio di errore
    """
    
    def __init__(self, inpainter: str, stage: str = "unknown", 
                 image_info: dict = None, message: str = None):
        self.inpainter = inpainter
        self.stage = stage
        self.image_info = image_info or {}
        
        if message is None:
            message = f"Errore inpainting in {inpainter} durante {stage}"
            if 'size' in self.image_info:
                message += f" (immagine: {self.image_info['size']})"
        
        self.message = message
        super().__init__(self.message)

class ConfigurationException(KomicTranslateException):
    """
    Eccezione sollevata per errori di configurazione.
    
    Attributes:
        component: Componente che ha il problema di configurazione
        config_key: Chiave di configurazione problematica
        message: Messaggio di errore
    """
    
    def __init__(self, component: str, config_key: str = None, message: str = None):
        self.component = component
        self.config_key = config_key
        
        if message is None:
            message = f"Errore configurazione in {component}"
            if config_key:
                message += f" (chiave: {config_key})"
        
        self.message = message
        super().__init__(self.message)

class ModelException(KomicTranslateException):
    """
    Eccezione sollevata per errori nei modelli AI/ML.
    
    Attributes:
        model_name: Nome del modello
        model_type: Tipo di modello ('ocr', 'translation', 'detection', etc.)
        error_stage: Fase dove è avvenuto l'errore ('loading', 'inference', etc.)
        message: Messaggio di errore
    """
    
    def __init__(self, model_name: str, model_type: str = "unknown", 
                 error_stage: str = "unknown", message: str = None):
        self.model_name = model_name
        self.model_type = model_type
        self.error_stage = error_stage
        
        if message is None:
            message = f"Errore modello {model_type} '{model_name}' durante {error_stage}"
        
        self.message = message
        super().__init__(self.message)

class NetworkException(KomicTranslateException):
    """
    Eccezione sollevata per errori di rete.
    
    Attributes:
        url: URL che ha causato l'errore
        status_code: Codice di stato HTTP (se disponibile)
        timeout: Se l'errore è dovuto a timeout
        message: Messaggio di errore
    """
    
    def __init__(self, url: str = None, status_code: int = None, 
                 timeout: bool = False, message: str = None):
        self.url = url
        self.status_code = status_code
        self.timeout = timeout
        
        if message is None:
            if timeout:
                message = "Timeout di rete"
            elif status_code:
                message = f"Errore HTTP {status_code}"
            else:
                message = "Errore di rete"
            
            if url:
                message += f" per {url}"
        
        self.message = message
        super().__init__(self.message)

# Funzioni di utilità per creare eccezioni comuni

def create_quota_exception(provider: str, api_key_hint: str = None, 
                          quota_type: str = "unknown", reset_time: float = None):
    """Crea un'eccezione per quota esaurita."""
    return QuotaExhaustedException(provider, api_key_hint, quota_type, reset_time)

def create_api_key_exception(provider: str, api_key_hint: str = None, 
                            error_type: str = "invalid"):
    """Crea un'eccezione per problemi con chiave API."""
    return APIKeyException(provider, api_key_hint, error_type)

def create_ocr_exception(engine: str, stage: str = "processing", 
                        image_info: dict = None):
    """Crea un'eccezione per errori OCR."""
    return OCRException(engine, stage, image_info)

def create_translation_exception(translator: str, source_lang: str = "unknown", 
                               target_lang: str = "unknown", text_preview: str = None):
    """Crea un'eccezione per errori di traduzione."""
    return TranslationException(translator, source_lang, target_lang, text_preview)
