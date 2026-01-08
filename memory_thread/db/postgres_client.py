"""
Memory Thread: PostgreSQL Client
=================================
Production-grade database client with:
- Connection pooling (SimpleConnectionPool)
- Automatic retry with exponential backoff
- Health checks
- Graceful error handling
"""

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool
from contextlib import contextmanager
import time
import logging

from memory_thread.config.settings import settings

log = logging.getLogger(__name__)

# Connection pool (singleton)
_connection_pool = None


def _get_pool():
    """Get or create connection pool"""
    global _connection_pool
    if _connection_pool is None:
        try:
            _connection_pool = pool.SimpleConnectionPool(
                minconn=1,
                maxconn=10,
                dbname=settings.POSTGRES_DB,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                host=settings.POSTGRES_SERVER,
                port=settings.POSTGRES_PORT
            )
            log.info("PostgreSQL connection pool created")
        except Exception as e:
            log.error(f"Failed to create connection pool: {e}")
            raise
    return _connection_pool


def get_postgres_connection():
    """Get connection from pool"""
    return _get_pool().getconn()


def return_connection(conn):
    """Return connection to pool"""
    if _connection_pool:
        _connection_pool.putconn(conn)


class PostgresClient:
    """
    Production-grade PostgreSQL client.
    
    Features:
    - Connection pooling
    - Automatic retry (3 attempts)
    - Health check method
    - Context manager for cursor
    """
    
    MAX_RETRIES = 3
    RETRY_DELAY = 0.5  # seconds
    
    def __init__(self):
        self._pool = _get_pool()
    
    @contextmanager
    def get_cursor(self, retry: bool = True):
        """
        Get a database cursor with automatic retry.
        
        Usage:
            with client.get_cursor() as cur:
                cur.execute("SELECT 1")
        """
        conn = None
        attempt = 0
        last_error = None
        
        while attempt < (self.MAX_RETRIES if retry else 1):
            try:
                conn = get_postgres_connection()
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    yield cur
                conn.commit()
                return  # Success - exit
            except psycopg2.OperationalError as e:
                # Connection error - retry
                last_error = e
                attempt += 1
                if attempt < self.MAX_RETRIES:
                    log.warning(f"Database connection failed (attempt {attempt}), retrying...")
                    time.sleep(self.RETRY_DELAY * attempt)
            except Exception as e:
                # Other errors - rollback and raise
                if conn:
                    conn.rollback()
                raise
            finally:
                if conn:
                    return_connection(conn)
        
        # All retries failed
        if last_error:
            log.error(f"Database connection failed after {self.MAX_RETRIES} attempts")
            raise last_error
    
    def health_check(self) -> bool:
        """Check if database is accessible"""
        try:
            with self.get_cursor(retry=False) as cur:
                cur.execute("SELECT 1")
                return True
        except Exception as e:
            log.warning(f"Health check failed: {e}")
            return False
    
    def execute(self, query: str, params: tuple = None) -> list:
        """Execute query and return all results"""
        with self.get_cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall()
    
    def execute_one(self, query: str, params: tuple = None):
        """Execute query and return first result"""
        with self.get_cursor() as cur:
            cur.execute(query, params)
            return cur.fetchone()


def close_pool():
    """Close all connections in pool (for graceful shutdown)"""
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        _connection_pool = None
        log.info("PostgreSQL connection pool closed")

