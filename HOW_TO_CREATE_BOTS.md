# 🤖 Как создавать ботов в BotFactory Runtime

## 📋 API для управления ботами

### 1. Создание нового бота

```bash
curl -X POST 'http://localhost:8000/bots' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "MyAwesomeBot",
    "token": "YOUR_BOT_TOKEN_FROM_BOTFATHER"
  }'
```

**Ответ:**
```json
{
  "bot_id": "uuid-генерируется-автоматически",
  "name": "MyAwesomeBot",
  "status": "active"
}
```

### 2. Добавление спецификации (flows и команд)

```bash
curl -X PUT 'http://localhost:8000/bots/{bot_id}/spec' \
  -H 'Content-Type: application/json' \
  -d '{
    "flows": [
      {
        "steps": [
          {
            "reply": "Привет! Я ваш новый бот!"
          }
        ],
        "entry_cmd": "/start"
      }
    ]
  }'
```

### 3. Настройка webhook

```bash
curl -X POST "https://api.telegram.org/bot{YOUR_TOKEN}/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-domain.com/tg/{bot_id}"
  }'
```

## 🔧 Формат спецификации бота

### Базовая структура flows

```json
{
  "flows": [
    {
      "entry_cmd": "/command_name",
      "steps": [
        {
          "reply": "Текст ответа бота"
        }
      ]
    }
  ]
}
```

### Примеры команд

#### Простая команда
```json
{
  "entry_cmd": "/start",
  "steps": [
    {
      "reply": "🎉 Добро пожаловать! Я готов к работе."
    }
  ]
}
```

#### Команда помощи
```json
{
  "entry_cmd": "/help",
  "steps": [
    {
      "reply": "📚 Доступные команды:\n\n/start - Начать\n/help - Помощь\n/status - Статус"
    }
  ]
}
```

#### Команда статуса
```json
{
  "entry_cmd": "/status",
  "steps": [
    {
      "reply": "📊 Статус бота:\n\n✅ Система работает\n✅ Команды обрабатываются\n✅ Всё в порядке!"
    }
  ]
}
```

## 🚀 Полный пример создания бота

### Шаг 1: Создание бота
```bash
# Создаем бота
RESPONSE=$(curl -s -X POST 'http://localhost:8000/bots' \
  -H 'Content-Type: application/json' \
  -d '{"name": "TestBot", "token": "YOUR_BOT_TOKEN"}')

# Извлекаем bot_id
BOT_ID=$(echo $RESPONSE | jq -r '.bot_id')
echo "Bot ID: $BOT_ID"
```

### Шаг 2: Добавление функциональности
```bash
# Добавляем commands
curl -X PUT "http://localhost:8000/bots/$BOT_ID/spec" \
  -H 'Content-Type: application/json' \
  -d '{
    "flows": [
      {
        "entry_cmd": "/start",
        "steps": [{"reply": "🎉 Привет! Я ваш новый бот!"}]
      },
      {
        "entry_cmd": "/help",
        "steps": [{"reply": "📚 Команды: /start, /help, /about"}]
      },
      {
        "entry_cmd": "/about",
        "steps": [{"reply": "🤖 Я создан с помощью BotFactory Runtime!"}]
      }
    ]
  }'
```

### Шаг 3: Настройка webhook
```bash
# Настраиваем webhook (для production)
curl -X POST "https://api.telegram.org/bot$YOUR_TOKEN/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"https://your-domain.com/tg/$BOT_ID\"}"
```

## ⚡ Особенности системы

### ✅ Что работает:
- **Hot reload** - изменения применяются мгновенно
- **Мультитенантность** - множественные боты работают параллельно
- **Независимость** - каждый бот имеет свою конфигурацию
- **Масштабируемость** - неограниченное количество ботов

### 🔧 Технические детали:
- Каждый бот получает уникальный `bot_id` (UUID)
- Webhook endpoint: `/tg/{bot_id}`
- Спецификации хранятся в PostgreSQL
- Router строится динамически для каждого запроса

### 📝 Правила написания flows:
1. **entry_cmd** должно начинаться с `/`
2. **steps** содержит массив шагов
3. **reply** - текст ответа бота
4. Поддерживаются эмодзи и markdown
5. Длинные сообщения автоматически форматируются

## 🛠️ API Endpoints

| Метод | Endpoint | Описание |
|-------|----------|----------|
| `POST` | `/bots` | Создать нового бота |
| `PUT` | `/bots/{id}/spec` | Обновить спецификацию |
| `GET` | `/bots/{id}` | Получить информацию о боте |
| `POST` | `/bots/{id}/reload` | Перезагрузить кэш бота |
| `POST` | `/tg/{id}` | Webhook endpoint для Telegram |

## 🎯 Быстрый старт

```bash
# 1. Создать бота в @BotFather и получить токен
# 2. Создать в системе:
curl -X POST 'http://localhost:8000/bots' -H 'Content-Type: application/json' \
  -d '{"name": "QuickBot", "token": "YOUR_TOKEN"}'

# 3. Добавить базовые команды:
curl -X PUT 'http://localhost:8000/bots/BOT_ID/spec' -H 'Content-Type: application/json' \
  -d '{"flows": [{"entry_cmd": "/start", "steps": [{"reply": "Привет! 👋"}]}]}'

# 4. Настроить webhook и начать использовать!
```

🎉 **Готово! Ваш бот работает и отвечает на команды!**