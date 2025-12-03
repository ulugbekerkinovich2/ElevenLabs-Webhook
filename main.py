# main.py
import os
import hmac
import hashlib
import requests
import json
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv

app = FastAPI()
load_dotenv()

TELEGRAM_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-")
HMAC_SECRET = os.getenv("HMAC_SECRET", "YOUR_HMAC_SECRET").encode()

TELEGRAM_SEND_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

TELEGRAM_MAX_LEN = 4000  # xavfsiz limit


def send_to_telegram(text: str):
    """Katta text bo'lsa ham bo'lib-bo'lib yuboradi."""
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
            "text": chunk,
            # markdown muammolar bo'lmasin desak, oddiy text:
            # "parse_mode": "Markdown",
        },
        timeout=10,
    )
    resp.raise_for_status()


def verify_signature(raw_body: bytes, signature: str) -> bool:
    mac = hmac.new(HMAC_SECRET, msg=raw_body, digestmod=hashlib.sha256)
    expected = mac.hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/elevenlabs/webhook")
async def elevenlabs_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("ElevenLabs-Signature")

    # HMAC ishlatmoqchi bo'lsang, shu 3 qatordan kommentni olib tashlaysan:
    # if not signature or not verify_signature(raw_body, signature):
    #     raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()

    # JSON'ni chiroyli formatga keltiramiz
    pretty = json.dumps(payload, indent=2, ensure_ascii=False)

    # Juda uzun bo'lsa, biroz qisqartiramiz
    max_len = 3500
    if len(pretty) > max_len:
        pretty = pretty[:max_len] + "\n...\n[truncated]"

    text = "📦 ElevenLabs webhook payload:\n\n" + pretty

    send_to_telegram(text)

    return {"status": "ok"}
