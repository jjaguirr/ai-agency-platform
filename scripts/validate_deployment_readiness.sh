#!/bin/bash
# Meta-Compliant WhatsApp Webhook Service - Deployment Readiness Validation
# Comprehensive pre-deployment validation script

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# Counters
CHECKS_TOTAL=0
CHECKS_PASSED=0
CHECKS_FAILED=0
CHECKS_WARNING=0

# Test results storage
RESULTS=()

# Logging functions
log_header() {
    echo -e "\n${BOLD}${BLUE}═══ ${1} ═══${NC}"
}

log_check() {
    echo -e "${BLUE}▶ ${1}${NC}"
    CHECKS_TOTAL=$((CHECKS_TOTAL + 1))
}

log_pass() {
    echo -e "  ${GREEN}✅ ${1}${NC}"
    CHECKS_PASSED=$((CHECKS_PASSED + 1))
    RESULTS+=("✅ $1")
}

log_fail() {
    echo -e "  ${RED}❌ ${1}${NC}"
    CHECKS_FAILED=$((CHECKS_FAILED + 1))
    RESULTS+=("❌ $1")
}

log_warning() {
    echo -e "  ${YELLOW}⚠️  ${1}${NC}"
    CHECKS_WARNING=$((CHECKS_WARNING + 1))
    RESULTS+=("⚠️  $1")
}

log_info() {
    echo -e "  ${BLUE}ℹ️  ${1}${NC}"
}

# Validation functions
check_file_exists() {
    local file_path="$1"
    local description="$2"

    log_check "Checking $description"

    if [[ -f "$file_path" ]]; then
        log_pass "$description exists"
        return 0
    else
        log_fail "$description missing: $file_path"
        return 1
    fi
}

check_environment_variable() {
    local var_name="$1"
    local min_length="$2"
    local file_path="$3"

    if grep -q "^${var_name}=" "$file_path"; then
        local value=$(grep "^${var_name}=" "$file_path" | cut -d'=' -f2- | tr -d '"' | tr -d "'")

        if [[ -n "$value" && "$value" != "your-"* ]]; then
            if [[ ${#value} -ge $min_length ]]; then
                log_pass "$var_name configured (${#value} chars)"
                return 0
            else
                log_fail "$var_name too short (${#value} chars, minimum: $min_length)"
                return 1
            fi
        else
            log_fail "$var_name not configured or using template value"
            return 1
        fi
    else
        log_fail "$var_name not found in environment file"
        return 1
    fi
}

check_command_available() {
    local cmd="$1"
    local description="$2"

    log_check "Checking $description"

    if command -v "$cmd" &> /dev/null; then
        local version=$($cmd --version 2>&1 | head -n1 || echo "Unknown version")
        log_pass "$description available: $version"
        return 0
    else
        log_fail "$description not available"
        return 1
    fi
}

check_python_dependencies() {
    local requirements_file="$1"

    log_check "Checking Python dependencies in $requirements_file"

    if [[ ! -f "$requirements_file" ]]; then
        log_fail "Requirements file not found: $requirements_file"
        return 1
    fi

    local missing_deps=()
    while IFS= read -r line; do
        # Skip comments and empty lines
        [[ "$line" =~ ^#.*$ ]] && continue
        [[ -z "$line" ]] && continue

        # Extract package name
        local package=$(echo "$line" | cut -d'>' -f1 | cut -d'=' -f1 | cut -d'[' -f1)

        if ! python -c "import $package" &>/dev/null 2>&1; then
            missing_deps+=("$package")
        fi
    done < "$requirements_file"

    if [[ ${#missing_deps[@]} -eq 0 ]]; then
        log_pass "All Python dependencies available"
        return 0
    else
        log_fail "Missing Python dependencies: ${missing_deps[*]}"
        log_info "Run: pip install -r $requirements_file"
        return 1
    fi
}

check_docker_build() {
    local dockerfile="$1"

    log_check "Testing Docker build with $dockerfile"

    if ! command -v docker &> /dev/null; then
        log_warning "Docker not available - skipping build test"
        return 0
    fi

    if docker build -f "$dockerfile" -t webhook-validation:test . &>/dev/null; then
        log_pass "Docker build successful"
        # Cleanup
        docker rmi webhook-validation:test &>/dev/null || true
        return 0
    else
        log_fail "Docker build failed"
        return 1
    fi
}

check_security_configuration() {
    local env_file="$1"

    log_check "Validating security configuration"

    # Check if production mode enables security
    if grep -q "^PRODUCTION_MODE=true" "$env_file"; then
        log_pass "Production mode enabled"
    else
        log_warning "Production mode not enabled"
    fi

    # Check security features
    local security_checks=0
    local security_passed=0

    # IP allowlist
    security_checks=$((security_checks + 1))
    if grep -q "^ENABLE_IP_ALLOWLIST=true" "$env_file"; then
        security_passed=$((security_passed + 1))
    fi

    # Webhook signature enforcement
    security_checks=$((security_checks + 1))
    if grep -q "^ENFORCE_WEBHOOK_SECRET=true" "$env_file"; then
        security_passed=$((security_passed + 1))
    fi

    # HTTPS enforcement
    security_checks=$((security_checks + 1))
    if grep -q "^SECURE_COOKIES=true" "$env_file"; then
        security_passed=$((security_passed + 1))
    fi

    if [[ $security_passed -eq $security_checks ]]; then
        log_pass "Security features properly configured"
        return 0
    else
        log_warning "Some security features not enabled ($security_passed/$security_checks)"
        return 1
    fi
}

check_meta_configuration() {
    local env_file="$1"

    log_check "Validating Meta configuration"

    local meta_vars=("META_APP_ID" "META_APP_SECRET" "WHATSAPP_BUSINESS_TOKEN" "WHATSAPP_VERIFY_TOKEN")
    local configured_count=0

    for var in "${meta_vars[@]}"; do
        if check_environment_variable "$var" 10 "$env_file" &>/dev/null; then
            configured_count=$((configured_count + 1))
        fi
    done

    if [[ $configured_count -eq ${#meta_vars[@]} ]]; then
        log_pass "Meta configuration complete"
        return 0
    else
        log_fail "Meta configuration incomplete ($configured_count/${#meta_vars[@]} variables)"
        return 1
    fi
}

check_deployment_files() {
    log_header "DEPLOYMENT FILES VALIDATION"

    # Essential deployment files
    check_file_exists "$PROJECT_ROOT/.do/app-production.yaml" "DigitalOcean production app configuration"
    check_file_exists "$PROJECT_ROOT/.env.production.webhook" "Production environment configuration"
    check_file_exists "$PROJECT_ROOT/requirements-webhook.txt" "Webhook requirements file"
    check_file_exists "$PROJECT_ROOT/src/webhook/Dockerfile.production" "Production Dockerfile"
    check_file_exists "$PROJECT_ROOT/scripts/deploy_production_webhook.sh" "Deployment script"
    check_file_exists "$PROJECT_ROOT/scripts/rollback_webhook_deployment.sh" "Rollback script"

    # Documentation files
    check_file_exists "$PROJECT_ROOT/docs/META_DEVELOPER_SETUP_GUIDE.md" "Meta setup guide"
    check_file_exists "$PROJECT_ROOT/docs/PRODUCTION_DEPLOYMENT_GUIDE.md" "Production deployment guide"

    # Source files
    check_file_exists "$PROJECT_ROOT/src/webhook/whatsapp_webhook_service.py" "Main webhook service"
    check_file_exists "$PROJECT_ROOT/src/webhook/meta_business_api.py" "Meta Business API integration"
    check_file_exists "$PROJECT_ROOT/src/webhook/production_monitoring.py" "Production monitoring"
    check_file_exists "$PROJECT_ROOT/src/webhook/security_config.py" "Security configuration"
    check_file_exists "$PROJECT_ROOT/src/webhook/templates/embedded_signup.html" "Embedded signup template"
}

check_environment_configuration() {
    log_header "ENVIRONMENT CONFIGURATION VALIDATION"

    local env_file="$PROJECT_ROOT/.env.production.webhook"

    if [[ ! -f "$env_file" ]]; then
        log_fail "Production environment file not found"
        log_info "Copy from template: cp .env.production.template .env.production.webhook"
        return 1
    fi

    # Critical environment variables
    check_environment_variable "META_APP_ID" 10 "$env_file"
    check_environment_variable "META_APP_SECRET" 32 "$env_file"
    check_environment_variable "WHATSAPP_BUSINESS_TOKEN" 50 "$env_file"
    check_environment_variable "WHATSAPP_VERIFY_TOKEN" 20 "$env_file"
    check_environment_variable "ENCRYPTION_KEY" 32 "$env_file"
    check_environment_variable "WHATSAPP_WEBHOOK_SECRET" 32 "$env_file"

    # Optional but recommended
    check_environment_variable "REDIS_URL" 10 "$env_file"
    check_environment_variable "EMBEDDED_SIGNUP_CONFIG_ID" 10 "$env_file"

    # Security configuration
    check_security_configuration "$env_file"

    # Meta-specific configuration
    check_meta_configuration "$env_file"
}

check_system_dependencies() {
    log_header "SYSTEM DEPENDENCIES VALIDATION"

    # Required command-line tools
    check_command_available "doctl" "DigitalOcean CLI"
    check_command_available "python3" "Python 3"
    check_command_available "pip" "Python package manager"
    check_command_available "git" "Git version control"
    check_command_available "curl" "HTTP client"
    check_command_available "jq" "JSON processor"

    # Optional but useful
    if command -v docker &> /dev/null; then
        log_pass "Docker available"
    else
        log_warning "Docker not available (optional for local testing)"
    fi

    # Check doctl authentication
    log_check "DigitalOcean CLI authentication"
    if doctl auth list | grep -q "current context"; then
        log_pass "DigitalOcean CLI authenticated"
    else
        log_fail "DigitalOcean CLI not authenticated"
        log_info "Run: doctl auth init"
    fi

    # Check Python version
    log_check "Python version compatibility"
    if python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" &>/dev/null; then
        local py_version=$(python3 --version)
        log_pass "Python version compatible: $py_version"
    else
        log_fail "Python 3.11+ required"
    fi
}

check_python_environment() {
    log_header "PYTHON ENVIRONMENT VALIDATION"

    # Check if we're in a virtual environment
    log_check "Virtual environment"
    if [[ -n "${VIRTUAL_ENV:-}" ]]; then
        log_pass "Running in virtual environment: $VIRTUAL_ENV"
    else
        log_warning "Not in virtual environment (recommended for testing)"
    fi

    # Check webhook dependencies
    if [[ -f "$PROJECT_ROOT/requirements-webhook.txt" ]]; then
        log_check "Webhook dependencies"
        # Create temporary venv for testing
        if python3 -m venv /tmp/webhook_test_env &>/dev/null; then
            source /tmp/webhook_test_env/bin/activate

            if pip install -q -r "$PROJECT_ROOT/requirements-webhook.txt" &>/dev/null; then
                log_pass "Webhook dependencies installable"
            else
                log_fail "Failed to install webhook dependencies"
            fi

            deactivate
            rm -rf /tmp/webhook_test_env
        else
            log_warning "Could not create test virtual environment"
        fi
    fi

    # Test basic imports
    log_check "Core Python imports"
    if python3 -c "
import flask, redis, aiohttp, requests, cryptography
print('Core imports successful')
" &>/dev/null; then
        log_pass "Core Python imports working"
    else
        log_fail "Core Python imports failed"
    fi
}

check_docker_setup() {
    log_header "DOCKER CONFIGURATION VALIDATION"

    if [[ -f "$PROJECT_ROOT/src/webhook/Dockerfile.production" ]]; then
        check_docker_build "$PROJECT_ROOT/src/webhook/Dockerfile.production"
    fi

    # Check if production requirements exist
    if [[ -f "$PROJECT_ROOT/requirements-production.txt" ]]; then
        log_pass "Production requirements file exists"
    else
        log_warning "Production requirements file not found (will fallback to webhook requirements)"
    fi
}

check_git_status() {
    log_header "GIT REPOSITORY VALIDATION"

    log_check "Git repository status"
    if git status &>/dev/null; then
        log_pass "In git repository"

        # Check current branch
        local current_branch=$(git branch --show-current)
        log_info "Current branch: $current_branch"

        if [[ "$current_branch" == "main" || "$current_branch" == "production" ]]; then
            log_pass "On production-suitable branch"
        else
            log_warning "Not on main or production branch"
        fi

        # Check if there are uncommitted changes
        if git diff --quiet && git diff --cached --quiet; then
            log_pass "No uncommitted changes"
        else
            log_warning "Uncommitted changes present"
            log_info "Consider committing changes before deployment"
        fi

        return 0
    else
        log_fail "Not in git repository"
        return 1
    fi
}

check_network_connectivity() {
    log_header "NETWORK CONNECTIVITY VALIDATION"

    # Test connectivity to essential services
    local services=(
        "https://graph.facebook.com:443"
        "https://api.digitalocean.com:443"
        "https://registry.hub.docker.com:443"
    )

    for service in "${services[@]}"; do
        local host=$(echo "$service" | cut -d'/' -f3 | cut -d':' -f1)
        local port=$(echo "$service" | cut -d':' -f3)

        log_check "Connectivity to $host:$port"

        if timeout 10 bash -c "</dev/tcp/$host/$port" &>/dev/null; then
            log_pass "Can connect to $host:$port"
        else
            log_fail "Cannot connect to $host:$port"
            log_info "Check firewall and network settings"
        fi
    done

    # Test DNS resolution
    log_check "DNS resolution"
    if nslookup graph.facebook.com &>/dev/null; then
        log_pass "DNS resolution working"
    else
        log_fail "DNS resolution issues"
    fi
}

generate_summary_report() {
    log_header "VALIDATION SUMMARY REPORT"

    echo -e "${BOLD}Deployment Readiness Validation Complete${NC}"
    echo -e "Date: $(date)"
    echo -e "Project: AI Agency Platform - WhatsApp Webhook Service\n"

    # Statistics
    echo -e "${BOLD}Statistics:${NC}"
    echo -e "  Total Checks: $CHECKS_TOTAL"
    echo -e "  ${GREEN}Passed: $CHECKS_PASSED${NC}"
    echo -e "  ${RED}Failed: $CHECKS_FAILED${NC}"
    echo -e "  ${YELLOW}Warnings: $CHECKS_WARNING${NC}"
    echo

    # Overall status
    if [[ $CHECKS_FAILED -eq 0 ]]; then
        echo -e "${GREEN}${BOLD}✅ READY FOR PRODUCTION DEPLOYMENT${NC}"
        echo -e "All critical checks passed. You may proceed with deployment."
    else
        echo -e "${RED}${BOLD}❌ NOT READY FOR DEPLOYMENT${NC}"
        echo -e "Critical issues must be resolved before deployment."
    fi

    if [[ $CHECKS_WARNING -gt 0 ]]; then
        echo -e "${YELLOW}${BOLD}⚠️  WARNINGS PRESENT${NC}"
        echo -e "Review warnings and consider addressing them."
    fi

    echo
    echo -e "${BOLD}Next Steps:${NC}"

    if [[ $CHECKS_FAILED -eq 0 ]]; then
        echo -e "  1. Review any warnings above"
        echo -e "  2. Run deployment script: ./scripts/deploy_production_webhook.sh"
        echo -e "  3. Monitor deployment progress"
        echo -e "  4. Validate post-deployment functionality"
    else
        echo -e "  1. Fix all failed checks listed above"
        echo -e "  2. Re-run this validation script"
        echo -e "  3. Proceed with deployment when all checks pass"
    fi

    echo
    echo -e "${BOLD}Resources:${NC}"
    echo -e "  • Production Guide: docs/PRODUCTION_DEPLOYMENT_GUIDE.md"
    echo -e "  • Meta Setup Guide: docs/META_DEVELOPER_SETUP_GUIDE.md"
    echo -e "  • Deployment Script: scripts/deploy_production_webhook.sh"
    echo -e "  • Rollback Script: scripts/rollback_webhook_deployment.sh"

    # Return appropriate exit code
    if [[ $CHECKS_FAILED -eq 0 ]]; then
        return 0
    else
        return 1
    fi
}

# Main execution
main() {
    echo -e "${BOLD}${BLUE}"
    cat << 'EOF'
╔═══════════════════════════════════════════════════════════════╗
║           Meta-Compliant WhatsApp Webhook Service            ║
║              Deployment Readiness Validation                 ║
╚═══════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"

    cd "$PROJECT_ROOT"

    # Run all validation checks
    check_deployment_files
    check_system_dependencies
    check_environment_configuration
    check_python_environment
    check_docker_setup
    check_git_status
    check_network_connectivity

    # Generate final report
    generate_summary_report
}

# Execute main function
main "$@"