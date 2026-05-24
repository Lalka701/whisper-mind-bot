# Telegram AI Bot (Gemini + Groq)

Telegram-бот с поддержкой текстовых и голосовых сообщений. **Полностью бесплатный стек**:

- **Чат** — Google Gemini 3.5 Flash (бесплатный API)
- **Голос** — Groq Whisper Large v3 Turbo (бесплатный API)
- **Хостинг** — Koyeb (бесплатный тариф)
- **История** — SQLite (последние 20 сообщений передаются как контекст)

## Команды бота

- `/start` — приветствие
- `/clear` — очистить историю диалога

---

## Где взять ключи (всё бесплатно)

| Что | Где получить | Нужна карта? |
|-----|-------------|--------------|
| `TELEGRAM_BOT_TOKEN` | Telegram → [@BotFather](https://t.me/BotFather) → `/newbot` | Нет |
| `GEMINI_API_KEY` | https://aistudio.google.com/apikey → Create API key | Нет |
| `GROQ_API_KEY` | https://console.groq.com/keys → Create API Key | Нет |

> Лимиты бесплатных тарифов щедрые: Gemini — 15 запросов/мин, Groq — ~30 запросов/мин. Для личного бота с головой.

---

## Локальный запуск

```bash
pip install -r requirements.txt
copy .env.example .env
```

Открой `.env` и впиши три ключа (`WEBHOOK_URL` оставь пустым). Запусти:

```bash
python bot.py
```

Бот заработает в polling-режиме, пока окно открыто.

---

## Деплой на Koyeb

### Шаг 1. Загрузить код на GitHub

1. Создай новый репозиторий на GitHub (можно приватный).
2. Загрузи туда файлы: `bot.py`, `requirements.txt`, `Procfile`, `.env.example`, `README.md`.
3. **`.env` не загружай** — реальные ключи не должны попасть в репозиторий.

### Шаг 2. Создать аккаунт на Koyeb

Зарегистрируйся на [koyeb.com](https://koyeb.com). Бесплатный тариф — один сервис без карты.

### Шаг 3. Создать сервис

1. Дашборд Koyeb → **Create Service** → **GitHub**.
2. Подключи GitHub-аккаунт, выбери репозиторий с ботом.
3. Koyeb сам определит Python-приложение.

### Шаг 4. Настройки сервиса

- **Branch**: `main`
- **Build command**: пусто (Koyeb сам выполнит `pip install -r requirements.txt`)
- **Run command**: `python bot.py`
- **Port**: `8000`
- **Instance**: `Free` (eco-nano)

### Шаг 5. Переменные окружения

В разделе **Environment variables** добавь:

| Ключ | Значение |
|------|---------|
| `TELEGRAM_BOT_TOKEN` | токен из BotFather |
| `GEMINI_API_KEY` | ключ из Google AI Studio |
| `GROQ_API_KEY` | ключ из Groq Console |

> `WEBHOOK_URL` пока **не указывай** — бот запустится в polling-режиме (проще и надёжнее).

### Шаг 6. Деплой

Нажми **Deploy**. Сборка займёт 2–3 минуты. Открой бота в Telegram — он должен отвечать.

---

## (Опционально) Webhook-режим

Webhook быстрее polling. После успешного деплоя:

1. Скопируй URL приложения из Koyeb (например `https://my-bot-abc123.koyeb.app`).
2. Добавь переменную: `WEBHOOK_URL=https://my-bot-abc123.koyeb.app`
3. Передеплой сервис.

---

## Ограничения бесплатного тарифа Koyeb

- SQLite-база (`history.db`) **сбрасывается при каждом редеплое** — файл лежит в памяти контейнера.
- Для большинства личных сценариев это не проблема. Если нужна постоянная история — подключи бесплатный PostgreSQL ([Neon](https://neon.tech) даёт 0.5 ГБ бесплатно).

---

## Структура проекта

```
bot.py            — основной код бота
requirements.txt  — зависимости
Procfile          — команда запуска для Koyeb
.env.example      — пример переменных окружения
README.md         — эта инструкция
history.db        — SQLite (создаётся автоматически, в git не коммитить)
```
