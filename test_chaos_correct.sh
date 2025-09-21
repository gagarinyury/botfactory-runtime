#!/bin/bash
# Правильный chaos тест для PG с фактическими DB endpoints

echo "🔥 Chaos Testing - PostgreSQL outage and recovery"
echo "Тестируем /health/db endpoint (который обязательно использует БД)"

start_time=$(date +%s)
outage_detected=false

# Test during outage
echo "📊 Testing during PG outage..."
for i in {1..15}; do
    echo "Test $i at $(date '+%H:%M:%S'):"

    response=$(curl -s -w "\nSTATUS:%{http_code}" http://localhost:8000/health/db)
    status_code=$(echo "$response" | grep "STATUS:" | cut -d: -f2)
    body=$(echo "$response" | grep -v "STATUS:")

    echo "  Status: $status_code"
    echo "  Body: $body"

    if [[ "$status_code" == "503" ]] && echo "$body" | grep -q "db_ok.*false"; then
        echo "  ✅ Correct 503 db_unavailable response"
        outage_detected=true
    else
        echo "  ❌ Unexpected response (expected 503 with db_ok: false)"
    fi

    sleep 3
done

if [ "$outage_detected" = false ]; then
    echo "❌ FAIL - No proper 503 responses detected during outage"
    exit 1
fi

echo ""
echo "🔄 Restarting PostgreSQL..."
docker compose start pg

echo "⏱️  Waiting for PG initialization..."
sleep 15

echo ""
echo "🧪 Testing recovery - measuring recovery time..."

# Test recovery
recovery_start=$(date +%s)
recovery_success=false

for i in {1..20}; do
    echo "Recovery test $i at $(date '+%H:%M:%S'):"

    response=$(curl -s -w "\nSTATUS:%{http_code}" http://localhost:8000/health/db)
    status_code=$(echo "$response" | grep "STATUS:" | cut -d: -f2)
    body=$(echo "$response" | grep -v "STATUS:")

    echo "  Status: $status_code"
    echo "  Body: $body"

    if [[ "$status_code" == "200" ]] && echo "$body" | grep -q "db_ok.*true"; then
        recovery_end=$(date +%s)
        recovery_duration=$((recovery_end - recovery_start))
        echo "  ✅ Recovery successful after ${recovery_duration}s"

        if [[ $recovery_duration -le 300 ]]; then
            echo "  ✅ Recovery within 5 minutes criterion (${recovery_duration}s ≤ 300s)"
            recovery_success=true
        else
            echo "  ❌ Recovery took longer than 5 minutes (${recovery_duration}s > 300s)"
        fi
        break
    elif [[ "$status_code" == "503" ]]; then
        echo "  ⏳ Still recovering... (DB not ready)"
    else
        echo "  ❓ Unexpected status: $status_code"
    fi

    sleep 15
done

total_time=$(( $(date +%s) - start_time ))

echo ""
echo "📊 Chaos Testing Results:"
echo "  Outage detected: $outage_detected"
echo "  Recovery successful: $recovery_success"
echo "  Total test duration: ${total_time}s"

if [ "$outage_detected" = true ] && [ "$recovery_success" = true ]; then
    echo "✅ PASS - Chaos test completed successfully"
    echo "  - 503 db_unavailable during outage: ✓"
    echo "  - Recovery within 5 minutes: ✓"

    # Record metrics for verification
    echo "{
  \"chaos_test\": \"postgresql\",
  \"outage_detected\": $outage_detected,
  \"recovery_successful\": $recovery_success,
  \"recovery_duration_seconds\": $((recovery_end - recovery_start)),
  \"total_duration_seconds\": $total_time,
  \"criterion_met\": true
}" > artifacts/chaos_test_results.json

    exit 0
else
    echo "❌ FAIL - Chaos test failed"

    echo "{
  \"chaos_test\": \"postgresql\",
  \"outage_detected\": $outage_detected,
  \"recovery_successful\": $recovery_success,
  \"total_duration_seconds\": $total_time,
  \"criterion_met\": false
}" > artifacts/chaos_test_results.json

    exit 1
fi