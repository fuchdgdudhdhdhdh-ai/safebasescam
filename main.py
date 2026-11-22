import os
import html
import logging
import secrets
from contextlib import asynccontextmanager

from aiogram import Bot, Dispatcher, F
from aiogram.types import Update, InlineQuery, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram.filters import Command
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select

from database import init_db, close_db, Session, lookup, log_check, Vote
from admin_panel import router as admin_router

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("safebase")
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ADMIN_ID = int(os.environ["ADMIN_ID"])
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
PUBLIC_URL = os.environ["RENDER_EXTERNAL_URL"].rstrip("/")
WEBHOOK_PATH = "/telegram/" + WEBHOOK_SECRET

bot = Bot(TOKEN)
dp = Dispatcher()
dp.include_router(admin_router)

def card(person, query, count):
    safe_query = html.escape(query)
    if person is None:
        return (
            f"🟡 <b>Информация о {safe_query}</b>\\n\\n"
            "⚠️ В базе SafeBase нет записей об этом аккаунте.\\n"
            "Отсутствие записи не подтверждает надёжность пользователя. "
            "Проверяйте сделки и используйте безопасные способы оплаты.\\n\\n"
            f"🔎 Пользователя искали {count} раз",
            "🟡 Нет в базе / нет подтверждённых записей",
        )
    label = html.escape(person.username or str(person.telegram_id or query))
    description = html.escape(person.description or "Не указано")
    if person.kind == "admin":
        return (
            f"🛡 <b>Информация о {label}</b>\\n\\n"
            "⭐ Данный пользователь указан как администратор базы SafeBase.\\n"
            f"Описание: {description}\\n\\n🔎 Пользователя искали {count} раз",
            "🛡 Администратор базы SafeBase",
        )
    return (
        f"🚨 <b>Информация о {label}</b>\\n\\n"
        "🔴 <b>Репутация: СКАМЕР</b>\\n"
        f"Описание: {description}\\n\\n"
        "ℹ️ Это пользовательская запись базы, а не официальное заключение. "
        "Учитывайте возможность ошибок и проверяйте доказательства.\\n\\n"
        f"🔎 Пользователя искали {count} раз",
        "🚨 Скамер — есть запись в базе",
    )

@dp.inline_query()
async def inline_check(query: InlineQuery):
    raw = (query.query or "").strip()
    if not raw:
        await query.answer([], cache_time=1)
        return
    try:
        async with Session() as s:
            person = await lookup(s, raw)
            count = await log_check(s, raw, query.from_user.id)
        body, title = card(person, raw, count)
        result = InlineQueryResultArticle(
            id=secrets.token_hex(8),
            title=title,
            description=f"Результат проверки: {raw}",
            input_message_content=InputTextMessageContent(message_text=body, parse_mode="HTML"),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="👍", callback_data="vote:1:" + raw[:45]),
                InlineKeyboardButton(text="👎", callback_data="vote:-1:" + raw[:45]),
            ]]),
        )
        await query.answer([result], cache_time=2, is_personal=True)
    except Exception:
        log.exception("Inline lookup failed")
        await query.answer([], cache_time=1)

@dp.callback_query(F.data.startswith("vote:"))
async def vote(callback: CallbackQuery):
    try:
        _, value, target = callback.data.split(":", 2)
        async with Session() as s:
            old = await s.scalar(select(Vote).where(Vote.voter_id == callback.from_user.id, Vote.target_key == target.lower()))
            if old:
                old.value = int(value)
            else:
                s.add(Vote(voter_id=callback.from_user.id, target_key=target.lower(), value=int(value)))
            await s.commit()
        await callback.answer("Спасибо, оценка учтена.")
    except Exception:
        log.exception("Vote failed")
        await callback.answer("Не удалось сохранить оценку.", show_alert=True)

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "🛡 <b>SafeBase — проверка репутации</b>\\n\\n"
        "В любом чате введите имя бота в поле сообщения, затем @username или числовой Telegram ID.\\n"
        "Пример: <code>@SafeBase_checkbot @example</code>\\n\\n"
        "Отсутствие записи в базе не гарантирует безопасность сделки.",
        parse_mode="HTML",
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await bot.set_webhook(
        PUBLIC_URL + WEBHOOK_PATH,
        secret_token=WEBHOOK_SECRET,
        allowed_updates=dp.resolve_used_update_types(),
        drop_pending_updates=True,
    )
    log.info("SafeBase webhook configured")
    yield
    await bot.delete_webhook()
    await bot.session.close()
    await close_db()

app = FastAPI(title="SafeBase", lifespan=lifespan)

@app.get("/")
async def health():
    return {"status": "ok", "service": "SafeBase"}

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")
    try:
        update = Update.model_validate(await request.json(), context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception:
        log.exception("Update processing failed")
        raise HTTPException(status_code=500, detail="Update processing failed")
    return JSONResponse({"ok": True})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "10000")))
