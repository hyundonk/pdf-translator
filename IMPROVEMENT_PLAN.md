# Improvement Plan: Generalizing pdf-translate for Arbitrary Japanese PDFs

## Current Hardcoded Assumptions

The following values and logic were tuned for a specific 2-page, A4,
3-column customer story PDF. Each is a potential failure point for other documents.

### 1. parser.py

| Location | Hardcoded Value | Assumption | Risk |
|---|---|---|---|
| `_extract_line_blocks` | `abs(...) < 3` (y-grouping) | Lines on same row are within 3pt vertically | Fails for documents with larger line spacing variation or superscript/subscript |
| `_extract_line_blocks` | `gap > 15` (column split) | 15pt horizontal gap = column boundary | Too small for wide-gutter docs (splits mid-line); too large for narrow-gutter docs (merges columns) |
| `_merge_blocks` | `round(b.x0 / 50)` (column sort) | Blocks within 50pt x-range are same column | Fails for documents with many narrow columns or unusual layouts |
| `_merge_blocks` | `-4 <= v_gap` | Lines overlapping up to 4pt should merge | May over-merge separate sections in tightly-spaced documents |
| `_merge_blocks` | `v_gap < font_size * 0.8` | Vertical gap < 80% of font size = same paragraph | Different documents use different paragraph spacing |
| `_merge_blocks` | `h_overlap > 0.4` | 40% horizontal overlap = same column | May fail for indented paragraphs or mixed-width blocks |
| `_merge_blocks` | `abs(prev.x0 - block.x0) < font_size * 3` | Left edges within 3x font size = same column | Arbitrary; fails for large indents |
| `_merge_blocks` | `"＿＿＿"` divider detection | Only this specific divider pattern | Other dividers (───, ━━━, blank lines) not detected |
| `_extract_line_blocks` | `font_sizes if s > 4.0` | Sizes ≤ 4pt are bullets/decorative | May filter out legitimate small text (footnotes, captions) |
| `parse_pdf` | `bbox[1] < 0` filter | Negative y = off-page content | Some PDFs use negative coordinates legitimately |

### 2. renderer.py

| Location | Hardcoded Value | Assumption | Risk |
|---|---|---|---|
| `_adjust_blocks` | `b.x0 < 180` | Left column is x < 180pt | Completely wrong for different page layouts |
| `_adjust_blocks` | `b.x1 = 170` | Expand left column to 170pt | Arbitrary; may overlap center column in other docs |
| `_wrap_text` | Character-level wrapping | No word-boundary awareness | Splits English words mid-character; ugly for mixed JP/EN text |
| Redaction | `rect expanded by 1pt` | 1pt margin covers text edges | May not cover all text in documents with different rendering |
| `line_height = font_size * 1.35` | Fixed line height ratio | 1.35x is standard | Some documents use tighter or looser leading |
| Single-line shrink | `font_size * 0.6` minimum | 60% shrink is acceptable | May be too aggressive or not enough for different content |
| White fill redaction | `fill=(1, 1, 1)` | Background is white | Fails for colored backgrounds, gradients, or textured pages |

### 3. cli.py

| Location | Hardcoded Value | Assumption | Risk |
|---|---|---|---|
| `_prepare_text` | `"●"` bullet detection | Only ● bullets | Misses ・, ■, ▪, ▶, numbered lists (1., (1), ①) |
| `_prepare_text` | `len(joined) < 100` | Short = title, don't split | Some short paragraphs legitimately contain multiple sentences |
| `_prepare_text` | Split at `。` only | Japanese sentence ending | Misses `！`, `？`, `」` at paragraph boundaries |

### 4. translator.py

| Location | Hardcoded Value | Assumption | Risk |
|---|---|---|---|
| `max_tokens: 8192` | Fixed output limit | Enough for one page | Pages with dense text may need more |
| Single API call per page | All blocks fit in one prompt | Prompt + response < model context | Very text-heavy pages may exceed context window |

---

## Improvement Plan

### Priority 1: Critical for general use (breaks on most other PDFs)

#### P1.1 — Remove hardcoded left column adjustment
**Problem**: `_adjust_blocks` assumes left column at x<180, expands to 170pt.
**Fix**: Remove `_adjust_blocks` entirely. Instead, compute per-block expansion:
- For each block, find the nearest block to its right on the same y-range
- Expand x1 to `min(nearest_right_block.x0 - 10, x1 * 1.2)` — 20% wider max, never overlapping neighbors
- This adapts to any layout automatically.

#### P1.2 — Adaptive column gap detection
**Problem**: 15pt gap threshold is arbitrary.
**Fix**: Per page, analyze all horizontal gaps between same-row fragments:
- Compute gap histogram
- Find the natural break point (bimodal distribution: within-line gaps vs column gaps)
- Use the valley between the two modes as the threshold
- Fallback to `median_gap * 2` if distribution is unimodal

#### P1.3 — Background color detection for redaction
**Problem**: White fill assumes white background.
**Fix**: Before redacting, sample the background color at the block's position:
- Render a small region of the page (without text) as an image
- Sample the dominant color in that region
- Use that color as the redaction fill
- For complex backgrounds (gradients, images), use `fill=False` (transparent)

#### P1.4 — Detect actual page background under text blocks
**Problem**: `over_image` only checks PyMuPDF image blocks, misses vector backgrounds.
**Fix**: Render the page at low DPI, check if the region under each text block is
non-white. If so, treat as `over_image=True` (transparent redaction).

### Priority 2: Important for quality (causes visual issues)

#### P2.1 — Word-aware text wrapping
**Problem**: Character-level wrapping splits English words mid-character.
**Fix**: Wrap at word boundaries for Latin text, character boundaries for CJK:
- Split text into tokens (CJK chars are individual tokens, Latin words are tokens)
- Wrap at token boundaries
- Fall back to character-level only when a single token exceeds line width

#### P2.2 — Adaptive line height
**Problem**: Fixed 1.35x line height ratio.
**Fix**: Compute from original block:
- `line_height = (block.y1 - block.y0) / original_line_count`
- This preserves the original document's leading

#### P2.3 — Vertical overflow detection
**Problem**: Translated text may overflow bounding box, overlapping blocks below.
**Fix**: After wrapping, check if total text height exceeds box height:
- If overflow < 20%: extend bounding box downward (check no collision with next block)
- If overflow > 20%: reduce font size incrementally until it fits
- Log a warning when overflow occurs

#### P2.4 — Extended bullet/list detection
**Problem**: Only `●` is detected.
**Fix**: Detect common Japanese/Unicode list markers:
```python
BULLETS = {"●", "・", "■", "▪", "▶", "◆", "○", "□", "※"}
# Also detect numbered patterns: r"^\d+[.、）]", r"^[（(]\d+[）)]", r"^[①-⑳]"
```

#### P2.5 — Extended divider detection
**Problem**: Only `＿＿＿` is detected.
**Fix**: Detect common divider patterns:
```python
DIVIDERS = {"＿", "─", "━", "―", "—", "="}
# A line is a divider if >60% of its characters are divider chars
```

### Priority 3: Nice to have (edge cases)

#### P3.1 — Adaptive merge thresholds
**Problem**: Fixed -4pt overlap and 0.8x gap thresholds.
**Fix**: Compute per-page from actual line spacing:
- Measure the most common vertical gap between consecutive same-column lines
- Set merge threshold to `common_gap * 1.5`
- Set overlap threshold to `common_gap * -0.5`

#### P3.2 — Multi-sentence paragraph splitting improvements
**Problem**: Splitting at `。` only, with 100-char threshold.
**Fix**:
- Split at `。`, `！`, `？` followed by non-quote characters
- Use line count instead of char count: don't split blocks with ≤3 original lines
- Preserve `「...」` quoted passages as single units

#### P3.3 — Large page chunking for translation
**Problem**: Very text-heavy pages may exceed API context window.
**Fix**: If a page has >50 blocks or >5000 chars, split into multiple API calls
(groups of ~20 blocks each) and merge results.

#### P3.4 — Font style matching
**Problem**: Single font (Noto Sans CJK KR) for all text.
**Fix**: Detect original font characteristics and select closest Korean match:
- Serif original → use Noto Serif CJK KR
- Monospace original → use Noto Sans Mono CJK KR
- Light weight → use NotoSansCJKkr-Light.otf

#### P3.5 — Table content translation (optional)
**Problem**: Tables are completely skipped.
**Fix**: Detect table cells, translate cell content individually, render back
into the same cell positions. Complex but high value for data-heavy documents.

---

## Implementation Order

For a production-ready general-purpose tool, implement in this order:

1. **P1.1** Remove hardcoded column adjustment → 30 min
2. **P1.3** Background color detection → 1 hour
3. **P2.1** Word-aware wrapping → 1 hour
4. **P1.2** Adaptive column gap → 2 hours
5. **P2.3** Vertical overflow detection → 1 hour
6. **P2.4 + P2.5** Extended bullets and dividers → 30 min
7. **P2.2** Adaptive line height → 30 min
8. **P3.1** Adaptive merge thresholds → 1 hour
9. **P3.2** Better paragraph splitting → 1 hour
10. **P1.4** Vector background detection → 1 hour
11. **P3.3** Large page chunking → 1 hour
12. **P3.4** Font style matching → 2 hours

Total estimated effort: ~12 hours for full generalization.

Items 1-6 alone (~6 hours) would handle the vast majority of standard
Japanese business documents (reports, case studies, brochures, manuals).
