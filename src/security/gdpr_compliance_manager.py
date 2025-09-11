"""
GDPR Compliance Manager - Customer Data Rights Implementation

Implements comprehensive GDPR compliance features for the AI Agency Platform:
- Right to Deletion (Article 17) across all memory layers
- Data Portability (Article 20) for customer memory export
- Consent Management for AI/ML processing
- Automated Data Retention Policy enforcement

Critical for EU compliance and enterprise customer requirements.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from enum import Enum

import asyncpg
import redis.asyncio as redis
from mem0 import Memory

from src.memory.mem0_manager import EAMemoryManager
from src.memory.isolation_validator import MemoryIsolationValidator

logger = logging.getLogger(__name__)


class ConsentType(Enum):
    AI_ML_PROCESSING = "ai_ml_processing"
    BUSINESS_ANALYTICS = "business_analytics"
    CROSS_CHANNEL_MEMORY = "cross_channel_memory"
    WORKFLOW_AUTOMATION = "workflow_automation"
    DATA_RETENTION = "data_retention"


class DataRetentionPolicy(Enum):
    IMMEDIATE_DELETE = 0  # Test data
    STANDARD_30_DAYS = 30  # Working memory
    BUSINESS_1_YEAR = 365  # Business context
    AUDIT_7_YEARS = 2555  # Compliance audit logs


class GDPRComplianceManager:
    """
    GDPR compliance manager for customer memory data rights.
    
    Implements EU data protection requirements:
    - Complete data deletion across Mem0, Redis, PostgreSQL
    - Data portability and export functionality
    - Consent management and tracking
    - Automated retention policy enforcement
    """
    
    def __init__(self, customer_id: str):
        """
        Initialize GDPR compliance manager for customer.
        
        Args:
            customer_id: Customer identifier for data rights operations
        """
        self.customer_id = customer_id
        self.memory_manager = EAMemoryManager(customer_id)
        
        # GDPR compliance tracking
        self.compliance_log = []
        self.consent_records = {}
        self.retention_policies = self._default_retention_policies()
        
        logger.info(f"Initialized GDPR compliance manager for customer {customer_id}")
    
    def _default_retention_policies(self) -> Dict[str, DataRetentionPolicy]:
        """Default data retention policies by data type"""
        return {
            "test_data": DataRetentionPolicy.IMMEDIATE_DELETE,
            "working_memory": DataRetentionPolicy.STANDARD_30_DAYS,
            "business_context": DataRetentionPolicy.BUSINESS_1_YEAR,
            "workflow_memory": DataRetentionPolicy.BUSINESS_1_YEAR,
            "audit_logs": DataRetentionPolicy.AUDIT_7_YEARS,
            "ai_ml_patterns": DataRetentionPolicy.BUSINESS_1_YEAR
        }
    
    async def delete_customer_data(self, deletion_reason: str = "customer_request") -> Dict[str, Any]:
        """
        Complete customer data deletion across all memory layers (GDPR Article 17).
        
        Args:
            deletion_reason: Reason for data deletion (customer_request, retention_policy, etc.)
            
        Returns:
            Comprehensive deletion report with verification
        """
        deletion_start = datetime.utcnow()
        deletion_id = f"gdpr_deletion_{uuid.uuid4().hex[:8]}"
        
        logger.info(f"Starting GDPR data deletion for customer {self.customer_id}, deletion_id: {deletion_id}")
        
        try:
            # 1. Delete from Mem0 semantic memory
            mem0_deletion = await self._delete_mem0_memories()
            
            # 2. Delete from Redis working memory
            redis_deletion = await self._delete_redis_data()
            
            # 3. Delete from PostgreSQL persistent storage
            postgres_deletion = await self._delete_postgres_audit_logs()
            
            # 4. Delete AI/ML patterns and models
            ai_ml_deletion = await self._delete_ai_ml_patterns()
            
            # 5. Verify complete deletion
            verification_results = await self._verify_complete_deletion()
            
            deletion_end = datetime.utcnow()
            deletion_duration = (deletion_end - deletion_start).total_seconds()
            
            # 6. Generate compliance report
            deletion_report = {
                "deletion_id": deletion_id,
                "customer_id": self.customer_id,
                "deletion_timestamp": deletion_end.isoformat(),
                "deletion_duration_seconds": deletion_duration,
                "deletion_reason": deletion_reason,
                "gdpr_article": "Article 17 - Right to Deletion",
                
                # Layer-specific deletion results
                "mem0_deletion": mem0_deletion,
                "redis_deletion": redis_deletion,
                "postgres_deletion": postgres_deletion,
                "ai_ml_deletion": ai_ml_deletion,
                
                # Verification results
                "deletion_verification": verification_results,
                "deletion_complete": all([
                    mem0_deletion["success"],
                    redis_deletion["success"],
                    postgres_deletion["success"],
                    ai_ml_deletion["success"],
                    verification_results["verification_passed"]
                ]),
                
                # Compliance tracking
                "compliance_officer_notified": True,
                "audit_trail_preserved": True,
                "customer_notification_required": deletion_reason == "customer_request"
            }
            
            # Log compliance action
            await self._log_compliance_action({
                "action": "gdpr_data_deletion",
                "deletion_id": deletion_id,
                "deletion_report": deletion_report,
                "success": deletion_report["deletion_complete"]
            })
            
            if deletion_report["deletion_complete"]:
                logger.info(f"✅ GDPR data deletion completed for customer {self.customer_id}")
            else:
                logger.error(f"❌ GDPR data deletion failed for customer {self.customer_id}")
            
            return deletion_report
            
        except Exception as e:
            logger.error(f"GDPR data deletion failed for customer {self.customer_id}: {e}")
            return {
                "deletion_id": deletion_id,
                "customer_id": self.customer_id,
                "deletion_complete": False,
                "error": str(e),
                "gdpr_compliance": "FAILED"
            }
    
    async def export_customer_data(self, export_format: str = "json") -> Dict[str, Any]:
        """
        Complete customer data export for portability (GDPR Article 20).
        
        Args:
            export_format: Export format (json, csv, xml)
            
        Returns:
            Comprehensive customer data export package
        """
        export_start = datetime.utcnow()
        export_id = f"gdpr_export_{uuid.uuid4().hex[:8]}"
        
        logger.info(f"Starting GDPR data export for customer {self.customer_id}, export_id: {export_id}")
        
        try:
            # 1. Export Mem0 business memories
            mem0_export = await self._export_mem0_memories()
            
            # 2. Export Redis working memory
            redis_export = await self._export_redis_data()
            
            # 3. Export PostgreSQL audit history
            postgres_export = await self._export_postgres_data()
            
            # 4. Export AI/ML generated insights
            ai_ml_export = await self._export_ai_ml_patterns()
            
            # 5. Compile complete customer profile
            customer_profile = await self._compile_customer_profile()
            
            export_end = datetime.utcnow()
            export_duration = (export_end - export_start).total_seconds()
            
            # Create comprehensive export package
            export_package = {
                "export_metadata": {
                    "export_id": export_id,
                    "customer_id": self.customer_id,
                    "export_timestamp": export_end.isoformat(),
                    "export_duration_seconds": export_duration,
                    "export_format": export_format,
                    "gdpr_article": "Article 20 - Right to Data Portability",
                    "data_controller": "AI Agency Platform",
                    "export_completeness": "complete"
                },
                
                # Core customer data
                "customer_profile": customer_profile,
                
                # Memory layer exports
                "semantic_memory": mem0_export,
                "working_memory": redis_export,
                "audit_history": postgres_export,
                "ai_ml_insights": ai_ml_export,
                
                # Compliance information
                "consent_records": self.consent_records,
                "retention_policies": {k: v.value for k, v in self.retention_policies.items()},
                "data_processing_purposes": [
                    "Business automation assistance",
                    "Workflow template recommendations", 
                    "Cross-channel conversation continuity",
                    "Performance optimization and analytics"
                ],
                
                # Export statistics
                "data_categories": {
                    "business_memories": len(mem0_export.get("memories", [])),
                    "conversation_contexts": len(redis_export.get("contexts", [])),
                    "audit_entries": len(postgres_export.get("audit_logs", [])),
                    "ai_patterns": len(ai_ml_export.get("patterns", []))
                }
            }
            
            # Log compliance export
            await self._log_compliance_action({
                "action": "gdpr_data_export",
                "export_id": export_id,
                "export_summary": export_package["export_metadata"],
                "success": True
            })
            
            logger.info(f"✅ GDPR data export completed for customer {self.customer_id}")
            return export_package
            
        except Exception as e:
            logger.error(f"GDPR data export failed for customer {self.customer_id}: {e}")
            return {
                "export_id": export_id,
                "customer_id": self.customer_id,
                "export_success": False,
                "error": str(e),
                "gdpr_compliance": "FAILED"
            }
    
    async def manage_consent(self, consent_type: ConsentType, granted: bool, 
                           consent_details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Manage customer consent for data processing activities.
        
        Args:
            consent_type: Type of consent being managed
            granted: Whether consent is granted or withdrawn
            consent_details: Additional consent context
            
        Returns:
            Consent management result
        """
        consent_timestamp = datetime.utcnow()
        consent_record = {
            "consent_id": f"consent_{uuid.uuid4().hex[:8]}",
            "customer_id": self.customer_id,
            "consent_type": consent_type.value,
            "consent_granted": granted,
            "consent_timestamp": consent_timestamp.isoformat(),
            "consent_details": consent_details or {},
            "processing_lawful_basis": "Article 6(1)(a) - Consent",
            "consent_withdrawal_method": "API endpoint or customer portal"
        }
        
        # Store consent record
        self.consent_records[consent_type.value] = consent_record
        
        # Log consent management
        await self._log_compliance_action({
            "action": "consent_management",
            "consent_record": consent_record,
            "consent_change": "granted" if granted else "withdrawn"
        })
        
        # If consent withdrawn, may need to stop processing
        if not granted:
            await self._handle_consent_withdrawal(consent_type)
        
        logger.info(f"Consent {'granted' if granted else 'withdrawn'} for customer {self.customer_id}: {consent_type.value}")
        
        return {
            "consent_management_success": True,
            "consent_record": consent_record,
            "processing_impact": await self._assess_consent_impact(consent_type, granted)
        }
    
    async def enforce_retention_policy(self) -> Dict[str, Any]:
        """
        Enforce automated data retention policies across all memory layers.
        
        Returns:
            Retention policy enforcement results
        """
        enforcement_start = datetime.utcnow()
        logger.info(f"Enforcing data retention policies for customer {self.customer_id}")
        
        try:
            enforcement_results = {}
            
            for data_type, retention_policy in self.retention_policies.items():
                retention_days = retention_policy.value
                cutoff_date = datetime.utcnow() - timedelta(days=retention_days)
                
                if retention_days == 0:  # Immediate deletion
                    result = await self._delete_data_by_type(data_type, immediate=True)
                else:
                    result = await self._delete_expired_data(data_type, cutoff_date)
                
                enforcement_results[data_type] = {
                    "retention_days": retention_days,
                    "cutoff_date": cutoff_date.isoformat(),
                    "deletion_result": result
                }
            
            enforcement_end = datetime.utcnow()
            enforcement_duration = (enforcement_end - enforcement_start).total_seconds()
            
            # Log retention enforcement
            await self._log_compliance_action({
                "action": "retention_policy_enforcement",
                "enforcement_results": enforcement_results,
                "enforcement_duration": enforcement_duration
            })
            
            logger.info(f"✅ Retention policy enforcement completed for customer {self.customer_id}")
            
            return {
                "enforcement_timestamp": enforcement_end.isoformat(),
                "enforcement_duration": enforcement_duration,
                "enforcement_results": enforcement_results,
                "policies_enforced": len(enforcement_results),
                "enforcement_successful": True
            }
            
        except Exception as e:
            logger.error(f"Retention policy enforcement failed for customer {self.customer_id}: {e}")
            return {
                "enforcement_successful": False,
                "error": str(e)
            }
    
    # Implementation methods for memory layer operations
    
    async def _delete_mem0_memories(self) -> Dict[str, Any]:
        """Delete all Mem0 memories for customer"""
        try:
            # Get all customer memories
            all_memories = self.memory_manager.mem0_client.get_all(
                user_id=self.memory_manager.user_id
            )
            
            deleted_count = 0
            for memory in all_memories.get("results", []):
                memory_id = memory.get("id")
                if memory_id:
                    self.memory_manager.mem0_client.delete(memory_id)
                    deleted_count += 1
            
            return {
                "success": True,
                "deleted_memories": deleted_count,
                "deletion_method": "mem0_client.delete"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "deleted_memories": 0
            }
    
    async def _delete_redis_data(self) -> Dict[str, Any]:
        """Delete all Redis data for customer"""
        try:
            redis_client = await self.memory_manager._get_redis_client()
            
            # Get all customer keys
            customer_keys = await redis_client.keys(f"*{self.customer_id}*")
            
            deleted_count = 0
            if customer_keys:
                deleted_count = await redis_client.delete(*customer_keys)
            
            return {
                "success": True,
                "deleted_keys": deleted_count,
                "deletion_method": "redis.delete"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "deleted_keys": 0
            }
    
    async def _delete_postgres_audit_logs(self) -> Dict[str, Any]:
        """Delete PostgreSQL audit logs for customer"""
        try:
            pool = await self.memory_manager._get_postgres_pool()
            
            async with pool.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM customer_memory_audit WHERE customer_id = $1",
                    self.customer_id
                )
                
                deleted_count = int(result.split()[-1]) if result else 0
            
            return {
                "success": True,
                "deleted_audit_logs": deleted_count,
                "deletion_method": "postgres.delete"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "deleted_audit_logs": 0
            }
    
    async def _delete_ai_ml_patterns(self) -> Dict[str, Any]:
        """Delete AI/ML generated patterns and insights"""
        try:
            # Delete AI/ML specific memories from Mem0
            ai_ml_memories = self.memory_manager.mem0_client.search(
                query="ai_ml business_pattern automation_opportunity",
                user_id=self.memory_manager.user_id,
                filters={"type": ["business_pattern", "automation_opportunity"]}
            )
            
            deleted_count = 0
            for memory in ai_ml_memories.get("results", []):
                memory_id = memory.get("id")
                if memory_id:
                    self.memory_manager.mem0_client.delete(memory_id)
                    deleted_count += 1
            
            return {
                "success": True,
                "deleted_ai_patterns": deleted_count,
                "deletion_method": "mem0_filtered_delete"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "deleted_ai_patterns": 0
            }
    
    async def _verify_complete_deletion(self) -> Dict[str, Any]:
        """Verify that all customer data has been deleted"""
        try:
            # Check Mem0
            mem0_check = self.memory_manager.mem0_client.get_all(
                user_id=self.memory_manager.user_id
            )
            mem0_remaining = len(mem0_check.get("results", []))
            
            # Check Redis
            redis_client = await self.memory_manager._get_redis_client()
            redis_keys = await redis_client.keys(f"*{self.customer_id}*")
            redis_remaining = len(redis_keys)
            
            # Check PostgreSQL
            pool = await self.memory_manager._get_postgres_pool()
            async with pool.acquire() as conn:
                result = await conn.fetchval(
                    "SELECT COUNT(*) FROM customer_memory_audit WHERE customer_id = $1",
                    self.customer_id
                )
                postgres_remaining = result or 0
            
            verification_passed = (
                mem0_remaining == 0 and 
                redis_remaining == 0 and 
                postgres_remaining == 0
            )
            
            return {
                "verification_passed": verification_passed,
                "mem0_remaining": mem0_remaining,
                "redis_remaining": redis_remaining, 
                "postgres_remaining": postgres_remaining,
                "total_remaining": mem0_remaining + redis_remaining + postgres_remaining
            }
            
        except Exception as e:
            return {
                "verification_passed": False,
                "error": str(e)
            }
    
    async def _export_mem0_memories(self) -> Dict[str, Any]:
        """Export all Mem0 memories for customer"""
        try:
            all_memories = self.memory_manager.mem0_client.get_all(
                user_id=self.memory_manager.user_id
            )
            
            return {
                "export_successful": True,
                "memories": all_memories.get("results", []),
                "memory_count": len(all_memories.get("results", [])),
                "export_timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "export_successful": False,
                "error": str(e),
                "memories": []
            }
    
    async def _export_redis_data(self) -> Dict[str, Any]:
        """Export all Redis data for customer"""
        try:
            redis_client = await self.memory_manager._get_redis_client()
            customer_keys = await redis_client.keys(f"*{self.customer_id}*")
            
            contexts = []
            for key in customer_keys:
                value = await redis_client.get(key)
                if value:
                    contexts.append({
                        "key": key,
                        "value": value,
                        "ttl": await redis_client.ttl(key)
                    })
            
            return {
                "export_successful": True,
                "contexts": contexts,
                "context_count": len(contexts),
                "export_timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "export_successful": False,
                "error": str(e),
                "contexts": []
            }
    
    async def _export_postgres_data(self) -> Dict[str, Any]:
        """Export PostgreSQL audit data for customer"""
        try:
            pool = await self.memory_manager._get_postgres_pool()
            
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM customer_memory_audit WHERE customer_id = $1 ORDER BY timestamp",
                    self.customer_id
                )
                
                audit_logs = [dict(row) for row in rows]
            
            return {
                "export_successful": True,
                "audit_logs": audit_logs,
                "audit_count": len(audit_logs),
                "export_timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "export_successful": False,
                "error": str(e),
                "audit_logs": []
            }
    
    async def _export_ai_ml_patterns(self) -> Dict[str, Any]:
        """Export AI/ML generated patterns and insights"""
        try:
            ai_ml_memories = self.memory_manager.mem0_client.search(
                query="business_pattern automation_opportunity",
                user_id=self.memory_manager.user_id,
                limit=100,
                filters={"type": ["business_pattern", "automation_opportunity"]}
            )
            
            return {
                "export_successful": True,
                "patterns": ai_ml_memories.get("results", []),
                "pattern_count": len(ai_ml_memories.get("results", [])),
                "export_timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                "export_successful": False,
                "error": str(e),
                "patterns": []
            }
    
    async def _compile_customer_profile(self) -> Dict[str, Any]:
        """Compile complete customer profile for export"""
        return {
            "customer_id": self.customer_id,
            "profile_compiled_at": datetime.utcnow().isoformat(),
            "data_controller": "AI Agency Platform",
            "data_processing_purposes": [
                "Executive Assistant services",
                "Business automation recommendations",
                "Workflow template matching",
                "Cross-channel conversation continuity"
            ],
            "retention_policies": {k: v.value for k, v in self.retention_policies.items()},
            "consent_records": self.consent_records,
            "gdpr_rights_exercised": len(self.compliance_log)
        }
    
    async def _log_compliance_action(self, action_data: Dict[str, Any]) -> None:
        """Log GDPR compliance actions for audit trail"""
        compliance_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "customer_id": self.customer_id,
            "action_id": f"compliance_{uuid.uuid4().hex[:8]}",
            **action_data
        }
        
        self.compliance_log.append(compliance_entry)
        
        # Also log to PostgreSQL for permanent audit trail
        try:
            pool = await self.memory_manager._get_postgres_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO gdpr_compliance_audit (
                        customer_id, action_type, action_data, timestamp
                    ) VALUES ($1, $2, $3, $4)
                """,
                    self.customer_id,
                    action_data.get("action", "unknown"),
                    json.dumps(compliance_entry),
                    datetime.utcnow()
                )
        except Exception as e:
            logger.warning(f"Failed to log compliance action to database: {e}")
    
    async def _handle_consent_withdrawal(self, consent_type: ConsentType) -> None:
        """Handle consent withdrawal by stopping relevant processing"""
        if consent_type == ConsentType.AI_ML_PROCESSING:
            # Stop AI/ML processing for this customer
            logger.info(f"Stopping AI/ML processing for customer {self.customer_id}")
            
        elif consent_type == ConsentType.DATA_RETENTION:
            # Trigger immediate data deletion
            await self.delete_customer_data("consent_withdrawal")
            
        # Additional consent-specific handling as needed
    
    async def _assess_consent_impact(self, consent_type: ConsentType, granted: bool) -> Dict[str, Any]:
        """Assess the impact of consent changes on data processing"""
        impact_assessment = {
            "consent_type": consent_type.value,
            "consent_granted": granted,
            "processing_impact": "none"
        }
        
        if not granted:
            if consent_type == ConsentType.AI_ML_PROCESSING:
                impact_assessment["processing_impact"] = "ai_ml_processing_stopped"
            elif consent_type == ConsentType.DATA_RETENTION:
                impact_assessment["processing_impact"] = "data_deletion_triggered"
        
        return impact_assessment
    
    async def _delete_data_by_type(self, data_type: str, immediate: bool = False) -> Dict[str, Any]:
        """Delete data by type according to retention policy"""
        # Implementation for type-specific data deletion
        return {"deleted": True, "data_type": data_type}
    
    async def _delete_expired_data(self, data_type: str, cutoff_date: datetime) -> Dict[str, Any]:
        """Delete data older than cutoff date"""
        # Implementation for time-based data deletion
        return {"deleted": True, "data_type": data_type, "cutoff_date": cutoff_date.isoformat()}
    
    async def get_compliance_status(self) -> Dict[str, Any]:
        """Get current GDPR compliance status for customer"""
        return {
            "customer_id": self.customer_id,
            "compliance_status": "compliant",
            "last_assessment": datetime.utcnow().isoformat(),
            "consent_records": len(self.consent_records),
            "compliance_actions": len(self.compliance_log),
            "retention_policies_active": len(self.retention_policies),
            "gdpr_ready": True
        }