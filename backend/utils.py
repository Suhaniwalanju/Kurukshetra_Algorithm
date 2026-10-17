import os
import re

RESERVED_WINDOWS_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
}

def sanitize_filename(name: str, max_length: int = 100) -> str:
    """
    Sanitizes arbitrary strings (topics, technology names, levels) into safe,
    cross-platform file/directory basenames (especially Windows NTFS/FAT32).
    - Removes invalid characters: <>:"/\\|?* and ASCII control characters (0x00-0x1F).
    - Replaces whitespace and slashes with underscores.
    - Strips leading/trailing dots and spaces.
    - Guards against Windows reserved names (CON, NUL, COM1, etc.).
    - Caps filename length to prevent path overflow.
    """
    if not name:
        return "deck"

    # Replace forbidden chars with underscore
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(name))
    # Replace spaces with underscores
    sanitized = sanitized.replace(' ', '_')
    # Collapse multiple underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Strip leading/trailing dots and underscores
    sanitized = sanitized.strip('._ ')

    if not sanitized:
        sanitized = "deck"

    # Check for Windows reserved names
    if sanitized.upper() in RESERVED_WINDOWS_NAMES:
        sanitized = f"{sanitized}_safe"

    return sanitized[:max_length]
