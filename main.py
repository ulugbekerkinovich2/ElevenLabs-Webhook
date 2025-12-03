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
MAX_LEN = 3900   # Telegram safe limit


def send_to_telegram(text: str):
    # bo‘lib yuborish
    if len(text) <= MAX_LEN:
        _send_chunk(text)
        return

    start = 0
    while start < len(text):
        end = start + MAX_LEN
        _send_chunk(text[start:end])
        start = end


def _send_chunk(chunk: str):
    requests.post(
        TELEGRAM_SEND_URL,
        json={"chat_id": TELEGRAM_CHAT_ID, "text": chunk},
        timeout=10
    )


def format_pretty(payload: dict) -> str:
    data = payload.get("data", {}) or {}

    event_type = payload.get("type", "unknown")
    status = data.get("status", "unknown")
    conv_id = data.get("conversation_id", "-")
    agent_id = data.get("agent_id", "-")
    user_id = data.get("user_id", "-")

    ts = payload.get("event_timestamp")
    if isinstance(ts, (int, float)):
        ts_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    else:
        ts_str = str(ts)

    # 1) HEADER (pretty)
    header = f"""
📞 *ElevenLabs Conversation Log*
──────────────────────────────
# 🧩 *Type:* `{event_type}`
📊 *Status:* `{status}`
# 🗣 *Conversation ID:* `{conv_id}`
# 🤖 *Agent ID:* `{agent_id}`
# 👤 *User ID:* `{user_id}`
⏱ Event time: `{ts_str}`

💬 *Transcript*
──────────────────────────────
    """.strip()

    # 2) TRANSCRIPT FORMAT
    transcript_lines = []
    transcript_items = data.get("transcript", [])

    for item in transcript_items:
        role = (item.get("role") or "").lower()
        msg = item.get("message") or ""

        if role == "user":
            prefix = "👤 *User:*"
        else:
            prefix = "🤖 *Agent:*"

        block = f"{prefix}\n{msg}\n"
        transcript_lines.append(block)

    transcript = "\n".join(transcript_lines).strip()
    final_text = header + "\n\n" + transcript

    # Juda uzun bo‘lsa, kesib yuboramiz
    if len(final_text) > MAX_LEN:
        final_text = final_text[:MAX_LEN] + "\n… (truncated)"

    return final_text


@app.post("/elevenlabs/webhook")
async def elevenlabs_webhook(request: Request):
    payload = await request.json()

    pretty = format_pretty(payload)

    send_to_telegram(pretty)

    return {"status": "ok"}
