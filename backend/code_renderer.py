import os
import re
from typing import List, Dict, Any, Tuple, Optional
from pygments import lex
from pygments.lexers import get_lexer_by_name, TextLexer
from pygments.token import Token

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Table

# Pygments RGB Color Map for python-pptx
PPTX_TOKEN_COLOR_MAP = {
    Token.Keyword: (198, 120, 221),       # Magenta / Purple
    Token.Keyword.Constant: (229, 192, 123),# Amber
    Token.Name.Class: (229, 192, 123),    # Gold / Yellow
    Token.Name.Function: (97, 175, 239),  # Light Blue
    Token.Name.Builtin: (229, 192, 123),  # Gold
    Token.String: (152, 195, 121),        # Green
    Token.Number: (209, 154, 102),        # Orange
    Token.Comment: (120, 130, 145),       # Slate Gray
    Token.Operator: (86, 182, 194),       # Cyan
    Token.Punctuation: (171, 178, 191),   # Light Gray
}
DEFAULT_CODE_RGB = (240, 244, 250)

# Pygments Hex Map for ReportLab / HTML
REPORTLAB_TOKEN_HEX_MAP = {
    Token.Keyword: "#C678DD",
    Token.Keyword.Constant: "#E5C07B",
    Token.Name.Class: "#E5C07B",
    Token.Name.Function: "#61AFEF",
    Token.Name.Builtin: "#E5C07B",
    Token.String: "#98C379",
    Token.Number: "#D19A66",
    Token.Comment: "#788291",
    Token.Operator: "#56B6C2",
    Token.Punctuation: "#ABB2BF",
}
DEFAULT_CODE_HEX = "#F0F4FA"


def sanitize_code_line(line: str, max_cols: int = 60) -> str:
    """Preserves leading indentation and ensures length does not exceed max_cols without ugly wrapping."""
    if len(line) <= max_cols:
        return line
    return line[:max_cols - 3] + "..."


def split_or_excerpt_code(
    code_text: str,
    max_lines: int = 14,
    max_cols: int = 60
) -> Tuple[List[str], Optional[str]]:
    """
    Splits code exceeding limits into labeled parts ("1/2", "2/2")
    or returns an excerpt within limits alongside the full source.
    """
    raw_lines = code_text.splitlines()
    sanitized_lines = [sanitize_code_line(l, max_cols=max_cols) for l in raw_lines]
    
    if len(sanitized_lines) <= max_lines:
        return ["\n".join(sanitized_lines)], None

    # Exceeds max lines: split into labeled parts
    parts = []
    chunk_size = max_lines
    total_parts = (len(sanitized_lines) + chunk_size - 1) // chunk_size
    
    for i in range(total_parts):
        start = i * chunk_size
        end = start + chunk_size
        chunk = sanitized_lines[start:end]
        header = f"// Part {i + 1}/{total_parts}" if not code_text.startswith("#") else f"# Part {i + 1}/{total_parts}"
        parts.append(f"{header}\n" + "\n".join(chunk))
        
    excerpt = "\n".join(sanitized_lines[:max_lines])
    return parts, excerpt


def get_pygments_tokens(source_code: str, language: str) -> List[Tuple[Any, str]]:
    """Returns Pygments tokens for given language."""
    clean_lang = (language or "text").lower().strip()
    try:
        lexer = get_lexer_by_name(clean_lang, stripall=False)
    except Exception:
        lexer = TextLexer()
    return list(lex(source_code, lexer))


def render_code_block(
    code: str,
    language: str = "text",
    palette: Optional[Dict[str, str]] = None,
    font_size_pt: int = 14,
    max_lines: int = 14,
    max_cols: int = 60,
    target_format: str = "tokens",  # "tokens", "reportlab", "html"
) -> Dict[str, Any]:
    """
    Shared code block renderer used everywhere (slides, notes, exercises, quiz, PPTX, PDF).
    Guarantees:
      - Monospace font (Consolas)
      - Pygments syntax highlighting
      - At least 14pt font size
      - Max 14 lines and 60 columns
      - Preserved indentation, no line wrapping
      - Padded panel with template palette
    """
    actual_font_pt = max(14, font_size_pt)
    code_bg = (palette or {}).get("code_bg", "#1E1E2E")
    code_text_color = (palette or {}).get("code_text", "#F8F8F2")
    border_color = (palette or {}).get("primary", "#002147")

    parts, excerpt = split_or_excerpt_code(code, max_lines=max_lines, max_cols=max_cols)
    primary_code = parts[0] if parts else code

    # Tokenized syntax tree
    tokens = get_pygments_tokens(primary_code, language)

    # HTML / ReportLab formatted inline markup
    formatted_html_lines = []
    current_line = ""
    for token_type, value in tokens:
        color = REPORTLAB_TOKEN_HEX_MAP.get(token_type, DEFAULT_CODE_HEX)
        # Normalize sub-tokens
        if color == DEFAULT_CODE_HEX:
            for parent_t, p_col in REPORTLAB_TOKEN_HEX_MAP.items():
                if token_type in parent_t:
                    color = p_col
                    break
        
        # Escape HTML chars
        safe_val = value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace(" ", "&nbsp;")
        if "\n" in safe_val:
            segments = safe_val.split("\n")
            for idx, seg in enumerate(segments):
                if seg:
                    current_line += f"<font color='{color}'>{seg}</font>"
                if idx < len(segments) - 1:
                    formatted_html_lines.append(current_line)
                    current_line = ""
        else:
            current_line += f"<font color='{color}'>{safe_val}</font>"
            
    if current_line:
        formatted_html_lines.append(current_line)

    html_markup = "<br/>".join(formatted_html_lines)

    return {
        "code": primary_code,
        "parts": parts,
        "excerpt": excerpt,
        "full_code": code,
        "is_split": len(parts) > 1,
        "tokens": tokens,
        "font_family": "Consolas",
        "font_size_pt": actual_font_pt,
        "bg_color": code_bg,
        "text_color": code_text_color,
        "border_color": border_color,
        "padding_px": 16,
        "max_lines": max_lines,
        "max_columns": max_cols,
        "html_markup": html_markup,
    }


def render_code_block_reportlab_table(
    code: str,
    language: str = "text",
    palette: Optional[Dict[str, str]] = None,
    width: float = 510,
    font_size_pt: int = 14,
) -> Table:
    """
    Renders a ReportLab Table element with Pygments syntax highlighting and template panel padding.
    Used in PDF generation (Student Notes, Quiz, Verification Report).
    """
    block = render_code_block(code, language=language, palette=palette, font_size_pt=font_size_pt)
    c_style = ParagraphStyle(
        'CodeBlockPara',
        fontName='Courier',
        fontSize=max(10, font_size_pt - 4),  # Scale neatly for A4 printable width
        leading=max(13, font_size_pt - 1),
        textColor=colors.HexColor(block["text_color"]),
    )
    p = Paragraph(block["html_markup"], c_style)
    t = Table([[p]], colWidths=[width], style=[
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor(block["bg_color"])),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor(block["border_color"])),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
    ])
    return t
