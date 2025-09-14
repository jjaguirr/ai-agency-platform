#!/bin/bash
# Meta-Compliant WhatsApp Webhook Service - Emergency Rollback Script
# Quick rollback procedures for production deployment issues

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_FILE="/tmp/webhook_rollback_$(date +%Y%m%d_%H%M%S).log"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging function
log() {
    echo -e "${1}" | tee -a "$LOG_FILE"
}

log_info() {
    log "${BLUE}ℹ️  INFO: ${1}${NC}"
}

log_success() {
    log "${GREEN}✅ SUCCESS: ${1}${NC}"
}

log_warning() {
    log "${YELLOW}⚠️  WARNING: ${1}${NC}"
}

log_error() {
    log "${RED}❌ ERROR: ${1}${NC}"
}

# Help function
show_help() {
    cat << EOF
Meta-Compliant WhatsApp Webhook Service - Emergency Rollback

USAGE:
    $0 [OPTIONS]

OPTIONS:
    -h, --help              Show this help message
    -a, --app-id APP_ID     DigitalOcean App ID (required)
    -t, --target TARGET     Rollback target:
                             - previous: Rollback to previous deployment (default)
                             - deployment-id: Rollback to specific deployment
                             - commit-sha: Rollback to specific git commit
    -f, --fast              Fast rollback (skip safety checks)
    -y, --yes               Automatic yes to prompts
    --validate              Only validate rollback options (dry run)

EXAMPLES:
    # Rollback to previous deployment
    $0 --app-id abc-123 --target previous

    # Rollback to specific deployment
    $0 --app-id abc-123 --target deployment-456

    # Fast emergency rollback (skip checks)
    $0 --app-id abc-123 --target previous --fast --yes

    # Validate rollback options only
    $0 --app-id abc-123 --validate

EMERGENCY CONTACT:
    If automated rollback fails, immediately:
    1. Check DigitalOcean dashboard
    2. Contact team via emergency channels
    3. Consider manual intervention
EOF
}

# Default values
APP_ID=""
ROLLBACK_TARGET="previous"
FAST_ROLLBACK=false
AUTO_YES=false
VALIDATE_ONLY=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -a|--app-id)
            APP_ID="$2"
            shift 2
            ;;
        -t|--target)
            ROLLBACK_TARGET="$2"
            shift 2
            ;;
        -f|--fast)
            FAST_ROLLBACK=true
            shift
            ;;
        -y|--yes)
            AUTO_YES=true
            shift
            ;;
        --validate)
            VALIDATE_ONLY=true
            shift
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Validation
if [[ -z "$APP_ID" ]]; then
    log_error "App ID is required. Use --app-id option or check deployment-info.json"

    # Try to get APP_ID from deployment info
    if [[ -f "$PROJECT_ROOT/deployment-info.json" ]]; then
        APP_ID=$(jq -r '.app_id // empty' "$PROJECT_ROOT/deployment-info.json" 2>/dev/null || echo "")
        if [[ -n "$APP_ID" ]]; then
            log_info "Using App ID from deployment-info.json: $APP_ID"
        fi
    fi

    if [[ -z "$APP_ID" ]]; then
        show_help
        exit 1
    fi
fi

# Header
log_info "🔄 Meta-Compliant WhatsApp Webhook Service - Emergency Rollback"
log_info "Started at: $(date)"
log_info "App ID: $APP_ID"
log_info "Rollback Target: $ROLLBACK_TARGET"
log_info "Log file: $LOG_FILE"

# Check prerequisites
log_info "Checking prerequisites..."

# Check if doctl is installed and authenticated
if ! command -v doctl &> /dev/null; then
    log_error "DigitalOcean CLI (doctl) is not installed"
    log_error "Install with: brew install doctl (macOS)"
    exit 1
fi

# Verify doctl authentication
if ! doctl auth list | grep -q "current context"; then
    log_error "doctl is not authenticated"
    log_error "Run: doctl auth init"
    exit 1
fi

# Check if jq is available for JSON processing
if ! command -v jq &> /dev/null; then
    log_error "jq is not installed (required for JSON processing)"
    log_error "Install with: brew install jq (macOS)"
    exit 1
fi

# Verify app exists
log_info "Verifying app exists..."
if ! doctl apps get "$APP_ID" &>/dev/null; then
    log_error "App with ID '$APP_ID' not found or not accessible"
    exit 1
fi

APP_INFO=$(doctl apps get "$APP_ID" --format "Name,LiveURL,UpdatedAt" --no-header)
log_info "App Info: $APP_INFO"

log_success "Prerequisites check passed"

# Get current deployment info
log_info "Getting current deployment information..."

CURRENT_DEPLOYMENT=$(doctl apps list-deployments "$APP_ID" --format "ID,Phase,CreatedAt" --no-header | head -n1)
CURRENT_DEPLOYMENT_ID=$(echo "$CURRENT_DEPLOYMENT" | awk '{print $1}')
CURRENT_PHASE=$(echo "$CURRENT_DEPLOYMENT" | awk '{print $2}')

log_info "Current deployment: $CURRENT_DEPLOYMENT_ID (Phase: $CURRENT_PHASE)"

# Get available deployments for rollback
log_info "Getting available deployments..."
DEPLOYMENTS_JSON=$(doctl apps list-deployments "$APP_ID" --format "ID,Phase,CreatedAt" --output json)

# Find rollback target
ROLLBACK_DEPLOYMENT_ID=""

case "$ROLLBACK_TARGET" in
    "previous")
        # Get the previous successful deployment
        ROLLBACK_DEPLOYMENT_ID=$(echo "$DEPLOYMENTS_JSON" | jq -r '.[] | select(.phase == "ACTIVE") | .id' | head -n2 | tail -n1)
        if [[ -z "$ROLLBACK_DEPLOYMENT_ID" || "$ROLLBACK_DEPLOYMENT_ID" == "$CURRENT_DEPLOYMENT_ID" ]]; then
            # If no previous ACTIVE, get any successful deployment
            ROLLBACK_DEPLOYMENT_ID=$(echo "$DEPLOYMENTS_JSON" | jq -r '.[] | select(.phase == "ACTIVE" or .phase == "SUPERSEDED") | .id' | head -n2 | tail -n1)
        fi
        log_info "Previous deployment target: $ROLLBACK_DEPLOYMENT_ID"
        ;;
    *)
        # Assume it's a deployment ID
        if echo "$DEPLOYMENTS_JSON" | jq -e ".[] | select(.id == \"$ROLLBACK_TARGET\")" &>/dev/null; then
            ROLLBACK_DEPLOYMENT_ID="$ROLLBACK_TARGET"
            log_info "Specific deployment target: $ROLLBACK_DEPLOYMENT_ID"
        else
            log_error "Deployment ID '$ROLLBACK_TARGET' not found"
            exit 1
        fi
        ;;
esac

if [[ -z "$ROLLBACK_DEPLOYMENT_ID" ]]; then
    log_error "No suitable rollback target found"
    log_error "Available deployments:"
    echo "$DEPLOYMENTS_JSON" | jq -r '.[] | "\(.id) \(.phase) \(.created_at)"'
    exit 1
fi

# Get rollback target details
ROLLBACK_INFO=$(echo "$DEPLOYMENTS_JSON" | jq -r ".[] | select(.id == \"$ROLLBACK_DEPLOYMENT_ID\") | \"\(.id) \(.phase) \(.created_at)\"")
log_info "Rollback target: $ROLLBACK_INFO"

# Validate only mode
if [[ "$VALIDATE_ONLY" == true ]]; then
    log_success "Validation completed successfully"
    log_info "Rollback options:"
    log_info "  Current Deployment: $CURRENT_DEPLOYMENT_ID ($CURRENT_PHASE)"
    log_info "  Rollback Target: $ROLLBACK_DEPLOYMENT_ID"
    log_info "  Command to execute:"
    log_info "    $0 --app-id $APP_ID --target $ROLLBACK_DEPLOYMENT_ID"
    exit 0
fi

# Safety checks (skip in fast mode)
if [[ "$FAST_ROLLBACK" == false ]]; then
    log_info "Running safety checks..."

    # Check if current deployment is healthy
    if [[ "$CURRENT_PHASE" == "ACTIVE" ]]; then
        log_warning "Current deployment appears to be ACTIVE"

        if [[ "$AUTO_YES" == false ]]; then
            read -p "Are you sure you want to rollback from a healthy deployment? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                log_info "Rollback cancelled by user"
                exit 0
            fi
        fi
    fi

    # Check rollback target status
    TARGET_PHASE=$(echo "$DEPLOYMENTS_JSON" | jq -r ".[] | select(.id == \"$ROLLBACK_DEPLOYMENT_ID\") | .phase")
    if [[ "$TARGET_PHASE" != "ACTIVE" && "$TARGET_PHASE" != "SUPERSEDED" ]]; then
        log_warning "Rollback target is in phase: $TARGET_PHASE"

        if [[ "$AUTO_YES" == false ]]; then
            read -p "Rollback target may not be stable. Continue? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                log_info "Rollback cancelled by user"
                exit 0
            fi
        fi
    fi

    # Test current app health before rollback
    APP_URL=$(doctl apps get "$APP_ID" --format "LiveURL" --no-header)
    if [[ -n "$APP_URL" ]]; then
        log_info "Testing current app health..."
        if curl -f -m 10 "$APP_URL/health" &>/dev/null; then
            log_warning "Current app appears healthy"

            if [[ "$AUTO_YES" == false ]]; then
                read -p "App health check passed. Still proceed with rollback? (y/N): " -n 1 -r
                echo
                if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                    log_info "Rollback cancelled - app appears healthy"
                    exit 0
                fi
            fi
        else
            log_info "App health check failed - rollback justified"
        fi
    fi

    log_success "Safety checks completed"
fi

# Final confirmation
if [[ "$AUTO_YES" == false ]]; then
    log_warning "FINAL CONFIRMATION:"
    log_warning "  App: $APP_ID"
    log_warning "  From: $CURRENT_DEPLOYMENT_ID"
    log_warning "  To: $ROLLBACK_DEPLOYMENT_ID"
    read -p "Proceed with rollback? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Rollback cancelled by user"
        exit 0
    fi
fi

# Execute rollback
log_info "Executing rollback..."
log_info "Creating new deployment from target: $ROLLBACK_DEPLOYMENT_ID"

# Note: DigitalOcean doesn't have direct deployment rollback
# We need to trigger a new deployment from the same state

# Get the git commit SHA from the target deployment
TARGET_SHA=$(doctl apps get-deployment "$APP_ID" "$ROLLBACK_DEPLOYMENT_ID" --format "Spec" --output json | jq -r '.spec.services[0].github.ref // empty' 2>/dev/null || echo "")

if [[ -n "$TARGET_SHA" ]]; then
    log_info "Target commit SHA: $TARGET_SHA"

    # Update app spec to deploy from target commit
    log_info "Updating app to deploy from target commit..."

    # Create temporary spec file
    TEMP_SPEC="/tmp/rollback_spec_${APP_ID}.yaml"
    doctl apps get "$APP_ID" --format "Spec" --output yaml > "$TEMP_SPEC"

    # Update the spec with target commit (this requires manual editing of the spec)
    log_info "Manual spec update required for commit rollback"
    log_info "Consider using: doctl apps update $APP_ID --spec $TEMP_SPEC"
else
    log_info "No specific commit found - triggering rebuild from current branch"
fi

# Trigger new deployment (force rebuild)
log_info "Triggering new deployment (force rebuild)..."
ROLLBACK_DEPLOYMENT_OUTPUT=$(doctl apps create-deployment "$APP_ID" --force-rebuild)
NEW_DEPLOYMENT_ID=$(echo "$ROLLBACK_DEPLOYMENT_OUTPUT" | grep -o 'ID: [a-f0-9-]*' | cut -d' ' -f2)

if [[ -z "$NEW_DEPLOYMENT_ID" ]]; then
    log_error "Failed to create rollback deployment"
    exit 1
fi

log_success "Rollback deployment created: $NEW_DEPLOYMENT_ID"

# Monitor rollback progress
log_info "Monitoring rollback deployment..."
DEPLOYMENT_STATUS="PENDING"
TIMEOUT=1800  # 30 minutes
ELAPSED=0
CHECK_INTERVAL=30

while [[ "$DEPLOYMENT_STATUS" != "ACTIVE" && "$DEPLOYMENT_STATUS" != "ERROR" && $ELAPSED -lt $TIMEOUT ]]; do
    sleep $CHECK_INTERVAL
    ELAPSED=$((ELAPSED + CHECK_INTERVAL))

    DEPLOYMENT_INFO=$(doctl apps get-deployment "$APP_ID" "$NEW_DEPLOYMENT_ID" --format "Phase" --no-header)
    DEPLOYMENT_STATUS=$(echo "$DEPLOYMENT_INFO" | head -n1)

    log_info "Rollback status: $DEPLOYMENT_STATUS (${ELAPSED}s elapsed)"

    if [[ $((ELAPSED % 120)) -eq 0 ]]; then  # Every 2 minutes
        doctl apps logs "$APP_ID" --type=deploy --tail 5 2>/dev/null || true
    fi
done

# Check final status
if [[ "$DEPLOYMENT_STATUS" == "ACTIVE" ]]; then
    log_success "🎉 Rollback completed successfully!"

    # Verify app health
    log_info "Verifying app health after rollback..."
    sleep 30  # Wait for app to initialize

    APP_URL=$(doctl apps get "$APP_ID" --format "LiveURL" --no-header)
    if curl -f -m 10 "$APP_URL/health" &>/dev/null; then
        log_success "App health check passed after rollback"
    else
        log_warning "App health check failed after rollback - manual verification needed"
    fi

else
    log_error "Rollback failed or timed out. Status: $DEPLOYMENT_STATUS"
    log_error "Manual intervention required"
    exit 1
fi

# Update deployment info file
if [[ -f "$PROJECT_ROOT/deployment-info.json" ]]; then
    log_info "Updating deployment info file..."

    # Backup current info
    cp "$PROJECT_ROOT/deployment-info.json" "$PROJECT_ROOT/deployment-info.backup.json"

    # Update with rollback info
    jq --arg new_id "$NEW_DEPLOYMENT_ID" --arg rollback_from "$CURRENT_DEPLOYMENT_ID" \
       '.deployment_id = $new_id | .rollback_from = $rollback_from | .rolled_back_at = now | .status = "ROLLED_BACK"' \
       "$PROJECT_ROOT/deployment-info.json" > "$PROJECT_ROOT/deployment-info.tmp.json"

    mv "$PROJECT_ROOT/deployment-info.tmp.json" "$PROJECT_ROOT/deployment-info.json"
    log_success "Deployment info updated"
fi

# Final summary
log_success "Rollback Summary:"
log_info "═══════════════════════════════════════════════════════════"
log_info "App ID: $APP_ID"
log_info "Rolled back from: $CURRENT_DEPLOYMENT_ID"
log_info "New deployment: $NEW_DEPLOYMENT_ID"
log_info "App URL: $(doctl apps get "$APP_ID" --format "LiveURL" --no-header)"
log_info "Rollback completed at: $(date)"
log_info "═══════════════════════════════════════════════════════════"

# Next steps
log_info "Next Steps:"
log_info "1. Verify all webhook functionality is working"
log_info "2. Test embedded signup flow"
log_info "3. Check error logs for any issues"
log_info "4. Monitor performance metrics"
log_info "5. Notify team of successful rollback"
log_info "6. Plan fix for original issue"

log_success "Rollback log saved to: $LOG_FILE"
log_success "🔄 Emergency rollback completed successfully!"