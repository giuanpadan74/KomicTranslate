import hashlib

from PySide6 import QtGui

from modules.image_codec_service import png_base64_to_qimage, qimage_to_png_base64


def normalize_qimage(image: QtGui.QImage) -> QtGui.QImage:
    if image.isNull():
        return QtGui.QImage()
    return image.convertToFormat(QtGui.QImage.Format.Format_RGBA8888)


def qimage_to_bytes(image: QtGui.QImage) -> bytes:
    normalized = normalize_qimage(image)
    if normalized.isNull():
        return b""
    return normalized.bits().tobytes()


def qimage_sha256(image: QtGui.QImage) -> str:
    payload = qimage_to_bytes(image)
    return hashlib.sha256(payload).hexdigest() if payload else ""


def qimage_signature(image: QtGui.QImage) -> str:
    normalized = normalize_qimage(image)
    if normalized.isNull():
        return ""
    return f"{normalized.width()}x{normalized.height()}:{qimage_sha256(normalized)}"


def images_match(first: QtGui.QImage, second: QtGui.QImage) -> bool:
    normalized_first = normalize_qimage(first)
    normalized_second = normalize_qimage(second)
    if normalized_first.isNull() or normalized_second.isNull():
        return False
    if normalized_first.size() != normalized_second.size():
        return False
    return qimage_to_bytes(normalized_first) == qimage_to_bytes(normalized_second)


def image_from_base64(data: str) -> QtGui.QImage:
    return png_base64_to_qimage(data) if data else QtGui.QImage()


def image_to_base64(image: QtGui.QImage) -> str:
    return qimage_to_png_base64(image) if not image.isNull() else ""
