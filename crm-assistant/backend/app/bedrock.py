"""Amazon Bedrock client: chat (Claude), embeddings (Cohere), fact/opinion classifier."""
import json
import boto3
from . import config

_rt = boto3.client("bedrock-runtime", region_name=config.AWS_REGION)


def chat(system_prompt, messages, max_tokens=1024, temperature=0.2, model_id=None):
    """messages: list of {"role": "user"|"assistant", "text": str}. Returns text."""
    model_id = model_id or config.CHAT_MODEL_ID
    converse_msgs = [
        {"role": m["role"], "content": [{"text": m["text"]}]} for m in messages
    ]
    kwargs = {
        "modelId": model_id,
        "messages": converse_msgs,
        "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature},
    }
    if system_prompt:
        kwargs["system"] = [{"text": system_prompt}]
    resp = _rt.converse(**kwargs)
    return resp["output"]["message"]["content"][0]["text"]


def embed(texts, input_type="search_document"):
    """Embed a list of texts using Cohere multilingual. Returns list of vectors."""
    if isinstance(texts, str):
        texts = [texts]
    # Cohere allows up to 96 texts per call.
    out = []
    for i in range(0, len(texts), 90):
        batch = texts[i:i + 90]
        body = json.dumps({"texts": batch, "input_type": input_type})
        resp = _rt.invoke_model(
            modelId=config.EMBED_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=body,
        )
        data = json.loads(resp["body"].read())
        out.extend(data["embeddings"])
    return out


def embed_query(text):
    return embed([text], input_type="search_query")[0]


IMAGE_FORMATS = {"png": "png", "jpg": "jpeg", "jpeg": "jpeg", "gif": "gif", "webp": "webp"}


def describe_image(image_bytes, fmt="png", note=None):
    """Use Claude vision to produce a searchable description + OCR of an image."""
    fmt = IMAGE_FORMATS.get(fmt.lower().lstrip("."), "png")
    prompt = ("อธิบายภาพนี้โดยละเอียดเป็นภาษาไทย และถอดข้อความ/ตัวเลข/ตารางที่ปรากฏในภาพออกมา "
              "(ถ้ามี) เพื่อใช้ค้นหาภายหลัง ตอบเป็นข้อความล้วน")
    if note:
        prompt += f"\nบริบทเพิ่มเติมจากผู้ใช้: {note}"
    content = [
        {"image": {"format": fmt, "source": {"bytes": image_bytes}}},
        {"text": prompt},
    ]
    resp = _rt.converse(
        modelId=config.CHAT_MODEL_ID,
        messages=[{"role": "user", "content": content}],
        inferenceConfig={"maxTokens": 700, "temperature": 0.2},
    )
    return resp["output"]["message"]["content"][0]["text"]


FACT_OPINION_SYSTEM = """You classify statements from CRM/meeting notes as FACT or OPINION for business executives.
- FACT: verifiable, objective info (dates, names, numbers, signed deals, documented events, contract terms).
- OPINION: subjective judgment, prediction, sentiment, or interpretation (e.g. "the client seems unhappy", "I think they will renew", "their team is strong").
- MIXED: contains both.
Return STRICT JSON only, no prose:
{"items":[{"i":0,"label":"fact|opinion|mixed","confidence":0.0-1.0,"source_person":null_or_name}]}
"source_person" = the person whose opinion/statement it is if identifiable, else null."""


def classify_fact_opinion(segments):
    """segments: list of str. Returns list of dicts {label, confidence, source_person}."""
    if not segments:
        return []
    numbered = "\n".join(f"[{i}] {s}" for i, s in enumerate(segments))
    user = f"Classify each numbered statement.\n{numbered}"
    try:
        raw = chat(FACT_OPINION_SYSTEM, [{"role": "user", "text": user}],
                   max_tokens=1500, temperature=0.0, model_id=config.CLASSIFY_MODEL_ID)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw)
        by_i = {it["i"]: it for it in data.get("items", [])}
        results = []
        for i in range(len(segments)):
            it = by_i.get(i, {})
            results.append({
                "label": it.get("label", "fact"),
                "confidence": float(it.get("confidence", 0.5)),
                "source_person": it.get("source_person"),
            })
        return results
    except Exception:
        # Fallback: default everything to fact with low confidence.
        return [{"label": "fact", "confidence": 0.3, "source_person": None} for _ in segments]
