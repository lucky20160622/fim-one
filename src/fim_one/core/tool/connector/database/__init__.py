"""Database connector infrastructure — drivers, pool, safety, and tool adapter."""

from .adapter import DatabaseToolAdapter
from .base import ColumnInfo, DatabaseDriver, QueryResult, TableInfo
from .meta_tool import (
    DatabaseMetaTool,
    DatabaseStub,
    build_database_meta_tool,
    get_database_tool_mode,
)
from .pool import ConnectionPoolManager
from .safety import SqlSafetyError, validate_sql

__all__ = [
    "ColumnInfo",
    "ConnectionPoolManager",
    "DatabaseDriver",
    "DatabaseMetaTool",
    "DatabaseStub",
    "DatabaseToolAdapter",
    "QueryResult",
    "SqlSafetyError",
    "TableInfo",
    "build_database_meta_tool",
    "get_database_tool_mode",
    "validate_sql",
]
