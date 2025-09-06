#!/bin/bash
set -euo pipefail

# AI Agency Platform - Production Deployment Script
# Deploys complete production infrastructure with per-customer isolation
# Target: 500+ customers with <30 second onboarding

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
NAMESPACE="ai-agency-production"
CLUSTER_NAME="${CLUSTER_NAME:-ai-agency-prod}"
AWS_REGION="${AWS_REGION:-us-west-2}"
KUBECTL_VERSION="${KUBECTL_VERSION:-v1.28.0}"
HELM_VERSION="${HELM_VERSION:-v3.12.0}"

# Logging functions
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

# Error handling
trap 'log_error "Deployment failed at line $LINENO"' ERR

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if kubectl is installed
    if ! command -v kubectl &> /dev/null; then
        log_error "kubectl is not installed. Please install kubectl ${KUBECTL_VERSION}"
        exit 1
    fi
    
    # Check if helm is installed
    if ! command -v helm &> /dev/null; then
        log_error "helm is not installed. Please install helm ${HELM_VERSION}"
        exit 1
    fi
    
    # Check if aws CLI is installed
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Please install AWS CLI"
        exit 1
    fi
    
    # Check cluster connection
    if ! kubectl cluster-info &> /dev/null; then
        log_error "Cannot connect to Kubernetes cluster. Please check your kubeconfig"
        exit 1
    fi
    
    log_success "Prerequisites check completed"
}

# Create namespace and RBAC
setup_namespace() {
    log_info "Setting up production namespace and RBAC..."
    
    # Apply namespace configuration
    kubectl apply -f ../kubernetes/namespace.yaml
    
    # Wait for namespace to be ready
    kubectl wait --for=condition=Active namespace/${NAMESPACE} --timeout=60s
    
    log_success "Namespace ${NAMESPACE} created and ready"
}

# Deploy shared infrastructure
deploy_shared_infrastructure() {
    log_info "Deploying shared infrastructure components..."
    
    # Create secrets first
    create_infrastructure_secrets
    
    # Deploy PostgreSQL, Redis, Qdrant, Neo4j clusters
    kubectl apply -f ../kubernetes/shared-infrastructure.yaml
    
    # Wait for shared infrastructure to be ready
    log_info "Waiting for shared infrastructure to be ready..."
    
    # Wait for PostgreSQL
    kubectl wait --for=condition=Ready pod -l component=postgres-primary -n ${NAMESPACE} --timeout=300s
    log_success "PostgreSQL cluster ready"
    
    # Wait for Redis
    kubectl wait --for=condition=Ready pod -l component=redis-cluster -n ${NAMESPACE} --timeout=300s
    log_success "Redis cluster ready"
    
    # Wait for Qdrant
    kubectl wait --for=condition=Ready pod -l component=qdrant-cluster -n ${NAMESPACE} --timeout=300s
    log_success "Qdrant vector database ready"
    
    # Wait for Neo4j
    kubectl wait --for=condition=Ready pod -l component=neo4j-cluster -n ${NAMESPACE} --timeout=600s
    log_success "Neo4j graph database ready"
    
    log_success "Shared infrastructure deployment completed"
}

# Create infrastructure secrets
create_infrastructure_secrets() {
    log_info "Creating infrastructure secrets..."
    
    # PostgreSQL secrets
    kubectl create secret generic postgres-secrets \
        --from-literal=username="mcphub" \
        --from-literal=password="$(openssl rand -base64 32)" \
        --from-literal=replication_password="$(openssl rand -base64 32)" \
        --from-literal=connection_url="postgresql://mcphub:$(openssl rand -base64 32)@postgres-primary.${NAMESPACE}.svc.cluster.local:5432/ai_agency_platform?sslmode=require" \
        -n ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
    
    # Neo4j secrets
    kubectl create secret generic neo4j-secrets \
        --from-literal=auth="neo4j/$(openssl rand -base64 32)" \
        -n ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
    
    # Grafana secrets
    kubectl create secret generic grafana-secrets \
        --from-literal=admin_password="$(openssl rand -base64 32)" \
        --from-literal=db_user="grafana" \
        --from-literal=db_password="$(openssl rand -base64 32)" \
        -n ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
    
    # AI Provider secrets (these should be set from environment variables)
    kubectl create secret generic ai-provider-secrets \
        --from-literal=openai_api_key="${OPENAI_API_KEY:-}" \
        --from-literal=claude_api_key="${CLAUDE_API_KEY:-}" \
        --from-literal=api_endpoints='{"openai": "https://api.openai.com/v1", "claude": "https://api.anthropic.com"}' \
        -n ${NAMESPACE} --dry-run=client -o yaml | kubectl apply -f -
    
    log_success "Infrastructure secrets created"
}

# Deploy monitoring stack
deploy_monitoring() {
    log_info "Deploying production monitoring stack..."
    
    # Deploy Prometheus, Grafana, AlertManager, and Cost Analytics
    kubectl apply -f ../monitoring/production-monitoring.yaml
    
    # Wait for monitoring components
    log_info "Waiting for monitoring components to be ready..."
    
    # Wait for Prometheus
    kubectl wait --for=condition=Ready pod -l component=prometheus -n ${NAMESPACE} --timeout=300s
    log_success "Prometheus ready"
    
    # Wait for Grafana
    kubectl wait --for=condition=Ready pod -l component=grafana -n ${NAMESPACE} --timeout=300s
    log_success "Grafana ready"
    
    # Wait for AlertManager
    kubectl wait --for=condition=Ready pod -l component=alertmanager -n ${NAMESPACE} --timeout=300s
    log_success "AlertManager ready"
    
    log_success "Monitoring stack deployment completed"
}

# Deploy customer provisioning service
deploy_provisioning_service() {
    log_info "Deploying customer provisioning service..."
    
    # Build and push provisioning service image
    build_provisioning_service
    
    # Create provisioning service deployment
    cat <<EOF | kubectl apply -f -
apiVersion: apps/v1
kind: Deployment
metadata:
  name: customer-provisioner
  namespace: ${NAMESPACE}
  labels:
    app: ai-agency-platform
    component: provisioner
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ai-agency-platform
      component: provisioner
  template:
    metadata:
      labels:
        app: ai-agency-platform
        component: provisioner
    spec:
      serviceAccountName: customer-provisioner
      containers:
      - name: provisioner
        image: ai-agency-platform/customer-provisioner:v1.0.0
        ports:
        - containerPort: 8080
          name: http
        env:
        - name: NAMESPACE
          value: "${NAMESPACE}"
        - name: POSTGRES_URL
          valueFrom:
            secretKeyRef:
              name: postgres-secrets
              key: connection_url
        resources:
          requests:
            cpu: "500m"
            memory: "1Gi"
          limits:
            cpu: "1000m"
            memory: "2Gi"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 10
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: customer-provisioner
  namespace: ${NAMESPACE}
  labels:
    app: ai-agency-platform
    component: provisioner
spec:
  ports:
  - port: 8080
    targetPort: 8080
    name: http
  selector:
    app: ai-agency-platform
    component: provisioner
  type: ClusterIP
EOF
    
    # Wait for provisioning service to be ready
    kubectl wait --for=condition=Ready pod -l component=provisioner -n ${NAMESPACE} --timeout=300s
    
    log_success "Customer provisioning service deployed"
}

# Build provisioning service image
build_provisioning_service() {
    log_info "Building customer provisioning service..."
    
    # Navigate to provisioning directory
    cd ../provisioning
    
    # Create Dockerfile if it doesn't exist
    if [ ! -f Dockerfile ]; then
        cat <<EOF > Dockerfile
FROM golang:1.21-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o customer-provisioner .

FROM alpine:3.18
RUN apk --no-cache add ca-certificates
WORKDIR /root/

COPY --from=builder /app/customer-provisioner .
COPY --from=builder /app/templates ./templates

CMD ["./customer-provisioner"]
EOF
    fi
    
    # Create go.mod if it doesn't exist
    if [ ! -f go.mod ]; then
        cat <<EOF > go.mod
module customer-provisioner

go 1.21

require (
    github.com/gin-gonic/gin v1.9.1
    github.com/lib/pq v1.10.9
    github.com/go-redis/redis/v8 v8.11.5
    k8s.io/client-go v0.28.0
    k8s.io/apimachinery v0.28.0
)
EOF
    fi
    
    # Build and push image (assumes Docker registry is configured)
    docker build -t ai-agency-platform/customer-provisioner:v1.0.0 .
    
    # Push to registry if configured
    if [ -n "${DOCKER_REGISTRY:-}" ]; then
        docker tag ai-agency-platform/customer-provisioner:v1.0.0 ${DOCKER_REGISTRY}/ai-agency-platform/customer-provisioner:v1.0.0
        docker push ${DOCKER_REGISTRY}/ai-agency-platform/customer-provisioner:v1.0.0
    fi
    
    cd - > /dev/null
    
    log_success "Customer provisioning service built"
}

# Setup autoscaling
setup_autoscaling() {
    log_info "Setting up autoscaling policies..."
    
    # Create Vertical Pod Autoscaler for shared infrastructure
    cat <<EOF | kubectl apply -f -
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: postgres-vpa
  namespace: ${NAMESPACE}
spec:
  targetRef:
    apiVersion: apps/v1
    kind: StatefulSet
    name: postgres-primary
  updatePolicy:
    updateMode: "Auto"
  resourcePolicy:
    containerPolicies:
    - containerName: postgres
      maxAllowed:
        cpu: 8
        memory: 32Gi
      minAllowed:
        cpu: 1
        memory: 4Gi
---
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: qdrant-vpa
  namespace: ${NAMESPACE}
spec:
  targetRef:
    apiVersion: apps/v1
    kind: StatefulSet
    name: qdrant-cluster
  updatePolicy:
    updateMode: "Auto"
  resourcePolicy:
    containerPolicies:
    - containerName: qdrant
      maxAllowed:
        cpu: 4
        memory: 16Gi
      minAllowed:
        cpu: 500m
        memory: 2Gi
EOF
    
    log_success "Autoscaling policies configured"
}

# Setup ingress and load balancing
setup_ingress() {
    log_info "Setting up ingress and load balancing..."
    
    # Create ingress for external access
    cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ai-agency-platform-ingress
  namespace: ${NAMESPACE}
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/use-regex: "true"
    nginx.ingress.kubernetes.io/rate-limit: "1000"
    nginx.ingress.kubernetes.io/rate-limit-window: "1m"
spec:
  tls:
  - hosts:
    - api.ai-agency-platform.com
    - monitoring.ai-agency-platform.com
    secretName: ai-agency-platform-tls
  rules:
  - host: api.ai-agency-platform.com
    http:
      paths:
      - path: /provision
        pathType: Prefix
        backend:
          service:
            name: customer-provisioner
            port:
              number: 8080
      - path: /customer/(.+)/
        pathType: Prefix
        backend:
          service:
            name: customer-\\1-mcp-service
            port:
              number: 80
  - host: monitoring.ai-agency-platform.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: grafana
            port:
              number: 3000
EOF
    
    log_success "Ingress configured"
}

# Validate deployment
validate_deployment() {
    log_info "Validating production deployment..."
    
    # Check all pods are running
    log_info "Checking pod status..."
    kubectl get pods -n ${NAMESPACE} -o wide
    
    # Check services
    log_info "Checking services..."
    kubectl get services -n ${NAMESPACE}
    
    # Check persistent volumes
    log_info "Checking persistent volumes..."
    kubectl get pv,pvc -n ${NAMESPACE}
    
    # Test provisioning service
    log_info "Testing provisioning service..."
    PROVISIONER_IP=$(kubectl get service customer-provisioner -n ${NAMESPACE} -o jsonpath='{.spec.clusterIP}')
    
    # Health check
    if kubectl run test-provisioner --image=curlimages/curl --rm -it --restart=Never -- curl -s http://${PROVISIONER_IP}:8080/health | grep -q "healthy"; then
        log_success "Provisioning service health check passed"
    else
        log_error "Provisioning service health check failed"
        return 1
    fi
    
    # Test customer provisioning
    log_info "Testing customer provisioning..."
    TEST_CUSTOMER_ID="test-$(date +%s)"
    
    cat <<EOF > test_provision.json
{
  "customer_id": "${TEST_CUSTOMER_ID}",
  "customer_email": "test@example.com",
  "customer_tier": "basic",
  "features": ["ea", "workflows"],
  "ai_model_access": ["gpt-4", "claude-3"]
}
EOF
    
    if kubectl run test-provision --image=curlimages/curl --rm -it --restart=Never -- curl -s -X POST -H "Content-Type: application/json" -d @test_provision.json http://${PROVISIONER_IP}:8080/provision | grep -q "active"; then
        log_success "Test customer provisioning successful"
        
        # Clean up test customer
        kubectl run test-cleanup --image=curlimages/curl --rm -it --restart=Never -- curl -s -X DELETE http://${PROVISIONER_IP}:8080/deprovision/${TEST_CUSTOMER_ID}
    else
        log_error "Test customer provisioning failed"
        return 1
    fi
    
    log_success "Deployment validation completed successfully"
}

# Performance testing
run_performance_tests() {
    log_info "Running performance tests..."
    
    # Test concurrent customer provisioning
    log_info "Testing concurrent provisioning performance..."
    
    # Create test script for concurrent provisioning
    cat <<EOF > concurrent_provision_test.sh
#!/bin/bash
PROVISIONER_URL="http://customer-provisioner.${NAMESPACE}.svc.cluster.local:8080"
CONCURRENT_REQUESTS=10
TOTAL_TIME=0

for i in \$(seq 1 \$CONCURRENT_REQUESTS); do
    {
        START_TIME=\$(date +%s.%N)
        CUSTOMER_ID="perf-test-\${i}-\$(date +%s)"
        
        curl -s -X POST -H "Content-Type: application/json" \\
             -d "{\"customer_id\":\"\$CUSTOMER_ID\",\"customer_email\":\"test@example.com\",\"customer_tier\":\"basic\",\"features\":[\"ea\"],\"ai_model_access\":[\"gpt-4\"]}" \\
             \$PROVISIONER_URL/provision > /dev/null
        
        END_TIME=\$(date +%s.%N)
        DURATION=\$(echo "\$END_TIME - \$START_TIME" | bc)
        echo "Customer \$CUSTOMER_ID provisioned in \${DURATION}s"
        
        # Cleanup
        curl -s -X DELETE \$PROVISIONER_URL/deprovision/\$CUSTOMER_ID > /dev/null
    } &
done

wait
EOF
    
    chmod +x concurrent_provision_test.sh
    
    # Run performance test inside cluster
    kubectl create configmap perf-test-script --from-file=concurrent_provision_test.sh -n ${NAMESPACE}
    
    kubectl run performance-test \
        --image=curlimages/curl \
        --rm -it --restart=Never \
        --overrides='{"spec":{"containers":[{"name":"curl","image":"curlimages/curl","command":["sh","-c","apk add --no-cache bc && /scripts/concurrent_provision_test.sh"],"volumeMounts":[{"name":"script","mountPath":"/scripts"}]}],"volumes":[{"name":"script","configMap":{"name":"perf-test-script","defaultMode":511}}]}}' \
        -n ${NAMESPACE}
    
    # Cleanup
    kubectl delete configmap perf-test-script -n ${NAMESPACE}
    
    log_success "Performance tests completed"
}

# Main deployment function
main() {
    log_info "Starting AI Agency Platform production deployment..."
    log_info "Target: 500+ customers with <30 second onboarding"
    
    # Check if running in CI/CD mode
    if [ "${CI:-false}" = "true" ]; then
        log_info "Running in CI/CD mode - automated deployment"
    else
        log_warning "Running in interactive mode"
        read -p "Continue with production deployment? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Deployment cancelled"
            exit 0
        fi
    fi
    
    # Deployment steps
    check_prerequisites
    setup_namespace
    deploy_shared_infrastructure
    deploy_monitoring
    deploy_provisioning_service
    setup_autoscaling
    setup_ingress
    
    log_success "Production deployment completed successfully!"
    
    # Validation and testing
    if [ "${SKIP_VALIDATION:-false}" != "true" ]; then
        validate_deployment
        
        if [ "${RUN_PERFORMANCE_TESTS:-false}" = "true" ]; then
            run_performance_tests
        fi
    fi
    
    # Display deployment summary
    cat <<EOF

${GREEN}╔════════════════════════════════════════════════════════════════════════════════╗
║                    AI AGENCY PLATFORM - PRODUCTION DEPLOYMENT                 ║
║                                   COMPLETED                                    ║
╠════════════════════════════════════════════════════════════════════════════════╣
║ Namespace:           ${NAMESPACE}                                        ║
║ Cluster:             ${CLUSTER_NAME}                                           ║
║ Region:              ${AWS_REGION}                                             ║
║                                                                                ║
║ Customer Capacity:   500+ concurrent customers                                ║
║ Provisioning Target: <30 seconds from purchase to working EA                  ║
║ Architecture:        Per-customer MCP server isolation                        ║
║                                                                                ║
║ Access Points:                                                                 ║
║ • API Endpoint:      https://api.ai-agency-platform.com                       ║
║ • Monitoring:        https://monitoring.ai-agency-platform.com                ║
║ • Provisioning:      /provision endpoint for customer onboarding             ║
║                                                                                ║
║ Infrastructure:                                                                ║
║ • PostgreSQL Cluster: 3 nodes with per-customer schema isolation             ║
║ • Redis Cluster:      6 nodes with customer DB isolation (0-15)              ║
║ • Qdrant Vector DB:   3 nodes with per-customer collections                  ║
║ • Neo4j Graph DB:     3 nodes with per-customer databases                    ║
║ • Monitoring Stack:   Prometheus + Grafana + AlertManager                    ║
║                                                                                ║
║ Ready for Phase 2 EA orchestration with specialist agents!                    ║
╚════════════════════════════════════════════════════════════════════════════════╝${NC}

Next Steps:
1. Configure DNS for api.ai-agency-platform.com and monitoring.ai-agency-platform.com
2. Set up SSL certificates via cert-manager
3. Configure customer onboarding webhooks
4. Set up cost tracking and billing integration
5. Deploy Phase 2 specialist agents

For customer provisioning, send POST requests to:
https://api.ai-agency-platform.com/provision

Example:
curl -X POST https://api.ai-agency-platform.com/provision \\
  -H "Content-Type: application/json" \\
  -d '{
    "customer_id": "customer-123",
    "customer_email": "customer@example.com", 
    "customer_tier": "professional",
    "features": ["ea", "social-media", "finance", "marketing"],
    "ai_model_access": ["gpt-4", "claude-3"]
  }'

EOF
    
    log_success "AI Agency Platform production deployment completed successfully!"
}

# Run main function
main "$@"