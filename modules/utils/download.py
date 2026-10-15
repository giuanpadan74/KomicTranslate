import os, sys, hashlib
from loguru import logger
from .paths import get_models_base_dir, get_model_path

# Define a persistent base directory for all models
models_base_dir = get_models_base_dir()

# Ensure models_base_dir exists
os.makedirs(models_base_dir, exist_ok=True)

def calculate_sha256_checksum(file_path):
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read and update hash in chunks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_models(data):
    from torch.hub import download_url_to_file
    save_dir = data['save_dir']
    
    logger.info(f"[DOWNLOAD] Model download starting - save_dir: {save_dir}")
    
    if not os.path.exists(save_dir):
        os.makedirs(save_dir, exist_ok=True)
        logger.info(f"[DOWNLOAD] Created directory: {save_dir}")

    for i, file_name in enumerate(data['files']):
        file_url = f"{data['url']}{file_name}"
        file_path = os.path.join(data['save_dir'], file_name)
        expected_checksum = data['sha256_pre_calculated'][i]

        if os.path.exists(file_path):
            logger.info(f"[DOWNLOAD] File exists: {file_path}")
            if expected_checksum is not None:
                calculated_checksum = calculate_sha256_checksum(file_path)
                if calculated_checksum == expected_checksum:
                    logger.info(f"[DOWNLOAD] Checksum OK for {file_name}")
                    continue
                else:
                    logger.warning(f"[DOWNLOAD] Checksum mismatch for {file_name}. Expected {expected_checksum}, got {calculated_checksum}. Redownloading...")

        logger.info(f"[DOWNLOAD] Starting download: {file_url}")
        logger.info(f"[DOWNLOAD] Target path: {file_path}")
        
        try:
            sys.stderr.write('Downloading: "{}" to {}\n'.format(file_url, save_dir))
            download_url_to_file(file_url, file_path, hash_prefix=None, progress=True)
            logger.info(f"[DOWNLOAD] Download completed for {file_name}")
        except Exception as e:
            logger.error(f"[DOWNLOAD] Failed to download {file_name}: {e}")
            raise

        if expected_checksum:
            calculated_checksum = calculate_sha256_checksum(file_path)
            if calculated_checksum == expected_checksum:
                logger.info(f"[DOWNLOAD] Download verified successfully, sha256: {calculated_checksum}")
            else:
                try:
                    os.remove(file_path)
                    logger.error(f"[DOWNLOAD] Model sha256 mismatch: got {calculated_checksum}, expected {expected_checksum}. File deleted.")
                except:
                    logger.error(f"[DOWNLOAD] Model sha256 mismatch: got {calculated_checksum}, expected {expected_checksum}. Please delete {file_path} manually.")
                exit(-1)

# Default Models
manga_ocr_data = {
    'url': 'https://huggingface.co/kha-white/manga-ocr-base/resolve/main/',
    'files': [
        'pytorch_model.bin', 'config.json', 'preprocessor_config.json',
        'README.md', 'special_tokens_map.json', 'tokenizer_config.json', 'vocab.txt'
    ],
    'sha256_pre_calculated': [
        'c63e0bb5b3ff798c5991de18a8e0956c7ee6d1563aca6729029815eda6f5c2eb', 
        '8c0e395de8fa699daaac21aee33a4ba9bd1309cfbff03147813d2a025f39f349', 
        'af4eb4d79cf61b47010fc0bc9352ee967579c417423b4917188d809b7e048948', 
        '32f413afcc4295151e77d25202c5c5d81ef621b46f947da1c3bde13256dc0d5f', 
        '303df45a03609e4ead04bc3dc1536d0ab19b5358db685b6f3da123d05ec200e3', 
        'd775ad1deac162dc56b84e9b8638f95ed8a1f263d0f56f4f40834e26e205e266', 
        '344fbb6b8bf18c57839e924e2c9365434697e0227fac00b88bb4899b78aa594d'
    ],
    'save_dir': os.path.join(models_base_dir, 'ocr', 'manga-ocr-base')
}

comic_text_segmenter_data = {
    'url': 'https://huggingface.co/ogkalu/comic-text-segmenter-yolov8m/resolve/main/',
    'files': ['comic-text-segmenter.pt'],
    'sha256_pre_calculated': [
        'f2dded0d2f5aaa25eed49f1c34a4720f1c1cd40da8bc3138fde1abb202de625e', 
    ],
    'save_dir': os.path.join(models_base_dir, 'detection')
}

inpaint_lama_finetuned_data = {
    'url': 'https://huggingface.co/dreMaz/AnimeMangaInpainting/resolve/main/',
    'files': ['lama_large_512px.ckpt'],
    'sha256_pre_calculated': [
        "11d30fbb3000fb2eceae318b75d9ced9229d99ae990a7f8b3ac35c8d31f2c935"
    ],
    'save_dir': os.path.join(models_base_dir, 'inpainting')
}

comic_bubble_detector_data = {
    'url': 'https://huggingface.co/ogkalu/comic-speech-bubble-detector-yolov8m/resolve/main/',
    'files': ['comic-speech-bubble-detector.pt'],
    'sha256_pre_calculated': [
        '10bc9f702698148e079fb4462a6b910fcd69753e04838b54087ef91d5633097b'
    ],
    'save_dir': os.path.join(models_base_dir, 'detection')
}

pororo_data = {
    'url': 'https://twg.kakaocdn.net/pororo/ko/models/misc/',
    'files': ['craft.pt', 'brainocr.pt', 'ocr-opt.txt'],
    'sha256_pre_calculated': [
        '4a5efbfb48b4081100544e75e1e2b57f8de3d84f213004b14b85fd4b3748db17',
        '125820ba8ae4fa5d9fd8b8a2d4d4a7afe96a70c32b1aa01d4129001a6f61baec',
        'dd471474e91d78e54b179333439fea58158ad1a605df010ea0936dcf4387a8c2'
    ],
    'save_dir': os.path.join(models_base_dir, 'ocr', 'pororo')
}

manga_text_detector_data = {
    'url': 'https://huggingface.co/ogkalu/manga-text-detector-yolov8s/resolve/main/',
    'files': ['manga-text-detector.pt'],
    'sha256_pre_calculated': [
        '297447cc99c47f15ffced11bebebd88034e56f0fac6c96d9a27cd725314909a1'
    ],
    'save_dir': os.path.join(models_base_dir, 'detection')
}

mandatory_models = [comic_text_segmenter_data, inpaint_lama_finetuned_data,
                    comic_bubble_detector_data, manga_text_detector_data]

def ensure_models_downloaded(model_names: list[str]):
    """
    Verifies if the specified models exist and downloads them if missing.
    Args:
        model_names: List of model identifiers (e.g., 'lama', 'comic-speech-bubble-detector')
    """
    model_map = {
        'lama': inpaint_lama_finetuned_data,
        'comic-text-segmenter': comic_text_segmenter_data,
        'comic-speech-bubble-detector': comic_bubble_detector_data,
        'manga-text-detector': manga_text_detector_data,
        'manga-ocr': manga_ocr_data,
        'pororo': pororo_data
    }
    
    for name in model_names:
        if name in model_map:
            get_models(model_map[name])
        else:
            logger.warning(f"Unknown model requested for download: {name}")
