"""AURA SQLite Database subsystem — sample employee database and query execution."""
from __future__ import annotations
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_DB_PATH = Path("./data/employees.db")


def get_db_path() -> Path:
    db_url = os.getenv("DATABASE_URL")
    if db_url and "sqlite:" in db_url:
        clean = db_url.split("sqlite:///", 1)[-1] if "sqlite:///" in db_url else db_url.split("sqlite://", 1)[-1]
        p = Path(clean)
    else:
        env_path = os.getenv("AURA_SQLITE_PATH")
        if env_path:
            p = Path(env_path)
        else:
            p = DEFAULT_DB_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    return p



def init_sample_database(db_path: Optional[Path] = None) -> Path:
    """Initialize SQLite database with a rich sample employee and department dataset."""
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()

    # Create departments table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS departments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        budget REAL NOT NULL,
        manager TEXT NOT NULL
    );
    """)

    # Create employees table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        department TEXT NOT NULL,
        role TEXT NOT NULL,
        salary REAL NOT NULL,
        hire_date TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE
    );
    """)

    # Seed departments if empty
    cursor.execute("SELECT COUNT(*) FROM departments;")
    if cursor.fetchone()[0] == 0:
        departments_data = [
            (1, "Engineering", 2500000.0, "Alice Johnson"),
            (2, "Product", 1200000.0, "David Kim"),
            (3, "Security", 950000.0, "Elena Rostova"),
            (4, "Marketing", 800000.0, "Marcus Vance"),
            (5, "Human Resources", 600000.0, "Julia Chen"),
        ]
        cursor.executemany("INSERT INTO departments (id, name, budget, manager) VALUES (?, ?, ?, ?);", departments_data)

    # Seed employees if empty
    cursor.execute("SELECT COUNT(*) FROM employees;")
    if cursor.fetchone()[0] == 0:
        employees_data = [
            (101, "Alice Johnson", "Engineering", "VP of Engineering", 185000.0, "2020-01-15", "alice@company.com"),
            (102, "Bob Smith", "Engineering", "Senior Backend Engineer", 140000.0, "2021-03-20", "bob@company.com"),
            (103, "Charlie Davis", "Engineering", "Full Stack Developer", 115000.0, "2022-07-10", "charlie@company.com"),
            (104, "David Kim", "Product", "Head of Product", 160000.0, "2020-05-12", "david@company.com"),
            (105, "Elena Rostova", "Security", "Principal Security Architect", 175000.0, "2019-11-01", "elena@company.com"),
            (106, "Frank Miller", "Engineering", "DevOps / SRE Lead", 145000.0, "2021-09-15", "frank@company.com"),
            (107, "Grace Hopper", "Security", "AppSec Analyst", 125000.0, "2023-02-01", "grace@company.com"),
            (108, "Hannah Abbott", "Marketing", "Growth Lead", 105000.0, "2022-11-15", "hannah@company.com"),
            (109, "Ian Malcolm", "Product", "Data Scientist", 135000.0, "2021-08-20", "ian@company.com"),
            (110, "Julia Chen", "Human Resources", "People Operations Manager", 95000.0, "2023-04-10", "julia@company.com"),
        ]
        cursor.executemany(
            "INSERT INTO employees (id, name, department, role, salary, hire_date, email) VALUES (?, ?, ?, ?, ?, ?, ?);",
            employees_data,
        )

    conn.commit()
    conn.close()
    return path


def format_sql_cli_table(columns: List[str], rows: List[List[Any]], rows_affected: Optional[int] = None) -> str:
    """Format query results in the standard CLI tabular SQL format."""
    if not columns and rows_affected is not None:
        return f"Query OK, {rows_affected} row{'s' if rows_affected != 1 else ''} affected."
    if not columns:
        return "Empty set (0 rows)."

    # Format values as clean strings
    str_rows: List[List[str]] = []
    for row in rows:
        formatted_row = []
        for v in row:
            if v is None:
                formatted_row.append("NULL")
            elif isinstance(v, float):
                # If it's a salary-like number, format cleanly
                if v.is_integer():
                    formatted_row.append(str(int(v)))
                else:
                    formatted_row.append(f"{v:.2f}")
            else:
                formatted_row.append(str(v))
        str_rows.append(formatted_row)

    # Compute maximum width per column
    widths = [len(col) for col in columns]
    for r in str_rows:
        for i, val in enumerate(r):
            widths[i] = max(widths[i], len(val))

    # Construct the box borders
    border = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    header = "| " + " | ".join(columns[i].ljust(widths[i]) for i in range(len(columns))) + " |"

    lines = [border, header, border]
    for r in str_rows:
        row_str = "| " + " | ".join(r[i].ljust(widths[i]) for i in range(len(columns))) + " |"
        lines.append(row_str)
    lines.append(border)
    lines.append(f"({len(rows)} row{'s' if len(rows) != 1 else ''} in set)")
    return "\n".join(lines)


def run_sqlite_query(query: str, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Execute an SQL query against the SQLite database and return structured results + CLI table."""
    path = db_path or get_db_path()
    if not path.exists():
        init_sample_database(path)

    query_stripped = query.strip()
    is_select = query_stripped.upper().startswith(("SELECT", "PRAGMA", "EXPLAIN", "WITH"))

    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()

    try:
        cursor.execute(query)
        if is_select:
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            row_list = [list(r) for r in rows]
            table_str = format_sql_cli_table(columns, row_list)
            return {
                "success": True,
                "is_mutating": False,
                "query": query,
                "columns": columns,
                "rows": row_list,
                "count": len(row_list),
                "row_count": len(row_list),
                "table": table_str,
            }

        else:
            conn.commit()
            rows_affected = cursor.rowcount
            table_str = format_sql_cli_table([], [], rows_affected=rows_affected)
            return {
                "success": True,
                "is_mutating": True,
                "query": query,
                "rows_affected": rows_affected,
                "table": table_str,
            }
    except Exception as e:
        return {
            "success": False,
            "query": query,
            "error": str(e),
            "table": f"ERROR: {e}",
        }
    finally:
        conn.close()
