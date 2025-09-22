# Bot Factory Runtime

🤖 **Мультитенантная система для создания и управления Telegram ботами**

✨ **Особенности:**
- 🚀 **Hot Reload** - изменения применяются мгновенно без перезапуска
- 🎯 **Мультитенантность** - неограниченное количество ботов на одном сервере
- ⚡ **Независимость** - каждый бот имеет свою конфигурацию и команды
- 🔧 **Простота** - создание бота через REST API за минуту

## 🚀 Быстрый старт

```bash
# 1. Запуск системы
docker-compose up -d

# 2. Проверка работоспособности
curl http://localhost:8000/health

# 3. Создание первого бота
curl -X POST 'http://localhost:8000/bots' \
  -H 'Content-Type: application/json' \
  -d '{"name": "MyBot", "token": "YOUR_BOT_TOKEN_FROM_BOTFATHER"}'
```

**📖 Полная инструкция:** [HOW_TO_CREATE_BOTS.md](./HOW_TO_CREATE_BOTS.md)

## 🤖 Примеры работающих ботов

| Бот | Username | Функции |
|-----|----------|---------|
| BusinessAssistant Pro | [@BusinessAssistantProBot](https://t.me/BusinessAssistantProBot) | `/start`, `/help`, `/status` |
| Terminal Bot | [@terminalv_bot](https://t.me/terminalv_bot) | `/start`, `/help`, `/status`, `/test` |

## 📁 Структура проекта

```
runtime/
  main.py           # ✅ FastAPI: /health, /tg/{bot_id}, webhook processing
  loader.py         # загрузка конфигурации ботов из БД
  registry.py       # CRUD операции с ботами
  dsl_engine.py     # динамическая сборка aiogram роутеров
  management_api.py # API для создания и управления ботами
  wizard_engine.py  # обработка команд и flows
  telemetry.py      # /metrics для мониторинга
migrations/         # миграции PostgreSQL
docker/            # Docker конфигурация
```

## 🔧 Конфигурация

```bash
# Переменные окружения (в docker-compose.yml)
DATABASE_URL=postgresql+psycopg://dev:dev@pg:5432/botfactory
REDIS_URL=redis://redis:6379/0
```

## 📚 API Endpoints

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `GET` | `/health` | Проверка работоспособности |
| `GET` | `/bots` | **НОВЫЙ** Список всех ботов |
| `POST` | `/bots` | Создать нового бота |
| `GET` | `/bots/{id}` | Информация о боте |
| `PUT` | `/bots/{id}/spec` | Обновить команды бота |
| `GET` | `/bots/{id}/spec` | **НОВЫЙ** Получить DSL спецификацию |
| `DELETE` | `/bots/{id}` | **НОВЫЙ** Удалить бота |
| `DELETE` | `/bots/{id}/data` | **НОВЫЙ** Очистить данные бота |
| `POST` | `/bots/{id}/validate` | **НОВЫЙ** Валидация DSL |
| `POST` | `/bots/{id}/reload` | Перезагрузить кэш |
| `POST` | `/tg/{id}` | Webhook для Telegram |
| `GET` | `/docs` | Swagger документация |

## 🛠️ Разработка

```bash
# Установка зависимостей
pip install -e .

# Запуск (с hot reload)
uvicorn runtime.main:app --reload --host 0.0.0.0 --port 8000

# Тесты
pytest
```

## 🎯 Создание нового бота (быстро)

```bash
# 1. Получите токен от @BotFather
# 2. Создайте бота:
curl -X POST 'http://localhost:8000/bots' \
  -H 'Content-Type: application/json' \
  -d '{"name": "QuickBot", "token": "YOUR_TOKEN"}'

# 3. Добавьте команды:
curl -X PUT 'http://localhost:8000/bots/BOT_ID/spec' \
  -H 'Content-Type: application/json' \
  -d '{
    "flows": [
      {"entry_cmd": "/start", "steps": [{"reply": "Привет! 👋"}]},
      {"entry_cmd": "/help", "steps": [{"reply": "Доступные команды: /start, /help"}]}
    ]
  }'

# 4. Настройте webhook и готово!
```

## 🖥️ Продакшн

- **Сервер:** https://profy.top/bot/
- **SSH:** `server2`
- **Мониторинг:** `/metrics`
- **Документация сервера:** [SERVER.md](./SERVER.md)