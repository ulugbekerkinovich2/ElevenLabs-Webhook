# main.py
import os
import hmac
import hashlib
import requests
from fastapi import FastAPI, Request, HTTPException
from dotenv import load_dotenv

app = FastAPI()
load_dotenv()

TELEGRAM_TOKEN = os.getenv("BOT_TOKEN", "YOUR_TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-")
HMAC_SECRET = os.getenv("HMAC_SECRET", "YOUR_HMAC_SECRET").encode()

TELEGRAM_SEND_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

# Telegram limitiga xavfsiz sig‘ishi uchun
TELEGRAM_MAX_LEN = 4000   # 4096 dan biroz kamroq
TRANSCRIPT_MAX_LEN = 3000 # header + transcript birga sig‘ishi uchun


def send_to_telegram(message: str):
    """
    Katta matn bo'lsa ham problem bo'lmasligi uchun
    textni bo'lib-bo'lib yuboradi.
    """
    if len(message) <= TELEGRAM_MAX_LEN:
        _send_chunk(message)
        return

    start = 0
    while start < len(message):
        end = start + TELEGRAM_MAX_LEN
        chunk = message[start:end]
        _send_chunk(chunk)
        start = end


def _send_chunk(chunk: str):
    resp = requests.post(
        TELEGRAM_SEND_URL,
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "Markdown",
        },
        timeout=10,
    )
    resp.raise_for_status()


def verify_signature(raw_body: bytes, signature: str) -> bool:
    mac = hmac.new(HMAC_SECRET, msg=raw_body, digestmod=hashlib.sha256)
    expected = mac.hexdigest()
    return hmac.compare_digest(expected, signature)


def build_transcript(conv: dict) -> str:
    """
    ElevenLabs conversation strukturasiga qarab transcript hosil qiladi.
    Agar messages bo'lsa, ularni chiroyli qilib birma-bir formatlaydi.
    Bo'lmasa transcript/summary fieldlarni ishlatadi.
    """
    # Agar messages list bo'lsa (role + content)
    messages = conv.get("messages")
    if isinstance(messages, list) and messages:
        lines = []
        for msg in messages[:50]:   # juda ko'p bo'lsa ham 50 taga cheklaymiz
            role = msg.get("role", "unknown").lower()
            content = msg.get("content") or msg.get("text") or ""
            if not content:
                continue

            if role in ("user", "human", "caller"):
                prefix = "👤 User:"
            elif role in ("assistant", "agent", "ai"):
                prefix = "🤖 Agent:"
            else:
                prefix = f"{role}:"

            lines.append(f"{prefix} {content}")

        transcript = "\n".join(lines)
    else:
        # fallback: oddiy transcript/summary
        transcript = (
            conv.get("transcript")
            or conv.get("summary")
            or "No transcript"
        )

    # Juda uzun bo'lsa so'z bo'yicha kesamiz
    if len(transcript) > TRANSCRIPT_MAX_LEN:
        cut = transcript[:TRANSCRIPT_MAX_LEN]
        # oxirgi probel/nuqtaga qadar kesish
        last_space = cut.rfind(" ")
        if last_space > 0:
            cut = cut[:last_space]
        transcript = cut + "\n\n… (davomi kesildi, juda uzun transcript)"
    return transcript


@app.post("/elevenlabs/webhook")
async def elevenlabs_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("ElevenLabs-Signature")

    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature")

    # Hozircha HMAC o‘chirilgan bo‘lsa, shu qatorni uncomment qilsang bo'ladi:
    # if not verify_signature(raw_body, signature):
    #     raise HTTPException(status_code=401, detail="Invalid signature")
    payload = await request.json()

    event = payload.get("event", "unknown_event")
    conv = payload.get("conversation", payload)

    user = (
        conv.get("user_name")
        or conv.get("caller_id")
        or conv.get("phone_number")
        or "Unknown user"
    )
    conv_id = conv.get("id", "N/A")
    duration = conv.get("duration") or conv.get("call_duration")

    transcript = build_transcript(conv)

    header_lines = [
        "📞 *ElevenLabs Conversation Log*",
        f"*Event:* `{event}`",
        f"*User:* {user}",
        f"*Conversation ID:* `{conv_id}`",
    ]

    if duration:
        header_lines.append(f"*Duration:* {duration} sec")

    header_lines.append("")
    header_lines.append("*Transcript:*")

    text = "\n".join(header_lines) + "\n" + transcript

    send_to_telegram(text)

    return {"status": "ok"}
