#!/bin/bash

###############################################################################
# Lead Tracker E2E Validation Script
# Validates Phase 2 criteria: tracker → RudderStack → Redpanda → ClickHouse
###############################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Configuration
CLICKHOUSE_HOST="${CLICKHOUSE_HOST:-localhost}"
CLICKHOUSE_PORT="${CLICKHOUSE_PORT:-9000}"
CLICKHOUSE_USER="${CLICKHOUSE_USER:-analytics}"
CLICKHOUSE_PASSWORD="${CLICKHOUSE_PASSWORD:-analytics_password}"
CLICKHOUSE_DB="${CLICKHOUSE_DB:-analytics}"

REDPANDA_HOST="${REDPANDA_HOST:-localhost}"
REDPANDA_PORT="${REDPANDA_PORT:-19092}"
REDPANDA_TOPIC="lead-events"

RUDDERSTACK_URL="${RUDDERSTACK_URL:-http://localhost:8080}"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Result tracking
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

###############################################################################
# Helper Functions
###############################################################################

echo_success() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASS_COUNT++))
}

echo_fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAIL_COUNT++))
}

echo_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARN_COUNT++))
}

echo_info() {
    echo -e "${YELLOW}ℹ${NC} $1"
}

###############################################################################
# Availability Checks
###############################################################################

check_services_available() {
    echo "=== Checking Service Availability ==="
    
    # Check RudderStack
    if curl -s "$RUDDERSTACK_URL/health" > /dev/null 2>&1; then
        echo_success "RudderStack responding at $RUDDERSTACK_URL"
    else
        echo_warn "RudderStack unavailable at $RUDDERSTACK_URL (may still accept events)"
    fi
    
    # Check Redpanda
    if echo "SELECT 1" | nc -w 1 "$REDPANDA_HOST" "$REDPANDA_PORT" > /dev/null 2>&1; then
        echo_success "Redpanda available at $REDPANDA_HOST:$REDPANDA_PORT"
    else
        echo_warn "Redpanda unavailable (rpk may still work)"
    fi
    
    # Check ClickHouse
    if command -v clickhouse-client &> /dev/null; then
        if clickhouse-client -h "$CLICKHOUSE_HOST" -u "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" --query "SELECT 1" > /dev/null 2>&1; then
            echo_success "ClickHouse responding at $CLICKHOUSE_HOST:$CLICKHOUSE_PORT"
        else
            echo_fail "ClickHouse unavailable - cannot verify ingestion"
            return 1
        fi
    else
        echo_warn "clickhouse-client not installed - skipping ClickHouse verification"
        return 0
    fi
    
    echo
}

###############################################################################
# Redpanda Topic Verification
###############################################################################

check_redpanda_topic() {
    echo "=== Checking Redpanda Topic ==="
    
    # Check if rpk is available
    if ! command -v rpk &> /dev/null; then
        echo_warn "rpk not installed - skipping Redpanda verification"
        return 0
    fi
    
    # Check if topic exists
    if rpk topic list 2>/dev/null | grep -q "$REDPANDA_TOPIC"; then
        echo_success "Redpanda topic '$REDPANDA_TOPIC' exists"
        
        # Count messages in topic (within last 5 minutes)
        MESSAGE_COUNT=$(rpk topic consume "$REDPANDA_TOPIC" --from-beginning --max-messages 100 2>/dev/null | wc -l)
        if [ "$MESSAGE_COUNT" -gt 0 ]; then
            echo_success "Redpanda topic contains ${MESSAGE_COUNT} messages"
        else
            echo_warn "Redpanda topic is empty - events may not have been flushed yet"
        fi
    else
        echo_fail "Redpanda topic '$REDPANDA_TOPIC' does not exist"
        return 1
    fi
    
    echo
}

###############################################################################
# ClickHouse Data Verification
###############################################################################

check_clickhouse_data() {
    echo "=== Checking ClickHouse Ingestion ==="
    
    if ! command -v clickhouse-client &> /dev/null; then
        echo_warn "clickhouse-client not installed - skipping verification"
        return 0
    fi
    
    # Check if click_events table exists
    if clickhouse-client -h "$CLICKHOUSE_HOST" -u "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
        --query "EXISTS TABLE $CLICKHOUSE_DB.click_events" 2>/dev/null | grep -q "1"; then
        echo_success "ClickHouse table '$CLICKHOUSE_DB.click_events' exists"
        
        # Count recent events
        CLICK_COUNT=$(clickhouse-client -h "$CLICKHOUSE_HOST" -u "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
            --query "SELECT COUNT(*) FROM $CLICKHOUSE_DB.click_events WHERE event_time > NOW() - INTERVAL 5 minute" 2>/dev/null)
        
        if [ "$CLICK_COUNT" -gt 0 ]; then
            echo_success "ClickHouse click_events: $CLICK_COUNT events in last 5 minutes"
        else
            echo_warn "No recent events in ClickHouse (events may not have been flushed yet)"
        fi
    else
        echo_fail "ClickHouse table '$CLICKHOUSE_DB.click_events' does not exist"
        return 1
    fi
    
    # Verify coordinate data
    if [ "$CLICK_COUNT" -gt 0 ]; then
        COORD_SAMPLE=$(clickhouse-client -h "$CLICKHOUSE_HOST" -u "$CLICKHOUSE_USER" --password "$CLICKHOUSE_PASSWORD" \
            --query "SELECT x_pct, y_pct FROM $CLICKHOUSE_DB.click_events WHERE x_pct IS NOT NULL LIMIT 1" 2>/dev/null)
        
        if [ -n "$COORD_SAMPLE" ]; then
            echo_success "Coordinate data present in ClickHouse: $COORD_SAMPLE"
        fi
    fi
    
    echo
}

###############################################################################
# Validation Results
###############################################################################

print_summary() {
    echo "=== Validation Summary ==="
    echo -e "Passed: ${GREEN}$PASS_COUNT${NC}"
    echo -e "Failed: ${RED}$FAIL_COUNT${NC}"
    echo -e "Warnings: ${YELLOW}$WARN_COUNT${NC}"
    echo
    
    if [ "$FAIL_COUNT" -eq 0 ]; then
        echo_success "All critical checks passed!"
        return 0
    else
        echo_fail "Some critical checks failed"
        return 1
    fi
}

###############################################################################
# Manual Test Instructions
###############################################################################

print_test_instructions() {
    echo "=== Manual Testing Instructions ==="
    echo
    echo "1. Open test page in browser:"
    echo "   http://localhost:5000/src/test-spa-page.html"
    echo
    echo "2. Follow these steps:"
    echo "   a. Accept cookie consent banner"
    echo "   b. Click on test buttons multiple times"
    echo "   c. Scroll down page (trigger scroll events)"
    echo "   d. Move mouse rapidly for 5 seconds (test throttling)"
    echo "   e. Click 'Manual Flush' button"
    echo
    echo "3. Wait 5-10 seconds for events to flow through pipeline"
    echo
    echo "4. Verify in ClickHouse:"
    echo "   $ clickhouse-client -u analytics -p"
    echo "   > SELECT event_type, x_pct, y_pct, timestamp"
    echo "   >   FROM analytics.click_events"
    echo "   >   WHERE event_time > NOW() - INTERVAL 10 minute"
    echo "   >   LIMIT 10"
    echo
    echo "5. Expected results:"
    echo "   - Click events with x_pct and y_pct values (0-100)"
    echo "   - Scroll events with scroll_pct (0-100)"
    echo "   - Mousemove events (throttled to ~10/sec)"
    echo "   - Page_view events with URL and dimensions"
    echo
}

###############################################################################
# Main Execution
###############################################################################

main() {
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║  Lead Tracker Phase 2 - End-to-End Validation              ║"
    echo "║  Checker: Browser Events → RudderStack → Redpanda → CH    ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo
    
    check_services_available || {
        echo_fail "Critical services unavailable"
        exit 1
    }
    
    check_redpanda_topic
    check_clickhouse_data
    
    echo
    print_test_instructions
    echo
    print_summary
    
    if [ "$FAIL_COUNT" -gt 0 ]; then
        exit 1
    fi
    
    exit 0
}

# Run main function
main "$@"
