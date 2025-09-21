#!/bin/bash
# Chaos testing PG outage and recovery

echo "🔥 Starting chaos testing - PG outage"
echo "Testing API responses during PG downtime..."

start_time=$(date +%s)

# Test during outage
for i in {1..10}; do
    echo "Test $i at $(date '+%H:%M:%S'):"

    response=$(curl -s -w "\nSTATUS:%{http_code}" \
        -H 'Content-Type: application/json' \
        -d '{"bot_id":"test","text":"/start"}' \
        http://localhost:8000/preview/send)

    status_code=$(echo "$response" | grep "STATUS:" | cut -d: -f2)
    body=$(echo "$response" | grep -v "STATUS:")

    echo "  Status: $status_code"
    echo "  Body: $body"

    # Check for 503 db_unavailable
    if [[ "$status_code" == "503" ]] && echo "$body" | grep -q "db_unavailable"; then
        echo "  ✅ Correct 503 db_unavailable response"
    else
        echo "  ❌ Unexpected response"
    fi

    sleep 2
done

echo ""
echo "🔄 Restarting PostgreSQL..."
docker compose start pg

echo "⏱️  Waiting for PG to be ready..."
sleep 10

echo ""
echo "🧪 Testing recovery..."

# Test recovery
recovery_start=$(date +%s)
for i in {1..15}; do
    echo "Recovery test $i at $(date '+%H:%M:%S'):"

    response=$(curl -s -w "\nSTATUS:%{http_code}" \
        -H 'Content-Type: application/json' \
        -d '{"bot_id":"test","text":"/start"}' \
        http://localhost:8000/preview/send)

    status_code=$(echo "$response" | grep "STATUS:" | cut -d: -f2)
    body=$(echo "$response" | grep -v "STATUS:")

    echo "  Status: $status_code"

    if [[ "$status_code" == "200" ]]; then
        recovery_end=$(date +%s)
        recovery_duration=$((recovery_end - recovery_start))
        echo "  ✅ Recovery successful after ${recovery_duration}s"

        if [[ $recovery_duration -le 300 ]]; then
            echo "  ✅ Recovery within 5 minutes criterion"
        else
            echo "  ❌ Recovery took longer than 5 minutes"
        fi
        break
    elif [[ "$status_code" == "503" ]]; then
        echo "  ⏳ Still recovering..."
    else
        echo "  ❓ Unexpected status: $status_code"
    fi

    sleep 10
done

echo ""
echo "📊 Chaos testing completed"

total_time=$(( $(date +%s) - start_time ))
echo "Total test duration: ${total_time}s"