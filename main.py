import os
import requests
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from dotenv import load_dotenv
from typing import Set, Tuple

app = FastAPI()
load_dotenv()

TELEGRAM_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-")

TELEGRAM_SEND_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
MAX_LEN = 3900   # Telegram safe limit

# Bir xil event ikki marta kelganda filtr qilish uchun
# (conversation_id, event_timestamp) ni saqlaymiz
SEEN_EVENTS: Set[Tuple[str, int]] = set()


def send_to_telegram(text: str):
    """Matnni Telegramga yuborish, uzun bo'lsa bo'lib-bo'lib."""
    if len(text) <= MAX_LEN:
        _send_chunk(text)
        return

    start = 0
    while start < len(text):
        end = start + MAX_LEN
        _send_chunk(text[start:end])
        start = end


def _send_chunk(chunk: str):
    try:
        requests.post(
            TELEGRAM_SEND_URL,
            json={"chat_id": TELEGRAM_CHAT_ID, "text": chunk},
            timeout=10
        )
    except Exception as e:
        # xato bo'lsa server logga yozib qo'ysan bo'ladi
        print("Telegram send error:", e)


def format_pretty(payload: dict) -> str:
    data = payload.get("data", {}) or {}

    ts = payload.get("event_timestamp")
    if isinstance(ts, (int, float)):
        ts_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )
    else:
        ts_str = str(ts)

    # 1) HEADER (pretty)
    header = f"""
📞 *ElevenLabs Conversation Log*
──────────────────────────────
⏱ Event time: `{ts_str}`
──────────────────────────────
    """.strip()

    # 2) TRANSCRIPT FORMAT
    transcript_lines = []
    transcript_items = data.get("transcript", [])

    for item in transcript_items:
        role = (item.get("role") or "").lower()
        msg = item.get("message") or ""

        if role == "user":
            prefix = "👤 User:"
        else:
            prefix = "🤖 Agent:"

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
    data = payload.get("data", {}) or {}

    # Dublikatlarni filtrlash: conversation_id + event_timestamp
    conv_id = str(data.get("conversation_id", ""))
    ts = payload.get("event_timestamp")

    try:
        ts_int = int(ts) if isinstance(ts, (int, float, str)) and str(ts).isdigit() else 0
    except Exception:
        ts_int = 0

    key = (conv_id, ts_int)

    # Agar shu event oldin kelgan bo'lsa, Telegramga yubormaymiz
    if key in SEEN_EVENTS:
        return {"status": "duplicate_ignored"}

    SEEN_EVENTS.add(key)

    pretty = format_pretty(payload)
    send_to_telegram(pretty)

    return {"status": "ok"}
