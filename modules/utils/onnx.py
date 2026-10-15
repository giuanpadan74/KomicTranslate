import onnxruntime as ort
from typing import List, Optional, Any

def make_session(model_path: str, sess_options: Optional[ort.SessionOptions] = None, 
                 providers: Optional[List[str]] = None) -> ort.InferenceSession:
    """Create an ONNX Runtime inference session."""
    if sess_options is None:
        sess_options = ort.SessionOptions()
    
    if providers is None:
        # Scegli automaticamente il miglior provider disponibile
        available = ort.get_available_providers()
        if "CUDAExecutionProvider" in available:
            providers = ["CUDAExecutionProvider"]
        elif "TensorrtExecutionProvider" in available:
            providers = ["TensorrtExecutionProvider"]
        else:
            providers = ["CPUExecutionProvider"]
    else:
        # Filtra i provider richiesti per usarne uno valido
        available = ort.get_available_providers()
        providers = [p for p in providers if p in available]
        if not providers:
            providers = ["CPUExecutionProvider"]
    
    sess = ort.InferenceSession(model_path, sess_options=sess_options, providers=providers)
    return sess

def make_session_options(log_severity_level: int = 3) -> ort.SessionOptions:
    """Create ONNX Runtime session options."""
    sess_options = ort.SessionOptions()
    sess_options.log_severity_level = log_severity_level
    return sess_options
