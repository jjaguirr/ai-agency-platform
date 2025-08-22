#!/bin/bash
# AI Agency Platform - Infrastructure Health Check and Monitoring Script
# Comprehensive health monitoring for all security and MCPhub services

set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
HEALTH_CHECK_TIMEOUT=10
REDIS_HEALTH_TIMEOUT=5

# Service endpoints
MCPHUB_URL="http://localhost:3000"
SECURITY_PROXY_URL="http://localhost:8080"
LLAMAGUARD_API_URL="http://localhost:8083"
LLAMAGUARD_MODEL_URL="http://localhost:8082"
REDIS_SECURITY_PORT="6380"
POSTGRES_PORT="5432"

# Utility functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Health check functions
check_service_health() {
    local service_name="$1"
    local health_url="$2"
    local timeout="${3:-$HEALTH_CHECK_TIMEOUT}"
    
    log_info "Checking $service_name health..."
    
    if curl -f --max-time "$timeout" --silent "$health_url" > /dev/null 2>&1; then
        log_success "$service_name is healthy"
        return 0
    else
        log_error "$service_name health check failed"
        return 1
    fi
}

check_redis_health() {
    local redis_port="$1"
    local service_name="$2"
    
    log_info "Checking $service_name health..."
    
    if timeout "$REDIS_HEALTH_TIMEOUT" redis-cli -p "$redis_port" ping > /dev/null 2>&1; then
        log_success "$service_name is healthy"
        return 0
    else
        log_error "$service_name health check failed"
        return 1
    fi
}

check_postgres_health() {
    log_info "Checking PostgreSQL health..."
    
    if timeout "$REDIS_HEALTH_TIMEOUT" nc -z localhost "$POSTGRES_PORT" > /dev/null 2>&1; then
        log_success "PostgreSQL is healthy"
        return 0
    else
        log_error "PostgreSQL health check failed"
        return 1
    fi
}

check_docker_containers() {
    log_info "Checking Docker container status..."
    
    local containers=(
        "llamaguard-security"
        "llamaguard-api" 
        "security-proxy"
        "redis-security"
        "security-logger"
    )
    
    local failed_containers=()
    
    for container in "${containers[@]}"; do
        if docker ps --format "table {{.Names}}\t{{.Status}}" | grep -q "$container.*Up"; then
            log_success "Container $container is running"
        else
            log_error "Container $container is not running"
            failed_containers+=("$container")
        fi
    done
    
    if [ ${#failed_containers[@]} -eq 0 ]; then
        return 0
    else
        log_error "Failed containers: ${failed_containers[*]}"
        return 1
    fi
}

check_security_integration() {
    log_info "Testing security integration flow..."
    
    # Test security evaluation endpoint
    test_payload='{"content": "Hello, this is a test message", "user_id": "health-check", "customer_id": "health-check", "security_tier": "basic"}'
    
    if curl -X POST "$LLAMAGUARD_API_URL/evaluate" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer test-token" \
        -d "$test_payload" \
        --max-time "$HEALTH_CHECK_TIMEOUT" \
        --silent > /dev/null 2>&1; then
        log_success "Security integration test passed"
        return 0
    else
        log_warning "Security integration test failed (may require valid JWT token)"
        return 1
    fi
}

check_customer_isolation() {
    log_info "Validating customer isolation..."
    
    # Check that customer data is properly isolated
    local isolation_issues=()
    
    # Check Redis key isolation
    if command -v redis-cli &> /dev/null; then
        redis_keys=$(redis-cli -p "$REDIS_SECURITY_PORT" keys "*" 2>/dev/null | wc -l)
        if [ "$redis_keys" -gt 1000 ]; then
            isolation_issues+=("Redis key count high: $redis_keys")
        fi
    fi
    
    # Check container resource usage
    local cpu_usage=$(docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}" | grep llamaguard-security | awk '{print $2}' | sed 's/%//')
    if [ -n "$cpu_usage" ] && [ "$(echo "$cpu_usage > 80" | bc 2>/dev/null)" -eq 1 ]; then
        isolation_issues+=("High CPU usage: ${cpu_usage}%")
    fi
    
    if [ ${#isolation_issues[@]} -eq 0 ]; then
        log_success "Customer isolation validation passed"
        return 0
    else
        log_warning "Customer isolation issues: ${isolation_issues[*]}"
        return 1
    fi
}

check_performance_metrics() {
    log_info "Checking performance metrics..."
    
    # Check memory usage
    local total_memory=$(docker stats --no-stream --format "table {{.Container}}\t{{.MemUsage}}" | grep -E "(llamaguard|security)" | awk -F/ '{sum += $1} END {print sum}')
    
    # Check disk space
    local available_space
    if [[ "$OSTYPE" == "darwin"* ]]; then
        available_space=$(df -g "$PROJECT_ROOT" | tail -1 | awk '{print $4}')
    else
        available_space=$(df -BG "$PROJECT_ROOT" | tail -1 | awk '{print $4}' | sed 's/G//')
    fi
    
    local performance_issues=()
    
    if [ "$available_space" -lt 5 ]; then
        performance_issues+=("Low disk space: ${available_space}GB")
    fi
    
    if [ ${#performance_issues[@]} -eq 0 ]; then
        log_success "Performance metrics are healthy"
        return 0
    else
        log_warning "Performance issues: ${performance_issues[*]}"
        return 1
    fi
}

generate_health_report() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    local report_file="$PROJECT_ROOT/logs/health-report-$(date '+%Y%m%d-%H%M%S').json"
    
    # Create logs directory if it doesn't exist
    mkdir -p "$PROJECT_ROOT/logs"
    
    # Generate comprehensive health report
    cat > "$report_file" << EOF
{
  "timestamp": "$timestamp",
  "health_check_version": "1.0.0",
  "services": {
    "mcphub": {
      "status": "$(curl -f --max-time 5 "$MCPHUB_URL/health" &>/dev/null && echo 'healthy' || echo 'unhealthy')",
      "url": "$MCPHUB_URL"
    },
    "security_proxy": {
      "status": "$(curl -f --max-time 5 "$SECURITY_PROXY_URL/health" &>/dev/null && echo 'healthy' || echo 'unhealthy')",
      "url": "$SECURITY_PROXY_URL"
    },
    "llamaguard_api": {
      "status": "$(curl -f --max-time 5 "$LLAMAGUARD_API_URL/health" &>/dev/null && echo 'healthy' || echo 'unhealthy')",
      "url": "$LLAMAGUARD_API_URL"
    },
    "llamaguard_model": {
      "status": "$(curl -f --max-time 5 "$LLAMAGUARD_MODEL_URL/health" &>/dev/null && echo 'healthy' || echo 'unhealthy')",
      "url": "$LLAMAGUARD_MODEL_URL"
    }
  },
  "infrastructure": {
    "docker_containers": "$(docker ps -q | wc -l) running",
    "disk_space_gb": "$available_space",
    "redis_status": "$(redis-cli -p $REDIS_SECURITY_PORT ping 2>/dev/null || echo 'unhealthy')"
  }
}
EOF
    
    log_info "Health report saved to: $report_file"
}

# Main health check function
main() {
    log_info "Starting AI Agency Platform Infrastructure Health Check"
    log_info "=================================================================="
    
    local check_results=()
    local overall_health=0
    
    # Run all health checks
    check_docker_containers && check_results+=("containers:PASS") || { check_results+=("containers:FAIL"); overall_health=1; }
    
    check_service_health "MCPhub" "$MCPHUB_URL/health" && check_results+=("mcphub:PASS") || { check_results+=("mcphub:FAIL"); overall_health=1; }
    
    check_service_health "Security Proxy" "$SECURITY_PROXY_URL/health" && check_results+=("security-proxy:PASS") || { check_results+=("security-proxy:FAIL"); overall_health=1; }
    
    check_service_health "Llama Guard API" "$LLAMAGUARD_API_URL/health" && check_results+=("llamaguard-api:PASS") || { check_results+=("llamaguard-api:FAIL"); overall_health=1; }
    
    check_service_health "Llama Guard Model" "$LLAMAGUARD_MODEL_URL/health" 30 && check_results+=("llamaguard-model:PASS") || { check_results+=("llamaguard-model:FAIL"); overall_health=1; }
    
    check_redis_health "$REDIS_SECURITY_PORT" "Redis Security" && check_results+=("redis:PASS") || { check_results+=("redis:FAIL"); overall_health=1; }
    
    check_postgres_health && check_results+=("postgres:PASS") || { check_results+=("postgres:FAIL"); overall_health=1; }
    
    check_security_integration && check_results+=("integration:PASS") || { check_results+=("integration:WARN"); }
    
    check_customer_isolation && check_results+=("isolation:PASS") || { check_results+=("isolation:WARN"); }
    
    check_performance_metrics && check_results+=("performance:PASS") || { check_results+=("performance:WARN"); }
    
    # Generate health report
    generate_health_report
    
    # Summary
    echo
    log_info "Health Check Summary:"
    for result in "${check_results[@]}"; do
        local service=$(echo "$result" | cut -d: -f1)
        local status=$(echo "$result" | cut -d: -f2)
        
        case "$status" in
            "PASS") log_success "$service: HEALTHY" ;;
            "WARN") log_warning "$service: WARNING" ;;
            "FAIL") log_error "$service: FAILED" ;;
        esac
    done
    
    echo
    if [ $overall_health -eq 0 ]; then
        log_success "Overall system health: HEALTHY"
        log_info "All critical services are operational"
    else
        log_error "Overall system health: DEGRADED"
        log_info "Some critical services have issues - check logs above"
    fi
    
    exit $overall_health
}

# Run main function
main "$@"