from typing import List
from reportlab.pdfgen import canvas
from PySide6.QtGui import QColor

class PDFGenerator:
    def __init__(self, font_manager, text_renderer, image_processor):
        self.font_manager = font_manager
        self.text_renderer = text_renderer
        self.image_processor = image_processor
    
    def export_to_pdf(self,
                     output_path: str,
                     cleaned_image,
                     text_items: List,
                     image_width: int,
                     image_height: int,
                     image_quality: int = 85) -> bool:
        try:
            pil_image = self.image_processor.cv2_to_pil_image(cleaned_image, input_format='RGB')
            if pil_image is None:
                print("[ERROR] Impossibile convertire l'immagine")
                return False
            
            real_height, real_width = cleaned_image.shape[:2]
            pdf_canvas = canvas.Canvas(output_path, pagesize=(real_width, real_height))
            
            img_buffer = self.image_processor.image_to_jpeg_buffer(pil_image, image_quality)
            pdf_canvas.drawImage(img_buffer, 0, 0, width=real_width, height=real_height)
            
            for text_item in text_items:
                if not text_item.isVisible():
                    continue
                
                try:
                    text_content = text_item.toPlainText()
                    if not text_content.strip():
                        continue
                    
                    scale_x = real_width / image_width if image_width > 0 else 1.0
                    scale_y = real_height / image_height if image_height > 0 else 1.0
                    
                    scene_pos = text_item.scenePos()
                    scene_x = float(scene_pos.x()) * scale_x
                    scene_y = float(scene_pos.y()) * scale_y
                    
                    font_family = getattr(text_item, 'font_family', 'Arial')
                    font_size = float(getattr(text_item, 'font_size', 12)) * min(scale_x, scale_y)
                    font_height = font_size * 1.2
                    
                    x = scene_x
                    y = real_height - scene_y - font_height
                    
                    x = max(0, min(x, real_width))
                    y = max(0, min(y, real_height))
                    
                    if not self.font_manager.register_font_if_needed(font_family):
                        font_family = 'Helvetica'
                    
                    registered_font_name = self.font_manager.get_registered_font_name(font_family)
                    
                    text_color = getattr(text_item, 'text_color', QColor(0, 0, 0))
                    if isinstance(text_color, str):
                        text_color = QColor(text_color)
                    elif text_color is None:
                        text_color = QColor(0, 0, 0)
                    
                    color = self.image_processor.qcolor_to_reportlab_color(text_color)
                    
                    bold = getattr(text_item, 'bold', False)
                    italic = getattr(text_item, 'italic', False)
                    
                    font_name = registered_font_name
                    if bold and italic:
                        font_name += '-BoldItalic'
                    elif bold:
                        font_name += '-Bold'
                    elif italic:
                        font_name += '-Italic'
                    
                    try:
                        pdf_canvas.setFont(font_name, font_size)
                    except:
                        try:
                            pdf_canvas.setFont(registered_font_name, font_size)
                        except:
                            pdf_canvas.setFont('Helvetica', font_size)
                    
                    pdf_canvas.setFillColor(color)
                    
                    outline_width = float(getattr(text_item, 'outline_width', 0))
                    if outline_width > 0:
                        outline_color = getattr(text_item, 'outline_color', QColor(255, 255, 255))
                        if isinstance(outline_color, str):
                            outline_color = QColor(outline_color)
                        elif outline_color is None:
                            outline_color = QColor(255, 255, 255)
                        
                        stroke_color = self.image_processor.qcolor_to_reportlab_color(outline_color)
                        pdf_canvas.setStrokeColor(stroke_color)
                        pdf_canvas.setLineWidth(outline_width * min(scale_x, scale_y))
                    
                    text_width = text_item.boundingRect().width() * min(scale_x, scale_y)
                    max_width = text_width if text_width > 0 else None
                    
                    alignment_value = getattr(text_item, 'alignment', 'left')
                    alignment = self._convert_alignment(alignment_value)
                    
                    rotation = float(text_item.rotation())
                    if rotation != 0:
                        pdf_canvas.saveState()
                        pdf_canvas.translate(x, y)
                        pdf_canvas.rotate(rotation)
                        self.text_renderer.draw_multiline_text(pdf_canvas, 0, 0, text_content, font_name, font_size, max_width, alignment=alignment)
                        pdf_canvas.restoreState()
                    else:
                        self.text_renderer.draw_multiline_text(pdf_canvas, x, y, text_content, font_name, font_size, max_width, alignment=alignment)
                except Exception as e:
                    print(f"[WARNING] Errore nel rendering del testo: {e}")
                    continue
            
            pdf_canvas.save()
            print(f"[DEBUG] PDF esportato con successo: {output_path}")
            return True
            
        except Exception as e:
            print(f"[ERROR] Errore nell'esportazione PDF: {e}")
            return False
    
    def _convert_alignment(self, alignment_value) -> str:
        if isinstance(alignment_value, (int, type(alignment_value))):
            alignment_int = int(alignment_value)
            horizontal_align = alignment_int & 0x0F
            
            if alignment_int == 132 or (horizontal_align & 4):
                return 'center'
            elif alignment_int == 130 or (horizontal_align & 2):
                return 'right'
            else:
                return 'left'
        elif isinstance(alignment_value, str):
            alignment_lower = alignment_value.lower()
            if 'center' in alignment_lower or 'centre' in alignment_lower:
                return 'center'
            elif 'right' in alignment_lower:
                return 'right'
            else:
                return 'left'
        else:
            return 'left'
