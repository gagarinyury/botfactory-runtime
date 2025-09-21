#!/bin/bash

# BotFactory Runtime Smoke Test
# Быстрая проверка основного функционала

set -e

BASE_URL="http://localhost:8000"
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

echo "🚀 BotFactory Runtime Smoke Test"
echo "================================="

# Function to test endpoint
test_endpoint() {
    local name="$1"
    local method="$2"
    local url="$3"
    local data="$4"
    local expected_status="$5"

    echo -n "Testing $name... "

    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "%{http_code}" -o /tmp/smoke_response "$url")
    else
        response=$(curl -s -w "%{http_code}" -o /tmp/smoke_response -X "$method" \
            -H "Content-Type: application/json" \
            -d "$data" "$url")
    fi

    if [ "$response" = "$expected_status" ]; then
        echo -e "${GREEN}✅ OK${NC} ($response)"
        return 0
    else
        echo -e "${RED}❌ FAIL${NC} (got $response, expected $expected_status)"
        echo "Response: $(cat /tmp/smoke_response)"
        return 1
    fi
}

# Test counter
total_tests=0
failed_tests=0

# 1. Health Checks
echo -e "\n${YELLOW}🏥 HEALTH CHECKS${NC}"
((total_tests++))
test_endpoint "Basic health" "GET" "$BASE_URL/health" "" "200" || ((failed_tests++))

((total_tests++))
test_endpoint "Database health" "GET" "$BASE_URL/health/db" "" "200" || ((failed_tests++))

((total_tests++))
test_endpoint "Metrics endpoint" "GET" "$BASE_URL/metrics" "" "200" || ((failed_tests++))

# 2. Preview API
echo -e "\n${YELLOW}⚡ PREVIEW API${NC}"
((total_tests++))
test_endpoint "Preview basic" "POST" "$BASE_URL/preview/send" \
    '{"bot_id": "test-bot", "text": "/start"}' "200" || ((failed_tests++))

((total_tests++))
test_endpoint "Preview nonexistent bot" "POST" "$BASE_URL/preview/send" \
    '{"bot_id": "nonexistent-bot-12345", "text": "/start"}' "200" || ((failed_tests++))

# 3. Telegram Webhook
echo -e "\n${YELLOW}🤖 TELEGRAM WEBHOOK${NC}"
((total_tests++))
telegram_payload='{
    "update_id": 123,
    "message": {
        "message_id": 456,
        "date": 1640995200,
        "text": "/start",
        "from": {"id": 789, "is_bot": false, "first_name": "SmokeTest"},
        "chat": {"id": 789, "type": "private"}
    }
}'
test_endpoint "Telegram webhook" "POST" "$BASE_URL/tg/smoke-test-bot" \
    "$telegram_payload" "200" || ((failed_tests++))

# 4. DSL Functions (if demo bot exists)
echo -e "\n${YELLOW}🎯 DSL FUNCTIONS${NC}"

# Try to find a demo bot
demo_bot_id="c3b88b65-623c-41b5-a3c9-8d56fcbc4413"  # From bench.sh

((total_tests++))
test_endpoint "Demo bot /start" "POST" "$BASE_URL/preview/send" \
    "{\"bot_id\": \"$demo_bot_id\", \"text\": \"/start\"}" "200" || ((failed_tests++))

((total_tests++))
test_endpoint "Demo bot SQL query" "POST" "$BASE_URL/preview/send" \
    "{\"bot_id\": \"$demo_bot_id\", \"text\": \"/my\"}" "200" || ((failed_tests++))

((total_tests++))
test_endpoint "Demo bot wizard start" "POST" "$BASE_URL/preview/send" \
    "{\"bot_id\": \"$demo_bot_id\", \"text\": \"/book\"}" "200" || ((failed_tests++))

# 5. Bot Management
echo -e "\n${YELLOW}🔄 BOT MANAGEMENT${NC}"
((total_tests++))
test_endpoint "Bot reload" "POST" "$BASE_URL/bots/$demo_bot_id/reload" "" "200" || ((failed_tests++))

# Summary
echo -e "\n${YELLOW}📊 SMOKE TEST SUMMARY${NC}"
echo "================================="
passed_tests=$((total_tests - failed_tests))
echo -e "Total tests: $total_tests"
echo -e "Passed: ${GREEN}$passed_tests${NC}"
echo -e "Failed: ${RED}$failed_tests${NC}"

if [ $failed_tests -eq 0 ]; then
    echo -e "\n${GREEN}🎉 ALL SMOKE TESTS PASSED!${NC}"
    echo "✅ System appears to be working correctly"
    exit 0
else
    echo -e "\n${RED}💥 SOME SMOKE TESTS FAILED!${NC}"
    echo "❌ System may have issues, check the output above"
    exit 1
fi