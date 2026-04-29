"""
Database connection management for CityGrid AI Analyst.
"""

import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from typing import Any

from .validator import validate_sql, ValidationResult


class DatabaseConnection:
    """Manages database connection and query execution."""
    
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._engine = None
    
    @property
    def engine(self):
        """Lazy initialization of database engine."""
        if self._engine is None:
            if not self.db_path.exists():
                raise FileNotFoundError(f"Database not found: {self.db_path}")
            self._engine = create_engine(f"sqlite:///{self.db_path}")
        return self._engine
    
    def execute(
        self, 
        sql: str, 
        validate: bool = True,
        timeout: int = 60
    ) -> tuple[pd.DataFrame | None, str | None]:
        """
        Execute SQL query and return results.
        
        Args:
            sql: SQL query string
            validate: Whether to validate query before execution
            timeout: Query timeout in seconds
            
        Returns:
            Tuple of (DataFrame with results, error message or None)
        """
        # Validate if requested
        if validate:
            result = validate_sql(sql)
            if not result.is_valid:
                return None, f"Validation error: {result.error}"
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(sql))
                df = pd.DataFrame(result.fetchall(), columns=result.keys())
                return df, None
        except SQLAlchemyError as e:
            return None, f"Database error: {str(e)}"
        except Exception as e:
            return None, f"Unexpected error: {str(e)}"
    
    def get_schema_info(self) -> dict[str, list[dict[str, Any]]]:
        """Get schema information for all tables."""
        schema = {}
        
        # Get table list
        tables_df, _ = self.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
            validate=False
        )
        
        if tables_df is None:
            return schema
        
        for table_name in tables_df["name"]:
            # Get column info
            columns_df, _ = self.execute(
                f"PRAGMA table_info({table_name})",
                validate=False
            )
            if columns_df is not None:
                schema[table_name] = columns_df.to_dict("records")
        
        return schema
    
    def get_table_sample(self, table_name: str, limit: int = 5) -> pd.DataFrame | None:
        """Get sample rows from a table."""
        df, _ = self.execute(
            f"SELECT * FROM {table_name} LIMIT {limit}",
            validate=False  # We trust internal calls
        )
        return df


# === Global connection instance ===

_connection: DatabaseConnection | None = None

def get_connection(db_path: str | Path | None = None) -> DatabaseConnection:
    """Get or create database connection."""
    global _connection
    
    if db_path is not None:
        _connection = DatabaseConnection(db_path)
    elif _connection is None:
        # Default path
        default_path = Path(__file__).parent.parent.parent / "data" / "citygrid.db"
        _connection = DatabaseConnection(default_path)
    
    return _connection
