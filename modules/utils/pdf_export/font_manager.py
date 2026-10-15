import os
import platform
import glob
from typing import Optional

class FontManager:
    def __init__(self):
        self.registered_fonts = set()
        self.font_name_mapping = {}
    
    def get_font_from_windows_registry(self, font_family: str) -> Optional[str]:
        if platform.system() != "Windows":
            return None
        
        try:
            import winreg
            
            registry_keys = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
            ]
            
            for hkey, subkey in registry_keys:
                try:
                    with winreg.OpenKey(hkey, subkey) as key:
                        i = 0
                        while True:
                            try:
                                name, value, _ = winreg.EnumValue(key, i)
                                
                                if font_family.lower() in name.lower():
                                    if os.path.isabs(value):
                                        font_path = value
                                    else:
                                        fonts_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts')
                                        font_path = os.path.join(fonts_dir, value)
                                    
                                    if os.path.exists(font_path):
                                        print(f"[INFO] Font '{font_family}' trovato nel registro: {name} -> {font_path}")
                                        return font_path
                                        
                                i += 1
                            except OSError:
                                break
                                
                except FileNotFoundError:
                    continue
                    
        except Exception as e:
            print(f"[WARNING] Errore nell'accesso al registro Windows: {e}")
            
        return None
    
    def get_font_path_from_system(self, font_family: str) -> Optional[str]:
        if platform.system() == "Windows":
            registry_path = self.get_font_from_windows_registry(font_family)
            if registry_path:
                return registry_path
        
        project_font_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'fonts')
        
        if platform.system() == "Windows":
            font_dirs = [
                project_font_dir,
                os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts'),
                os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Windows', 'Fonts')
            ]
        elif platform.system() == "Darwin":
            font_dirs = [
                project_font_dir,
                '/System/Library/Fonts',
                '/Library/Fonts',
                os.path.expanduser('~/Library/Fonts')
            ]
        else:
            font_dirs = [
                project_font_dir,
                '/usr/share/fonts',
                '/usr/local/share/fonts',
                os.path.expanduser('~/.fonts'),
                os.path.expanduser('~/.local/share/fonts')
            ]
        
        for font_dir in font_dirs:
            if os.path.exists(font_dir):
                patterns = [
                    f"{font_family}*.ttf",
                    f"{font_family}*.otf",
                    f"{font_family.replace(' ', '')}*.ttf",
                    f"{font_family.replace(' ', '')}*.otf",
                    f"{font_family.replace(' ', '_')}*.ttf",
                    f"{font_family.replace(' ', '_')}*.otf",
                    f"{font_family.replace(' ', '-')}*.ttf",
                    f"{font_family.replace(' ', '-')}*.otf"
                ]
                
                for pattern in patterns:
                    matches = glob.glob(os.path.join(font_dir, pattern))
                    if matches:
                        return matches[0]
        
        return None
    
    def register_font_if_needed(self, font_family: str) -> bool:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from PySide6.QtGui import QFontDatabase
        
        if font_family not in self.registered_fonts:
            try:
                standard_fonts = ['Helvetica', 'Times-Roman', 'Courier']
                if font_family in standard_fonts:
                    self.registered_fonts.add(font_family)
                    self.font_name_mapping[font_family] = font_family
                    return True
                
                font_db = QFontDatabase()
                if font_family not in font_db.families():
                    print(f"[WARNING] Font {font_family} non disponibile nel sistema")
                
                font_path = self.get_font_path_from_system(font_family)
                
                if font_path and os.path.exists(font_path):
                    clean_font_name = font_family.replace(' ', '_').replace('.', '_')
                    pdfmetrics.registerFont(TTFont(clean_font_name, font_path))
                    self.registered_fonts.add(font_family)
                    self.font_name_mapping[font_family] = clean_font_name
                    print(f"[INFO] Font {font_family} registrato come '{clean_font_name}' da: {font_path}")
                    return True
                else:
                    print(f"[WARNING] File del font {font_family} non trovato nel sistema")
                    return False
                    
            except Exception as e:
                print(f"[WARNING] Impossibile registrare font {font_family}: {e}")
                return False
        return True
    
    def get_registered_font_name(self, font_family: str) -> str:
        return self.font_name_mapping.get(font_family, font_family)
