# main.py
import os
import hmac
import hashlib
import requests
import json
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv

app = FastAPI()
load_dotenv()

TELEGRAM_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-")
HMAC_SECRET = os.getenv("HMAC_SECRET", "YOUR_HMAC_SECRET").encode()

TELEGRAM_SEND_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

TELEGRAM_MAX_LEN = 4000   # xavfsiz limit
TRANSCRIPT_MAX_LEN = 3000 # transcript qismini kesish uchun


def send_to_telegram(text: str):
    """Textni Telegramga, kerak bo‘lsa bo‘lib-bo‘lib yuboradi."""
    if len(text) <= TELEGRAM_MAX_LEN:
        _send_chunk(text)
        return

    start = 0
    while start < len(text):
        end = start + TELEGRAM_MAX_LEN
        chunk = text[start:end]
        _send_chunk(chunk)
        start = end


def _send_chunk(chunk: str):
    resp = requests.post(
        TELEGRAM_SEND_URL,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,   # parse_mode bermaymiz – oddiy text
        },
        timeout=10,
    )
    resp.raise_for_status()


def verify_signature(raw_body: bytes, signature: str) -> bool:
    mac = hmac.new(HMAC_SECRET, msg=raw_body, digestmod=hashlib.sha256)
    expected = mac.hexdigest()
    return hmac.compare_digest(expected, signature)


def build_transcript_from_payload(payload: dict) -> str:
    """
    payload["data"]["transcript"] ichidan User/Agent dialogini yig'adi.
    """
    data = payload.get("data", {}) or {}
    items = data.get("transcript") or []

    lines = []

    for item in items:
        role = (item.get("role") or "").lower()
        msg = item.get("message") or ""
        if not msg:
            continue

        if role == "user":
            prefix = "👤 User:"
        elif role == "agent":
            prefix = "🤖 Agent:"
        else:
            prefix = f"{role or 'other'}:"

        # Har bir xabarni bitta qatorda
        lines.append(f"{prefix} {msg}")

    transcript = "\n\n".join(lines) if lines else "No transcript"

    # Juda uzun bo'lsa kesamiz
    if len(transcript) > TRANSCRIPT_MAX_LEN:
        cut = transcript[:TRANSCRIPT_MAX_LEN]
        # so'z o'rtasida kesilmasin
        last_space = cut.rfind(" ")
        if last_space > 0:
            cut = cut[:last_space]
        transcript = cut + "\n\n... (uzun transcript, davomi kesildi)"

    return transcript


@app.post("/elevenlabs/webhook")
async def elevenlabs_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("ElevenLabs-Signature")

    # Agar HMAC qo'yishni xohlasang, shu 3 qatordan kommentni olib tashlaysan:
    # if not signature or not verify_signature(raw_body, signature):
    #     raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()

    data = payload.get("data", {}) or {}

    event_type = payload.get("type", "unknown_type")               # masalan: post_call_transcription
    event_ts = payload.get("event_timestamp")                      # epoch
    agent_id = data.get("agent_id")
    conv_id = data.get("conversation_id")
    status = data.get("status")
    user_id = data.get("user_id")

    # timestampni odamlarcha formatga keltiramiz (UTC)
    if isinstance(event_ts, (int, float)):
        dt = datetime.fromtimestamp(event_ts, tz=timezone.utc)
        ts_str = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        ts_str = str(event_ts) if event_ts is not None else "unknown"

    transcript = build_transcript_from_payload(payload)

    header_lines = [
        "ElevenLabs Conversation Log",
        f"Type: {event_type}",
        f"Status: {status}",
        f"Conversation ID: {conv_id}",
        f"Agent ID: {agent_id}",
        f"User ID: {user_id}",
        f"Event time: {ts_str}",
        "",
        "Transcript:",
        "",
    ]

    text = "\n".join(header_lines) + transcript

    send_to_telegram(text)

    return {"status": "ok"}
