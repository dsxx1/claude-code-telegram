"""Validate image file paths and prepare them for Telegram delivery.

Used by the MCP ``send_image_to_user`` tool intercept — the stream callback
validates each path via :func:`validate_image_path` and collects
:class:`ImageAttachment` objects for later Telegram delivery.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger()

# Supported image extensions -> MIME types
IMAGE_EXTENSIONS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
}

# Raster formats that can be sent via reply_photo() (Telegram supports these natively)
TELEGRAM_PHOTO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}

# Safety caps
MAX_IMAGES_PER_RESPONSE = 10
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
PHOTO_SIZE_LIMIT = 10 * 1024 * 1024  # 10 MB — Telegram photo API limit


@dataclass
class ImageAttachment:
    """An image file to attach to a Telegram response."""

    path: Path
    mime_type: str
    original_reference: str


def allowed_roots(approved_directory: Path) -> list:
    """Approved directory plus targets of junction links directly inside it.

    The approved directory may consist of junction links
    (C:\\projects\\<proj> -> C:\\<proj>); Path.resolve() unwraps them, so a
    file saved through a junction path resolves outside the approved
    directory.  Junction targets therefore count as allowed roots too.
    """
    roots = [approved_directory.resolve()]
    try:
        roots += [c.resolve() for c in approved_directory.iterdir() if c.is_dir()]
    except OSError:
        pass
    return roots


def is_under_allowed_roots(resolved: Path, approved_directory: Path) -> bool:
    """True if *resolved* lies under the approved directory or a junction target."""
    for root in allowed_roots(approved_directory):
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def validate_image_path(
    file_path: str,
    approved_directory: Path,
    caption: str = "",
) -> Optional[ImageAttachment]:
    """Validate a single image path from an MCP ``send_image_to_user`` call.

    Returns an :class:`ImageAttachment` if the path is a valid, existing image
    inside *approved_directory*, or ``None`` otherwise.
    """
    try:
        path = Path(file_path)
        if not path.is_absolute():
            return None

        resolved = path.resolve()

        # Security: must be within approved directory (junction targets allowed)
        if not is_under_allowed_roots(resolved, approved_directory):
            logger.debug(
                "MCP image path outside approved directory",
                path=str(resolved),
                approved=str(approved_directory),
            )
            return None

        if not resolved.is_file():
            return None

        file_size = resolved.stat().st_size
        if file_size > MAX_FILE_SIZE_BYTES:
            logger.debug("MCP image file too large", path=str(resolved), size=file_size)
            return None

        ext = resolved.suffix.lower()
        mime_type = IMAGE_EXTENSIONS.get(ext)
        if not mime_type:
            return None

        return ImageAttachment(
            path=resolved,
            mime_type=mime_type,
            original_reference=caption or file_path,
        )
    except (OSError, ValueError) as e:
        logger.debug("MCP image path validation failed", path=file_path, error=str(e))
        return None


def should_send_as_photo(path: Path) -> bool:
    """Return True if the image should be sent via reply_photo().

    Raster images ≤ 10 MB are sent as photos (inline preview).
    SVGs and large files are sent as documents.
    """
    ext = path.suffix.lower()
    if ext not in TELEGRAM_PHOTO_EXTENSIONS:
        return False

    try:
        return path.stat().st_size <= PHOTO_SIZE_LIMIT
    except OSError:
        return False
