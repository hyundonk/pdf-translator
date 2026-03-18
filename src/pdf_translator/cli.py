"""CLI entry point for pdf-translate."""
import argparse
import os
import sys
import time

from .parser import parse_pdf
from .translator import translate_blocks
from .renderer import render_pdf


def _prepare_text(text: str) -> str:
    """Join lines into continuous text, re-inserting paragraph breaks at sentence boundaries."""
    joined = text.replace("\n", "")
    # Restore line breaks before bullet markers
    joined = joined.replace("●", "\n●")
    if joined.startswith("\n"):
        joined = joined[1:]
    # Only split at 。 for long text (>100 chars), skip for titles/short blocks
    if len(joined) < 100:
        return joined
    parts = []
    buf = ""
    for i, ch in enumerate(joined):
        buf += ch
        if ch == "\n":
            parts.append(buf.rstrip("\n"))
            buf = ""
        elif ch == "。" and i + 1 < len(joined) and joined[i + 1] != "\n":
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    return "\n".join(p for p in parts if p)


def main():
    parser = argparse.ArgumentParser(description="Translate Japanese PDF to Korean")
    parser.add_argument("input", help="Input Japanese PDF path")
    parser.add_argument("-o", "--output", help="Output file path (default: {input}_kr.pdf)")
    parser.add_argument("--model", default="global.anthropic.claude-sonnet-4-6",
                        help="Bedrock model ID")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument("--dpi", type=int, default=300, help="Background render DPI")
    args = parser.parse_args()

    if not os.path.exists(args.input):
        print(f"Error: {args.input} not found", file=sys.stderr)
        sys.exit(1)

    output = args.output or args.input.rsplit(".", 1)[0] + "_kr.pdf"
    total_start = time.time()

    t0 = time.time()
    print(f"Parsing {args.input}...")
    pages_data = parse_pdf(args.input)
    print(f"  Found {len(pages_data)} pages ({time.time() - t0:.1f}s)")

    translations = []
    for i, page in enumerate(pages_data):
        blocks = [{"id": j, "text": _prepare_text(b.text)} for j, b in enumerate(page.text_blocks)]
        print(f"  Page {i + 1}/{len(pages_data)}: {len(blocks)} text blocks")
        if blocks:
            translated = translate_blocks(blocks, args.model, args.region)
        else:
            translated = []
        translations.append(translated)

    t0 = time.time()
    print(f"Rendering {output}...")
    render_pdf(args.input, output, pages_data, translations, dpi=args.dpi)
    print(f"  Render: {time.time() - t0:.1f}s")

    print(f"Done! Output: {output} (total: {time.time() - total_start:.1f}s)")
