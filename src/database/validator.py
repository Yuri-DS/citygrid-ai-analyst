"""
SQL Validator for CityGrid AI Analyst.

Validates SQL queries for safety and compliance with CityGrid schema.
"""

import re
import sqlparse
from sqlparse.sql import IdentifierList, Identifier
from sqlparse.tokens import Keyword, DML
from dataclasses import dataclass


@dataclass
class ValidationResult:
    """Result of SQL validation."""
    is_valid: bool
    error: str | None = None
    tables: list[str] | None = None
    query_type: str | None = None


# === Configuration ===

# Allowed tables in CityGrid database
ALLOWED_TABLES = {
    "districts",
    "road_network_nodes",
    "city_objects",
    "sensors",
    "smart_meters",
    "sensor_readings",
    "meter_readings",
    "municipal_events",
    "citizen_requests",
    "public_transport_trips",
}

# Forbidden keywords (dangerous operations)
FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER",
    "TRUNCATE", "EXEC", "EXECUTE", "MERGE", "REPLACE",
    "GRANT", "REVOKE", "COMMIT", "ROLLBACK", "SAVEPOINT",
    "PRAGMA",  # SQLite specific
}

# Large tables that require time filters
LARGE_TABLES = {"sensor_readings", "meter_readings"}

# Query limits
MAX_LIMIT = 50000
DEFAULT_LIMIT = 1000


class SQLValidator:
    """Validates SQL queries for safety and schema compliance."""

    def __init__(
            self,
            allowed_tables: set[str] = ALLOWED_TABLES,
            forbidden_keywords: set[str] = FORBIDDEN_KEYWORDS,
            max_limit: int = MAX_LIMIT,
            require_time_filter_for_large_tables: bool = True,
    ):
        self.allowed_tables = {t.lower() for t in allowed_tables}
        self.forbidden_keywords = {k.upper() for k in forbidden_keywords}
        self.max_limit = max_limit
        self.require_time_filter = require_time_filter_for_large_tables

    def validate(self, sql: str) -> ValidationResult:
        """
        Validate SQL query.
        
        Args:
            sql: SQL query string
            
        Returns:
            ValidationResult with validation status and details
        """
        if not sql or not sql.strip():
            return ValidationResult(False, "Empty query")

        # Normalize
        sql_normalized = sql.strip()

        # Check for multiple statements
        if self._has_multiple_statements(sql_normalized):
            return ValidationResult(False, "Multiple statements not allowed")

        # Check for forbidden keywords
        forbidden = self._check_forbidden_keywords(sql_normalized)
        if forbidden:
            return ValidationResult(
                False,
                f"Forbidden keyword: {forbidden}. Only SELECT queries allowed."
            )

        # Parse query
        try:
            parsed = sqlparse.parse(sql_normalized)[0]
        except Exception as e:
            return ValidationResult(False, f"SQL parse error: {e}")

        # Check query type
        query_type = self._get_query_type(parsed)
        if query_type != "SELECT":
            return ValidationResult(
                False,
                f"Only SELECT queries allowed, got: {query_type or 'UNKNOWN'}"
            )

        # Extract tables
        tables = self._extract_tables(sql_normalized)

        # Check tables against whitelist
        invalid_tables = tables - self.allowed_tables
        if invalid_tables:
            return ValidationResult(
                False,
                f"Unknown tables: {', '.join(invalid_tables)}. "
                f"Allowed: {', '.join(sorted(self.allowed_tables))}"
            )

        # Check time filter for large tables
        if self.require_time_filter:
            large_tables_used = tables & LARGE_TABLES
            if large_tables_used and not self._has_time_filter(sql_normalized):
                return ValidationResult(
                    False,
                    f"Tables {', '.join(large_tables_used)} require a time filter "
                    f"(WHERE ts BETWEEN ... or WHERE ts >= ...)"
                )

        return ValidationResult(
            is_valid=True,
            tables=list(tables),
            query_type=query_type
        )

    def _has_multiple_statements(self, sql: str) -> bool:
        """Check if SQL contains multiple statements."""
        # Remove strings to avoid false positives
        sql_no_strings = re.sub(r"'[^']*'", "", sql)
        sql_no_strings = re.sub(r'"[^"]*"', "", sql_no_strings)
        # Count semicolons (allowing trailing one)
        parts = [p.strip() for p in sql_no_strings.split(";") if p.strip()]
        return len(parts) > 1

    def _check_forbidden_keywords(self, sql: str) -> str | None:
        """Check for forbidden keywords. Returns first found or None."""
        sql_upper = sql.upper()
        # Tokenize to avoid matching substrings
        tokens = re.findall(r'\b[A-Z_]+\b', sql_upper)
        for token in tokens:
            if token in self.forbidden_keywords:
                return token
        return None

    def _get_query_type(self, parsed) -> str | None:
        """Get the type of SQL query (SELECT, INSERT, etc.)."""
        for token in parsed.tokens:
            if token.ttype is DML:
                return token.value.upper()
        return None

    def _extract_tables(self, sql: str) -> set[str]:
        """Extract table names from SQL query."""
        tables = set()

        # Parse with sqlparse
        parsed = sqlparse.parse(sql)[0]

        # Method 1: Look for identifiers after FROM and JOIN
        sql_upper = sql.upper()

        # Simple regex patterns for common cases
        # FROM table
        from_pattern = r'\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        # JOIN table
        join_pattern = r'\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_]*)'

        for match in re.finditer(from_pattern, sql, re.IGNORECASE):
            tables.add(match.group(1).lower())

        for match in re.finditer(join_pattern, sql, re.IGNORECASE):
            tables.add(match.group(1).lower())

        return tables

    def _has_time_filter(self, sql: str) -> bool:
        """Check if query has a time filter (ts column)."""
        sql_lower = sql.lower()
        # Check for common time filter patterns
        patterns = [
            r'\bts\s*(>=|<=|>|<|=|between)\s*',
            r'\bwhere\b.*\bts\b',
            r'\bcreated_ts\s*(>=|<=|>|<|=|between)\s*',
            r'\bstart_ts\s*(>=|<=|>|<|=|between)\s*',
        ]
        for pattern in patterns:
            if re.search(pattern, sql_lower):
                return True
        return False

    def add_limit_if_missing(self, sql: str, limit: int = DEFAULT_LIMIT) -> str:
        """Add LIMIT clause if not present."""
        sql_upper = sql.upper().strip()
        if "LIMIT" not in sql_upper:
            # Remove trailing semicolon if present
            sql = sql.rstrip().rstrip(";")
            return f"{sql} LIMIT {limit}"
        return sql


# === Convenience function ===

_validator = SQLValidator()


def validate_sql(sql: str, add_limit: bool = False) -> tuple[str, ValidationResult]:
    """
    Validate SQL query and optionally add LIMIT clause.

    Args:
        sql: SQL query string
        add_limit: If True, adds LIMIT clause to valid queries

    Returns:
        Tuple of (processed SQL, ValidationResult)
    """
    result = _validator.validate(sql)
    if result.is_valid and add_limit:
        sql = _validator.add_limit_if_missing(sql)
    return sql, result
