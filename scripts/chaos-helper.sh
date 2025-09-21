#!/bin/bash
# Chaos testing helper for BotFactory Runtime
# Provides reliable service disruption and recovery testing

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${BLUE}[$(date +'%H:%M:%S')]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

# Check if service is running
check_service() {
    local service=$1
    docker compose ps "$service" --format "table {{.State}}" | grep -q "running"
}

# Wait for service to be healthy
wait_for_health() {
    local service=$1
    local max_wait=${2:-30}
    local counter=0

    log "Waiting for $service to become healthy (max ${max_wait}s)..."

    while [ $counter -lt $max_wait ]; do
        if check_service "$service"; then
            success "$service is healthy"
            return 0
        fi
        sleep 1
        counter=$((counter + 1))
        echo -n "."
    done

    error "$service failed to become healthy within ${max_wait}s"
    return 1
}

# Test PostgreSQL chaos
test_postgres_chaos() {
    local down_time=${1:-30}

    log "🔥 POSTGRES CHAOS TEST - DOWN FOR ${down_time}s"

    # Record baseline metrics
    log "Recording baseline metrics..."
    curl -s http://localhost:8000/health/pg > /dev/null || warn "PG health check failed before test"

    # Stop PostgreSQL
    log "Stopping PostgreSQL..."
    docker compose stop pg

    # Verify it's down
    sleep 2
    if curl -s http://localhost:8000/health/pg | grep -q '"pg_ok": false'; then
        success "PostgreSQL confirmed down"
    else
        error "PostgreSQL health check should fail"
    fi

    # Wait for specified time
    log "Waiting ${down_time}s with PostgreSQL down..."
    sleep "$down_time"

    # Restart PostgreSQL
    log "Restarting PostgreSQL..."
    docker compose start pg

    # Wait for recovery
    local recovery_start=$(date +%s)
    wait_for_health pg 60
    local recovery_end=$(date +%s)
    local recovery_time=$((recovery_end - recovery_start))

    # Test health endpoint
    if curl -s http://localhost:8000/health/pg | grep -q '"pg_ok": true'; then
        success "PostgreSQL chaos test completed - recovery time: ${recovery_time}s"
        return 0
    else
        error "PostgreSQL failed to recover properly"
        return 1
    fi
}

# Test Redis chaos
test_redis_chaos() {
    local down_time=${1:-30}

    log "🔥 REDIS CHAOS TEST - DOWN FOR ${down_time}s"

    # Record baseline
    curl -s http://localhost:8000/health/redis > /dev/null || warn "Redis health check failed before test"

    # Stop Redis
    log "Stopping Redis..."
    docker compose stop redis

    # Verify it's down
    sleep 2
    if curl -s http://localhost:8000/health/redis | grep -q '"redis_ok": false'; then
        success "Redis confirmed down"
    else
        error "Redis health check should fail"
    fi

    # Wait for specified time
    log "Waiting ${down_time}s with Redis down..."
    sleep "$down_time"

    # Restart Redis
    log "Restarting Redis..."
    docker compose start redis

    # Wait for recovery
    local recovery_start=$(date +%s)
    wait_for_health redis 30
    local recovery_end=$(date +%s)
    local recovery_time=$((recovery_end - recovery_start))

    # Test health endpoint
    if curl -s http://localhost:8000/health/redis | grep -q '"redis_ok": true'; then
        success "Redis chaos test completed - recovery time: ${recovery_time}s"
        return 0
    else
        error "Redis failed to recover properly"
        return 1
    fi
}

# Test network chaos using tc (traffic control)
test_network_chaos() {
    local service=${1:-runtime}
    local latency=${2:-100ms}
    local duration=${3:-30}

    log "🔥 NETWORK CHAOS TEST - Adding ${latency} latency for ${duration}s"

    # Get container ID
    local container_id=$(docker compose ps -q "$service")
    if [ -z "$container_id" ]; then
        error "Container $service not found"
        return 1
    fi

    # Add network latency
    log "Adding network latency to $service..."
    docker exec "$container_id" tc qdisc add dev eth0 root netem delay "$latency" 2>/dev/null || {
        warn "Failed to add latency (tc might not be available)"
        return 0
    }

    # Test with latency
    log "Testing with ${latency} latency..."
    local start_time=$(date +%s%3N)
    curl -s http://localhost:8000/health > /dev/null
    local end_time=$(date +%s%3N)
    local response_time=$((end_time - start_time))

    log "Response time with latency: ${response_time}ms"

    # Wait
    sleep "$duration"

    # Remove latency
    log "Removing network latency..."
    docker exec "$container_id" tc qdisc del dev eth0 root 2>/dev/null || warn "Failed to remove latency"

    success "Network chaos test completed"
}

# Test full chaos scenario
test_full_chaos() {
    log "🌪️  FULL CHAOS TEST - Multiple service failures"

    # Test both services down simultaneously
    log "Taking down both PostgreSQL and Redis..."
    docker compose stop pg redis

    sleep 5

    # Verify both are down
    local pg_down=$(curl -s http://localhost:8000/health/pg | grep -c '"pg_ok": false' || echo 0)
    local redis_down=$(curl -s http://localhost:8000/health/redis | grep -c '"redis_ok": false' || echo 0)

    if [ "$pg_down" -eq 1 ] && [ "$redis_down" -eq 1 ]; then
        success "Both services confirmed down"
    else
        error "Service health checks not behaving as expected"
    fi

    # Wait 30 seconds
    log "Waiting 30s with both services down..."
    sleep 30

    # Restart both
    log "Restarting both services..."
    docker compose start pg redis

    # Wait for recovery
    local recovery_start=$(date +%s)
    wait_for_health pg 60
    wait_for_health redis 30
    local recovery_end=$(date +%s)
    local total_recovery=$((recovery_end - recovery_start))

    # Final health check
    if curl -s http://localhost:8000/health | grep -q '"ok": true'; then
        success "Full chaos test completed - total recovery time: ${total_recovery}s"
        return 0
    else
        error "System failed to recover from full chaos"
        return 1
    fi
}

# Connection leak test
test_connection_leaks() {
    log "🔍 CONNECTION LEAK TEST"

    # Get initial connection counts
    local initial_pg_conns=$(docker compose exec -T pg psql -U dev -d botfactory -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='botfactory';" 2>/dev/null | tr -d ' ' || echo "0")

    log "Initial PG connections: $initial_pg_conns"

    # Run chaos test
    test_postgres_chaos 10

    # Wait for stabilization
    sleep 10

    # Check final connection count
    local final_pg_conns=$(docker compose exec -T pg psql -U dev -d botfactory -t -c "SELECT count(*) FROM pg_stat_activity WHERE datname='botfactory';" 2>/dev/null | tr -d ' ' || echo "0")

    log "Final PG connections: $final_pg_conns"

    # Check for leaks (allow some variance)
    local diff=$((final_pg_conns - initial_pg_conns))
    if [ "$diff" -le 2 ]; then
        success "No significant connection leaks detected (diff: $diff)"
        return 0
    else
        error "Possible connection leak detected (diff: $diff)"
        return 1
    fi
}

# Print usage
usage() {
    echo "Chaos Testing Helper for BotFactory Runtime"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  postgres [down_time]     Test PostgreSQL failure and recovery (default: 30s)"
    echo "  redis [down_time]        Test Redis failure and recovery (default: 30s)"
    echo "  network [latency] [duration] Test network latency (default: 100ms, 30s)"
    echo "  full                     Test multiple service failures"
    echo "  leaks                    Test for connection leaks after chaos"
    echo "  all                      Run all chaos tests sequentially"
    echo ""
    echo "Examples:"
    echo "  $0 postgres 60          # PostgreSQL down for 60 seconds"
    echo "  $0 redis 30             # Redis down for 30 seconds"
    echo "  $0 network 200ms 45     # Add 200ms latency for 45 seconds"
    echo "  $0 all                  # Run complete chaos test suite"
}

# Main execution
main() {
    cd "$PROJECT_DIR"

    case "${1:-}" in
        postgres)
            test_postgres_chaos "${2:-30}"
            ;;
        redis)
            test_redis_chaos "${2:-30}"
            ;;
        network)
            test_network_chaos "runtime" "${2:-100ms}" "${3:-30}"
            ;;
        full)
            test_full_chaos
            ;;
        leaks)
            test_connection_leaks
            ;;
        all)
            log "🌪️  RUNNING COMPLETE CHAOS TEST SUITE"
            test_redis_chaos 15
            sleep 5
            test_postgres_chaos 15
            sleep 5
            test_network_chaos "runtime" "50ms" 15
            sleep 5
            test_connection_leaks
            sleep 5
            test_full_chaos
            success "🎉 All chaos tests completed!"
            ;;
        -h|--help|help)
            usage
            ;;
        *)
            error "Unknown command: ${1:-}"
            usage
            exit 1
            ;;
    esac
}

main "$@"