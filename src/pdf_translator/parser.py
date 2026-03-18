"""PDF parsing: extract text blocks using PyMuPDF for better column detection."""
import fitz
from dataclasses import dataclass


@dataclass
class TextBlock:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    font_size: float
    color: tuple = (0, 0, 0)
    bold: bool = False
    over_image: bool = False


@dataclass
class PageData:
    width: float
    height: float
    text_blocks: list[TextBlock]


def _rects_overlap(a, b) -> bool:
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def _extract_line_blocks(block_dict, image_rects) -> list[TextBlock]:
    """Extract TextBlocks from a PyMuPDF block dict, merging same-row fragments
    but splitting by column (large horizontal gap)."""
    lines = block_dict["lines"]
    if not lines:
        return []

    # Group lines by y-position (same visual row)
    rows: list[list] = []
    for line in lines:
        bbox = line["bbox"]
        # Find existing row with matching y
        merged = False
        for row in rows:
            if abs(row[0]["bbox"][1] - bbox[1]) < 3:
                row.append(line)
                merged = True
                break
        if not merged:
            rows.append([line])

    results = []
    for row in rows:
        # Sort fragments left to right
        row.sort(key=lambda l: l["bbox"][0])

        # Split row into column segments by large horizontal gaps
        segments: list[list] = [[row[0]]]
        for frag in row[1:]:
            prev_x1 = segments[-1][-1]["bbox"][2]
            cur_x0 = frag["bbox"][0]
            gap = cur_x0 - prev_x1
            # Gap > 15pt = column break
            if gap > 15:
                segments.append([frag])
            else:
                segments[-1].append(frag)

        for seg in segments:
            # Combine all spans from all fragments in this segment
            all_spans = []
            for frag in seg:
                all_spans.extend(frag["spans"])

            text = "".join(s["text"] for s in all_spans).strip()
            if not text:
                continue

            font_sizes, colors = [], []
            bold_count = total = 0
            for s in all_spans:
                if s["text"].strip():
                    font_sizes.append(s["size"])
                    c = s["color"]
                    colors.append(((c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF))
                    if s["flags"] & 16:
                        bold_count += 1
                    total += 1

            if not font_sizes:
                continue

            normal_sizes = [s for s in font_sizes if s > 4.0] or font_sizes
            fs = max(set(normal_sizes), key=normal_sizes.count)
            dc = max(set(colors), key=colors.count)

            x0 = min(f["bbox"][0] for f in seg)
            y0 = min(f["bbox"][1] for f in seg)
            x1 = max(f["bbox"][2] for f in seg)
            y1 = max(f["bbox"][3] for f in seg)
            bbox = (x0, y0, x1, y1)

            results.append(TextBlock(
                x0=x0, y0=y0, x1=x1, y1=y1,
                text=text, font_size=fs,
                color=(dc[0] / 255, dc[1] / 255, dc[2] / 255),
                bold=bold_count > total / 2 if total else False,
                over_image=any(_rects_overlap(bbox, ir) for ir in image_rects),
            ))

    return results


def _merge_blocks(blocks: list[TextBlock]) -> list[TextBlock]:
    if not blocks:
        return []
    blocks.sort(key=lambda b: (round(b.x0 / 50), b.y0))
    merged = [blocks[0]]
    for block in blocks[1:]:
        prev = merged[-1]
        v_gap = block.y0 - prev.y1
        overlap_x0 = max(prev.x0, block.x0)
        overlap_x1 = min(prev.x1, block.x1)
        overlap_w = max(0, overlap_x1 - overlap_x0)
        min_w = min(prev.x1 - prev.x0, block.x1 - block.x0)
        h_overlap = overlap_w / min_w if min_w > 0 else 0
        same_font = abs(prev.font_size - block.font_size) < 1.0
        same_style = prev.bold == block.bold and prev.color == block.color
        is_divider = "＿＿＿" in block.text or "＿＿＿" in prev.text
        if (not is_divider
                and -4 <= v_gap < block.font_size * 0.8
                and h_overlap > 0.4
                and same_font and same_style
                and abs(prev.x0 - block.x0) < block.font_size * 3):
            prev.text += "\n" + block.text
            prev.y1 = max(prev.y1, block.y1)
            prev.x0 = min(prev.x0, block.x0)
            prev.x1 = max(prev.x1, block.x1)
            prev.over_image = prev.over_image or block.over_image
        else:
            merged.append(block)
    return merged


def parse_pdf(pdf_path: str) -> list[PageData]:
    doc = fitz.open(pdf_path)
    pages = []
    for page in doc:
        data = page.get_text("dict")
        image_rects = [b["bbox"] for b in data["blocks"] if b["type"] == 1]
        raw_blocks = []
        for block in data["blocks"]:
            if block["type"] != 0:
                continue
            if block["bbox"][1] < 0 or block["bbox"][3] < 0:
                continue
            raw_blocks.extend(_extract_line_blocks(block, image_rects))
        pages.append(PageData(
            width=float(page.rect.width), height=float(page.rect.height),
            text_blocks=_merge_blocks(raw_blocks),
        ))
    doc.close()
    return pages
