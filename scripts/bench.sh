#!/bin/bash

# Performance benchmark script for Bot Factory Runtime
# Tests /preview/send endpoint with configurable load

set -e

# Default configuration
ENDPOINT="http://localhost:8000/preview/send"
BOT_ID="c3b88b65-623c-41b5-a3c9-8d56fcbc4413"
REQUESTS=100
CONCURRENCY=10
TIMEOUT=30

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -r|--requests)
            REQUESTS="$2"
            shift 2
            ;;
        -c|--concurrency)
            CONCURRENCY="$2"
            shift 2
            ;;
        -u|--url)
            ENDPOINT="$2"
            shift 2
            ;;
        -b|--bot-id)
            BOT_ID="$2"
            shift 2
            ;;
        -t|--timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  -r, --requests NUM     Number of requests (default: 100)"
            echo "  -c, --concurrency NUM  Concurrent requests (default: 10)"
            echo "  -u, --url URL         Endpoint URL (default: http://localhost:8000/preview/send)"
            echo "  -b, --bot-id ID       Bot ID to test (default: c3b88b65-623c-41b5-a3c9-8d56fcbc4413)"
            echo "  -t, --timeout SEC     Request timeout (default: 30)"
            echo "  -h, --help           Show this help"
            echo ""
            echo "Examples:"
            echo "  $0                    # Run with defaults"
            echo "  $0 -r 200 -c 20      # 200 requests, 20 concurrent"
            echo "  $0 -u http://example.com/preview/send"
            exit 0
            ;;
        *)
            echo "Unknown option $1"
            exit 1
            ;;
    esac
done

echo "🚀 Bot Factory Runtime Performance Test"
echo "========================================"
echo "Endpoint: $ENDPOINT"
echo "Bot ID: $BOT_ID"
echo "Requests: $REQUESTS"
echo "Concurrency: $CONCURRENCY"
echo "Timeout: ${TIMEOUT}s"
echo ""

# Check if service is running
echo "🔍 Checking service availability..."
if ! curl -s --max-time 5 "http://localhost:8000/health" > /dev/null; then
    echo "❌ Service not available at http://localhost:8000"
    echo "Please ensure the service is running:"
    echo "  docker-compose up -d"
    exit 1
fi
echo "✅ Service is running"

# Create temporary files for test data
TEMP_DIR=$(mktemp -d)
JSON_FILE="$TEMP_DIR/request.json"
RESULTS_FILE="$TEMP_DIR/results.txt"

# Create test JSON payload
cat > "$JSON_FILE" << EOF
{
    "bot_id": "$BOT_ID",
    "text": "/start"
}
EOF

echo ""
echo "📊 Starting performance test..."
echo "Temporary files: $TEMP_DIR"

# Function to run tests with different tools
run_with_curl() {
    echo ""
    echo "🔧 Using curl for benchmarking..."

    start_time=$(date +%s.%N)

    # Run parallel curl requests
    for ((i=1; i<=REQUESTS; i++)); do
        (
            response=$(curl -s -w "@-" -X POST \
                --max-time "$TIMEOUT" \
                -H "Content-Type: application/json" \
                -d @"$JSON_FILE" \
                "$ENDPOINT" \
                --write-out "HTTPSTATUS:%{http_code};TIME_TOTAL:%{time_total};TIME_CONNECT:%{time_connect};TIME_APPCONNECT:%{time_appconnect};TIME_PRETRANSFER:%{time_pretransfer};TIME_STARTTRANSFER:%{time_starttransfer}" 2>/dev/null)

            echo "$response" >> "$RESULTS_FILE"
        ) &

        # Limit concurrency
        if (( i % CONCURRENCY == 0 )); then
            wait
        fi
    done

    # Wait for remaining jobs
    wait

    end_time=$(date +%s.%N)
    total_time=$(echo "$end_time - $start_time" | bc -l)

    # Parse results
    echo ""
    echo "📈 Results Analysis:"
    echo "==================="

    if [[ ! -f "$RESULTS_FILE" ]]; then
        echo "❌ No results file found"
        return 1
    fi

    # Count successful requests
    success_count=$(grep -c "HTTPSTATUS:200" "$RESULTS_FILE" 2>/dev/null || echo "0")
    total_requests=$(wc -l < "$RESULTS_FILE")

    echo "Total requests: $total_requests"
    echo "Successful requests: $success_count"
    echo "Failed requests: $((total_requests - success_count))"
    echo "Success rate: $(echo "scale=2; $success_count * 100 / $total_requests" | bc -l)%"
    echo "Total time: ${total_time}s"

    if [[ $success_count -gt 0 ]]; then
        # Extract timing data
        grep "HTTPSTATUS:200" "$RESULTS_FILE" | \
        sed 's/.*TIME_TOTAL:\([^;]*\).*/\1/' | \
        sort -n > "$TEMP_DIR/times.txt"

        # Calculate statistics
        times_count=$(wc -l < "$TEMP_DIR/times.txt")
        avg_time=$(awk '{sum+=$1} END {print sum/NR}' "$TEMP_DIR/times.txt")
        min_time=$(head -1 "$TEMP_DIR/times.txt")
        max_time=$(tail -1 "$TEMP_DIR/times.txt")

        # Calculate percentiles
        p50_line=$((times_count * 50 / 100))
        p95_line=$((times_count * 95 / 100))
        p99_line=$((times_count * 99 / 100))

        p50_time=$(sed -n "${p50_line}p" "$TEMP_DIR/times.txt")
        p95_time=$(sed -n "${p95_line}p" "$TEMP_DIR/times.txt")
        p99_time=$(sed -n "${p99_line}p" "$TEMP_DIR/times.txt")

        echo ""
        echo "⏱️  Response Times:"
        echo "Min: ${min_time}s"
        echo "Avg: $(printf "%.3f" "$avg_time")s"
        echo "Max: ${max_time}s"
        echo "p50: ${p50_time}s"
        echo "p95: ${p95_time}s"
        echo "p99: ${p99_time}s"

        # Convert to milliseconds for easier reading
        p95_ms=$(echo "$p95_time * 1000" | bc -l)
        echo ""
        echo "🎯 Key Metric:"
        echo "p95 latency: $(printf "%.0f" "$p95_ms")ms"

        # Check if p95 meets target (≤ 200ms)
        target_ms=200
        if (( $(echo "$p95_ms <= $target_ms" | bc -l) )); then
            echo "✅ p95 latency target met (≤ ${target_ms}ms)"
        else
            echo "❌ p95 latency target missed (> ${target_ms}ms)"
        fi

        # Calculate requests per second
        rps=$(echo "scale=2; $success_count / $total_time" | bc -l)
        echo ""
        echo "🚀 Throughput: ${rps} requests/second"
    fi
}

# Check for hey tool (better benchmarking tool)
if command -v hey >/dev/null 2>&1; then
    echo ""
    echo "🔧 Using 'hey' for benchmarking..."

    # Create a temporary script to use hey with POST data
    HEY_SCRIPT="$TEMP_DIR/hey_test.sh"
    cat > "$HEY_SCRIPT" << EOF
#!/bin/bash
hey -n $REQUESTS -c $CONCURRENCY -m POST -H "Content-Type: application/json" -d @"$JSON_FILE" "$ENDPOINT"
EOF
    chmod +x "$HEY_SCRIPT"

    "$HEY_SCRIPT"

elif command -v ab >/dev/null 2>&1; then
    echo ""
    echo "🔧 Using 'ab' for benchmarking..."
    ab -n "$REQUESTS" -c "$CONCURRENCY" -p "$JSON_FILE" -T "application/json" "$ENDPOINT"
else
    run_with_curl
fi

# Get current metrics
echo ""
echo "📊 Current Metrics:"
echo "=================="
if curl -s --max-time 5 "http://localhost:8000/metrics" | grep -E "(bot_updates_total|dsl_handle_latency)" | head -10; then
    echo ""
else
    echo "Could not fetch metrics"
fi

# Cleanup
echo ""
echo "🧹 Cleaning up..."
rm -rf "$TEMP_DIR"

echo ""
echo "✅ Benchmark completed!"
echo ""
echo "📋 Summary:"
echo "- Run 'docker-compose logs runtime' to check application logs"
echo "- Visit http://localhost:8000/metrics for detailed metrics"
echo "- Adjust -r and -c parameters for different load patterns"