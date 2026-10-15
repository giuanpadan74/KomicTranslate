import cv2
import numpy as np
import logging
from typing import List, Tuple, Dict, Any

def create_blocks_collage(crops: List[np.ndarray], 
                          indices: List[Any], 
                          max_width: int = 1500, 
                          padding: int = 20,
                          show_labels: bool = True) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Creates a composite image (collage) from a list of image crops.
    Used to optimize LLM processing by grouping multiple text blocks into one request.
    
    Args:
        crops: List of image crops (numpy arrays).
        indices: List of original identifiers (like block indices) corresponding to the crops.
        max_width: Maximum width of the collage canvas.
        padding: Padding between crops and edges.
        show_labels: Whether to draw numeric ID labels over each crop.
        
    Returns:
        A tuple of (collage_image, id_map) where id_map maps "local_id" (string) to original identifier.
    """
    if not crops:
        return np.zeros((10, 10, 3), dtype=np.uint8), {}

    # 1. Estimate canvas height
    canvas_width = max_width
    temp_x = padding
    temp_y = padding
    temp_row_h = 0
    
    # Pre-process crops (resize if wider than canvas)
    processed_crops = []
    available_w = canvas_width - 2 * padding
    
    for crop in crops:
        if len(crop.shape) == 2:
            crop = cv2.cvtColor(crop, cv2.COLOR_GRAY2BGR)
        
        h, w = crop.shape[:2]
        if w > available_w:
            scale = available_w / w
            new_w = int(w * scale)
            new_h = int(h * scale)
            crop = cv2.resize(crop, (new_w, new_h))
            w, h = new_w, new_h
            
        processed_crops.append(crop)
        
        if temp_x + w + padding > canvas_width:
            temp_x = padding
            temp_y += temp_row_h + padding
            temp_row_h = 0
        
        temp_row_h = max(temp_row_h, h)
        temp_x += w + padding
        
    canvas_height = temp_y + temp_row_h + padding
    
    # 2. Create canvas (white background)
    canvas = np.ones((canvas_height, canvas_width, 3), dtype=np.uint8) * 255
    
    # 3. Place images and draw labels
    current_x = padding
    current_y = padding
    row_height = 0
    id_map = {}
    
    for k, (crop, original_idx) in enumerate(zip(processed_crops, indices)):
        h, w = crop.shape[:2]
        local_id = str(k + 1)
        id_map[local_id] = original_idx
        
        if current_x + w + padding > canvas_width:
            current_x = padding
            current_y += row_height + padding
            row_height = 0
        
        # Place crop
        canvas[current_y:current_y+h, current_x:current_x+w] = crop
        
        if show_labels:
            # Draw Label (ID)
            label = str(local_id)
            font_scale = 1.0
            thickness = 2
            (text_w, text_h), baseline = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
            
            # Draw background for text (Red box)
            cv2.rectangle(canvas, 
                          (current_x, current_y), 
                          (current_x + text_w + 10, current_y + text_h + 10), 
                          (0, 0, 255), 
                          -1)
            
            # Draw text (White)
            cv2.putText(canvas, 
                        label, 
                        (current_x + 5, current_y + text_h + 5), 
                        cv2.FONT_HERSHEY_SIMPLEX, 
                        font_scale, 
                        (255, 255, 255), 
                        thickness)

        row_height = max(row_height, h)
        current_x += w + padding
        
    return canvas, id_map
