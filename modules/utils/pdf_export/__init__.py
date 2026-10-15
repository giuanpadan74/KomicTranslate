"""Sistema di esportazione PDF modulare."""
from .font_manager import FontManager
from .text_renderer import TextRenderer
from .image_processor import ImageProcessor
from .pdf_generator import PDFGenerator

class PDFExporter:
    def __init__(self):
        self.font_manager = FontManager()
        self.text_renderer = TextRenderer()
        self.image_processor = ImageProcessor()
        self.pdf_generator = PDFGenerator(
            self.font_manager,
            self.text_renderer,
            self.image_processor
        )
        self.registered_fonts = self.font_manager.registered_fonts
        self.font_name_mapping = self.font_manager.font_name_mapping
    
    def get_font_from_windows_registry(self, font_family: str):
        return self.font_manager.get_font_from_windows_registry(font_family)
    
    def get_font_path_from_system(self, font_family: str):
        return self.font_manager.get_font_path_from_system(font_family)
    
    def register_font_if_needed(self, font_family: str):
        return self.font_manager.register_font_if_needed(font_family)
    
    def get_registered_font_name(self, font_family: str):
        return self.font_manager.get_registered_font_name(font_family)
    
    def draw_multiline_text(self, canvas, x, y, text, font_name, font_size, max_width=None, line_height_factor=1.2, alignment='left'):
        return self.text_renderer.draw_multiline_text(
            canvas, x, y, text, font_name, font_size,
            max_width, line_height_factor, alignment
        )
    
    def cv2_to_pil_image(self, cv2_image, input_format='BGR'):
        return self.image_processor.cv2_to_pil_image(cv2_image, input_format)
    
    def qcolor_to_reportlab_color(self, qcolor):
        return self.image_processor.qcolor_to_reportlab_color(qcolor)
    
    def export_to_pdf(self, output_path, cleaned_image, text_items, image_width, image_height, image_quality=85):
        return self.pdf_generator.export_to_pdf(
            output_path, cleaned_image, text_items,
            image_width, image_height, image_quality
        )

__all__ = [
    'PDFExporter',
    'FontManager',
    'TextRenderer',
    'ImageProcessor',
    'PDFGenerator',
]
