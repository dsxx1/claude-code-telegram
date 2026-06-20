"""MCP server exposing Telegram-specific tools to Claude.

Runs as a stdio transport server. The ``send_image_to_user`` tool validates
file existence and extension, then returns a success string. Actual Telegram
delivery is handled by the bot's stream callback which intercepts the tool
call.

``send_link_via_gdrive`` is different: it actually performs the upload to
Google Drive inside the MCP server process and returns the public share
URL. The bot does not intercept it; Claude simply includes the returned
URL in the response text.
"""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}
TEXT_EXTENSIONS_FOR_GDRIVE = {".txt", ".md"}

mcp = FastMCP("telegram")


@mcp.tool()
async def send_image_to_user(file_path: str, caption: str = "") -> str:
    """Send an image file to the Telegram user.

    Args:
        file_path: Absolute path to the image file.
        caption: Optional caption to display with the image.

    Returns:
        Confirmation string when the image is queued for delivery.
    """
    path = Path(file_path)

    if not path.is_absolute():
        return f"Error: path must be absolute, got '{file_path}'"

    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        return (
            f"Error: unsupported image extension '{path.suffix}'. "
            f"Supported: {', '.join(sorted(IMAGE_EXTENSIONS))}"
        )

    if not path.is_file():
        return f"Error: file not found: {file_path}"

    return f"Image queued for delivery: {path.name}"


@mcp.tool()
async def send_file_to_user(file_path: str, caption: str = "") -> str:
    """Send any file (md, txt, csv, xlsx, docx, pdf, ...) to the Telegram user as a document.

    Use this whenever the user asks to export, download or receive content as
    a file (e.g. "выгрузи в md", "пришли файлом", "сохрани в txt и отправь").
    First write the file to disk (UTF-8 for text formats), then call this
    tool with the absolute path.

    Args:
        file_path: Absolute path to the file.
        caption: Optional caption.

    Returns:
        Confirmation string when the file is queued for delivery.
    """
    path = Path(file_path)

    if not path.is_absolute():
        return f"Error: path must be absolute, got '{file_path}'"

    if not path.is_file():
        return f"Error: file not found: {file_path}"

    if path.stat().st_size > 50 * 1024 * 1024:
        return "Error: file exceeds the 50 MB Telegram limit"

    return f"File queued for delivery: {path.name}"


@mcp.tool()
async def send_link_via_gdrive(file_path: str, caption: str = "") -> str:
    """Upload a .txt or .md file to Google Drive and return a public share link.

    Use this whenever the user asks to receive a .txt or .md file by
    Google Drive link (instead of as a Telegram document). The file is
    uploaded to the user's Drive, share permission is set to "anyone with
    link -> reader", and the returned URL is included verbatim in the
    bot's reply. For other formats (images, pdf, xlsx, etc.) keep using
    send_image_to_user / send_file_to_user.

    Args:
        file_path: Absolute path to the .txt or .md file.
        caption: Optional caption stored as the Drive file description.

    Returns:
        The public share URL on success, or an "Error: ..." string on
        validation / upload failure (Claude should surface it to the
        user verbatim).
    """
    path = Path(file_path)

    if not path.is_absolute():
        return f"Error: path must be absolute, got '{file_path}'"

    if path.suffix.lower() not in TEXT_EXTENSIONS_FOR_GDRIVE:
        return (
            f"Error: send_link_via_gdrive only handles "
            f"{', '.join(sorted(TEXT_EXTENSIONS_FOR_GDRIVE))}; "
            f"got '{path.suffix}'. Use send_file_to_user instead."
        )

    if not path.is_file():
        return f"Error: file not found: {file_path}"

    if path.stat().st_size > 100 * 1024 * 1024:
        return "Error: file exceeds the 100 MB upload limit"

    try:
        # The MCP server is launched as a standalone script (not a package),
        # so relative imports fail. Fall back to direct sibling import.
        try:
            from .gdrive import GDriveError, upload_and_share  # type: ignore
        except ImportError:
            import sys as _sys

            _here = Path(__file__).resolve().parent
            if str(_here) not in _sys.path:
                _sys.path.insert(0, str(_here))
            from gdrive import GDriveError, upload_and_share  # type: ignore
    except Exception as e:
        return f"Error: gdrive helper not importable ({e})"

    try:
        url = upload_and_share(path, caption=caption)
    except GDriveError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error: unexpected upload failure ({e})"

    return url


if __name__ == "__main__":
    mcp.run(transport="stdio")
