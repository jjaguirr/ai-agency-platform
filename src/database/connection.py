"""
Database Connection Management
Provides secure database connection handling with customer isolation
"""

import os
import asyncio
import logging
from typing import Optional, Dict, Any, AsyncGenerator
from contextlib import asynccontextmanager
import asyncpg
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from datetime import datetime

logger = logging.getLogger(__name__)

class DatabaseConfig:
    """Database configuration management"""
    
    def __init__(self):
        self.host = os.getenv('DB_HOST', 'localhost')
        self.port = int(os.getenv('DB_PORT', '5432'))
        self.database = os.getenv('DB_NAME', 'ai_agency_platform')
        self.user = os.getenv('DB_USER', 'postgres')
        self.password = os.getenv('DB_PASSWORD', 'postgres')
        self.pool_size = int(os.getenv('DB_POOL_SIZE', '20'))
        self.max_overflow = int(os.getenv('DB_MAX_OVERFLOW', '0'))
        self.pool_timeout = int(os.getenv('DB_POOL_TIMEOUT', '30'))
        self.pool_recycle = int(os.getenv('DB_POOL_RECYCLE', '3600'))
        
    @property
    def database_url(self) -> str:
        """Get SQLAlchemy database URL"""
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"
    
    @property
    def asyncpg_url(self) -> str:
        """Get asyncpg connection URL"""
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"

# Global configuration
db_config = DatabaseConfig()

# Global engine and session factory
engine: Optional[sa.engine.Engine] = None
async_session_factory: Optional[async_sessionmaker] = None

def initialize_database():
    """Initialize database engine and session factory"""
    global engine, async_session_factory
    
    if engine is None:
        engine = create_async_engine(
            db_config.database_url,
            pool_size=db_config.pool_size,
            max_overflow=db_config.max_overflow,
            pool_timeout=db_config.pool_timeout,
            pool_recycle=db_config.pool_recycle,
            poolclass=NullPool,  # For better connection management in async context
            echo=os.getenv('DB_ECHO', 'false').lower() == 'true',
            future=True
        )
        
        async_session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        
        logger.info(f"Database engine initialized for {db_config.host}:{db_config.port}/{db_config.database}")

async def get_db_connection() -> asyncpg.Connection:
    """
    Get a direct asyncpg database connection
    Used for raw SQL operations and security testing
    """
    try:
        # Ensure database is initialized
        if engine is None:
            initialize_database()
            
        connection = await asyncpg.connect(db_config.asyncpg_url)
        
        # Set customer isolation session variables
        await connection.execute("SET row_security = on")
        await connection.execute("SET session_replication_role = 'origin'")
        
        logger.debug("Database connection established with security settings")
        return connection
        
    except Exception as e:
        logger.error(f"Failed to establish database connection: {e}")
        raise

@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Get an async SQLAlchemy session with proper cleanup
    """
    if async_session_factory is None:
        initialize_database()
    
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()

async def verify_customer_isolation(customer_id: str, connection: Optional[asyncpg.Connection] = None) -> bool:
    """
    Verify customer data isolation is working correctly
    Critical security function for multi-tenant architecture
    """
    should_close = False
    if connection is None:
        connection = await get_db_connection()
        should_close = True
    
    try:
        # Set current customer context
        await connection.execute(
            "SELECT set_config('app.current_customer_id', $1, true)",
            customer_id
        )
        
        # Test RLS policies are active
        result = await connection.fetchrow(
            "SELECT current_setting('row_security', true) as rls_enabled"
        )
        
        rls_enabled = result['rls_enabled'] == 'on'
        
        if not rls_enabled:
            logger.error(f"Row Level Security not enabled for customer {customer_id}")
            return False
        
        # Verify customer context is set
        current_customer = await connection.fetchval(
            "SELECT current_setting('app.current_customer_id', true)"
        )
        
        if current_customer != customer_id:
            logger.error(f"Customer context mismatch: expected {customer_id}, got {current_customer}")
            return False
        
        logger.info(f"Customer isolation verified for customer {customer_id}")
        return True
        
    except Exception as e:
        logger.error(f"Customer isolation verification failed: {e}")
        return False
    finally:
        if should_close:
            await connection.close()

async def test_database_connectivity() -> Dict[str, Any]:
    """
    Test database connectivity and return status information
    """
    status = {
        "connected": False,
        "latency_ms": None,
        "server_version": None,
        "database": db_config.database,
        "host": db_config.host,
        "port": db_config.port,
        "error": None,
        "rls_enabled": False,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    try:
        start_time = asyncio.get_event_loop().time()
        connection = await get_db_connection()
        end_time = asyncio.get_event_loop().time()
        
        status["latency_ms"] = round((end_time - start_time) * 1000, 2)
        status["connected"] = True
        
        # Get server version
        version_result = await connection.fetchrow("SELECT version()")
        status["server_version"] = version_result['version']
        
        # Check RLS status
        rls_result = await connection.fetchrow(
            "SELECT current_setting('row_security', true) as rls_enabled"
        )
        status["rls_enabled"] = rls_result['rls_enabled'] == 'on'
        
        await connection.close()
        
    except Exception as e:
        status["error"] = str(e)
        logger.error(f"Database connectivity test failed: {e}")
    
    return status

async def create_customer_context(customer_id: str, connection: Optional[asyncpg.Connection] = None) -> bool:
    """
    Create secure customer context for database operations
    """
    should_close = False
    if connection is None:
        connection = await get_db_connection()
        should_close = True
    
    try:
        # Set customer context with security validation
        await connection.execute(
            "SELECT set_config('app.current_customer_id', $1, true)",
            customer_id
        )
        
        # Verify the context was set
        current_customer = await connection.fetchval(
            "SELECT current_setting('app.current_customer_id', true)"
        )
        
        if current_customer != customer_id:
            raise Exception(f"Failed to set customer context: {customer_id}")
        
        logger.debug(f"Customer context created for {customer_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create customer context for {customer_id}: {e}")
        return False
    finally:
        if should_close:
            await connection.close()

# Connection pool management for high-performance operations
class ConnectionPool:
    """
    Managed connection pool for high-performance database operations
    """
    
    def __init__(self, min_size: int = 10, max_size: int = 20):
        self.min_size = min_size
        self.max_size = max_size
        self.pool: Optional[asyncpg.Pool] = None
    
    async def initialize(self):
        """Initialize the connection pool"""
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                db_config.asyncpg_url,
                min_size=self.min_size,
                max_size=self.max_size,
                command_timeout=60,
                server_settings={
                    'row_security': 'on',
                    'session_replication_role': 'origin'
                }
            )
            logger.info(f"Connection pool initialized with {self.min_size}-{self.max_size} connections")
    
    async def get_connection(self) -> asyncpg.Connection:
        """Get a connection from the pool"""
        if self.pool is None:
            await self.initialize()
        return await self.pool.acquire()
    
    async def release_connection(self, connection: asyncpg.Connection):
        """Release a connection back to the pool"""
        if self.pool:
            await self.pool.release(connection)
    
    async def close(self):
        """Close the connection pool"""
        if self.pool:
            await self.pool.close()
            self.pool = None

# Global connection pool instance
connection_pool = ConnectionPool()

# Initialize database when module is imported
def init_db():
    """Initialize database components"""
    try:
        initialize_database()
        logger.info("Database connection module initialized")
    except Exception as e:
        logger.warning(f"Database initialization deferred: {e}")

# Lazy initialization - only initialize when needed
# init_db() - commented out for lazy loading