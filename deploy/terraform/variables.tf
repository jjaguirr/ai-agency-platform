# AI Agency Platform - Terraform Variables
# Variables for production infrastructure deployment

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "production"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "ai-agency-platform"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = "List of availability zones"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

variable "eks_cluster_version" {
  description = "Kubernetes version for EKS cluster"
  type        = string
  default     = "1.28"
}

variable "eks_node_instance_types" {
  description = "EC2 instance types for EKS nodes"
  type        = list(string)
  default     = ["m6i.xlarge", "m6i.2xlarge"]
}

variable "eks_node_desired_capacity" {
  description = "Desired number of EKS nodes"
  type        = number
  default     = 6
}

variable "eks_node_min_capacity" {
  description = "Minimum number of EKS nodes"
  type        = number
  default     = 3
}

variable "eks_node_max_capacity" {
  description = "Maximum number of EKS nodes"
  type        = number
  default     = 20
}

variable "rds_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.r6g.xlarge"
}

variable "rds_allocated_storage" {
  description = "Initial allocated storage for RDS"
  type        = number
  default     = 100
}

variable "rds_max_allocated_storage" {
  description = "Maximum allocated storage for RDS"
  type        = number
  default     = 1000
}

variable "rds_backup_retention_period" {
  description = "Backup retention period in days"
  type        = number
  default     = 30
}

variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.r6g.large"
}

variable "redis_num_cache_clusters" {
  description = "Number of Redis cache clusters"
  type        = number
  default     = 3
}

variable "backup_retention_days" {
  description = "Number of days to retain backups"
  type        = number
  default     = 30
}

variable "log_retention_days" {
  description = "Number of days to retain CloudWatch logs"
  type        = number
  default     = 30
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = "ai-agency.com"
}

variable "ssl_certificate_arn" {
  description = "ARN of SSL certificate for load balancer"
  type        = string
  default     = ""
}

variable "enable_cloudtrail" {
  description = "Enable CloudTrail for audit logging"
  type        = bool
  default     = true
}

variable "enable_config" {
  description = "Enable AWS Config for compliance monitoring"
  type        = bool
  default     = true
}

variable "enable_guardduty" {
  description = "Enable GuardDuty for threat detection"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Additional tags for resources"
  type        = map(string)
  default = {
    Project     = "ai-agency-platform"
    Environment = "production"
    ManagedBy   = "terraform"
  }
}

# Vault-specific variables
variable "vault_address" {
  description = "Vault server address"
  type        = string
  default     = "https://vault.production.ai-agency.com:8200"
}

variable "vault_namespace" {
  description = "Vault namespace for the project"
  type        = string
  default     = "ai-agency/production"
}

# Monitoring variables
variable "monitoring_enabled" {
  description = "Enable comprehensive monitoring"
  type        = bool
  default     = true
}

variable "alerting_enabled" {
  description = "Enable alerting for monitoring"
  type        = bool
  default     = true
}

variable "log_analytics_enabled" {
  description = "Enable log analytics"
  type        = bool
  default     = true
}

# Security variables
variable "enable_encryption" {
  description = "Enable encryption for all data at rest"
  type        = bool
  default     = true
}

variable "enable_ssl" {
  description = "Enable SSL/TLS for all communications"
  type        = bool
  default     = true
}

variable "enable_waf" {
  description = "Enable Web Application Firewall"
  type        = bool
  default     = true
}

# Cost optimization variables
variable "enable_spot_instances" {
  description = "Enable spot instances for cost optimization"
  type        = bool
  default     = false
}

variable "enable_auto_scaling" {
  description = "Enable auto-scaling for resources"
  type        = bool
  default     = true
}

# Backup variables
variable "backup_schedule" {
  description = "Cron schedule for automated backups"
  type        = string
  default     = "cron(0 2 * * ? *)"
}

variable "cross_region_backup" {
  description = "Enable cross-region backup replication"
  type        = bool
  default     = true
}

# Compliance variables
variable "enable_hipaa_compliance" {
  description = "Enable HIPAA compliance features"
  type        = bool
  default     = false
}

variable "enable_soc2_compliance" {
  description = "Enable SOC2 compliance features"
  type        = bool
  default     = true
}

variable "enable_gdpr_compliance" {
  description = "Enable GDPR compliance features"
  type        = bool
  default     = true
}

# Customer isolation variables
variable "enable_customer_isolation" {
  description = "Enable strict customer data isolation"
  type        = bool
  default     = true
}

variable "max_customers_per_cluster" {
  description = "Maximum number of customers per cluster"
  type        = number
  default     = 1000
}

variable "customer_subnet_range" {
  description = "Subnet range size per customer"
  type        = string
  default     = "/24"
}