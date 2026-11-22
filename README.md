# SafeBase

Telegram inline reputation lookup bot built with Python, aiogram 3, FastAPI webhooks and PostgreSQL. Intended for Render Web Service.

## Features
- Inline lookup using @username or numeric Telegram ID.
- Three result states: listed scam account, listed SafeBase database administrator, no record.
- Search counters and 👍/👎 feedback.
- Private /admin panel for the one configured master administrator.
- Master-only add scam, add database administrator, delete entry and statistics actions.
- PostgreSQL persistence and HTTP health endpoint.

A missing record only means that no entry was found. It is not proof that an account is safe. Reputation entries are user-submitted database records, not official findings. Review reports and evidence carefully and provide a correction/appeal process.

## Telegram setup
1. Create a bot with @BotFather and copy its token.
2. Use /setinline with BotFather to enable inline mode.
3. Set the inline placeholder to: Enter @username or numeric Telegram ID.
4. Note the exact bot username.

## Render setup
1. Create a PostgreSQL database in Render.
2. Create a Web Service from this repository (or use the Blueprint).
3. Build command: pip install -r requirements.txt
4. Start command: uvicorn main:app --host 0.0.0.0 --port $PORT
5. Set environment variables:
   - TELEGRAM_BOT_TOKEN: token from BotFather
   - ADMIN_ID: 9043787447
   - DATABASE_URL: Render PostgreSQL connection URL
   - WEBHOOK_SECRET: random secret of at least 32 characters; use letters, digits, underscore or hyphen.
6. Deploy and open the service URL. It should return {"status":"ok","service":"SafeBase"}.

Never commit bot tokens or database credentials to GitHub.

## Permissions
Only the numeric ADMIN_ID can write to the reputation database through the admin panel. Entries of kind "admin" are informational and do not grant write access.

## Production notes
Use persistent PostgreSQL and scheduled backups. Start with one web worker; multiple workers need distributed update coordination. Test inline mode and admin actions in a private test chat before announcing the bot.
