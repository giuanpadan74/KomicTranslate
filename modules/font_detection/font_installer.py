"""Font Installation Module for automatic font management."""

import os
import sys
import shutil
import logging
import platform
import subprocess
from typing import List, Optional, Dict, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

class FontInstaller:
    """Handles automatic font installation and management."""
    
    def __init__(self):
        self.system = platform.system().lower()
        self.font_extensions = {'.ttf', '.otf', '.ttc', '.woff', '.woff2'}
        
    def can_install_fonts(self) -> bool:
        """Check if font installation is supported on this system."""
        return self.system in ['windows', 'darwin', 'linux']
    
    def get_system_font_directories(self) -> List[Path]:
        """Get system font directories for the current OS."""
        if self.system == 'windows':
            return [
                Path(os.environ.get('WINDIR', 'C:\\Windows')) / 'Fonts',
                Path.home() / 'AppData' / 'Local' / 'Microsoft' / 'Windows' / 'Fonts'
            ]
        elif self.system == 'darwin':  # macOS
            return [
                Path('/System/Library/Fonts'),
                Path('/Library/Fonts'),
                Path.home() / 'Library' / 'Fonts'
            ]
        elif self.system == 'linux':
            return [
                Path('/usr/share/fonts'),
                Path('/usr/local/share/fonts'),
                Path.home() / '.fonts',
                Path.home() / '.local' / 'share' / 'fonts'
            ]
        else:
            return []
    
    def get_user_font_directory(self) -> Optional[Path]:
        """Get the user-specific font directory."""
        if self.system == 'windows':
            return Path.home() / 'AppData' / 'Local' / 'Microsoft' / 'Windows' / 'Fonts'
        elif self.system == 'darwin':
            return Path.home() / 'Library' / 'Fonts'
        elif self.system == 'linux':
            return Path.home() / '.local' / 'share' / 'fonts'
        else:
            return None
    
    def search_installed_fonts(self, font_name: str) -> List[Path]:
        """Search for installed fonts matching the given name.
        
        Args:
            font_name: Name of the font to search for
            
        Returns:
            List of paths to matching font files
        """
        found_fonts = []
        font_name_lower = font_name.lower()
        
        for font_dir in self.get_system_font_directories():
            if not font_dir.exists():
                continue
                
            try:
                for font_file in font_dir.rglob('*'):
                    if (font_file.is_file() and 
                        font_file.suffix.lower() in self.font_extensions and
                        font_name_lower in font_file.stem.lower()):
                        found_fonts.append(font_file)
            except (PermissionError, OSError) as e:
                logger.warning(f"Cannot access font directory {font_dir}: {e}")
                
        return found_fonts
    
    def is_font_installed(self, font_name: str) -> bool:
        """Check if a font is already installed.
        
        Args:
            font_name: Name of the font to check
            
        Returns:
            True if font is installed, False otherwise
        """
        return len(self.search_installed_fonts(font_name)) > 0
    
    def install_font_file(self, font_path: Path) -> bool:
        """Install a font file to the system.
        
        Args:
            font_path: Path to the font file to install
            
        Returns:
            True if installation successful, False otherwise
        """
        if not font_path.exists() or font_path.suffix.lower() not in self.font_extensions:
            logger.error(f"Invalid font file: {font_path}")
            return False
        
        try:
            user_font_dir = self.get_user_font_directory()
            if not user_font_dir:
                logger.error("Cannot determine user font directory")
                return False
            
            # Create font directory if it doesn't exist
            user_font_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy font file
            dest_path = user_font_dir / font_path.name
            shutil.copy2(font_path, dest_path)
            
            # Platform-specific font registration
            if self.system == 'windows':
                self._register_font_windows(dest_path)
            elif self.system == 'linux':
                self._refresh_font_cache_linux()
            
            logger.info(f"Font installed successfully: {dest_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to install font {font_path}: {e}")
            return False
    
    def _register_font_windows(self, font_path: Path) -> bool:
        """Register font with Windows system."""
        try:
            import winreg
            
            # Get font name from file (simplified approach)
            font_name = font_path.stem
            
            # Register in Windows Registry
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 
                              r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts", 
                              0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, f"{font_name} (TrueType)", 0, 
                                winreg.REG_SZ, str(font_path))
            
            return True
            
        except Exception as e:
            logger.warning(f"Failed to register font in Windows registry: {e}")
            return False
    
    def _refresh_font_cache_linux(self) -> bool:
        """Refresh font cache on Linux systems."""
        try:
            subprocess.run(['fc-cache', '-f'], check=True, capture_output=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.warning(f"Failed to refresh font cache: {e}")
            return False
    
    def download_font_from_google_fonts(self, font_name: str) -> Optional[Path]:
        """Download font from Google Fonts (if available).
        
        Args:
            font_name: Name of the font to download
            
        Returns:
            Path to downloaded font file, or None if failed
        """
        try:
            import requests
            from urllib.parse import quote
            
            # Google Fonts API endpoint
            api_key = "AIzaSyBC8xFJrwBKONaWdGHlLvOhOOOOOOOOOOO"  # Replace with actual API key
            font_name_encoded = quote(font_name.replace(' ', '+'))
            
            # Search for font
            search_url = f"https://www.googleapis.com/webfonts/v1/webfonts?key={api_key}&family={font_name_encoded}"
            
            response = requests.get(search_url, timeout=10)
            if response.status_code != 200:
                logger.warning(f"Google Fonts API request failed: {response.status_code}")
                return None
            
            data = response.json()
            if not data.get('items'):
                logger.info(f"Font '{font_name}' not found in Google Fonts")
                return None
            
            # Get first matching font
            font_info = data['items'][0]
            font_files = font_info.get('files', {})
            
            # Prefer TTF, fallback to other formats
            download_url = None
            for variant in ['regular', '400', 'normal']:
                if variant in font_files:
                    download_url = font_files[variant]
                    break
            
            if not download_url:
                # Take first available variant
                download_url = next(iter(font_files.values()), None)
            
            if not download_url:
                logger.warning(f"No download URL found for font '{font_name}'")
                return None
            
            # Download font file
            font_response = requests.get(download_url, timeout=30)
            if font_response.status_code != 200:
                logger.warning(f"Failed to download font: {font_response.status_code}")
                return None
            
            # Save to temporary location
            temp_dir = Path.home() / '.comic_translate_temp'
            temp_dir.mkdir(exist_ok=True)
            
            font_filename = f"{font_name.replace(' ', '_')}.ttf"
            font_path = temp_dir / font_filename
            
            with open(font_path, 'wb') as f:
                f.write(font_response.content)
            
            logger.info(f"Font downloaded: {font_path}")
            return font_path
            
        except Exception as e:
            logger.error(f"Failed to download font from Google Fonts: {e}")
            return None
    
    def search_and_install(self, font_name: str) -> bool:
        """Search for a font and install it if found.
        
        Args:
            font_name: Name of the font to search and install
            
        Returns:
            True if font was found and installed, False otherwise
        """
        # Check if already installed
        if self.is_font_installed(font_name):
            logger.info(f"Font '{font_name}' is already installed")
            return True
        
        # Try to download from Google Fonts
        downloaded_font = self.download_font_from_google_fonts(font_name)
        if downloaded_font:
            success = self.install_font_file(downloaded_font)
            
            # Clean up temporary file
            try:
                downloaded_font.unlink()
            except Exception:
                pass
            
            return success
        
        logger.warning(f"Font '{font_name}' not found for automatic installation")
        return False
    
    def get_font_suggestions(self, font_name: str) -> List[str]:
        """Get suggestions for similar fonts that might be installed.
        
        Args:
            font_name: Original font name
            
        Returns:
            List of suggested font names
        """
        suggestions = []
        font_name_lower = font_name.lower()
        
        # Common font substitutions
        substitutions = {
            'arial': ['helvetica', 'liberation sans', 'dejavu sans'],
            'helvetica': ['arial', 'liberation sans', 'dejavu sans'],
            'times': ['times new roman', 'liberation serif', 'dejavu serif'],
            'times new roman': ['times', 'liberation serif', 'dejavu serif'],
            'courier': ['courier new', 'liberation mono', 'dejavu sans mono'],
            'courier new': ['courier', 'liberation mono', 'dejavu sans mono'],
        }
        
        # Check for direct substitutions
        for key, subs in substitutions.items():
            if key in font_name_lower:
                suggestions.extend(subs)
        
        # Search for similar installed fonts
        for font_dir in self.get_system_font_directories():
            if not font_dir.exists():
                continue
                
            try:
                for font_file in font_dir.rglob('*'):
                    if (font_file.is_file() and 
                        font_file.suffix.lower() in self.font_extensions):
                        
                        font_stem = font_file.stem.lower()
                        # Check for partial matches
                        if any(word in font_stem for word in font_name_lower.split()):
                            suggestions.append(font_file.stem)
                            
            except (PermissionError, OSError):
                continue
        
        # Remove duplicates and return
        return list(set(suggestions))
    
    def get_installed_fonts_list(self) -> List[str]:
        """Get a list of all installed fonts.
        
        Returns:
            List of installed font names
        """
        fonts = set()
        
        for font_dir in self.get_system_font_directories():
            if not font_dir.exists():
                continue
                
            try:
                for font_file in font_dir.rglob('*'):
                    if (font_file.is_file() and 
                        font_file.suffix.lower() in self.font_extensions):
                        fonts.add(font_file.stem)
            except (PermissionError, OSError):
                continue
        
        return sorted(list(fonts))