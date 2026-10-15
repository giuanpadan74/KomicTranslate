import os
from typing import List

def get_providers(device: str = 'cpu') -> List[str]:
    """Get ONNX runtime providers based on device."""
    if device.lower() == 'cuda':
        providers = ['CUDAExecutionProvider', 'CPUExecutionProvider']
    else:
        providers = ['CPUExecutionProvider']
    return providers
