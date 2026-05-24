import os
import logging
import sqlite3
import tempfile

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from google import genai
from google.genai import types as genai_types
from groq import AsyncGroq
import edge_tts

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
PORT = int(os.environ.get("PORT", 8000))

MAX_HISTORY = 20
DB_PATH = "history.db"
GEMINI_MODEL = "gemini-3.5-flash"
WHISPER_MODEL = "whisper-large-v3-turbo"
TTS_VOICE = "ru-RU-DmitryNeural"
VOICE_TRIGGERS = {"голос", "гс", "озвучь", "озвучить"}

gemini_client = genai.Client(api_key=GEMINI_API_KEY)
groq_client = AsyncGroq(api_key=GROQ_API_KEY)


# --- Database ---

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   INTEGER NOT NULL,
                role      TEXT    NOT NULL,
                content   TEXT    NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def save_message(user_id: int, role: str, content: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO messages (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, content),
        )
        conn.commit()


def get_history(user_id: int) -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """SELECT role, content FROM messages
               WHERE user_id = ?
               ORDER BY timestamp DESC
               LIMIT ?""",
            (user_id, MAX_HISTORY),
        )
        rows = cursor.fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]


def clear_history(user_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM messages WHERE user_id = ?", (user_id,))
        conn.commit()


def get_last_assistant_message(user_id: int) -> str | None:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """SELECT content FROM messages
               WHERE user_id = ? AND role = 'model'
               ORDER BY timestamp DESC
               LIMIT 1""",
            (user_id,),
        )
        row = cursor.fetchone()
    return row[0] if row else None


# --- Helpers ---

async def ask_gemini(user_id: int) -> str:
    history = get_history(user_id)
    contents = [
        genai_types.Content(
            role=msg["role"],
            parts=[genai_types.Part(text=msg["content"])],
        )
        for msg in history
    ]
    response = await gemini_client.aio.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
    )
    return response.text or ""


async def transcribe_voice(file_id: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    voice_file = await context.bot.get_file(file_id)

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        await voice_file.download_to_drive(tmp_path)
        with open(tmp_path, "rb") as audio:
            transcript = await groq_client.audio.transcriptions.create(
                file=(os.path.basename(tmp_path), audio.read()),
                model=WHISPER_MODEL,
            )
        return transcript.text
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


async def text_to_voice(text: str) -> str:
    """Generate MP3 from text via edge-tts. Returns path to temp file."""
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = tmp.name
    communicate = edge_tts.Communicate(text, TTS_VOICE)
    await communicate.save(tmp_path)
    return tmp_path


async def send_voice_reply(update: Update, text: str):
    """Send text as a Telegram voice message via edge-tts."""
    voice_path = await text_to_voice(text)
    try:
        with open(voice_path, "rb") as voice_file:
            await update.message.reply_voice(voice=voice_file)
    finally:
        if os.path.exists(voice_path):
            os.unlink(voice_path)


async def reply_long(update: Update, text: str):
    """Send text, splitting into chunks if it exceeds Telegram's 4096-char limit."""
    max_len = 4096
    while text:
        if len(text) <= max_len:
            await update.message.reply_text(text)
            break
        split = text.rfind("\n", 0, max_len)
        if split == -1:
            split = max_len
        await update.message.reply_text(text[:split])
        text = text[split:].lstrip("\n")


# --- Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! Я ИИ-ассистент на базе Gemini 3.5 Flash.\n\n"
        "Напиши мне что-нибудь или отправь голосовое сообщение.\n\n"
        "/start — это сообщение\n"
        "/clear — очистить историю диалога"
    )


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_history(update.effective_user.id)
    await update.message.reply_text("История диалога очищена.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text

    if user_message.strip().lower() in VOICE_TRIGGERS:
        last_reply = get_last_assistant_message(user_id)
        if not last_reply:
            await update.message.reply_text("Пока нечего озвучивать — задай вопрос сначала.")
            return
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id, action="record_voice"
        )
        try:
            await send_voice_reply(update, last_reply)
        except Exception as e:
            logger.error("TTS error: %s", e)
            await update.message.reply_text("Не удалось озвучить.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        save_message(user_id, "user", user_message)
        reply = await ask_gemini(user_id)
        if not reply.strip():
            reply = "Пустой ответ от модели. Попробуй переформулировать."
        save_message(user_id, "model", reply)
        await reply_long(update, reply)
    except Exception as e:
        logger.error("handle_text error: %s", e)
        await update.message.reply_text("Произошла ошибка. Попробуйте снова.")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        transcript = await transcribe_voice(update.message.voice.file_id, context)

        if not transcript.strip():
            await update.message.reply_text("Не удалось распознать речь.")
            return

        await update.message.reply_text(f"Транскрипция: {transcript}")
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

        save_message(user_id, "user", transcript)
        reply = await ask_gemini(user_id)
        if not reply.strip():
            reply = "Пустой ответ от модели. Попробуй переформулировать."
        save_message(user_id, "model", reply)
        await reply_long(update, reply)

        try:
            await context.bot.send_chat_action(
                chat_id=update.effective_chat.id, action="record_voice"
            )
            await send_voice_reply(update, reply)
        except Exception as e:
            logger.error("TTS error: %s", e)

    except Exception as e:
        logger.error("handle_voice error: %s", e)
        await update.message.reply_text("Ошибка при обработке голосового сообщения.")


# --- Entry point ---

def main():
    init_db()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("clear", clear_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    if WEBHOOK_URL:
        logger.info("Webhook mode: %s", WEBHOOK_URL)
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="/webhook",
            webhook_url=f"{WEBHOOK_URL}/webhook",
        )
    else:
        logger.info("Polling mode (local dev)")
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
