"""Translate text blocks using Claude via Amazon Bedrock (streaming)."""
import json
import time
import sys
import boto3


_client = None


def _get_client(region: str):
    global _client
    if _client is None:
        _client = boto3.client("bedrock-runtime", region_name=region)
    return _client


def translate_blocks(blocks: list[dict], model: str, region: str) -> list[str]:
    """Translate a list of text blocks (one page) via Bedrock Claude with streaming."""
    if not blocks:
        return []

    client = _get_client(region)

    prompt = (
        "Translate the following Japanese text blocks to Korean.\n"
        "Return ONLY a JSON array of objects with \"id\" and \"text\" keys.\n"
        "Each element corresponds to the input block with the same id.\n"
        "ALL Japanese text must be converted to Korean, including proper nouns.\n"
        "For proper nouns (person names, company names, product names), transliterate them into Korean (한글).\n"
        "Example: カプコン→캡콤, 筑紫啓雄→츠쿠시 아키오, モンスターハンターワイルズ→몬스터 헌터 와일즈\n"
        "Preserve paragraph breaks (\\n) within blocks but do not add new ones.\n\n"
        f"Input blocks:\n{json.dumps(blocks, ensure_ascii=False)}"
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": prompt}],
    })

    for attempt in range(3):
        try:
            t0 = time.time()
            print("    Calling Bedrock (streaming)...", end="", flush=True)

            resp = client.invoke_model_with_response_stream(modelId=model, body=body)
            chunks = []
            for event in resp["body"]:
                chunk = json.loads(event["chunk"]["bytes"])
                if chunk["type"] == "content_block_delta":
                    chunks.append(chunk["delta"]["text"])
                    print(".", end="", flush=True)

            print(f" {time.time() - t0:.1f}s")
            text = "".join(chunks)

            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]

            translated = json.loads(text.strip())
            tr_map = {item["id"]: item["text"] for item in translated}
            return [tr_map.get(b["id"], b["text"]) for b in blocks]
        except Exception as e:
            print(f"\n    Attempt {attempt + 1} failed: {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"Translation failed after 3 attempts: {e}") from e
