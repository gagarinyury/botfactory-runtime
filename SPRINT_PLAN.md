# Спринт: "Блоки v1 + Логи"

## Цель
Включить 3 блока (flow.wizard.v1, action.sql_exec.v1, action.sql_query.v1) и базовое логирование ботов так, чтобы сценарий бронирования (/book, /my, /cancel) работал через DSL без правки кода.

## Результат
- Спеки с блоками выполняются
- /book ведёт пошаговый визард с валидацией и записью в БД
- /my показывает последние записи
- /cancel удаляет последнюю запись
- Все события пишутся в bot_events, метрики инкрементируются
- Тесты 100% зелёные

## План работ

### 1. Миграции БД
- [ ] 1.1 Создать миграцию для таблицы components (id, type, version, params_schema JSONB, graph JSONB, created_at)
- [ ] 1.2 Создать миграцию для таблицы bot_components (bot_id UUID, component_id BIGINT, overrides JSONB, PRIMARY KEY(bot_id, component_id))
- [ ] 1.3 Создать миграцию для таблицы bot_events (id BIGSERIAL, ts TIMESTAMPTZ DEFAULT now(), bot_id UUID, user_id BIGINT, type TEXT, data JSONB)
- [ ] 1.4 Добавить индексы: ON bot_components(bot_id), ON bot_events(bot_id, ts DESC)

### 2. Расширение DSL
- [ ] 2.1 Расширить DSL схему для секции "use": ["flow.wizard.v1", "action.sql_query.v1", "action.sql_exec.v1"]
- [ ] 2.2 Добавить поддержку секции "flows" с полями: entry_cmd, steps: [{ ask, var, validate?: { regex, msg } }], on_enter/on_step/on_complete
- [ ] 2.3 Реализовать action.sql_query.v1: { sql, result_var }
- [ ] 2.4 Реализовать action.sql_exec.v1: { sql }
- [ ] 2.5 Реализовать action.reply_template.v1: { text, empty_text? }
- [ ] 2.6 Добавить шаблонизатор для {{var}} и {{#each rows}}...{{/each}}

### 3. Исполнитель
- [ ] 3.1 Настроить Redis для хранения состояния визардов state:{bot_id}:{user_id} с TTL ≥ 24h
- [ ] 3.2 Реализовать машину состояний визарда (создание ctx, переходы, завершение)
- [ ] 3.3 Добавить валидацию входных данных по regex с возвратом validate.msg
- [ ] 3.4 Реализовать SQL executor с параметрами :bot_id, :user_id, :var + транзакции
- [ ] 3.5 Интегрировать template renderer с простой логикой подстановки

### 4. Логирование и метрики
- [ ] 4.1 Расширить bot_events логирование для типов: "update", "flow_step", "action_sql", "action_reply", "error"
- [ ] 4.2 Добавить новые метрики: bot_updates_total{bot_id}, bot_errors_total{bot_id,where,code}, dsl_handle_latency_ms, webhook_latency_ms
- [ ] 4.3 Настроить structlog для визардов с trace_id, bot_id, user_id, spec_version, event

### 5. Безопасность
- [ ] 5.1 Обеспечить безопасность SQL выполнения (whitelist-пул, запрет ;, маскировка параметров)

### 6. Тесты
**Unit:**
- [ ] 6.1 Парсер DSL: корректно читает flows, steps, actions
- [ ] 6.2 Валидация regex: валид и невалид
- [ ] 6.3 Шаблоны: {{var}} и {{#each}} рендерятся
- [ ] 6.4 SQL builder: подстановка :bot_id, :user_id, переменных

**Integration:**
- [ ] 6.5 /book: step1 ask → ввод валидного → step2 ask → ввод валидного → запись в bookings → итоговый текст + невалидный ввод → validate.msg
- [ ] 6.6 /my: при наличии записей → вывод списка, при пустоте → empty_text; /cancel: удаляет последнюю запись, idempotent
- [ ] 6.7 Логи: после сценария есть записи update, flow_step, action_sql, action_reply; Метрики: инкременты по preview и webhook

**Fault tolerance:**
- [ ] 6.8 Падение БД → 503 db_unavailable, bot_errors_total{code="db"}; Ошибка SQL → 500 internal, bot_errors_total{code="sql"}; Повреждённое состояние визарда → сброс state

**Performance:**
- [ ] 6.9 100 запросов /preview/send p95 ≤ 200ms на dev

### 7. Документация
- [ ] 7.1 Создать docs/dsl-v1.md (формат flows, steps, actions, шаблоны)
- [ ] 7.2 Создать docs/events.md (типизация событий и поля)

## Пример целевой спеки
```json
{
  "use": ["flow.wizard.v1", "action.sql_exec.v1", "action.sql_query.v1"],
  "flows": [
    {
      "entry_cmd": "/book",
      "steps": [
        {"ask": "Какая услуга?", "var": "service", "validate": {"regex": "^(massage|spa|consultation)$", "msg": "Выберите: massage, spa, consultation"}},
        {"ask": "Когда удобно? (YYYY-MM-DD HH:MM)", "var": "slot", "validate": {"regex": "^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}$", "msg": "Формат: 2024-01-15 14:00"}}
      ],
      "on_complete": [
        {"action.sql_exec.v1": {"sql": "INSERT INTO bookings(bot_id, user_id, service, slot) VALUES(:bot_id, :user_id, :service, :slot::timestamptz)"}},
        {"action.reply_template.v1": {"text": "Забронировано: {{service}} на {{slot}}"}}
      ]
    },
    {
      "entry_cmd": "/my",
      "on_enter": [
        {"action.sql_query.v1": {"sql": "SELECT service, slot FROM bookings WHERE bot_id=:bot_id AND user_id=:user_id ORDER BY created_at DESC LIMIT 5", "result_var": "bookings"}},
        {"action.reply_template.v1": {"text": "Ваши брони:\n{{#each bookings}}{{service}} - {{slot}}\n{{/each}}", "empty_text": "У вас нет активных броней"}}
      ]
    },
    {
      "entry_cmd": "/cancel",
      "on_enter": [
        {"action.sql_exec.v1": {"sql": "DELETE FROM bookings WHERE bot_id=:bot_id AND user_id=:user_id AND id=(SELECT id FROM bookings WHERE bot_id=:bot_id AND user_id=:user_id ORDER BY created_at DESC LIMIT 1)"}},
        {"action.reply_template.v1": {"text": "Последняя бронь отменена"}}
      ]
    }
  ]
}
```

## Приёмка (DoD)
- [ ] Спека бронирования работает end-to-end через preview и реальный webhook
- [ ] В bot_events фиксируются ключевые шаги
- [ ] Метрики видны в /metrics
- [ ] Все новые тесты зелёные, общее 100%
- [ ] Миграции применяются автоматически в контейнере
- [ ] Документация готова: docs/dsl-v1.md, docs/events.md