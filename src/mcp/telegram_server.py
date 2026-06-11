"""MCP server exposing Telegram-specific tools to Claude.

Runs as a stdio transport server. The ``send_image_to_user`` tool validates
file existence and extension, then returns a success string. Actual Telegram
delivery is handled by the bot's stream callback which intercepts the tool
call.
"""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"}

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


if __name__ == "__main__":
    mcp.run(transport="stdio")
