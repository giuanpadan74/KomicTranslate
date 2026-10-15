import textwrap
from typing import Optional

class TextRenderer:
    def __init__(self):
        pass
    
    def draw_multiline_text(self,
                           canvas,
                           x: float,
                           y: float,
                           text: str,
                           font_name: str,
                           font_size: float,
                           max_width: Optional[float] = None,
                           line_height_factor: float = 1.2,
                           alignment: str = 'left'):
        if not text:
            return
        
        from reportlab.pdfbase.pdfmetrics import stringWidth
        
        lines = text.split('\n')
        line_height = font_size * line_height_factor
        
        if max_width and max_width > 0:
            wrapped_lines = []
            for line in lines:
                if not line.strip():
                    wrapped_lines.append('')
                    continue
                    
                avg_char_width = stringWidth('M', font_name, font_size)
                chars_per_line = max(1, int(max_width / avg_char_width))
                
                wrapper = textwrap.TextWrapper(
                    width=chars_per_line,
                    break_long_words=True,
                    break_on_hyphens=True,
                    expand_tabs=False
                )
                
                line_wrapped = wrapper.wrap(line)
                if line_wrapped:
                    wrapped_lines.extend(line_wrapped)
                else:
                    wrapped_lines.append('')
            
            lines = wrapped_lines
        
        for i, line in enumerate(lines):
            if line.strip():
                line_y = y - (i * line_height)
                
                if max_width and max_width > 0:
                    actual_width = stringWidth(line, font_name, font_size)
                    if actual_width > max_width:
                        truncated_line = line
                        while len(truncated_line) > 1 and stringWidth(truncated_line, font_name, font_size) > max_width:
                            truncated_line = truncated_line[:-1]
                        line = truncated_line
                
                line_x = x
                if alignment == 'center' and max_width and max_width > 0:
                    text_width = stringWidth(line, font_name, font_size)
                    line_x = x + (max_width - text_width) / 2.0
                elif alignment == 'right' and max_width and max_width > 0:
                    text_width = stringWidth(line, font_name, font_size)
                    line_x = x + max_width - text_width
                
                canvas.drawString(float(line_x), float(line_y), line.strip())
