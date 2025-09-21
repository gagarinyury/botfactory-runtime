# LLM Setup Guide

Руководство по настройке и использованию локального LLM модуля с 3B моделью для улучшения текстов ботов.

## Обзор

LLM модуль добавляет возможности NLU (Natural Language Understanding) и генерации текстов в runtime с помощью локальной 3B модели:

- **Модель**: Microsoft Phi-3-mini (3.8B параметров)
- **API**: OpenAI-совместимый HTTP интерфейс
- **Производительность**: ~30-60 токенов/сек на consumer GPU
- **Контекст**: 4K токенов
- **Кэширование**: Redis с TTL 15 минут
- **Rate limiting**: 10 запросов/минуту на пользователя

## Быстрый старт

### 1. Запуск LLM сервиса

```bash
# Поднять LLM сервис
docker compose -f docker-compose.llm.yml up -d llm

# Дождаться готовности (может занять несколько минут для загрузки модели)
docker logs -f botfactory-llm

# Проверить здоровье сервиса
curl http://localhost:11434/health
```

### 2. Тестирование API

```bash
# Тест chat completions
curl -s http://localhost:11434/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "microsoft/Phi-3-mini-4k-instruct",
    "messages": [
      {"role": "user", "content": "Привет! Как дела?"}
    ],
    "max_tokens": 100,
    "temperature": 0.2
  }'

# Тест completions
curl -s http://localhost:11434/v1/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "microsoft/Phi-3-mini-4k-instruct",
    "prompt": "Переведи на английский: Привет мир",
    "max_tokens": 50
  }'
```

### 3. Включение LLM в runtime

```bash
# Установить переменные окружения
export LLM_ENABLED=true
export LLM_BASE_URL=http://llm:11434
export LLM_MODEL=microsoft/Phi-3-mini-4k-instruct

# Перезапустить runtime
docker compose restart runtime
```

## Конфигурация

### Переменные окружения

```bash
# Основные настройки
LLM_ENABLED=true                           # Включить/выключить LLM
LLM_BASE_URL=http://llm:11434             # URL LLM сервиса
LLM_MODEL=microsoft/Phi-3-mini-4k-instruct # ID модели

# Производительность
LLM_TIMEOUT=30                            # Таймаут запросов (сек)
LLM_MAX_RETRIES=3                         # Количество повторов

# Безопасность (автоматически применяется)
LLM_RATE_LIMIT=10                         # Запросов/минуту на пользователя
LLM_CACHE_TTL=900                         # TTL кэша (сек)
```

### Альтернативные модели

```yaml
# docker-compose.llm.yml
services:
  llm:
    environment:
      # Быстрая модель (2B параметров)
      - MODEL_ID=google/gemma-2b-it

      # Мультиязычная модель (3B параметров)
      - MODEL_ID=Qwen/Qwen2.5-3B-Instruct

      # Сбалансированная модель (3.8B параметров, по умолчанию)
      - MODEL_ID=microsoft/Phi-3-mini-4k-instruct
```

## Использование в ботах

### 1. Улучшение текстов в action.reply_template.v1

```json
{
  "type": "action.reply_template.v1",
  "params": {
    "text": "Ваш заказ {{order_id}} готов к выдаче",
    "llm_improve": true,
    "keyboard": [
      {"text": "Спасибо!", "callback": "/thanks"}
    ]
  }
}
```

**Результат**: "Отлично! Ваш заказ {{order_id}} готов к выдаче! 🎉 Можете забирать в удобное время."

### 2. Умная валидация ввода

```python
from runtime.llm_client import llm_client
from runtime.llm_prompts import BotPromptConfigs

# Проверить корректность ввода пользователя
config = BotPromptConfigs.smart_validate_input(
    user_input="завтра в 3 дня",
    expectation="дата и время в формате YYYY-MM-DD HH:MM"
)

response = await llm_client.complete(**config)
result = LLMPrompts.parse_json_response(response.content)

if not result["valid"]:
    print(f"Ошибка: {result['reason']}")
    print(f"Предложение: {result['suggestion']}")
```

### 3. Генерация динамических меню

```python
# Создать меню на основе контекста
config = BotPromptConfigs.generate_dynamic_menu(
    context="пользователь интересуется спа-процедурами",
    topic="услуги салона красоты"
)

response = await llm_client.complete(**config)
menu_items = LLMPrompts.parse_json_response(response.content)["items"]

# Результат: [
#   {"text": "💆 Массаж лица", "description": "Расслабляющий массаж"},
#   {"text": "🧖 Уход за кожей", "description": "Профессиональная чистка"},
#   ...
# ]
```

### 4. Классификация намерений

```python
# Определить что хочет пользователь
config = BotPromptConfigs.classify_user_intent(
    message="хочу записаться на завтра к мастеру",
    available_intents=["book_service", "cancel_booking", "get_info", "help"]
)

response = await llm_client.complete(**config)
intent_result = LLMPrompts.parse_json_response(response.content)

print(f"Намерение: {intent_result['intent']}")  # book_service
print(f"Уверенность: {intent_result['confidence']}")  # 0.95
print(f"Сущности: {intent_result['entities']}")  # {"time": "завтра"}
```

## Мониторинг

### Метрики Prometheus

```
# Запросы
llm_requests_total{type="chat_completion",status="success"}
llm_requests_total{type="completion",status="failed"}

# Производительность
llm_latency_ms{type="chat_completion",cached="false"}
llm_latency_ms{type="completion",cached="true"}

# Использование токенов
llm_tokens_total{model="microsoft/Phi-3-mini-4k-instruct",type="input"}
llm_tokens_total{model="microsoft/Phi-3-mini-4k-instruct",type="output"}

# Кэширование
llm_cache_hits_total{model="microsoft/Phi-3-mini-4k-instruct"}

# Ошибки
llm_errors_total{model="microsoft/Phi-3-mini-4k-instruct",error_type="timeout"}
llm_errors_total{model="microsoft/Phi-3-mini-4k-instruct",error_type="rate_limit_exceeded"}
```

### Логи

```bash
# Просмотр логов LLM сервиса
docker logs botfactory-llm

# Логи runtime с LLM событиями
docker logs botfactory-runtime | grep llm_

# Основные события:
# - llm_request: новый запрос к LLM
# - llm_success: успешный ответ
# - llm_cache_hit: попадание в кэш
# - llm_text_improved: текст улучшен
# - llm_rate_limit_exceeded: превышен лимит
```

## Troubleshooting

### LLM сервис не запускается

```bash
# Проверить логи
docker logs botfactory-llm

# Типичные проблемы:
# 1. Недостаточно памяти (нужно минимум 4GB RAM)
# 2. Модель не загрузилась (проверить MODEL_ID)
# 3. Проблемы с сетью (проверить порты)

# Решение: увеличить memory limit
docker compose -f docker-compose.llm.yml up -d --scale llm=1 \
  --memory=6g llm
```

### Медленные ответы

```bash
# Проверить использование GPU
docker exec botfactory-llm nvidia-smi

# Если GPU недоступен, модель работает на CPU
# Решение: использовать меньшую модель
MODEL_ID=google/gemma-2b-it  # Вместо Phi-3
```

### Ошибки кэширования

```bash
# Проверить Redis
docker exec botfactory-redis redis-cli ping

# Очистить кэш LLM
docker exec botfactory-redis redis-cli del "llm:cache:*"
```

### Rate limit превышен

```bash
# Увеличить лимит или очистить счетчики
docker exec botfactory-redis redis-cli del "llm:ratelimit:*"

# Или изменить лимит в коде (llm_client.py:395)
if current_count >= 20:  # Вместо 10
```

## Производительность

### Бенчмарки

| Модель | Размер | Скорость | Память | Качество |
|--------|--------|----------|---------|----------|
| Gemma-2B | 2B | 60 tok/s | 3GB | Хорошее |
| Phi-3-mini | 3.8B | 40 tok/s | 4GB | Отличное |
| Qwen2.5-3B | 3B | 45 tok/s | 3.5GB | Отличное |

### Оптимизация

```yaml
# Для максимальной скорости
environment:
  - MODEL_ID=google/gemma-2b-it
  - QUANTIZE=int4
  - MAX_BATCH_TOTAL_TOKENS=4096

# Для лучшего качества
environment:
  - MODEL_ID=microsoft/Phi-3-mini-4k-instruct
  - QUANTIZE=gptq
  - MAX_BATCH_TOTAL_TOKENS=8192
```

## Безопасность

### Встроенная защита

- **Rate limiting**: 10 запросов/минуту на пользователя
- **Input sanitization**: Ограничение длины промптов
- **Timeout protection**: Автоматический таймаут 30 сек
- **Caching**: Кэширование предотвращает повторные вычисления
- **Error handling**: Graceful fallback при ошибках

### Дополнительные меры

```bash
# Ограничить доступ к LLM сервису
iptables -A INPUT -p tcp --dport 11434 -s 10.0.0.0/8 -j ACCEPT
iptables -A INPUT -p tcp --dport 11434 -j DROP

# Мониторинг использования ресурсов
docker stats botfactory-llm

# Ротация логов
docker run --log-driver=syslog --log-opt max-size=10m botfactory-llm
```

---

**Готово!** LLM модуль полностью интегрирован и готов к использованию. Начните с включения `llm_improve: true` в ваших reply templates.