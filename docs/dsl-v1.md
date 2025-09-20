# DSL v1 Specification

Bot Factory Runtime DSL (Domain Specific Language) v1 позволяет создавать интерактивных ботов с помощью декларативных JSON-спецификаций.

## Обзор

DSL v1 поддерживает:
- **Простые команды** с немедленными ответами
- **Пошаговые визарды** с валидацией ввода
- **SQL действия** для работы с базой данных
- **Шаблонизацию** ответов с переменными и циклами

## Структура спецификации

```json
{
  "use": ["компонент1", "компонент2"],
  "intents": [
    {"cmd": "/команда", "reply": "ответ"}
  ],
  "flows": [
    {
      "entry_cmd": "/команда",
      "steps": [...],
      "on_enter": [...],
      "on_step": [...],
      "on_complete": [...]
    }
  ]
}
```

## Секция `use`

Определяет используемые компоненты DSL:

```json
{
  "use": [
    "flow.wizard.v1",
    "action.sql_exec.v1",
    "action.sql_query.v1",
    "action.reply_template.v1"
  ]
}
```

### Доступные компоненты

| Компонент | Описание |
|-----------|----------|
| `flow.wizard.v1` | Пошаговые визарды с состоянием |
| `flow.menu.v1` | Простые меню с inline-кнопками |
| `action.sql_exec.v1` | Выполнение SQL команд (INSERT, DELETE) |
| `action.sql_query.v1` | SQL запросы (SELECT) |
| `action.reply_template.v1` | Шаблонизация ответов |

## Секция `intents`

Простые команды с немедленными ответами:

```json
{
  "intents": [
    {"cmd": "/start", "reply": "Добро пожаловать!"},
    {"cmd": "/help", "reply": "Доступные команды: /start, /book, /my, /cancel"}
  ]
}
```

### Поля intent

- `cmd` (string) - команда бота (с префиксом `/`)
- `reply` (string) - текст ответа

## Секция `flows`

Пошаговые визарды с состоянием и действиями:

```json
{
  "flows": [
    {
      "entry_cmd": "/book",
      "steps": [
        {
          "ask": "Какая услуга?",
          "var": "service",
          "validate": {
            "regex": "^(massage|spa|consultation)$",
            "msg": "Выберите: massage, spa, consultation"
          }
        }
      ],
      "on_complete": [
        {"action.sql_exec.v1": {"sql": "INSERT INTO bookings..."}}
      ]
    }
  ]
}
```

### Поля flow

- `entry_cmd` (string) - команда для запуска flow
- `steps` (array, optional) - шаги визарда
- `on_enter` (array, optional) - действия при входе в flow
- `on_step` (array, optional) - действия после каждого шага
- `on_complete` (array, optional) - действия при завершении

### Шаги визарда (`steps`)

Каждый шаг определяет вопрос пользователю:

```json
{
  "ask": "Когда удобно? (YYYY-MM-DD HH:MM)",
  "var": "slot",
  "validate": {
    "regex": "^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}$",
    "msg": "Формат: 2024-01-15 14:00"
  }
}
```

#### Поля step

- `ask` (string) - вопрос пользователю
- `var` (string) - имя переменной для сохранения ответа
- `validate` (object, optional) - валидация ввода

#### Валидация (`validate`)

- `regex` (string) - регулярное выражение для проверки
- `msg` (string) - сообщение об ошибке при невалидном вводе

## Меню flows (flow.menu.v1)

Простые меню с inline-кнопками для навигации. Это stateless flows, которые отображают заголовок и кнопки выбора.

### Структура menu flow

```json
{
  "type": "flow.menu.v1",
  "entry_cmd": "/команда",
  "params": {
    "title": "Заголовок меню",
    "options": [
      {"text": "Текст кнопки", "callback": "callback_data|/intent"}
    ]
  }
}
```

### Поля menu flow

- `type` (string) - должно быть `"flow.menu.v1"`
- `entry_cmd` (string) - команда для вызова меню
- `params.title` (string) - заголовок меню
- `params.options` (array) - массив кнопок

### Поля кнопки

- `text` (string) - текст кнопки
- `callback` (string) - callback_data или intent (если начинается с /)

### Примеры menu flows

#### Главное меню

```json
{
  "type": "flow.menu.v1",
  "entry_cmd": "/start",
  "params": {
    "title": "🏠 Добро пожаловать!\\nВыберите действие:",
    "options": [
      {"text": "📅 Забронировать", "callback": "/book"},
      {"text": "📋 Мои записи", "callback": "/my"},
      {"text": "❓ Помощь", "callback": "/help"}
    ]
  }
}
```

#### Меню категорий

```json
{
  "type": "flow.menu.v1",
  "entry_cmd": "/services",
  "params": {
    "title": "Выберите категорию услуг:",
    "options": [
      {"text": "💆 Массаж", "callback": "category_massage"},
      {"text": "💇 Парикмахер", "callback": "category_hair"},
      {"text": "✨ Косметология", "callback": "category_cosmo"},
      {"text": "🔙 Назад", "callback": "/start"}
    ]
  }
}
```

### Размещение menu flows

Menu flows можно размещать в двух секциях:

1. **В секции `flows`** - вместе с wizard flows:
```json
{
  "use": ["flow.menu.v1"],
  "flows": [
    {
      "type": "flow.menu.v1",
      "entry_cmd": "/start",
      "params": {...}
    }
  ]
}
```

2. **В секции `menu_flows`** - отдельно:
```json
{
  "use": ["flow.menu.v1"],
  "menu_flows": [
    {
      "type": "flow.menu.v1",
      "entry_cmd": "/start",
      "params": {...}
    }
  ]
}
```

### Приоритет обработки

Menu flows имеют приоритет над wizard flows для одинаковых команд.

## Действия (Actions)

### action.sql_exec.v1

Выполнение SQL команд (INSERT, DELETE):

```json
{
  "action.sql_exec.v1": {
    "sql": "INSERT INTO bookings(bot_id, user_id, service, slot) VALUES(:bot_id, :user_id, :service, :slot::timestamptz)"
  }
}
```

**Параметры:**
- `sql` (string) - SQL команда

**Доступные параметры в SQL:**
- `:bot_id` - ID бота
- `:user_id` - ID пользователя
- `:variable` - любая переменная из контекста визарда

**Ограничения безопасности:**
- Разрешены только INSERT и DELETE
- Запрещены множественные SQL команды (`;`)
- Все параметры экранируются автоматически

### action.sql_query.v1

SQL запросы (SELECT):

```json
{
  "action.sql_query.v1": {
    "sql": "SELECT service, slot FROM bookings WHERE bot_id=:bot_id AND user_id=:user_id ORDER BY created_at DESC LIMIT 5",
    "result_var": "bookings"
  }
}
```

**Параметры:**
- `sql` (string) - SQL запрос
- `result_var` (string) - имя переменной для результата

**Результат:** массив объектов с полями из SELECT

### action.reply_template.v1

Шаблонизация ответов с поддержкой inline-клавиатур:

```json
{
  "action.reply_template.v1": {
    "text": "Ваши брони:\\n{{#each bookings}}{{service}} - {{slot}}\\n{{/each}}",
    "empty_text": "У вас нет активных броней",
    "keyboard": [
      {"text": "Забронировать", "callback": "/book"},
      {"text": "Отменить", "callback": "/cancel"}
    ]
  }
}
```

**Параметры:**
- `text` (string) - шаблон текста с поддержкой {{var}} и {{#each}}
- `empty_text` (string, опционально) - текст при пустых данных
- `keyboard` (array, опционально) - массив кнопок inline-клавиатуры

**Формат кнопок:**
- `text` (string) - текст кнопки
- `callback` (string) - callback_data или intent (если начинается с /)

**Результат:** объект с полями `type: "reply"`, `text`, `keyboard?`

## Шаблонизация

### Подстановка переменных

```
Забронировано: {{service}} на {{slot}}
```

Поддерживаются переменные типов:
- `string` - подставляется как есть
- `number` - преобразуется в строку
- `boolean` - преобразуется в "True"/"False"

### Циклы

```
Ваши брони:
{{#each bookings}}
{{service}} - {{slot}}
{{/each}}
```

**Поведение:**
- Если `bookings` пустой и задан `empty_text` - возвращается `empty_text`
- Каждый элемент массива должен быть объектом
- Поля объекта доступны как `{{field_name}}`

### Экранирование

Специальные символы в переменных обрабатываются безопасно. SQL инъекции невозможны благодаря параметризованным запросам.

## Полные примеры

### Система бронирования

```json
{
  "use": ["flow.wizard.v1", "action.sql_exec.v1", "action.sql_query.v1", "action.reply_template.v1"],
  "intents": [
    {"cmd": "/start", "reply": "Добро пожаловать в систему бронирования!\\nДоступные команды: /book, /my, /cancel"}
  ],
  "flows": [
    {
      "entry_cmd": "/book",
      "steps": [
        {
          "ask": "Какая услуга?",
          "var": "service",
          "validate": {
            "regex": "^(massage|spa|consultation)$",
            "msg": "Выберите: massage, spa, consultation"
          }
        },
        {
          "ask": "Когда удобно? (YYYY-MM-DD HH:MM)",
          "var": "slot",
          "validate": {
            "regex": "^\\d{4}-\\d{2}-\\d{2} \\d{2}:\\d{2}$",
            "msg": "Формат: 2024-01-15 14:00"
          }
        }
      ],
      "on_complete": [
        {
          "action.sql_exec.v1": {
            "sql": "INSERT INTO bookings(bot_id, user_id, service, slot) VALUES(:bot_id, :user_id, :service, :slot::timestamptz)"
          }
        },
        {
          "action.reply_template.v1": {
            "text": "✅ Забронировано: {{service}} на {{slot}}"
          }
        }
      ]
    },
    {
      "entry_cmd": "/my",
      "on_enter": [
        {
          "action.sql_query.v1": {
            "sql": "SELECT service, slot FROM bookings WHERE bot_id=:bot_id AND user_id=:user_id ORDER BY created_at DESC LIMIT 5",
            "result_var": "bookings"
          }
        },
        {
          "action.reply_template.v1": {
            "text": "📋 Ваши брони:\\n{{#each bookings}}• {{service}} - {{slot}}\\n{{/each}}",
            "empty_text": "У вас нет активных броней",
            "keyboard": [
              {"text": "Забронировать ещё", "callback": "/book"},
              {"text": "Отменить последнюю", "callback": "/cancel"}
            ]
          }
        }
      ]
    },
    {
      "entry_cmd": "/cancel",
      "on_enter": [
        {
          "action.sql_exec.v1": {
            "sql": "DELETE FROM bookings WHERE bot_id=:bot_id AND user_id=:user_id AND id=(SELECT id FROM bookings WHERE bot_id=:bot_id AND user_id=:user_id ORDER BY created_at DESC LIMIT 1)"
          }
        },
        {
          "action.reply_template.v1": {
            "text": "❌ Последняя бронь отменена"
          }
        }
      ]
    }
  ]
}
```

### Простая анкета

```json
{
  "use": ["flow.wizard.v1", "action.sql_exec.v1", "action.reply_template.v1"],
  "flows": [
    {
      "entry_cmd": "/survey",
      "steps": [
        {
          "ask": "Как вас зовут?",
          "var": "name"
        },
        {
          "ask": "Ваш возраст?",
          "var": "age",
          "validate": {
            "regex": "^\\d{1,3}$",
            "msg": "Введите возраст числом"
          }
        },
        {
          "ask": "Оцените сервис от 1 до 5",
          "var": "rating",
          "validate": {
            "regex": "^[1-5]$",
            "msg": "Введите число от 1 до 5"
          }
        }
      ],
      "on_complete": [
        {
          "action.sql_exec.v1": {
            "sql": "INSERT INTO surveys(bot_id, user_id, name, age, rating) VALUES(:bot_id, :user_id, :name, :age, :rating)"
          }
        },
        {
          "action.reply_template.v1": {
            "text": "Спасибо, {{name}}! Ваша оценка {{rating}} сохранена."
          }
        }
      ]
    }
  ]
}
```

## Состояние визарда

### Хранение

Состояние визарда хранится в Redis с ключом `state:{bot_id}:{user_id}` и TTL 24 часа.

### Структура состояния

```json
{
  "flow": {...},
  "step": 2,
  "vars": {
    "service": "massage",
    "slot": "2024-01-15 14:00"
  },
  "started_at": "2024-01-15T10:00:00Z"
}
```

### Автоочистка

- Состояние удаляется при завершении визарда
- Автоматическое истечение через 24 часа
- Сброс при повреждении данных

## Обработка ошибок

### Валидация ввода

При невалидном вводе возвращается `validate.msg` и повторяется вопрос.

### Ошибки SQL

- Синтаксические ошибки: HTTP 500
- Нарушение ограничений: graceful handling
- Недоступность БД: HTTP 503

### Повреждение состояния

При повреждении состояния визарда происходит автоматический сброс и начало заново.

## Производительность

### Кеширование

- Спецификации ботов кешируются в памяти
- Роутеры строятся один раз и переиспользуются
- TTL кеш с автоматической инвалидацией

### Метрики

Автоматически собираются метрики:
- `bot_updates_total{bot_id}` - количество сообщений
- `dsl_handle_latency_ms` - время обработки
- `bot_errors_total{bot_id,where,code}` - ошибки

### Требования

- P95 latency ≤ 200ms для /preview/send
- Поддержка множественных concurrent пользователей
- Graceful degradation при сбоях

## Безопасность

### SQL Injection

- Все SQL параметризованы (:param)
- Запрещены множественные команды (;)
- Whitelist разрешённых SQL операций

### Входные данные

- Валидация всех пользовательских вводов
- Экранирование в шаблонах
- Ограничение размеров ввода

### Изоляция

- Состояние пользователей изолировано
- Данные ботов изолированы по bot_id
- SQL запросы автоматически фильтруются по bot_id/user_id

## Миграция и версионирование

### Обратная совместимость

DSL v1 совместим с legacy интентами. Старые спецификации продолжают работать.

### Обновление спецификаций

```bash
POST /bots/{bot_id}/reload
```

Инвалидирует кеш и перезагружает спецификацию бота.

### Схема БД

Новые таблицы:
- `components` - реестр компонентов DSL
- `bot_components` - компоненты для каждого бота
- `bot_events` - события и логи ботов

## Отладка

### Логирование

Все действия логируются в `bot_events` с типами:
- `update` - входящие сообщения
- `flow_step` - шаги визарда
- `action_sql` - SQL операции
- `action_reply` - ответы ботов
- `error` - ошибки

### Trace ID

Каждый запрос имеет уникальный trace_id для отслеживания в логах.

### Мониторинг

- Метрики Prometheus доступны на `/metrics`
- Health checks: `/health`, `/health/db`
- Структурированные логи с полным контекстом

## Ограничения

### Текущие ограничения

- Максимум 10 шагов в визарде
- TTL состояния 24 часа
- Размер ввода ограничен разумными пределами
- Nested loops в шаблонах не поддерживаются

### Планы развития

- Условная логика в flows
- Внешние API интеграции
- Богатые медиа (кнопки, изображения)
- Расширенная шаблонизация