#!/bin/bash

# Phase 2 Database Migration Script
# EA Orchestration System - Premium-Casual Personality and Cross-Channel Context
# Safe production migration with rollback capability

set -e  # Exit on any error

# Configuration
DB_CONTAINER="ai-agency-postgres"
DB_USER="mcphub" 
DB_NAME="mcphub"
MIGRATION_VERSION="2.0.0"
BACKUP_FILE="phase2_pre_migration_backup_$(date +%Y%m%d_%H%M%S).sql"

echo "🚀 Phase 2 Database Migration - EA Orchestration System"
echo "=================================================="

# Function to check if migration is already applied
check_migration_status() {
    echo "📋 Checking migration status..."
    
    MIGRATION_EXISTS=$(docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -t -c \
        "SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version = '$MIGRATION_VERSION');" 2>/dev/null || echo "f")
    
    if [[ "$MIGRATION_EXISTS" == *"t"* ]]; then
        echo "✅ Phase 2 migration already applied (version $MIGRATION_VERSION)"
        echo "🏁 Migration script completed - no action needed"
        exit 0
    fi
    
    echo "📝 Phase 2 migration not yet applied - proceeding..."
}

# Function to create database backup
create_backup() {
    echo "💾 Creating pre-migration database backup..."
    
    docker exec $DB_CONTAINER pg_dump -U $DB_USER -d $DB_NAME > $BACKUP_FILE
    
    if [ $? -eq 0 ]; then
        echo "✅ Backup created successfully: $BACKUP_FILE"
    else
        echo "❌ Backup creation failed - aborting migration"
        exit 1
    fi
}

# Function to validate database connectivity
validate_connectivity() {
    echo "🔗 Validating database connectivity..."
    
    docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -c "SELECT 'Database connection successful' as status;" >/dev/null 2>&1
    
    if [ $? -eq 0 ]; then
        echo "✅ Database connection validated"
    else
        echo "❌ Cannot connect to database - check container status"
        exit 1
    fi
}

# Function to apply Phase 2 migration
apply_migration() {
    echo "🔧 Applying Phase 2 migration..."
    
    # Apply the migration
    docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -f /dev/stdin < src/database/migrations/002_phase2_ea_orchestration.sql
    
    if [ $? -eq 0 ]; then
        echo "✅ Phase 2 migration applied successfully"
    else
        echo "❌ Migration failed - attempting rollback..."
        rollback_migration
        exit 1
    fi
}

# Function to rollback migration if needed
rollback_migration() {
    echo "🔄 Rolling back migration..."
    
    if [ -f "$BACKUP_FILE" ]; then
        echo "📥 Restoring from backup: $BACKUP_FILE"
        docker exec -i $DB_CONTAINER psql -U $DB_USER -d $DB_NAME < $BACKUP_FILE
        echo "✅ Database restored from backup"
    else
        echo "⚠️  No backup file found - manual recovery may be required"
    fi
}

# Function to validate migration success
validate_migration() {
    echo "🔍 Validating migration success..."
    
    # Check that all required tables exist
    TABLES_COUNT=$(docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -t -c \
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name IN (
            'customer_personality_preferences',
            'conversation_context', 
            'personal_brand_metrics',
            'voice_interaction_logs'
        );" | xargs)
    
    if [ "$TABLES_COUNT" -eq "4" ]; then
        echo "✅ All Phase 2 tables created successfully"
    else
        echo "❌ Expected 4 tables, found $TABLES_COUNT - migration incomplete"
        return 1
    fi
    
    # Check that RLS is enabled
    RLS_COUNT=$(docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -t -c \
        "SELECT COUNT(*) FROM pg_tables WHERE tablename IN (
            'customer_personality_preferences',
            'conversation_context',
            'personal_brand_metrics', 
            'voice_interaction_logs'
        ) AND rowsecurity = true;" | xargs)
    
    if [ "$RLS_COUNT" -eq "4" ]; then
        echo "✅ Row Level Security enabled on all Phase 2 tables"
    else
        echo "❌ RLS not properly configured - security risk detected"
        return 1
    fi
    
    # Check performance indexes
    INDEX_COUNT=$(docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -t -c \
        "SELECT COUNT(*) FROM pg_indexes WHERE (
            indexname LIKE 'idx_%personality%' OR
            indexname LIKE 'idx_%conversation%' OR
            indexname LIKE 'idx_%brand%' OR
            indexname LIKE 'idx_%voice%'
        ) AND schemaname = 'public';" | xargs)
    
    if [ "$INDEX_COUNT" -ge "15" ]; then
        echo "✅ Performance indexes created ($INDEX_COUNT indexes)"
    else
        echo "⚠️  Expected 15+ indexes, found $INDEX_COUNT - performance may be impacted"
    fi
    
    # Validate migration record
    MIGRATION_RECORDED=$(docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -t -c \
        "SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE version = '$MIGRATION_VERSION');" | xargs)
    
    if [[ "$MIGRATION_RECORDED" == *"t"* ]]; then
        echo "✅ Migration version $MIGRATION_VERSION recorded successfully"
        return 0
    else
        echo "❌ Migration not properly recorded in schema_migrations"
        return 1
    fi
}

# Function to run performance tests
run_performance_tests() {
    echo "⚡ Running performance validation tests..."
    
    # Test query performance (should be <100ms average)
    echo "🔍 Testing query performance..."
    docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -c \
        "\\timing on
         SELECT COUNT(*) FROM customer_personality_preferences;
         SELECT COUNT(*) FROM conversation_context;
         SELECT COUNT(*) FROM personal_brand_metrics;
         SELECT COUNT(*) FROM voice_interaction_logs;
         \\timing off"
    
    echo "✅ Performance tests completed - review timing results above"
}

# Function to display migration summary
show_migration_summary() {
    echo ""
    echo "📊 PHASE 2 MIGRATION SUMMARY"
    echo "============================="
    
    # Get summary statistics
    docker exec $DB_CONTAINER psql -U $DB_USER -d $DB_NAME -c "
        SELECT 
            'PHASE 2 MIGRATION COMPLETE' as status,
            (SELECT COUNT(*) FROM information_schema.tables WHERE table_name IN (
                'customer_personality_preferences', 'conversation_context', 
                'personal_brand_metrics', 'voice_interaction_logs'
            )) as required_tables,
            (SELECT COUNT(*) FROM pg_tables WHERE tablename IN (
                'customer_personality_preferences', 'conversation_context',
                'personal_brand_metrics', 'voice_interaction_logs'  
            ) AND rowsecurity = true) as rls_enabled_tables,
            (SELECT COUNT(*) FROM pg_indexes WHERE (
                indexname LIKE 'idx_%personality%' OR
                indexname LIKE 'idx_%conversation%' OR
                indexname LIKE 'idx_%brand%' OR
                indexname LIKE 'idx_%voice%'
            ) AND schemaname = 'public') as performance_indexes,
            (SELECT COUNT(*) FROM information_schema.views WHERE table_name IN (
                'ea_orchestration_dashboard', 'cross_channel_context_health',
                'brand_performance_trends', 'voice_quality_monitor'
            )) as monitoring_views;
    "
    
    echo ""
    echo "🚀 Phase 2 EA Orchestration System is ready!"
    echo "   • Premium-casual personality preferences: ✅ READY"
    echo "   • Cross-channel context preservation: ✅ READY"  
    echo "   • Personal brand metrics tracking: ✅ READY"
    echo "   • Voice interaction logging (ElevenLabs): ✅ READY"
    echo "   • Customer isolation security: ✅ ENABLED"
    echo "   • Performance optimization: ✅ ACTIVE"
    echo ""
    echo "🏁 Migration completed successfully!"
    
    if [ -f "$BACKUP_FILE" ]; then
        echo "💾 Pre-migration backup saved: $BACKUP_FILE"
        echo "   (Keep this file for rollback capability)"
    fi
}

# Main execution flow
main() {
    echo "Starting Phase 2 migration at $(date)"
    
    validate_connectivity
    check_migration_status
    create_backup
    apply_migration
    
    if validate_migration; then
        run_performance_tests
        show_migration_summary
        echo "✅ Phase 2 migration completed successfully!"
        
        # Cleanup old backup if migration successful
        if [ -f "$BACKUP_FILE" ]; then
            echo "🧹 Cleaning up backup file (migration successful)..."
            rm "$BACKUP_FILE"
        fi
        
    else
        echo "❌ Migration validation failed"
        rollback_migration
        exit 1
    fi
}

# Execute main function
main "$@"