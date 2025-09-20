# Bot Factory Runtime

Система выполнения Telegram ботов на основе FastAPI.

## 🚀 Быстрый старт

```bash
# Локальная разработка
docker-compose up -d

# Доступ к API
curl http://localhost:8000/health
```

## 📁 Структура проекта

```
runtime/
  app.py            # FastAPI: /health, /preview, /tg/{bot_id}
  loader.py         # загрузка бота из БД/плагина
  registry.py       # CRUD ботов
  dsl_engine.py     # сборка роутеров из JSONB
  telemetry.py      # /metrics
migrations/         # миграции БД
docker/            # Docker конфигурация
```

## 🔧 Конфигурация

Скопируйте `.env.example` в `.env` и настройте:

```bash
DATABASE_URL=postgresql+psycopg://dev:dev@pg:5432/botfactory
REDIS_URL=redis://redis:6379/0
TELEGRAM_DOMAIN=https://your.domain
```

## 🖥️ Сервер и деплой

**Подробная документация по серверу:** [SERVER.md](./SERVER.md)

- **Продакшн:** https://profy.top/bot/
- **SSH доступ:** `server2`
- **SSL:** Sectigo сертификаты

## 📚 API Документация

После запуска доступна по адресу: `/docs`

## 🛠️ Разработка

```bash
# Установка зависимостей
pip install -e .

# Запуск
uvicorn runtime.app:app --reload

# Тесты
pytest
```