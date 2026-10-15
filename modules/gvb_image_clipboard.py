import os
import subprocess
import tempfile

import cv2
import numpy as np
from PIL import ImageGrab
from PySide6 import QtGui


def copy_image_file_to_windows_clipboard(image_path: str) -> bool:
    if not image_path or not os.path.exists(image_path):
        return False
    command = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        f"$img = [System.Drawing.Image]::FromFile('{image_path}'); "
        "try { [System.Windows.Forms.Clipboard]::SetImage($img); $true } "
        "finally { $img.Dispose() }"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", command],
            capture_output=True,
            text=True,
            creationflags=0x08000000,
            timeout=15,
            check=False,
        )
        return result.returncode == 0 and "$true" not in (result.stderr or "")
    except Exception:
        return False


def save_cv2_image_to_clipboard(image_array) -> tuple[bool, str]:
    if image_array is None:
        return False, ""
    temp_path = os.path.join(tempfile.gettempdir(), 'gvb_image.png')
    if not cv2.imwrite(temp_path, image_array):
        return False, temp_path
    return copy_image_file_to_windows_clipboard(temp_path), temp_path


def copy_qimage_to_windows_clipboard(image: QtGui.QImage) -> bool:
    if image.isNull():
        return False
    ptr = image.bits()
    arr = np.array(ptr).reshape(image.height(), image.bytesPerLine())
    arr = arr[:, :image.width() * 4].reshape((image.height(), image.width(), 4)).copy()
    arr = cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)
    return save_cv2_image_to_clipboard(arr)[0]


def copy_text_to_windows_clipboard(text: str) -> bool:
    if not text:
        return False
    escaped = text.replace('"', '\\"').replace('\n', '`n')
    command = f'Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.Clipboard]::SetText("{escaped}")'
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", command],
            capture_output=True,
            text=True,
            creationflags=0x08000000,
            timeout=10,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


def get_image_from_windows_clipboard() -> QtGui.QImage:
    try:
        grabbed = ImageGrab.grabclipboard()
    except Exception:
        return QtGui.QImage()
    if grabbed is None:
        return QtGui.QImage()
    if hasattr(grabbed, 'convert'):
        rgba = grabbed.convert('RGBA')
        data = rgba.tobytes('raw', 'RGBA')
        image = QtGui.QImage(data, rgba.size[0], rgba.size[1], QtGui.QImage.Format.Format_RGBA8888)
        return image.copy()
    return QtGui.QImage()
