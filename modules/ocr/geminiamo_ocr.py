import cv2
import numpy as np
import tempfile
import os
import logging
import json
import time
from .base import OCREngine
from ..utils.textblock import TextBlock, adjust_text_line_coordinates
from ..api_clients.geminiamo_client import geminiamo_client
from ..utils.exceptions import GeminiamoSaturationError

class GeminiamoOCR(OCREngine):
    """OCR engine using Gemini via browser cookies (Geminiamo) with Collage strategy."""
    
    def __init__(self):
        self.settings = None
        self.expansion_percentage = 5
        self.client = geminiamo_client
        self.max_collage_width = 1500  # Max width for the collage image
        self.padding = 20  # Padding between blocks in collage

    def initialize(self, settings, **kwargs) -> None:
        """
        Initialize the Geminiamo OCR.
        
        Args:
            settings: Settings page
            **kwargs: Other parameters
        """
        self.settings = settings
        self.expansion_percentage = kwargs.get('expansion_percentage', 5)
        print("Geminiamo OCR initialized (Collage Strategy).")

    def process_image(self, img: np.ndarray, blk_list: list[TextBlock]) -> list[TextBlock]:
        """
        Process an image with Geminiamo OCR using Collage strategy.
        
        Args:
            img: Input image as numpy array
            blk_list: List of TextBlock objects to update with OCR text
            
        Returns:
            List of updated TextBlock objects with recognized text
        """
        if not blk_list:
            return blk_list

        print(f"Geminiamo OCR processing {len(blk_list)} blocks with Collage Strategy...")
        
        valid_blocks = []
        valid_indices = []

        # 1. Extract crops
        crops = []
        for i, blk in enumerate(blk_list):
            try:
                # Get box coordinates (cast a int per caselle manuali float)
                if blk.bubble_xyxy is not None:
                    x1, y1, x2, y2 = [int(v) for v in blk.bubble_xyxy]
                else:
                    x1, y1, x2, y2 = adjust_text_line_coordinates(
                        blk.xyxy,
                        self.expansion_percentage,
                        self.expansion_percentage,
                        img
                    )
                    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                
                # Check if coordinates are valid
                if x1 < x2 and y1 < y2 and x1 >= 0 and y1 >= 0 and x2 <= img.shape[1] and y2 <= img.shape[0]:
                    cropped_img = img[y1:y2, x1:x2]
                    if cropped_img.size > 0:
                        crops.append(cropped_img)
                        valid_blocks.append(blk)
                        valid_indices.append(i)
                else:
                    print(f"Block {i+1}: invalid coordinates, skipping.")
            except Exception as e:
                print(f"Error preparing block {i+1}: {e}")

        if not crops:
            print("No valid crops found.")
            return blk_list

        # 2. Create Collage
        collage_path = None
        try:
            collage_img, id_map = self._create_collage(crops, valid_indices)
            
            # Save collage to temp file
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                collage_path = tmp.name
            
            # Save as optimized JPG (quality 85) to reduce upload time
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
            cv2.imwrite(collage_path, collage_img, encode_param)
            print(f"Collage created at {collage_path}, size: {collage_img.shape}")

            # 3. Call Gemini (Simplified prompt)
            prompt = (
                "OCR task. Extract text from numbered blocks in this image. "
                "Output ONLY a raw JSON object: {\"1\": \"text1\", \"2\": \"text2\"}. "
                "No markdown, no explanations."
            )
            
            # Retry logic
            max_attempts = 2
            response_text = None
            
            for attempt in range(max_attempts):
                try:
                    print(f"Attempt {attempt + 1}/{max_attempts} calling Geminiamo...")
                    response_text = self.client.generate_content(prompt, image_path=collage_path)
                    
                    if response_text and "error" not in response_text.lower(): # Basic check, client usually raises exception
                        break
                    else:
                        print(f"Attempt {attempt + 1} failed (empty or error response).")
                        if attempt < max_attempts - 1:
                            time.sleep(2) # Wait before retry
                except Exception as e:
                    print(f"Attempt {attempt + 1} exception: {e}")
                    if attempt < max_attempts - 1:
                         time.sleep(2)
                    else:
                        # If it's the last attempt, check if it looks like saturation/network error
                        # Assuming generic exception implies failure here.
                        # We raise specific error to trigger fallback logic
                        raise GeminiamoSaturationError(f"Geminiamo failed after {max_attempts} attempts: {str(e)}")

            if not response_text:
                 raise GeminiamoSaturationError("Geminiamo returned empty response after retries.")

            # 4. Parse Response
            extracted_data = self._parse_json_response(response_text)
            
            # 5. Update Blocks (chiavi locali 1-based -> indice originale;
            # fallback a indice 0-based per risposte legacy)
            success_count = 0
            for str_idx, text in extracted_data.items():
                try:
                    key = str(str_idx).strip().strip('"').strip("'")
                    original_idx = None
                    if isinstance(id_map, dict) and key in id_map:
                        original_idx = int(id_map[key])
                    else:
                        try:
                            as_int = int(key)
                        except ValueError:
                            continue
                        if isinstance(id_map, dict) and str(as_int) in (id_map or {}):
                            original_idx = int(id_map[str(as_int)])
                        elif 0 <= as_int < len(blk_list):
                            # Etichetta 0-based legacy
                            original_idx = as_int
                        elif 1 <= as_int <= len(crops) and (as_int - 1) < len(valid_indices):
                            # Risposta 1-based su collage legacy 0-based
                            original_idx = int(valid_indices[as_int - 1])
                        else:
                            continue
                    if original_idx is not None and 0 <= original_idx < len(blk_list):
                        blk_list[original_idx].text = text.strip() if isinstance(text, str) else text
                        success_count += 1
                except ValueError:
                    continue
            
            print(f"Successfully updated {success_count} blocks out of {len(valid_blocks)}.")

        except GeminiamoSaturationError:
            # Re-raise specifically
            raise
        except Exception as e:
            print(f"Error in Geminiamo Collage processing: {e}")
        finally:
            if collage_path and os.path.exists(collage_path):
                try:
                    os.remove(collage_path)
                except:
                    pass

        return blk_list

    def _create_collage(self, crops, indices):
        """
        Stitch crops into a single image with ID labels.
        Usa ID locali 1-based con id_map (come create_blocks_collage):
        le etichette "1","2",... corrispondono all'esempio nel prompt e la
        mappatura locale->originale evita l'off-by-one che lasciava vuoti
        i blocchi (tipicamente l'ultimo, spesso quello disegnato a mano).
        """
        from ..utils.image_utils import create_blocks_collage
        canvas, id_map = create_blocks_collage(
            crops, indices,
            max_width=self.max_collage_width,
            padding=self.padding,
            show_labels=True,
        )
        return canvas, id_map

    def _parse_json_response(self, text):
        """Parse JSON from Gemini response."""
        try:
            cleaned_text = text.strip()
            if "```json" in cleaned_text:
                cleaned_text = cleaned_text.split("```json")[1].split("```")[0]
            elif "```" in cleaned_text:
                cleaned_text = cleaned_text.split("```")[1].split("```")[0]
            
            start_idx = cleaned_text.find('{')
            end_idx = cleaned_text.rfind('}')
            
            if start_idx != -1 and end_idx != -1:
                cleaned_text = cleaned_text[start_idx:end_idx+1]
                
            return json.loads(cleaned_text)
        except Exception as e:
            print(f"Error parsing JSON response: {e}")
            return {}
