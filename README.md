# Piercing Tycoon Telegram Mini App (Python + Phaser)

MVP-прототип idle/tycoon игры для Telegram Mini App:
- FastAPI backend (`/auth`, `/sync`, `/upgrade`, `/event/resolve`, `/leaderboard`)
- Phaser 3 frontend с простой сценой, HUD и UI-кнопками
- SQLite хранение прогресса
- Офлайн-начисление с лимитом 12 часов

## Запуск локально

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Открыть: `http://localhost:8000`

## Telegram initData

В проде установите `TELEGRAM_BOT_TOKEN` для проверки подписи `initData`.
В этом MVP без токена используется `dev-token` и фронт отправляет тестовый payload.
