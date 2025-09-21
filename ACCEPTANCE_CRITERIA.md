# 🎯 ACCEPTANCE CRITERIA - BotFactory Runtime

**Версия:** 2.0 (улучшенная)
**Дата:** 2025-09-21
**Статус:** Production Ready Criteria

---

## 📊 КРАТКИЙ ОБЗОР

| Категория | Статус | Комментарий |
|-----------|--------|-------------|
| **Функциональность** | ✅ ГОТОВО | Все DSL блоки работают |
| **API Endpoints** | ✅ ГОТОВО | Health checks детализированы |
| **Performance** | ⚠️ ТРЕБУЕТ ВАЛИДАЦИИ | Нужно нагрузочное тестирование |
| **Unit Tests** | ❌ ТРЕБУЕТ ИСПРАВЛЕНИЯ | Mock'и устарели |
| **Observability** | ✅ ГОТОВО | Метрики + алерты настроены |
| **Fault Tolerance** | ✅ ГОТОВО | Circuit breaker + chaos testing |

---

## 🔥 КРИТИЧЕСКИЕ ТРЕБОВАНИЯ (P0)

### 1. **UNIT TESTS: 0 XFAIL, 0 ERROR**
**Было:** "95%+ зелёных"
**Стало:** "0 xfail, 0 error"

```bash
# Критерий прохождения:
make test-unit
# Результат должен быть: ===== X passed, 0 failed, 0 error, 0 xfail =====
```

**Текущие проблемы:**
- Mock'и указывают на устаревшие пути импортов
- `runtime.actions.bot_sql_query_total` → `runtime.telemetry.bot_sql_query_total`
- `runtime.broadcast_engine.I18nManager` → `runtime.i18n_manager.I18nManager`

### 2. **CHAOS RECOVERY: МЕТРИКИ К BASELINE ЗА ≤5 МИН**
**Было:** "Recovery после падения сервисов"
**Стало:** "После восстановления все метрики возвращаются к базовой линии за ≤5 мин"

```bash
# Критерий прохождения:
make test-chaos
# Все сервисы должны восстановиться и метрики вернуться к норме
```

**Измеримые критерии:**
- `bot_errors_total` rate ≤ 1% после восстановления
- `dsl_handle_latency_ms` p95 ≤ 300ms после восстановления
- `llm_timeout_total` rate ≤ 3% после восстановления
- Время восстановления ≤ 5 минут

### 3. **LLM PERFORMANCE: P95 ≤ 1.5S, ERROR ≤ 3%, CACHE ≥ 30%**
**Было:** "p95 ≤ 200ms @ 100 RPS"
**Стало:** "p95 ≤ 1.5s при 32 параллельных, error rate ≤ 3%, cache hit ≥ 30%"

```bash
# Критерий прохождения:
make test-llm-stress
```

**Измеримые критерии:**
- LLM latency p95: ≤ 1500ms
- Success rate: ≥ 97% (error ≤ 3%)
- Cache hit rate: ≥ 30%
- Circuit breaker: должен срабатывать при 5+ ошибках подряд

---

## 🛠️ ФУНКЦИОНАЛЬНЫЕ ТРЕБОВАНИЯ

### **DSL Блоки (100% работоспособность)**
- ✅ `action.sql_query.v1` - SQL запросы с безопасностью
- ✅ `action.sql_exec.v1` - SQL выполнение с транзакциями
- ✅ `action.reply_template.v1` - Шаблонизация ответов
- ✅ `flow.wizard.v1` - Многошаговые диалоги
- ✅ `flow.menu.v1` - Интерактивные меню
- ✅ `widget.calendar.v1` - Календарные виджеты

### **API Endpoints (Детализированные Health Checks)**
```bash
GET /health        → {"ok": true}               # Общий статус
GET /health/pg     → {"pg_ok": true}           # PostgreSQL
GET /health/redis  → {"redis_ok": true}        # Redis
GET /health/llm    → {"llm_ok": true}          # LLM сервис
GET /health/db     → {"db_ok": true}           # Legacy поддержка
```

**Требования:**
- Все endpoints отвечают за ≤ 200ms
- Health checks возвращают корректные статус коды (200/503)
- При недоступности сервисов health checks не падают

---

## ⚡ ПРОИЗВОДИТЕЛЬНОСТЬ

### **Базовые Метрики**
- **DSL обработка:** p95 ≤ 300ms
- **Webhook latency:** p95 ≤ 200ms
- **SQL queries:** p95 ≤ 100ms
- **Memory usage:** ≤ 2GB под нагрузкой

### **LLM Производительность**
- **Latency:** p95 ≤ 1.5s, p99 ≤ 3s
- **Throughput:** 32 параллельных запроса успешно
- **Error rate:** ≤ 3% при нормальной работе
- **Cache hit rate:** ≥ 30% для повторных запросов
- **Timeout rate:** ≤ 3%

### **Circuit Breaker Работает**
- Открывается после 5 ошибок подряд
- Half-open через 30 секунд
- Закрывается после 2 успешных запросов
- Per-bot изоляция работает

---

## 🔍 OBSERVABILITY

### **Prometheus Метрики (40+ метрик доступны)**
**Критические для алертов:**
- `bot_errors_total{bot_id}` - ошибки по ботам
- `dsl_handle_latency_ms` - латентность обработки
- `llm_timeout_total{bot_id}` - таймауты LLM
- `circuit_breaker_state_changes_total` - состояния circuit breaker
- `llm_circuit_breaker_rejections_total` - отказы от circuit breaker

### **Алерты Настроены**
**Critical алерты (срабатывают немедленно):**
- Error rate > 1% за 5 минут
- Circuit breaker открылся
- LLM timeout rate > 3%

**Warning алерты (срабатывают через 3-5 минут):**
- DSL latency p95 > 300ms
- LLM latency p95 > 1.5s
- Cache hit rate < 30%

### **Логирование**
- Structured logs с уровнями (debug, info, warning, error)
- Отсутствие sensitive data в логах
- Request tracing по bot_id + user_id

---

## 🛡️ FAULT TOLERANCE

### **Infrastructure Resilience**
**PostgreSQL отказ:**
- Система gracefully отвечает 503 на /health/pg
- Основные endpoints не падают
- Recovery за ≤ 60 секунд после восстановления БД

**Redis отказ:**
- LLM кэш недоступен, но запросы идут напрямую
- Wizard state теряется gracefully
- Recovery за ≤ 30 секунд

**LLM сервис отказ:**
- Circuit breaker активируется за ≤ 30 секунд
- Fallback responses возвращаются пользователям
- Recovery за ≤ 2 минуты после восстановления

### **Chaos Engineering Ready**
```bash
# Все тесты должны проходить:
make test-chaos              # Полный набор
make test-chaos-postgres     # PostgreSQL down 30s
make test-chaos-redis        # Redis down 30s
make test-chaos-network      # Сетевые задержки
make test-chaos-full         # Множественные сбои
```

---

## 🚀 ДЕПЛОЙ READINESS

### **Staging Deployment (8.5/10)**
**Готово к staging при выполнении:**
- ✅ Функциональность: Все DSL работают
- ✅ Health checks: Детализированные endpoints
- ✅ Fault tolerance: Circuit breaker + chaos testing
- ✅ Observability: Метрики + алерты
- ⚠️ Performance: Нужна валидация под нагрузкой
- ❌ Unit tests: Нужно исправить mock'и

### **Production Deployment (требует 100%)**
**Дополнительно для продакшена:**
1. **Unit tests:** 0 xfail, все mock'и исправлены
2. **Load testing:** Валидация под реальной нагрузкой 1000+ RPS
3. **Security audit:** Penetration testing
4. **Runbooks:** Готовые инструкции для oncall
5. **Backup/restore:** Процедуры восстановления данных

---

## 📋 CHECKLIST ДЛЯ ТЕСТИРОВЩИКА

### **Быстрая проверка (5 минут):**
```bash
make dev                     # Запуск системы
./scripts/smoke-test.sh      # Smoke test
```

### **Полная валидация (30 минут):**
```bash
make test-unit              # Unit tests (должны быть 0 xfail)
make test-chaos             # Chaos engineering
make test-llm-stress        # LLM performance
make lint && make typecheck # Code quality
```

### **Production readiness (1 час):**
```bash
make test                   # Все тесты
# + Load testing
# + Security audit
# + Documentation review
```

---

## 🎯 КРИТЕРИИ УСПЕХА

**Staging Ready:** 4/6 критериев выполнены (текущий статус)
**Production Ready:** 6/6 критериев выполнены

**Система считается готовой к production при:**
- 0 падающих unit тестов
- Все chaos tests проходят с recovery ≤ 5 минут
- LLM performance соответствует SLA (p95 ≤ 1.5s, error ≤ 3%)
- Circuit breaker работает корректно
- Алерты настроены и не дают false positives
- Runbooks написаны для основных инцидентов

---

*Acceptance criteria v2.0 созданы с учётом реальных требований production-ready системы*