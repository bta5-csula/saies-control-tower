"""
Load the SQLite demo warehouse into MySQL.

This script is optional. The live dashboard continues to use SQLite for a
portable demo, while this loader proves that the same warehouse model can be
created and populated in MySQL for advisor review or production deployment.

Usage:
    python scripts/load_mysql_warehouse.py --user root --password your_password

Environment variables are also supported:
    MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
from pathlib import Path
from typing import Iterable

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE_DB = BASE_DIR / "saies_warehouse.db"
DEFAULT_SCHEMA = BASE_DIR / "mysql" / "saies_warehouse_schema.sql"

LOAD_ORDER = [
    "dim_product",
    "dim_location",
    "dim_customer",
    "dim_sales_org",
    "dim_date",
    "dim_simulation",
    "dim_emission_type",
    "dim_emission_scope",
    "fact_sales",
    "fact_pricing",
    "fact_carbon",
]

DATE_COLUMNS = {
    "dim_date": {"SIM_CALENDAR_DATE", "calendar_date"},
}


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def import_mysql_driver():
    try:
        import mysql.connector  # type: ignore

        return "mysql-connector-python", mysql.connector.connect
    except ModuleNotFoundError:
        pass

    try:
        import pymysql  # type: ignore

        return "PyMySQL", pymysql.connect
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "No MySQL Python driver found. Install one first:\n"
            "  pip install mysql-connector-python\n"
            "or:\n"
            "  pip install PyMySQL"
        ) from exc


def quote_identifier(identifier: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", identifier):
        raise ValueError(f"Unsafe MySQL identifier: {identifier}")
    return f"`{identifier}`"


def split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    i = 0

    while i < len(sql):
        char = sql[i]
        next_char = sql[i + 1] if i + 1 < len(sql) else ""

        if quote is None and char == "-" and next_char == "-":
            while i < len(sql) and sql[i] not in "\r\n":
                i += 1
            continue

        if quote is None and char == "/" and next_char == "*":
            i += 2
            while i + 1 < len(sql) and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i += 2
            continue

        if char in ("'", '"', "`"):
            if quote is None:
                quote = char
            elif quote == char:
                if i + 1 < len(sql) and sql[i + 1] == char:
                    current.append(char)
                    i += 1
                else:
                    quote = None

        if char == ";" and quote is None:
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)

        i += 1

    statement = "".join(current).strip()
    if statement:
        statements.append(statement)
    return statements


def connect(args, database: str | None = None):
    driver_name, connect_fn = import_mysql_driver()
    kwargs = {
        "host": args.host,
        "port": args.port,
        "user": args.user,
        "password": args.password,
    }
    if database:
        kwargs["database"] = database
    if driver_name == "PyMySQL":
        kwargs["charset"] = "utf8mb4"
        kwargs["autocommit"] = False
    else:
        kwargs["autocommit"] = False
    return driver_name, connect_fn(**kwargs)


def execute_schema(mysql_con, schema_path: Path, database: str) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    sql = sql.replace("`saies_warehouse`", quote_identifier(database))

    cur = mysql_con.cursor()
    for statement in split_sql_statements(sql):
        cur.execute(statement)
    mysql_con.commit()
    cur.close()


def sqlite_columns(sqlite_con: sqlite3.Connection, table: str) -> list[str]:
    return [row[1] for row in sqlite_con.execute(f"PRAGMA table_info({table})").fetchall()]


def normalize_value(table: str, column: str, value):
    if value is None:
        return None
    if column in DATE_COLUMNS.get(table, set()):
        return str(value).split(" ")[0]
    return value


def sqlite_rows(sqlite_con: sqlite3.Connection, table: str, columns: Iterable[str]) -> list[tuple]:
    cols = list(columns)
    quoted_cols = ", ".join(f'"{col}"' for col in cols)
    rows = sqlite_con.execute(f'SELECT {quoted_cols} FROM "{table}"').fetchall()
    return [
        tuple(normalize_value(table, col, row[col]) for col in cols)
        for row in rows
    ]


def load_tables(sqlite_db: Path, mysql_con, database: str) -> dict[str, int]:
    sqlite_con = sqlite3.connect(sqlite_db)
    sqlite_con.row_factory = sqlite3.Row

    cur = mysql_con.cursor()
    cur.execute(f"USE {quote_identifier(database)}")

    loaded: dict[str, int] = {}
    for table in LOAD_ORDER:
        columns = sqlite_columns(sqlite_con, table)
        rows = sqlite_rows(sqlite_con, table, columns)
        placeholders = ", ".join(["%s"] * len(columns))
        mysql_columns = ", ".join(quote_identifier(col) for col in columns)
        sql = f"INSERT INTO {quote_identifier(table)} ({mysql_columns}) VALUES ({placeholders})"
        if rows:
            cur.executemany(sql, rows)
        loaded[table] = len(rows)
        print(f"  OK {table:20s} {len(rows):>6,} rows")

    mysql_con.commit()
    cur.close()
    sqlite_con.close()
    return loaded


def verify_load(mysql_con, database: str, expected: dict[str, int]) -> None:
    cur = mysql_con.cursor()
    cur.execute(f"USE {quote_identifier(database)}")
    print("\n-- MySQL validation -----------------------------------------")

    for table, expected_count in expected.items():
        cur.execute(f"SELECT COUNT(*) FROM {quote_identifier(table)}")
        actual_count = cur.fetchone()[0]
        status = "OK" if actual_count == expected_count else "MISMATCH"
        print(f"  {status} {table:20s} expected={expected_count:>6,} actual={actual_count:>6,}")

    cur.execute("SELECT ROUND(SUM(NET_VALUE), 2), ROUND(SUM(CONTRIBUTION_MARGIN), 2) FROM fact_sales")
    revenue, profit = cur.fetchone()
    cur.execute("SELECT ROUND(SUM(TOTAL_CO2E_EMISSIONS), 2) FROM fact_carbon")
    total_co2e = cur.fetchone()[0]
    cur.execute(
        """
        SELECT COUNT(DISTINCT INDEX_NAME)
        FROM information_schema.statistics
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME LIKE 'fact\\_%'
          AND INDEX_NAME LIKE 'idx\\_fact\\_%'
        """,
        (database,),
    )
    index_count = cur.fetchone()[0]

    print(f"  Total revenue: {revenue}")
    print(f"  Total profit: {profit}")
    print(f"  Total CO2e emissions: {total_co2e}")
    print(f"  Fact FK indexes: {index_count}")
    cur.close()


def parse_args() -> argparse.Namespace:
    load_dotenv(BASE_DIR / ".env")
    parser = argparse.ArgumentParser(description="Load the SAIES SQLite warehouse into MySQL.")
    parser.add_argument("--host", default=os.environ.get("MYSQL_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("MYSQL_PORT", "3306")))
    parser.add_argument("--user", default=os.environ.get("MYSQL_USER", "root"))
    parser.add_argument("--password", default=os.environ.get("MYSQL_PASSWORD", ""))
    parser.add_argument("--database", default=os.environ.get("MYSQL_DATABASE", "saies_warehouse"))
    parser.add_argument("--sqlite-db", type=Path, default=DEFAULT_SQLITE_DB)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.sqlite_db.exists():
        raise SystemExit(f"SQLite warehouse not found: {args.sqlite_db}")
    if not args.schema.exists():
        raise SystemExit(f"MySQL schema not found: {args.schema}")

    print("-- Connecting to MySQL --------------------------------------")
    driver_name, mysql_con = connect(args)
    print(f"  Driver: {driver_name}")
    print(f"  Server: {args.host}:{args.port}")
    print(f"  Database: {args.database}")

    print("\n-- Creating MySQL schema ------------------------------------")
    execute_schema(mysql_con, args.schema, args.database)

    print("\n-- Loading rows from SQLite ---------------------------------")
    loaded = load_tables(args.sqlite_db, mysql_con, args.database)
    verify_load(mysql_con, args.database, loaded)

    mysql_con.close()
    print("\nDone - MySQL warehouse loaded successfully.")


if __name__ == "__main__":
    main()
