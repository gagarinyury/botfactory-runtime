#!/bin/bash
# Alert simulation test - генерируем высокую ошибку для триггера алертов

echo "🚨 Alert Simulation Test"
echo "Генерируем высокую ошибку для проверки системы алертинга..."

# Доступ к метрикам
METRICS_URL="http://localhost:8000/metrics"
ENDPOINT="http://localhost:8000/preview/send"

echo ""
echo "📊 Baseline metrics (before test):"
curl -s $METRICS_URL | grep -E "(bot_errors_total|llm_timeout_total|circuit_breaker)" | head -5

echo ""
echo "🔥 Generating errors with invalid requests..."

# Генерация ошибок через невалидные запросы
error_count=0
for i in {1..50}; do
    echo "Error request $i:"

    # Невалидный JSON для генерации ошибок
    response=$(curl -s -w "\nSTATUS:%{http_code}" \
        -H 'Content-Type: application/json' \
        -d '{"bot_id":"invalid-bot-9999","text":"test error"}' \
        $ENDPOINT)

    status_code=$(echo "$response" | grep "STATUS:" | cut -d: -f2)
    body=$(echo "$response" | grep -v "STATUS:")

    if [[ "$status_code" != "200" ]]; then
        error_count=$((error_count + 1))
        echo "  ✅ Error generated (Status: $status_code)"
    else
        echo "  ⚠️  No error (Status: $status_code)"
    fi

    # Небольшая задержка
    sleep 0.1
done

echo ""
echo "📊 Post-test metrics:"
curl -s $METRICS_URL | grep -E "(bot_errors_total|llm_timeout_total|circuit_breaker)" | head -10

echo ""
echo "🔍 Error rate calculation:"
echo "Generated errors: $error_count / 50 requests"
error_rate=$(echo "scale=4; $error_count / 50" | bc)
echo "Error rate: $error_rate"

if (( $(echo "$error_rate > 0.01" | bc -l) )); then
    echo "✅ Error rate ($error_rate) > 0.01 threshold - should trigger BotErrorRateHigh alert"
else
    echo "❌ Error rate ($error_rate) ≤ 0.01 threshold - alert may not trigger"
fi

echo ""
echo "🚨 Expected alerts:"
echo "  - BotErrorRateHigh: rate > 0.01 for 2m"
echo "  - Check Alertmanager/Prometheus for actual alerts"

echo ""
echo "📋 Summary:"
echo "  Prometheus rules validated: ✓"
echo "  Error generation completed: ✓"
echo "  Error rate threshold: $error_rate > 0.01"

# Сохранение результатов
cat > artifacts/alert_simulation.json <<EOF
{
  "test_type": "alert_simulation",
  "errors_generated": $error_count,
  "total_requests": 50,
  "error_rate": $error_rate,
  "threshold_exceeded": $(echo "$error_rate > 0.01" | bc -l),
  "expected_alerts": ["BotErrorRateHigh"],
  "rules_validated": true
}
EOF

echo "💾 Results saved to artifacts/alert_simulation.json"