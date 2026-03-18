# pdf-translate

CLI tool that translates Japanese PDF documents into Korean, preserving the original layout, images, and text styling. Translation powered by Claude via Amazon Bedrock.

## Features

- Translates selectable text from Japanese to Korean (no OCR)
- Preserves original layout, images, tables, and formatting
- Font color and bold style preserved
- Font subsetting keeps output size close to original
- Streaming Bedrock API with progress display
- Proper nouns transliterated to Korean (한글)

## Prerequisites

- Python 3.11+
- AWS credentials with Bedrock access (Claude model enabled)
- `fontTools` with mutator support

## Installation

```bash
git clone https://github.com/hyundonk/pdf-translate.git
cd pdf-translate
pip install -e .
./setup_fonts.sh
```

`setup_fonts.sh` downloads Noto Sans KR and creates static Regular/Bold TTF files with TrueType outlines (`glyf` table) for maximum PDF viewer compatibility.

## Usage

```bash
# Basic usage (output: input_ko.pdf)
pdf-translate input.pdf

# Specify output file
pdf-translate input.pdf -o output_ko.pdf

# Custom model and region
pdf-translate input.pdf --model us.anthropic.claude-3-5-sonnet-20241022-v2:0 --region us-east-1
```

### Options

| Flag | Default | Description |
|---|---|---|
| `input` | (required) | Input Japanese PDF path |
| `-o, --output` | `{input}_ko.pdf` | Output file path |
| `--model` | `global.anthropic.claude-sonnet-4-6` | Bedrock model ID |
| `--region` | `us-west-2` | AWS region |

## Architecture

```
Input PDF
  → Parse (PyMuPDF): extract text blocks with position, font size, color, bold
  → Prepare: join line breaks, split at sentence boundaries
  → Translate (Claude via Bedrock): batch per page, streaming
  → Render (PyMuPDF):
      1. Redact original Japanese text (transparent over images, white over text)
      2. Overlay Korean text with matching style via TextWriter
      3. Subset fonts to minimize file size
  → Output PDF
```

## Font Compatibility Note

Korean fonts are embedded as `CIDFontType2` (TrueType outlines) for universal PDF viewer compatibility. CFF-based fonts (`CIDFontType0`) cause rendering issues in Apple Preview and some Windows viewers.

## Limitations

- Scanned/image-only PDFs not supported (no OCR)
- Complex multi-column layouts may have imperfect text grouping
- Vertical Japanese text not handled
- Some hardcoded thresholds tuned for common document layouts (see IMPROVEMENT_PLAN.md)

## License

Noto Sans KR is licensed under the [SIL Open Font License](https://scripts.sil.org/OFL).
