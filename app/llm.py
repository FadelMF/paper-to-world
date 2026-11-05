"""Vendor-agnostic LLM client.

Supports OpenAI-compatible Chat Completions and Responses endpoints.
Select the protocol with LLM_API and, optionally, VISION_API.

Text agents use LLM_*. Agents that look at images (figures, screenshots) use VISION_MODEL, with
VISION_BASE_URL and VISION_API_KEY defaulting to the LLM_* values when the same provider serves both.
"""

import base64
import json
import os
import re

from openai import OpenAI
from openai.types.responses import ResponseInputContentParam

from app import store

FENCE_NAMES = {"javascript": "javascript|js|mjs", "python": "python|py|python3", "json": "json"}


USAGE = []  # one entry per model reply in this process; the pipeline saves it as usage.json


def text_settings():
    return (
        os.getenv("LLM_BASE_URL") or "https://api.meta.ai/v1",
        os.getenv("LLM_API_KEY") or os.getenv("MODEL_API_KEY"),
        os.getenv("LLM_MODEL") or "muse-wonder-1.0",
    )


def protocol():
    return os.getenv("LLM_API") or ("responses" if text_settings()[0] == "https://api.meta.ai/v1" else "chat_completions")


def configured():
    return bool(text_settings()[1])


def vision_settings():
    base, key, _ = text_settings()
    return (os.getenv("VISION_BASE_URL") or base, os.getenv("VISION_API_KEY") or key, os.getenv("VISION_MODEL"))


def vision_configured():
    return all(vision_settings())


def complete(settings, system, content, api=None):
    base_url, api_key, model = settings
    # Reserve a conservative input-byte/output-token allowance before every HTTP attempt.
    # Images use a separate conservative allowance; this is not a provider price estimate.
    text = system + (content if isinstance(content, str) else "".join(p.get("text", "") for p in content))
    images = sum(p.get("type") == "image_url" for p in content) if isinstance(content, list) else 0
    store.reserve(len(text.encode()) + int(os.getenv("LLM_MAX_TOKENS", "16000")) + images * 131072 + 4096)
    with OpenAI(base_url=base_url, api_key=api_key, timeout=float(os.getenv("LLM_TIMEOUT", "600")), max_retries=0) as client:
        return complete_with_client(client, model, system, content, api)


def complete_with_client(client, model, system, content, api=None):
    api = api or protocol()
    if api == "responses":
        parts: list[ResponseInputContentParam] = []
        if isinstance(content, str):
            parts.append({"type": "input_text", "text": content})
        else:
            for part in content:
                if part["type"] == "text":
                    parts.append({"type": "input_text", "text": part["text"]})
                else:
                    parts.append({"type": "input_image", "image_url": part["image_url"]["url"], "detail": "auto"})
        resp = client.responses.create(
            model=model,
            max_output_tokens=int(os.getenv("LLM_MAX_TOKENS", "16000")),
            input=[
                {"role": "system", "content": [{"type": "input_text", "text": system}]},
                {"role": "user", "content": parts},
            ],
            stream=False,
        )
        reply = resp.output_text
        truncated = resp.status == "incomplete" and getattr(resp.incomplete_details, "reason", None) == "max_output_tokens"
        failed = resp.status != "completed" and not truncated
    elif api == "chat_completions":
        resp = client.chat.completions.create(
            model=model,
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", "16000")),
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
        )
        choice = resp.choices[0]
        reply = choice.message.content
        truncated = choice.finish_reason == "length"
        failed = False
    else:
        raise ValueError("LLM_API / VISION_API must be chat_completions or responses.")
    usage = getattr(resp, "usage", None)
    USAGE.append(
        {
            "model": model,
            "prompt_tokens": getattr(usage, "input_tokens" if api == "responses" else "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(usage, "output_tokens" if api == "responses" else "completion_tokens", 0) or 0,
            "images": sum(isinstance(c, dict) and c.get("type") == "image_url" for c in content) if isinstance(content, list) else 0,
        }
    )
    # The server also answers tutor requests; retain a bounded history in that process.
    del USAGE[:-1000]
    if failed:
        raise RuntimeError("The model response did not complete successfully.")
    if truncated:
        raise RuntimeError("The model reply was cut off; raise LLM_MAX_TOKENS or use a model with a larger output limit.")
    if not reply:
        raise RuntimeError("The model returned an empty reply.")
    return reply


def chat(system, user):
    if not configured():
        raise RuntimeError("Set LLM_BASE_URL, LLM_API_KEY and LLM_MODEL in .env, then restart the server.")
    return complete(text_settings(), system, user)


def chat_vision(system, user, images):
    """`images` are PNG bytes, sent after the text in the order given."""
    if not vision_configured():
        raise RuntimeError("Set VISION_MODEL (and VISION_BASE_URL, VISION_API_KEY if they differ from LLM_*) in .env.")
    content = [{"type": "text", "text": user}] + [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(image).decode()}} for image in images
    ]
    return complete(vision_settings(), system, content, api=os.getenv("VISION_API") or protocol())


def parse_json(text):
    """The first JSON object in a reply, ignoring fences and surrounding prose."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("The reply contains no JSON object")


def chat_json(system, user, images=None):
    """A JSON object reply, asked once more with the parse error if needed. With images, the vision model answers."""
    send = (lambda text: chat_vision(system, text, images)) if images is not None else (lambda text: chat(system, text))
    user += "\n\nRespond with one JSON object only."
    try:
        return parse_json(send(user))
    except ValueError as error:
        return parse_json(send(user + f"\n\nYour previous reply was not valid JSON ({error}). Reply with the corrected JSON object only."))


def extract_block(text, lang):
    match = re.search(rf"```(?:{FENCE_NAMES.get(lang, lang)})[^\S\n]*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if not match:
        raise ValueError(f"The reply has no ```{lang} block")
    return match.group(1)
