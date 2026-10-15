import os

import cv2
import torch

from ..utils.inpainting import (
    load_jit_model,
    download_model,
    get_cache_path_by_url,
    boxes_from_mask,
    resize_max_size,
    norm_img,
)
from .base import InpaintModel
from .schema import Config

MIGAN_MODEL_URL = os.environ.get(
    "MIGAN_MODEL_URL",
    "https://github.com/Sanster/models/releases/download/migan/migan_traced.pt",
)
MIGAN_MODEL_MD5 = os.environ.get("MIGAN_MODEL_MD5", "76eb3b1a71c400ee3290524f7a11b89c")


class MIGAN(InpaintModel):
    name = "migan"
    min_size = 512
    pad_mod = 512
    pad_to_square = True
    is_erase_model = True

    def init_model(self, device, **kwargs):
        self.model = load_jit_model(MIGAN_MODEL_URL, device, MIGAN_MODEL_MD5).eval()

    @staticmethod
    def download():
        download_model(MIGAN_MODEL_URL, MIGAN_MODEL_MD5)

    @staticmethod
    def is_downloaded() -> bool:
        return os.path.exists(get_cache_path_by_url(MIGAN_MODEL_URL))


    def forward(self, image, mask, config: Config):
        """Input images and output images have same size
        images: [H, W, C] RGB
        masks: [H, W] mask area == 255
        return: BGR IMAGE
        """
        print(f"[INPAINT_MODEL] Utilizzo modello MIGAN")

        image = norm_img(image)  # [0, 1]
        image = image * 2 - 1  # [0, 1] -> [-1, 1]
        mask = (mask > 120) * 255
        mask = norm_img(mask)

        image = torch.from_numpy(image).unsqueeze(0).to(self.device)
        mask = torch.from_numpy(mask).unsqueeze(0).to(self.device)

        erased_img = image * (1 - mask)
        input_image = torch.cat([0.5 - mask, erased_img], dim=1)

        output = self.model(input_image)
        output = (
            (output.permute(0, 2, 3, 1) * 127.5 + 127.5)
            .round()
            .clamp(0, 255)
            .to(torch.uint8)
        )
        output = output[0].cpu().numpy()
        cur_res = cv2.cvtColor(output, cv2.COLOR_RGB2BGR)
        return cur_res
