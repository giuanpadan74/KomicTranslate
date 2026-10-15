from __future__ import annotations

from typing import Any, List, Tuple, Optional
import os
import numpy as np

from ..base import OCREngine
from modules.utils.textblock import TextBlock
from modules.utils.pipeline_utils import lists_to_blk_list
from modules.utils.device import get_providers
from .preprocessing import det_preprocess, crop_quad, rec_resize_norm
from .postprocessing import DBPostProcessor, CTCLabelDecoder


LANG_TO_REC_MODEL: dict[str, str] = {
    'ch': 'ppocr-v5-rec-ch-mobile',
    'en': 'ppocr-v5-rec-en-mobile',
    'ko': 'ppocr-v5-rec-korean-mobile',
    'latin': 'ppocr-v5-rec-latin-mobile',
    'ru': 'ppocr-v5-rec-eslav-mobile',
    'eslav': 'ppocr-v5-rec-eslav-mobile',
}

PPOCR_V5_MODELS = {
    'ppocr-v5-det-mobile': {
        'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.4.0/onnx/PP-OCRv5/det/',
        'files': ['ch_PP-OCRv5_mobile_det.onnx'],
        'sha256': ['4d97c44a20d30a81aad087d6a396b08f786c4635742afc391f6621f5c6ae78ae'],
        'save_dir': 'ocr/ppocr-v5-onnx'
    },
    'ppocr-v5-rec-ch-mobile': {
        'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.4.0/onnx/PP-OCRv5/rec/',
        'files': ['ch_PP-OCRv5_rec_mobile_infer.onnx', 'ppocrv5_dict.txt'],
        'sha256': ['5825fc7ebf84ae7a412be049820b4d86d77620f204a041697b0494669b1742c5', None],
        'save_dir': 'ocr/ppocr-v5-onnx',
        'additional_urls': {
            'ppocrv5_dict.txt': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.4.0/paddle/PP-OCRv5/rec/ch_PP-OCRv5_rec_mobile_infer/'
        }
    },
    'ppocr-v5-rec-en-mobile': {
        'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.4.0/onnx/PP-OCRv5/rec/',
        'files': ['en_PP-OCRv5_rec_mobile_infer.onnx', 'ppocrv5_en_dict.txt'],
        'sha256': ['c3461add59bb4323ecba96a492ab75e06dda42467c9e3d0c18db5d1d21924be8', None],
        'save_dir': 'ocr/ppocr-v5-onnx',
        'additional_urls': {
            'ppocrv5_en_dict.txt': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.4.0/paddle/PP-OCRv5/rec/en_PP-OCRv5_rec_mobile_infer/'
        }
    },
    'ppocr-v5-rec-korean-mobile': {
        'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.4.0/onnx/PP-OCRv5/rec/',
        'files': ['korean_PP-OCRv5_rec_mobile_infer.onnx', 'ppocrv5_korean_dict.txt'],
        'sha256': ['cd6e2ea50f6943ca7271eb8c56a877a5a90720b7047fe9c41a2e541a25773c9b', None],
        'save_dir': 'ocr/ppocr-v5-onnx',
        'additional_urls': {
            'ppocrv5_korean_dict.txt': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.4.0/paddle/PP-OCRv5/rec/korean_PP-OCRv5_rec_mobile_infer/'
        }
    },
    'ppocr-v5-rec-latin-mobile': {
        'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.4.0/onnx/PP-OCRv5/rec/',
        'files': ['latin_PP-OCRv5_rec_mobile_infer.onnx', 'ppocrv5_latin_dict.txt'],
        'sha256': ['b20bd37c168a570f583afbc8cd7925603890efbcdc000a59e22c269d160b5f5a', None],
        'save_dir': 'ocr/ppocr-v5-onnx',
        'additional_urls': {
            'ppocrv5_latin_dict.txt': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.4.0/paddle/PP-OCRv5/rec/latin_PP-OCRv5_rec_mobile_infer/'
        }
    },
    'ppocr-v5-rec-eslav-mobile': {
        'url': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.4.0/onnx/PP-OCRv5/rec/',
        'files': ['eslav_PP-OCRv5_rec_mobile_infer.onnx', 'ppocrv5_eslav_dict.txt'],
        'sha256': ['08705d6721849b1347d26187f15a5e362c431963a2a62bfff4feac578c489aab', None],
        'save_dir': 'ocr/ppocr-v5-onnx',
        'additional_urls': {
            'ppocrv5_eslav_dict.txt': 'https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.4.0/paddle/PP-OCRv5/rec/eslav_PP-OCRv5_rec_mobile_infer/'
        }
    },
}


def ensure_ppocr_v5_model(model_id: str) -> str:
    """Ensure PP-OCRv5 model is downloaded and return its path."""
    from modules.utils.paths import get_models_base_dir
    import os
    import hashlib
    
    if model_id not in PPOCR_V5_MODELS:
        raise ValueError(f"Unknown PP-OCRv5 model: {model_id}")
    
    model_info = PPOCR_V5_MODELS[model_id]
    save_dir = os.path.join(get_models_base_dir(), model_info['save_dir'])
    os.makedirs(save_dir, exist_ok=True)
    
    for i, file_name in enumerate(model_info['files']):
        file_path = os.path.join(save_dir, file_name)
        expected_sha = model_info['sha256'][i] if i < len(model_info['sha256']) else None
        
        if os.path.exists(file_path) and expected_sha:
            calculated_sha = hashlib.sha256(open(file_path, 'rb').read()).hexdigest()
            if calculated_sha == expected_sha:
                continue
        
        url_base = model_info.get('additional_urls', {}).get(file_name, model_info['url'])
        file_url = f"{url_base}{file_name}"
        
        print(f"Downloading PP-OCRv5 model: {file_url}")
        import urllib.request
        urllib.request.urlretrieve(file_url, file_path)
        
        if expected_sha:
            calculated_sha = hashlib.sha256(open(file_path, 'rb').read()).hexdigest()
            if calculated_sha != expected_sha:
                raise RuntimeError(f"Checksum mismatch for {file_name}")
    
    return os.path.join(save_dir, model_info['files'][0])


class PPOCRv5Engine(OCREngine):
    """Lightweight PP-OCRv5 ONNX pipeline (det + rec)."""

    def __init__(self):
        self.det_sess: Optional[Any] = None
        self.rec_sess: Optional[Any] = None
        self.det_post = DBPostProcessor(
            thresh=0.3, 
            box_thresh=0.5, 
            unclip_ratio=2.0, 
            use_dilation=False
        )
        self.decoder: Optional[CTCLabelDecoder] = None
        self.rec_img_shape = (3, 48, 320)

    def initialize(self, lang: str = 'ch', device: str = 'cpu', det_model: str = 'mobile') -> None:
        det_id = 'ppocr-v5-det-mobile' if det_model == 'mobile' else 'ppocr-v5-det-server'
        rec_id = LANG_TO_REC_MODEL.get(lang, 'ppocr-v5-rec-latin-mobile')
        
        det_path = ensure_ppocr_v5_model(det_id)
        rec_path = ensure_ppocr_v5_model(rec_id)
        
        providers = get_providers(device)
        from modules.utils.onnx import make_session, make_session_options
        sess_opt = make_session_options(log_severity_level=3)
        self.det_sess = make_session(det_path, sess_options=sess_opt, providers=providers)
        
        rec_dir = os.path.dirname(rec_path)
        rec_files = PPOCR_V5_MODELS[rec_id]['files']
        rec_model_file = [f for f in rec_files if f.endswith('.onnx')][0]
        rec_model_path = os.path.join(rec_dir, rec_model_file)
        self.rec_sess = make_session(rec_model_path, sess_options=sess_opt, providers=providers)
        
        dict_file = [f for f in rec_files if f.endswith('.txt')][0]
        dict_path = os.path.join(rec_dir, dict_file)
        if os.path.exists(dict_path):
            self.decoder = CTCLabelDecoder(dict_path=dict_path)
        else:
            self.decoder = CTCLabelDecoder(charset=self._get_default_charset(lang))

    def _get_default_charset(self, lang: str) -> List[str]:
        """Get default charset for language."""
        if lang == 'ch':
            return list(range(0x4E00, 0x9FFF + 1))
        elif lang == 'en':
            return list('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789')
        elif lang == 'ko':
            return list(range(0xAC00, 0xD7AF + 1))
        elif lang in ['latin', 'ru', 'eslav']:
            return list('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!?-\'\" ')
        return list('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789')

    def _det_infer(self, img: np.ndarray) -> Tuple[np.ndarray, List[float]]:
        assert self.det_sess is not None
        inp = det_preprocess(img, limit_side_len=960, limit_type='min')
        input_name = self.det_sess.get_inputs()[0].name
        output_name = self.det_sess.get_outputs()[0].name
        pred = self.det_sess.run([output_name], {input_name: inp})[0]
        boxes, scores = self.det_post(pred, (img.shape[0], img.shape[1]))
        return boxes, scores

    def _rec_infer(self, crops: List[np.ndarray]) -> Tuple[List[str], List[float]]:
        import os
        assert self.rec_sess is not None and self.decoder is not None
        if not crops:
            return [], []
        ratios = [c.shape[1] / float(max(1, c.shape[0])) for c in crops]
        order = np.argsort(ratios)
        texts = [""] * len(crops)
        confs = [0.0] * len(crops)
        bs = 8
        c, H, W = self.rec_img_shape
        for b in range(0, len(crops), bs):
            idxs = order[b:b+bs]
            max_ratio = max(ratios[i] for i in idxs) if idxs.size > 0 else (W/float(H))
            batch = [rec_resize_norm(crops[i], self.rec_img_shape, max_ratio)[None, ...] for i in idxs]
            x = np.concatenate(batch, axis=0).astype(np.float32)
            inp_name = self.rec_sess.get_inputs()[0].name
            out_name = self.rec_sess.get_outputs()[0].name
            logits = self.rec_sess.run([out_name], {inp_name: x})[0]
            if logits.ndim == 3 and logits.shape[1] > logits.shape[2]:
                logits = np.transpose(logits, (0, 2, 1))
            dec_texts, dec_confs = self.decoder(logits, prob_threshold=0.0)
            for oi, t, s in zip(idxs, dec_texts, dec_confs):
                texts[oi] = t
                confs[oi] = float(s)
        return texts, confs

    def process_image(self, img: np.ndarray, blk_list: List[TextBlock]) -> List[TextBlock]:
        if self.det_sess is None or self.rec_sess is None or self.decoder is None:
            return blk_list
        boxes, _ = self._det_infer(img)
        if boxes is None or len(boxes) == 0:
            boxes = []
        else:
            crops = [crop_quad(img, quad.astype(np.float32)) for quad in boxes]
            texts, _ = self._rec_infer(crops)
            bboxes = []
            for quad in boxes:
                xs = quad[:, 0]
                ys = quad[:, 1]
                x1, y1, x2, y2 = int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
                bboxes.append((x1, y1, x2, y2))
            lists_to_blk_list(blk_list, bboxes, texts)
        # Fallback per caselle manuali: se il detector globale non ha visto il
        # testo dentro un blocco (motivo per cui l'utente lo ha disegnato a
        # mano), il mapping lascia blk.text == "" e la traduzione diventa '...'.
        # Riconosci direttamente il crop del blocco.
        for blk in blk_list:
            if getattr(blk, 'text', '') and getattr(blk, 'text').strip():
                continue
            try:
                if getattr(blk, 'bubble_xyxy', None) is not None:
                    x1, y1, x2, y2 = [int(v) for v in blk.bubble_xyxy]
                else:
                    from modules.utils.textblock import adjust_text_line_coordinates
                    x1, y1, x2, y2 = adjust_text_line_coordinates(blk.xyxy, 5, 5, img)
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                if x1 < x2 and y1 < y2 and x1 >= 0 and y1 >= 0 and x2 <= img.shape[1] and y2 <= img.shape[0]:
                    crop = img[y1:y2, x1:x2]
                    if crop.size > 0:
                        ftexts, _ = self._rec_infer([crop])
                        if ftexts and ftexts[0] and ftexts[0].strip():
                            blk.text = ftexts[0].strip()
            except Exception:
                pass
        return blk_list
