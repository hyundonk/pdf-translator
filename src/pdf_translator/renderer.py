"""Render translated PDF: redact Japanese text, overlay Korean with matching style."""
import os
import tempfile
import fitz
from fontTools.ttLib import TTFont
from fontTools.subset import Subsetter

from .parser import PageData, TextBlock

_FONT_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "fonts")
_FONT_REGULAR = os.path.join(_FONT_DIR, "NotoSansKR-400.ttf")
_FONT_BOLD = os.path.join(_FONT_DIR, "NotoSansKR-700.ttf")


def _subset_font(font_path: str, text: str) -> str:
    """Create a subsetted font containing only glyphs needed for text."""
    from fontTools.subset import Options
    font = TTFont(font_path)
    options = Options()
    options.name_IDs = ["*"]  # keep all name records
    options.name_legacy = True
    options.name_languages = ["*"]
    subsetter = Subsetter(options=options)
    subsetter.populate(text=text)
    subsetter.subset(font)
    tmp = tempfile.NamedTemporaryFile(suffix=".ttf", delete=False)
    font.save(tmp.name)
    font.close()
    return tmp.name


def _wrap_text(font: fitz.Font, text: str, max_width: float, font_size: float) -> list[str]:
    result = []
    for paragraph in text.split("\n"):
        chars = list(paragraph)
        if not chars:
            result.append("")
            continue
        line = ""
        for ch in chars:
            test = line + ch
            if font.text_length(test, fontsize=font_size) > max_width and line:
                result.append(line)
                line = ch
            else:
                line = test
        if line:
            result.append(line)
    return result


def _adjust_blocks(pages_data: list[PageData]):
    for page_data in pages_data:
        for b in page_data.text_blocks:
            if b.x0 < 180 and b.x1 < 170:
                b.x1 = 170


def render_pdf(
    input_path: str,
    output_path: str,
    pages_data: list[PageData],
    translations: list[list[str]],
    dpi: int = 300,
):
    _adjust_blocks(pages_data)

    # Collect all translated text to subset fonts
    all_text = "".join(t for page_tr in translations for t in page_tr)

    regular_sub = _subset_font(os.path.abspath(_FONT_REGULAR), all_text)
    bold_sub = _subset_font(os.path.abspath(_FONT_BOLD), all_text)

    font_regular = fitz.Font(fontfile=regular_sub)
    font_bold = fitz.Font(fontfile=bold_sub)

    doc = fitz.open(input_path)

    for page_idx, (page_data, page_translations) in enumerate(zip(pages_data, translations)):
        page = doc[page_idx]

        for block in page_data.text_blocks:
            rect = fitz.Rect(block.x0 - 1, block.y0 - 1, block.x1 + 1, block.y1 + 1)
            if block.over_image:
                page.add_redact_annot(rect, fill=False)
            else:
                page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        tw_by_color = {}
        for block, translated in zip(page_data.text_blocks, page_translations):
            color_key = block.color
            if color_key not in tw_by_color:
                tw_by_color[color_key] = fitz.TextWriter(page.rect)

            font = font_bold if block.bold else font_regular
            box_w = block.x1 - block.x0
            font_size = block.font_size
            line_height = font_size * 1.35

            wrapped = _wrap_text(font, translated, box_w, font_size)

            orig_lines = len(block.text.split("\n"))
            if orig_lines == 1 and len(wrapped) > 1:
                size = font_size
                while size > font_size * 0.6 and len(wrapped) > 1:
                    size -= 0.5
                    wrapped = _wrap_text(font, translated, box_w, size)
                font_size = size
                line_height = font_size * 1.35

            y = block.y0 + font_size
            for line in wrapped:
                tw_by_color[color_key].append(
                    fitz.Point(block.x0, y), line,
                    font=font, fontsize=font_size,
                )
                y += line_height

        for color, writer in tw_by_color.items():
            writer.write_text(page, color=color)

    doc.save(output_path, garbage=4, deflate=True)
    doc.close()

    # Cleanup temp files
    os.unlink(regular_sub)
    os.unlink(bold_sub)
