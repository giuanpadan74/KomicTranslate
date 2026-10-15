import cv2
import numpy as np
from .base import InpaintModel
from .schema import Config

class FastClean(InpaintModel):
    name = "fast_clean"
    pad_mod = 8

    def init_model(self, device, **kwargs):
        # No model needed for fast clean
        pass

    @staticmethod
    def is_downloaded() -> bool:
        # Always available since no download needed
        return True

    def forward(self, image, mask, config: Config):
        """Fill masked areas locally with detected background colors per block.
        image: [H, W, C] RGB
        mask: [H, W]
        return: BGR IMAGE
        """
        # Convert to BGR for output
        result = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

        # Ensure mask is 2D mapping
        m_2d = mask
        if len(m_2d.shape) == 3:
            m_2d = m_2d[:, :, 0]
            
        global_fill_mask = m_2d > 127
        img_h, img_w = image.shape[:2]

        # 1. Local Fill using blk_list
        if hasattr(config, 'blk_list') and config.blk_list:
            blk_list = config.blk_list
            
            # Calculate scale factor if the image has been resized
            scale_x = 1.0
            scale_y = 1.0
            if hasattr(config, 'original_size') and config.original_size:
                orig_h, orig_w = config.original_size
                scale_x = img_w / orig_w
                scale_y = img_h / orig_h

            for blk in blk_list:
                # Determine block coordinates and sampling area
                if blk.text_class == 'text_bubble' and blk.bubble_xyxy is not None:
                    bx1, by1, bx2, by2 = blk.bubble_xyxy
                else:
                    bx1, by1, bx2, by2 = blk.xyxy
                
                x1, y1, x2, y2 = int(bx1 * scale_x), int(by1 * scale_y), int(bx2 * scale_x), int(by2 * scale_y)
                
                # Expand slightly to sample surrounding color if not a bubble
                if blk.text_class != 'text_bubble' or blk.bubble_xyxy is None:
                    pad = 10
                    x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
                    x2, y2 = min(img_w, x2 + pad), min(img_h, y2 + pad)
                else:
                    x1, y1 = max(0, x1), max(0, y1)
                    x2, y2 = min(img_w, x2), min(img_h, y2)
                
                if x1 < x2 and y1 < y2:
                    patch_img = image[y1:y2, x1:x2]
                    patch_mask = m_2d[y1:y2, x1:x2]

                    # We want to find the true background color of the bubble, ignoring:
                    # 1. Antialiasing artifacts around the text (which are dark/grayish)
                    # 2. The black border of the balloon (if captured in xyxy)
                    # To do this, we sample all valid pixels and use the brightest ones.
                    
                    # Find ALL valid pixels (unmasked) in this specific block
                    valid_pixels = patch_img[patch_mask == 0]
                    
                    if len(valid_pixels) > 0:
                        # Convert to grayscale to find brightness/luminance
                        # Weights: R: 0.299, G: 0.587, B: 0.114
                        luminance = np.dot(valid_pixels[..., :3], [0.299, 0.587, 0.114])
                        
                        # Find the 80th percentile of brightness. 
                        # We want the bright part of the bubble, ignoring dark text edges/borders.
                        # If the background is actually dark, this still finds the dominant "clean" color
                        # rather than the darkest artifacts.
                        threshold = np.percentile(luminance, 80)
                        
                        # Select only pixels brighter than or equal to the threshold
                        bright_pixels = valid_pixels[luminance >= threshold]
                        
                        # If for some reason our filtering removes everything, fallback to all valid
                        if len(bright_pixels) == 0:
                            bright_pixels = valid_pixels
                            
                        # Calculate local median color (median is more robust to outliers than mean)
                        color_rgb = np.median(bright_pixels, axis=0).astype(int)
                        color_bgr = tuple(color_rgb[::-1])
                        
                        # Apply color ONLY to the masked pixels within this specific block
                        block_fill_mask = patch_mask > 127
                        # Use a slice of the global result to apply the color locally
                        result[y1:y2, x1:x2][block_fill_mask] = color_bgr
                        
                        # Remove filled pixels from global mask so they aren't overwritten later
                        global_fill_mask[y1:y2, x1:x2][block_fill_mask] = False

        # 2. Global Fallback for any remaining un-filled masked areas
        if np.any(global_fill_mask):
            valid_pixels = image[m_2d == 0]
            if len(valid_pixels) > 0:
                fallback_rgb = np.mean(valid_pixels, axis=0).astype(int)
                fallback_bgr = tuple(fallback_rgb[::-1])
            else:
                fallback_bgr = (255, 255, 255) # White fallback
            
            result[global_fill_mask] = fallback_bgr

        return result
