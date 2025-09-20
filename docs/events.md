# Bot Events Documentation

Система событий Bot Factory Runtime обеспечивает полную наблюдаемость за действиями ботов, логирование операций и сбор метрик.

## Обзор

Все взаимодействия с ботами фиксируются в виде событий, которые:
- Сохраняются в таблице `bot_events` для аудита
- Преобразуются в структурированные логи (structlog)
- Агрегируются в метрики Prometheus

## Схема базы данных

### Таблица `bot_events`

```sql
CREATE TABLE bot_events (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ DEFAULT now(),
    bot_id UUID NOT NULL,
    user_id BIGINT NOT NULL,
    type TEXT NOT NULL,
    data JSONB
);

CREATE INDEX idx_bot_events_bot_ts ON bot_events(bot_id, ts DESC);
```

#### Поля

| Поле | Тип | Описание |
|------|-----|----------|
| `id` | BIGSERIAL | Уникальный ID события |
| `ts` | TIMESTAMPTZ | Временная метка (UTC) |
| `bot_id` | UUID | Идентификатор бота |
| `user_id` | BIGINT | Идентификатор пользователя |
| `type` | TEXT | Тип события |
| `data` | JSONB | Дополнительные данные события |

## Типы событий

### `update`

Входящее сообщение от пользователя.

**Когда генерируется:**
- При получении любого сообщения через webhook или preview

**Структура данных:**
```json
{
  "cmd": "/start",
  "text_length": 6,
  "trace_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Поля data:**
- `cmd` (string, optional) - команда, если сообщение является командой
- `text_length` (integer) - длина текста сообщения
- `trace_id` (string) - уникальный ID для трассировки

### `flow_step`

Шаг визарда пройден пользователем.

**Когда генерируется:**
- При успешном прохождении каждого шага в wizard flow
- После валидации пользовательского ввода

**Структура данных:**
```json
{
  "flow_cmd": "/book",
  "step": 1,
  "var": "service",
  "input_length": 7,
  "validation_passed": true,
  "duration_ms": 45,
  "trace_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Поля data:**
- `flow_cmd` (string) - команда запуска flow
- `step` (integer) - номер шага (0-based)
- `var` (string) - имя переменной для этого шага
- `input_length` (integer) - длина пользовательского ввода
- `validation_passed` (boolean) - прошла ли валидация
- `duration_ms` (integer) - время обработки шага
- `trace_id` (string) - ID трассировки

### `action_sql`

Выполнение SQL действия (query или exec).

**Когда генерируется:**
- При выполнении `action.sql_query.v1`
- При выполнении `action.sql_exec.v1`

**Структура данных:**
```json
{
  "action_type": "sql_exec",
  "sql_hash": 1234,
  "rows_affected": 1,
  "duration_ms": 23,
  "success": true,
  "trace_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Поля data:**
- `action_type` (string) - "sql_query" или "sql_exec"
- `sql_hash` (integer) - хеш SQL запроса (для безопасности)
- `rows_affected` (integer, sql_exec) - количество затронутых строк
- `rows_count` (integer, sql_query) - количество возвращённых строк
- `result_var` (string, sql_query) - имя переменной результата
- `duration_ms` (integer) - время выполнения SQL
- `success` (boolean) - успешность операции
- `trace_id` (string) - ID трассировки

### `action_reply`

Отправка ответа пользователю через шаблон.

**Когда генерируется:**
- При выполнении `action.reply_template.v1`
- При отправке финального ответа пользователю

**Структура данных:**
```json
{
  "template_length": 156,
  "rendered_length": 89,
  "empty_text_used": false,
  "variables_count": 3,
  "loops_count": 1,
  "duration_ms": 12,
  "trace_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Поля data:**
- `template_length` (integer) - длина исходного шаблона
- `rendered_length` (integer) - длина отрендеренного текста
- `empty_text_used` (boolean) - использовался ли empty_text
- `variables_count` (integer) - количество подставленных переменных
- `loops_count` (integer) - количество циклов {{#each}}
- `duration_ms` (integer) - время рендеринга
- `trace_id` (string) - ID трассировки

### `error`

Ошибка в обработке бота.

**Когда генерируется:**
- При любых ошибках в процессе обработки
- При сбоях SQL операций
- При проблемах с Redis
- При ошибках валидации

**Структура данных:**
```json
{
  "error_type": "sql_error",
  "error_code": "syntax_error",
  "error_message": "syntax error at or near...",
  "context": "action_sql_exec",
  "sql_hash": 5678,
  "duration_ms": 156,
  "trace_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Поля data:**
- `error_type` (string) - категория ошибки
- `error_code` (string) - код ошибки
- `error_message` (string) - описание ошибки (обрезано)
- `context` (string) - контекст возникновения ошибки
- `sql_hash` (integer, optional) - хеш SQL при SQL ошибках
- `duration_ms` (integer) - время до ошибки
- `trace_id` (string) - ID трассировки

## Структурированное логирование

### Конфигурация structlog

Используется `structlog` для создания структурированных логов:

```python
import structlog

logger = structlog.get_logger()
```

### Обязательные поля

Каждая запись лога содержит:

```json
{
  "timestamp": "2024-01-15T14:30:45.123Z",
  "level": "info",
  "event": "wizard_step_completed",
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "bot_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_id": 987654321,
  "spec_version": 5
}
```

#### Описание полей

- `timestamp` (string) - время события в ISO 8601 UTC
- `level` (string) - уровень лога (info, warning, error)
- `event` (string) - название события
- `trace_id` (string) - уникальный ID запроса
- `bot_id` (string) - UUID бота
- `user_id` (integer) - ID пользователя Telegram
- `spec_version` (integer) - версия спецификации бота

### Примеры событий в логах

#### Успешный шаг визарда
```json
{
  "timestamp": "2024-01-15T14:30:45.123Z",
  "level": "info",
  "event": "wizard_step_completed",
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "bot_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_id": 987654321,
  "spec_version": 5,
  "step": 1,
  "var": "service",
  "input": "massage"
}
```

#### SQL операция
```json
{
  "timestamp": "2024-01-15T14:30:45.456Z",
  "level": "info",
  "event": "sql_exec_executed",
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "bot_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_id": 987654321,
  "spec_version": 5,
  "sql_hash": 1234,
  "rows_affected": 1,
  "duration_ms": 23
}
```

#### Ошибка
```json
{
  "timestamp": "2024-01-15T14:30:45.789Z",
  "level": "error",
  "event": "sql_exec_failed",
  "trace_id": "550e8400-e29b-41d4-a716-446655440000",
  "bot_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_id": 987654321,
  "spec_version": 5,
  "sql_hash": 5678,
  "error": "Database connection failed",
  "duration_ms": 156
}
```

### Маскирование чувствительных данных

Чувствительные данные автоматически маскируются:

- **SQL параметры** - заменяются на хеши
- **Пользовательские токены** - маскируются
- **Полные SQL запросы** - заменяются на хеши
- **Личные данные** - не логируются в открытом виде

Пример маскирования:
```json
{
  "sql_params": "***masked***",
  "sql_hash": 1234,
  "token": "***masked***"
}
```

## Метрики Prometheus

### bot_updates_total

Счётчик входящих сообщений.

```
bot_updates_total{bot_id="123e4567-e89b-12d3-a456-426614174000"} 45
```

**Лейблы:**
- `bot_id` - UUID бота

**Инкремент:**
- При каждом событии типа `update`

### bot_errors_total

Счётчик ошибок.

```
bot_errors_total{bot_id="123e4567-e89b-12d3-a456-426614174000",where="sql",code="syntax_error"} 2
```

**Лейблы:**
- `bot_id` - UUID бота
- `where` - место возникновения ошибки
- `code` - код/тип ошибки

**Возможные значения `where`:**
- `database` - ошибки подключения к БД
- `sql` - ошибки SQL операций
- `redis` - ошибки Redis
- `validation` - ошибки валидации
- `template` - ошибки рендеринга

**Возможные значения `code`:**
- `db` - недоступность БД
- `sql` - SQL ошибки
- `timeout` - превышение таймаута
- `validation` - ошибки валидации
- `template` - ошибки шаблонов

### dsl_handle_latency_ms

Гистограмма времени обработки DSL.

```
dsl_handle_latency_ms_bucket{le="50"} 120
dsl_handle_latency_ms_bucket{le="100"} 180
dsl_handle_latency_ms_bucket{le="200"} 195
dsl_handle_latency_ms_bucket{le="+Inf"} 200
```

**Измерение:**
- Время от получения сообщения до отправки ответа
- Включает все операции DSL

### webhook_latency_ms

Гистограмма времени обработки webhook'ов.

```
webhook_latency_ms_bucket{le="100"} 89
webhook_latency_ms_bucket{le="200"} 98
webhook_latency_ms_bucket{le="500"} 100
webhook_latency_ms_bucket{le="+Inf"} 100
```

**Измерение:**
- Полное время обработки HTTP запроса webhook
- От получения до HTTP ответа

## Запросы к событиям

### Получение событий бота

```sql
SELECT ts, type, data
FROM bot_events
WHERE bot_id = '123e4567-e89b-12d3-a456-426614174000'
ORDER BY ts DESC
LIMIT 100;
```

### События пользователя

```sql
SELECT ts, type, data
FROM bot_events
WHERE bot_id = '123e4567-e89b-12d3-a456-426614174000'
  AND user_id = 987654321
ORDER BY ts DESC
LIMIT 50;
```

### События по типу

```sql
SELECT ts, bot_id, user_id, data
FROM bot_events
WHERE type = 'error'
  AND ts > now() - interval '1 hour'
ORDER BY ts DESC;
```

### Статистика по ботам

```sql
SELECT
  bot_id,
  count(*) as total_events,
  count(*) FILTER (WHERE type = 'update') as updates,
  count(*) FILTER (WHERE type = 'error') as errors
FROM bot_events
WHERE ts > now() - interval '24 hours'
GROUP BY bot_id
ORDER BY total_events DESC;
```

### Trace анализ

```sql
SELECT ts, type, data
FROM bot_events
WHERE data->>'trace_id' = '550e8400-e29b-41d4-a716-446655440000'
ORDER BY ts;
```

## Ретенция и архивирование

### Политика хранения

- **Hot data**: последние 30 дней в основной таблице
- **Warm data**: до 6 месяцев в архивных партициях
- **Cold data**: старше 6 месяцев - удаление

### Партиционирование

```sql
-- Пример партиции по месяцам
CREATE TABLE bot_events_2024_01 PARTITION OF bot_events
FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
```

### Очистка старых данных

```sql
-- Автоматическая очистка событий старше 6 месяцев
DELETE FROM bot_events
WHERE ts < now() - interval '6 months';
```

## Мониторинг и алерты

### Рекомендуемые алерты

#### Высокий уровень ошибок
```yaml
alert: BotHighErrorRate
expr: rate(bot_errors_total[5m]) > 0.1
for: 2m
labels:
  severity: warning
annotations:
  summary: "High error rate for bot {{ $labels.bot_id }}"
```

#### Медленные ответы
```yaml
alert: BotSlowResponses
expr: histogram_quantile(0.95, rate(dsl_handle_latency_ms_bucket[5m])) > 200
for: 1m
labels:
  severity: warning
annotations:
  summary: "Bot responses are slow (P95 > 200ms)"
```

#### Отсутствие активности
```yaml
alert: BotNoActivity
expr: rate(bot_updates_total[10m]) == 0
for: 5m
labels:
  severity: info
annotations:
  summary: "No bot activity for 10 minutes"
```

### Дашборды

Рекомендуемые метрики для мониторинга:
- Количество активных ботов
- RPS по ботам
- Распределение времени ответа
- Количество ошибок по типам
- Активность пользователей
- Использование wizard flows

## Troubleshooting

### Отладка с помощью trace_id

1. Найти события по trace_id:
```sql
SELECT * FROM bot_events
WHERE data->>'trace_id' = 'YOUR_TRACE_ID'
ORDER BY ts;
```

2. Найти соответствующие логи:
```bash
grep "YOUR_TRACE_ID" /var/log/bot-factory/*.log
```

### Анализ проблем производительности

1. Медленные SQL операции:
```sql
SELECT
  data->>'sql_hash' as sql_hash,
  avg((data->>'duration_ms')::int) as avg_duration,
  count(*) as executions
FROM bot_events
WHERE type = 'action_sql'
  AND ts > now() - interval '1 hour'
GROUP BY data->>'sql_hash'
ORDER BY avg_duration DESC;
```

2. Медленные wizard flows:
```sql
SELECT
  data->>'flow_cmd' as flow,
  avg((data->>'duration_ms')::int) as avg_step_duration
FROM bot_events
WHERE type = 'flow_step'
  AND ts > now() - interval '1 hour'
GROUP BY data->>'flow_cmd'
ORDER BY avg_step_duration DESC;
```

### Анализ ошибок

1. Топ ошибок по типам:
```sql
SELECT
  data->>'error_type' as error_type,
  data->>'error_code' as error_code,
  count(*) as occurrences
FROM bot_events
WHERE type = 'error'
  AND ts > now() - interval '1 hour'
GROUP BY data->>'error_type', data->>'error_code'
ORDER BY occurrences DESC;
```

2. Ошибки конкретного бота:
```sql
SELECT ts, data
FROM bot_events
WHERE type = 'error'
  AND bot_id = 'YOUR_BOT_ID'
  AND ts > now() - interval '1 hour'
ORDER BY ts DESC;
```

## Конфигурация

### Переменные окружения

```bash
# Уровень логирования
LOG_LEVEL=info

# Настройки БД для событий
EVENTS_DB_RETENTION_DAYS=180
EVENTS_BATCH_SIZE=1000

# Настройки метрик
METRICS_ENABLED=true
METRICS_PREFIX=botfactory_

# Маскирование данных
MASK_SENSITIVE_DATA=true
```

### Настройка ротации логов

```yaml
# logrotate config
/var/log/bot-factory/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
}
```

## Примеры использования

### Анализ пользовательского опыта

```sql
-- Время прохождения wizard flows
WITH flow_sessions AS (
  SELECT
    data->>'trace_id' as trace_id,
    min(ts) as start_time,
    max(ts) as end_time,
    count(*) as steps_count
  FROM bot_events
  WHERE type = 'flow_step'
    AND ts > now() - interval '24 hours'
  GROUP BY data->>'trace_id'
)
SELECT
  avg(extract(epoch from (end_time - start_time))) as avg_duration_seconds,
  avg(steps_count) as avg_steps
FROM flow_sessions;
```

### Мониторинг SLA

```sql
-- Процент запросов быстрее 200ms
WITH response_times AS (
  SELECT (data->>'duration_ms')::int as duration
  FROM bot_events
  WHERE type = 'update'
    AND ts > now() - interval '1 hour'
    AND data ? 'duration_ms'
)
SELECT
  count(*) FILTER (WHERE duration <= 200) * 100.0 / count(*) as sla_percentage
FROM response_times;
```