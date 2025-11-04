#!/bin/bash

# AI Agency Platform - Deployment Configuration Validation Script
# Validates that all deployment configurations are properly integrated and consistent

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Validation counters
TOTAL_CHECKS=0
PASSED_CHECKS=0
FAILED_CHECKS=0

# Logging functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $*"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $*"
    ((PASSED_CHECKS++))
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $*"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $*"
    ((FAILED_CHECKS++))
}

# Validation functions
validate_file_exists() {
    local file="$1"
    local description="$2"

    ((TOTAL_CHECKS++))
    if [[ -f "$file" ]]; then
        log_success "$description exists: $file"
        return 0
    else
        log_error "$description missing: $file"
        return 1
    fi
}

validate_directory_exists() {
    local dir="$1"
    local description="$2"

    ((TOTAL_CHECKS++))
    if [[ -d "$dir" ]]; then
        log_success "$description exists: $dir"
        return 0
    else
        log_error "$description missing: $dir"
        return 1
    fi
}

validate_environment_file() {
    local file="$1"
    local environment="$2"

    ((TOTAL_CHECKS++))
    if [[ -f "$file" ]]; then
        # Check for required Vault configuration
        if grep -q "VAULT_ADDR" "$file" && grep -q "VAULT_SECRET_PATH" "$file"; then
            log_success "$environment environment configuration is valid"
            return 0
        else
            log_error "$environment environment missing Vault configuration"
            return 1
        fi
    else
        log_error "$environment environment file not found"
        return 1
    fi
}

validate_docker_compose() {
    local file="$1"

    ((TOTAL_CHECKS++))
    if [[ -f "$file" ]]; then
        # Check for required services
        local required_services=("postgres" "redis" "qdrant" "neo4j" "mcp-server" "prometheus" "grafana")
        local missing_services=()

        for service in "${required_services[@]}"; do
            if ! grep -q "services:" -A 100 "$file" | grep -q "^  $service:"; then
                missing_services+=("$service")
            fi
        done

        if [[ ${#missing_services[@]} -eq 0 ]]; then
            log_success "Docker Compose configuration includes all required services"
            return 0
        else
            log_error "Docker Compose missing services: ${missing_services[*]}"
            return 1
        fi
    else
        log_error "Docker Compose file not found"
        return 1
    fi
}

validate_kubernetes_manifests() {
    local dir="$1"

    ((TOTAL_CHECKS++))
    if [[ -d "$dir" ]]; then
        # Check for required manifest files
        local required_files=("ai-agency-application.yaml" "monitoring-stack.yaml" "security-vault.yaml")
        local missing_files=()

        for file in "${required_files[@]}"; do
            if [[ ! -f "$dir/$file" ]]; then
                missing_files+=("$file")
            fi
        done

        if [[ ${#missing_files[@]} -eq 0 ]]; then
            log_success "Kubernetes manifests are complete"
            return 0
        else
            log_error "Missing Kubernetes manifests: ${missing_files[*]}"
            return 1
        fi
    else
        log_error "Kubernetes directory not found"
        return 1
    fi
}

validate_terraform_files() {
    local dir="$1"

    ((TOTAL_CHECKS++))
    if [[ -d "$dir" ]]; then
        # Check for required Terraform files
        local required_files=("main.tf" "variables.tf")
        local missing_files=()

        for file in "${required_files[@]}"; do
            if [[ ! -f "$dir/$file" ]]; then
                missing_files+=("$file")
            fi
        done

        if [[ ${#missing_files[@]} -eq 0 ]]; then
            log_success "Terraform configuration is complete"
            return 0
        else
            log_error "Missing Terraform files: ${missing_files[*]}"
            return 1
        fi
    else
        log_error "Terraform directory not found"
        return 1
    fi
}

validate_security_policies() {
    local file="$1"

    ((TOTAL_CHECKS++))
    if [[ -f "$file" ]]; then
        # Check for required security sections
        if grep -q "authentication" "$file" && grep -q "authorization" "$file" && grep -q "dataProtection" "$file"; then
            log_success "Security policies configuration is valid"
            return 0
        else
            log_error "Security policies missing required sections"
            return 1
        fi
    else
        log_error "Security policies file not found"
        return 1
    fi
}

validate_vault_policies() {
    local file="$1"

    ((TOTAL_CHECKS++))
    if [[ -f "$file" ]]; then
        # Check for required Vault policy sections
        if grep -q "ai-agency/production" "$file" && grep -q "customer/production" "$file"; then
            log_success "Vault policies configuration is valid"
            return 0
        else
            log_error "Vault policies missing required sections"
            return 1
        fi
    else
        log_error "Vault policies file not found"
        return 1
    fi
}

validate_configuration_consistency() {
    ((TOTAL_CHECKS++))

    # Check that port ranges don't overlap between environments
    local dev_ports=$(grep "MCP_PORT=" deploy/config/development.env | cut -d'=' -f2)
    local staging_ports=$(grep "MCP_PORT=" deploy/config/staging.env | cut -d'=' -f2)
    local prod_ports=$(grep "MCP_PORT=" deploy/config/production.env | cut -d'=' -f2)

    if [[ "$dev_ports" != "$staging_ports" && "$staging_ports" != "$prod_ports" && "$dev_ports" != "$prod_ports" ]]; then
        log_success "Port configurations are consistent across environments"
        return 0
    else
        log_error "Port configurations overlap between environments"
        return 1
    fi
}

validate_dependencies() {
    ((TOTAL_CHECKS++))

    # Check if required external tools are available
    local required_tools=("docker" "kubectl" "terraform" "vault" "aws")
    local missing_tools=()

    for tool in "${required_tools[@]}"; do
        if ! command -v "$tool" &> /dev/null; then
            missing_tools+=("$tool")
        fi
    done

    if [[ ${#missing_tools[@]} -eq 0 ]]; then
        log_success "All required dependencies are installed"
        return 0
    else
        log_warning "Missing dependencies (may be optional): ${missing_tools[*]}"
        return 0
    fi
}

print_summary() {
    echo
    echo "=========================================="
    echo "        VALIDATION SUMMARY"
    echo "=========================================="
    echo "Total Checks: $TOTAL_CHECKS"
    echo "Passed: $PASSED_CHECKS"
    echo "Failed: $FAILED_CHECKS"
    echo "Success Rate: $(( (PASSED_CHECKS * 100) / TOTAL_CHECKS ))%"
    echo "=========================================="

    if [[ $FAILED_CHECKS -eq 0 ]]; then
        log_success "All validation checks passed!"
        return 0
    else
        log_error "$FAILED_CHECKS validation check(s) failed!"
        return 1
    fi
}

main() {
    log_info "Starting deployment configuration validation..."

    # Change to project root
    cd "$PROJECT_ROOT"

    # Core structure validation
    validate_directory_exists "deploy" "Deploy directory"
    validate_directory_exists "deploy/config" "Configuration directory"
    validate_directory_exists "deploy/kubernetes" "Kubernetes directory"
    validate_directory_exists "deploy/terraform" "Terraform directory"

    # Environment configuration validation
    validate_environment_file "deploy/config/production.env" "Production"
    validate_environment_file "deploy/config/staging.env" "Staging"
    validate_environment_file "deploy/config/development.env" "Development"

    # Docker Compose validation
    validate_docker_compose "docker-compose.production.yml"

    # Kubernetes validation
    validate_kubernetes_manifests "deploy/kubernetes/production"

    # Terraform validation
    validate_terraform_files "deploy/terraform"

    # Security validation
    validate_security_policies "deploy/config/security-policies.json"
    validate_vault_policies "deploy/config/vault-policies.hcl"

    # Integration validation
    validate_configuration_consistency
    validate_dependencies

    # Print summary
    print_summary
}

# Run validation if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi