"""
etl_star_schema.py
==================
SAIES Control Tower - Star Schema ETL
NSF Undergraduate Research Program, CSULA

Transforms Sales.xlsx and Prices.xlsx into a proper star-schema
data warehouse stored in SQLite (saies_warehouse.db).

Schema
------
Fact tables  : fact_sales, fact_pricing, fact_carbon
Dimensions   : dim_product, dim_location, dim_customer,
               dim_sales_org, dim_date, dim_simulation,
               dim_emission_type, dim_emission_scope

Usage
-----
    python etl_star_schema.py
    python etl_star_schema.py --sales path/to/Sales.xlsx --prices path/to/Prices.xlsx --carbon path/to/Carbon.xlsx
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

# --- Paths -------------------------------------------------------------------
BASE_DIR   = Path(__file__).resolve().parent
DB_PATH    = BASE_DIR / "saies_warehouse.db"

DEFAULT_SALES  = BASE_DIR / "Sales.xlsx"
DEFAULT_PRICES = BASE_DIR / "Prices.xlsx"
DEFAULT_CARBON = BASE_DIR / "Carbon Emissions.xlsx"

# --- Helpers -----------------------------------------------------------------

def load_excel(path: Path, sheet: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name=sheet)
    df.columns = [c.strip().upper() for c in df.columns]
    return df


def make_surrogate(df: pd.DataFrame, natural_keys: list[str], id_col: str) -> pd.DataFrame:
    """
    Return a deduplicated dimension table with a surrogate integer key.
    """
    dim = df[natural_keys].drop_duplicates().reset_index(drop=True)
    dim.insert(0, id_col, range(1, len(dim) + 1))
    return dim


def add_fk(fact: pd.DataFrame, dim: pd.DataFrame,
           join_on: list[str], fk_col: str) -> pd.DataFrame:
    """
    Left-join fact to dim on join_on and attach the surrogate key as fk_col.
    """
    merged = fact.merge(dim[join_on + [fk_col]], on=join_on, how="left")
    return merged


def require_foreign_keys(fact: pd.DataFrame, table_name: str, fk_cols: list[str]) -> None:
    """
    Fail before loading if a fact row could not resolve to its dimension key.
    """
    missing = {col: int(fact[col].isna().sum()) for col in fk_cols if fact[col].isna().any()}
    if missing:
        details = ", ".join(f"{col}={count}" for col, count in missing.items())
        raise ValueError(f"{table_name} has unresolved foreign keys: {details}")


# --- Build dimensions ---------------------------------------------------------

def build_dim_product(sales: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    cols = ["MATERIAL_NUMBER", "MATERIAL_DESCRIPTION",
            "MATERIAL_TYPE", "MATERIAL_CODE", "MATERIAL_LABEL"]
    # prices doesn't have MATERIAL_TYPE/CODE/LABEL, so we source from sales
    dim = make_surrogate(sales, cols, "product_key")
    return dim


def build_dim_location(sales: pd.DataFrame) -> pd.DataFrame:
    cols = ["STORAGE_LOCATION", "REGION", "AREA", "CITY", "COUNTRY", "POSTAL_CODE"]
    dim = make_surrogate(sales, cols, "location_key")
    return dim


def build_dim_customer(sales: pd.DataFrame) -> pd.DataFrame:
    cols = ["CUSTOMER_NUMBER", "DISTRIBUTION_CHANNEL"]
    dim = make_surrogate(sales, cols, "customer_key")
    return dim


def build_dim_sales_org(sales: pd.DataFrame, carbon: pd.DataFrame) -> pd.DataFrame:
    cols = ["SALES_ORGANIZATION"]
    carbon_orgs = carbon[["COMPANY_CODE"]].rename(
        columns={"COMPANY_CODE": "SALES_ORGANIZATION"}
    )
    combined = pd.concat([sales[cols], carbon_orgs], ignore_index=True)
    dim = make_surrogate(combined, cols, "sales_org_key")
    return dim


def build_dim_date(*sources: pd.DataFrame) -> pd.DataFrame:
    """
    Union all calendar dates and add BI-friendly calendar attributes.
    """
    date_cols = ["SIM_CALENDAR_DATE", "SIM_DATE", "SIM_PERIOD"]
    date_frames = [
        source[date_cols].copy()
        for source in sources
        if source is not None and not source.empty
    ]
    all_dates = (
        pd.concat(date_frames)
        .drop_duplicates(subset=["SIM_CALENDAR_DATE"])
        .sort_values("SIM_CALENDAR_DATE")
        .reset_index(drop=True)
    )
    all_dates["SIM_CALENDAR_DATE"] = pd.to_datetime(all_dates["SIM_CALENDAR_DATE"])
    calendar = all_dates["SIM_CALENDAR_DATE"].dt
    all_dates["calendar_date"] = all_dates["SIM_CALENDAR_DATE"].dt.strftime("%Y-%m-%d")
    all_dates["year"] = calendar.year
    all_dates["quarter"] = calendar.quarter
    all_dates["quarter_name"] = "Q" + calendar.quarter.astype(str)
    all_dates["month_number"] = calendar.month
    all_dates["month_name"] = calendar.month_name()
    all_dates["month_abbrev"] = calendar.strftime("%b")
    all_dates["week_number"] = calendar.isocalendar().week.astype(int)
    all_dates["day_of_month"] = calendar.day
    all_dates["day_of_week"] = calendar.dayofweek + 1
    all_dates["day_name"] = calendar.day_name()
    all_dates["is_weekend"] = calendar.dayofweek.isin([5, 6]).astype(int)
    all_dates["is_month_start"] = calendar.is_month_start.astype(int)
    all_dates["is_month_end"] = calendar.is_month_end.astype(int)
    all_dates["is_quarter_end"] = calendar.is_quarter_end.astype(int)
    all_dates["is_year_end"] = calendar.is_year_end.astype(int)
    all_dates.insert(0, "date_key", range(1, len(all_dates) + 1))
    return all_dates


def build_dim_simulation(*sources: pd.DataFrame) -> pd.DataFrame:
    """
    All unique simulation coordinate combinations.
    """
    sim_cols = ["SIM_ROUND", "SIM_STEP", "SIM_ELAPSED_STEPS"]
    combined = pd.concat(
        [
            source[sim_cols]
            for source in sources
            if source is not None and not source.empty
        ]
    ).drop_duplicates()
    dim = combined.sort_values(["SIM_ROUND", "SIM_STEP"]).reset_index(drop=True)
    dim.insert(0, "sim_key", range(1, len(dim) + 1))
    return dim


def build_dim_emission_type(carbon: pd.DataFrame) -> pd.DataFrame:
    cols = ["TYPE", "SUBTYPE"]
    dim = make_surrogate(carbon, cols, "emission_type_key")
    return dim


def build_dim_emission_scope(carbon: pd.DataFrame) -> pd.DataFrame:
    dim = carbon[["SCOPE"]].drop_duplicates().sort_values("SCOPE").reset_index(drop=True)
    dim["SCOPE_NAME"] = dim["SCOPE"].map({
        1: "Direct (Scope 1)",
        2: "Indirect energy (Scope 2)",
        3: "Value chain (Scope 3)",
    })
    dim.insert(0, "scope_key", range(1, len(dim) + 1))
    return dim


# --- Build fact tables --------------------------------------------------------

def build_fact_sales(sales: pd.DataFrame,
                     dim_product: pd.DataFrame,
                     dim_location: pd.DataFrame,
                     dim_customer: pd.DataFrame,
                     dim_sales_org: pd.DataFrame,
                     dim_date: pd.DataFrame,
                     dim_simulation: pd.DataFrame) -> pd.DataFrame:

    fact = sales.copy()
    fact["SIM_CALENDAR_DATE"] = pd.to_datetime(fact["SIM_CALENDAR_DATE"])

    fact = add_fk(fact, dim_product,
                  ["MATERIAL_NUMBER", "MATERIAL_DESCRIPTION",
                   "MATERIAL_TYPE", "MATERIAL_CODE", "MATERIAL_LABEL"],
                  "product_key")
    fact = add_fk(fact, dim_location,
                  ["STORAGE_LOCATION", "REGION", "AREA", "CITY", "COUNTRY", "POSTAL_CODE"],
                  "location_key")
    fact = add_fk(fact, dim_customer,
                  ["CUSTOMER_NUMBER", "DISTRIBUTION_CHANNEL"],
                  "customer_key")
    fact = add_fk(fact, dim_sales_org,
                  ["SALES_ORGANIZATION"],
                  "sales_org_key")
    fact = add_fk(fact, dim_date,
                  ["SIM_CALENDAR_DATE", "SIM_DATE", "SIM_PERIOD"],
                  "date_key")
    fact = add_fk(fact, dim_simulation,
                  ["SIM_ROUND", "SIM_STEP", "SIM_ELAPSED_STEPS"],
                  "sim_key")

    # Keep only measures + FKs
    measure_cols = [
        "ROW_ID", "SALES_ORDER_NUMBER", "LINE_ITEM",
        "QUANTITY", "QUANTITY_DELIVERED", "UNIT",
        "NET_PRICE", "NET_VALUE", "COST", "CURRENCY",
        "CONTRIBUTION_MARGIN", "CONTRIBUTION_MARGIN_PCT",
    ]
    fk_cols = ["product_key", "location_key", "customer_key",
               "sales_org_key", "date_key", "sim_key"]
    require_foreign_keys(fact, "fact_sales", fk_cols)
    return fact[fk_cols + measure_cols].reset_index(drop=True)


def build_fact_pricing(prices: pd.DataFrame,
                       dim_product: pd.DataFrame,
                       dim_sales_org: pd.DataFrame,
                       dim_date: pd.DataFrame,
                       dim_simulation: pd.DataFrame) -> pd.DataFrame:

    fact = prices.copy()
    fact["SIM_CALENDAR_DATE"] = pd.to_datetime(fact["SIM_CALENDAR_DATE"])

    # prices only has MATERIAL_NUMBER + MATERIAL_DESCRIPTION for product
    fact = fact.merge(
        dim_product[["product_key", "MATERIAL_NUMBER", "MATERIAL_DESCRIPTION"]],
        on=["MATERIAL_NUMBER", "MATERIAL_DESCRIPTION"],
        how="left"
    )
    fact = add_fk(fact, dim_sales_org, ["SALES_ORGANIZATION"], "sales_org_key")
    fact = add_fk(fact, dim_date,
                  ["SIM_CALENDAR_DATE", "SIM_DATE", "SIM_PERIOD"],
                  "date_key")
    fact = add_fk(fact, dim_simulation,
                  ["SIM_ROUND", "SIM_STEP", "SIM_ELAPSED_STEPS"],
                  "sim_key")

    measure_cols = [
        "ROW_ID", "DISTRIBUTION_CHANNEL", "DC_NAME", "PRICE", "CURRENCY"
    ]
    fk_cols = ["product_key", "sales_org_key", "date_key", "sim_key"]
    require_foreign_keys(fact, "fact_pricing", fk_cols)
    return fact[fk_cols + measure_cols].reset_index(drop=True)


def build_fact_carbon(carbon: pd.DataFrame,
                      dim_sales_org: pd.DataFrame,
                      dim_date: pd.DataFrame,
                      dim_simulation: pd.DataFrame,
                      dim_emission_type: pd.DataFrame,
                      dim_emission_scope: pd.DataFrame) -> pd.DataFrame:
    fact = carbon.copy()
    fact["SIM_CALENDAR_DATE"] = pd.to_datetime(fact["SIM_CALENDAR_DATE"])
    fact["SALES_ORGANIZATION"] = fact["COMPANY_CODE"]

    fact = add_fk(fact, dim_sales_org, ["SALES_ORGANIZATION"], "sales_org_key")
    fact = add_fk(fact, dim_date,
                  ["SIM_CALENDAR_DATE", "SIM_DATE", "SIM_PERIOD"],
                  "date_key")
    fact = add_fk(fact, dim_simulation,
                  ["SIM_ROUND", "SIM_STEP", "SIM_ELAPSED_STEPS"],
                  "sim_key")
    fact = add_fk(fact, dim_emission_type, ["TYPE", "SUBTYPE"], "emission_type_key")
    fact = add_fk(fact, dim_emission_scope, ["SCOPE"], "scope_key")

    measure_cols = [
        "ROW_ID", "ORIGIN", "DESTINATION", "PRODUCT", "MATERIAL_DOCUMENT",
        "EMISSIONS", "TOTAL_CO2E_EMISSIONS",
    ]
    fk_cols = ["sales_org_key", "date_key", "sim_key", "emission_type_key", "scope_key"]
    require_foreign_keys(fact, "fact_carbon", fk_cols)
    return fact[fk_cols + measure_cols].reset_index(drop=True)


# --- Write to SQLite ----------------------------------------------------------

SQLITE_SCHEMA = """
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS fact_carbon;
DROP TABLE IF EXISTS fact_pricing;
DROP TABLE IF EXISTS fact_sales;
DROP TABLE IF EXISTS dim_simulation;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS dim_sales_org;
DROP TABLE IF EXISTS dim_emission_scope;
DROP TABLE IF EXISTS dim_emission_type;
DROP TABLE IF EXISTS dim_customer;
DROP TABLE IF EXISTS dim_location;
DROP TABLE IF EXISTS dim_product;

CREATE TABLE dim_product (
    product_key INTEGER PRIMARY KEY,
    MATERIAL_NUMBER TEXT NOT NULL,
    MATERIAL_DESCRIPTION TEXT,
    MATERIAL_TYPE TEXT,
    MATERIAL_CODE TEXT,
    MATERIAL_LABEL TEXT
);

CREATE TABLE dim_location (
    location_key INTEGER PRIMARY KEY,
    STORAGE_LOCATION TEXT NOT NULL,
    REGION TEXT,
    AREA TEXT,
    CITY TEXT,
    COUNTRY TEXT,
    POSTAL_CODE TEXT
);

CREATE TABLE dim_customer (
    customer_key INTEGER PRIMARY KEY,
    CUSTOMER_NUMBER INTEGER NOT NULL,
    DISTRIBUTION_CHANNEL INTEGER NOT NULL
);

CREATE TABLE dim_sales_org (
    sales_org_key INTEGER PRIMARY KEY,
    SALES_ORGANIZATION TEXT NOT NULL UNIQUE
);

CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,
    SIM_CALENDAR_DATE TEXT NOT NULL UNIQUE,
    SIM_DATE TEXT NOT NULL,
    SIM_PERIOD INTEGER NOT NULL,
    calendar_date TEXT NOT NULL,
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL,
    quarter_name TEXT NOT NULL,
    month_number INTEGER NOT NULL,
    month_name TEXT NOT NULL,
    month_abbrev TEXT NOT NULL,
    week_number INTEGER NOT NULL,
    day_of_month INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL,
    day_name TEXT NOT NULL,
    is_weekend INTEGER NOT NULL,
    is_month_start INTEGER NOT NULL,
    is_month_end INTEGER NOT NULL,
    is_quarter_end INTEGER NOT NULL,
    is_year_end INTEGER NOT NULL
);

CREATE TABLE dim_simulation (
    sim_key INTEGER PRIMARY KEY,
    SIM_ROUND INTEGER NOT NULL,
    SIM_STEP INTEGER NOT NULL,
    SIM_ELAPSED_STEPS INTEGER NOT NULL,
    UNIQUE (SIM_ROUND, SIM_STEP, SIM_ELAPSED_STEPS)
);

CREATE TABLE dim_emission_type (
    emission_type_key INTEGER PRIMARY KEY,
    TYPE TEXT NOT NULL,
    SUBTYPE TEXT NOT NULL,
    UNIQUE (TYPE, SUBTYPE)
);

CREATE TABLE dim_emission_scope (
    scope_key INTEGER PRIMARY KEY,
    SCOPE INTEGER NOT NULL UNIQUE,
    SCOPE_NAME TEXT NOT NULL
);

CREATE TABLE fact_sales (
    product_key INTEGER NOT NULL,
    location_key INTEGER NOT NULL,
    customer_key INTEGER NOT NULL,
    sales_org_key INTEGER NOT NULL,
    date_key INTEGER NOT NULL,
    sim_key INTEGER NOT NULL,
    ROW_ID INTEGER PRIMARY KEY,
    SALES_ORDER_NUMBER INTEGER,
    LINE_ITEM INTEGER,
    QUANTITY REAL,
    QUANTITY_DELIVERED REAL,
    UNIT TEXT,
    NET_PRICE REAL,
    NET_VALUE REAL,
    COST REAL,
    CURRENCY TEXT,
    CONTRIBUTION_MARGIN REAL,
    CONTRIBUTION_MARGIN_PCT REAL,
    FOREIGN KEY (product_key) REFERENCES dim_product (product_key),
    FOREIGN KEY (location_key) REFERENCES dim_location (location_key),
    FOREIGN KEY (customer_key) REFERENCES dim_customer (customer_key),
    FOREIGN KEY (sales_org_key) REFERENCES dim_sales_org (sales_org_key),
    FOREIGN KEY (date_key) REFERENCES dim_date (date_key),
    FOREIGN KEY (sim_key) REFERENCES dim_simulation (sim_key)
);

CREATE TABLE fact_pricing (
    product_key INTEGER NOT NULL,
    sales_org_key INTEGER NOT NULL,
    date_key INTEGER NOT NULL,
    sim_key INTEGER NOT NULL,
    ROW_ID INTEGER PRIMARY KEY,
    DISTRIBUTION_CHANNEL INTEGER,
    DC_NAME TEXT,
    PRICE REAL,
    CURRENCY TEXT,
    FOREIGN KEY (product_key) REFERENCES dim_product (product_key),
    FOREIGN KEY (sales_org_key) REFERENCES dim_sales_org (sales_org_key),
    FOREIGN KEY (date_key) REFERENCES dim_date (date_key),
    FOREIGN KEY (sim_key) REFERENCES dim_simulation (sim_key)
);

CREATE TABLE fact_carbon (
    sales_org_key INTEGER NOT NULL,
    date_key INTEGER NOT NULL,
    sim_key INTEGER NOT NULL,
    emission_type_key INTEGER NOT NULL,
    scope_key INTEGER NOT NULL,
    ROW_ID INTEGER PRIMARY KEY,
    ORIGIN TEXT,
    DESTINATION TEXT,
    PRODUCT TEXT,
    MATERIAL_DOCUMENT INTEGER,
    EMISSIONS REAL,
    TOTAL_CO2E_EMISSIONS REAL,
    FOREIGN KEY (sales_org_key) REFERENCES dim_sales_org (sales_org_key),
    FOREIGN KEY (date_key) REFERENCES dim_date (date_key),
    FOREIGN KEY (sim_key) REFERENCES dim_simulation (sim_key),
    FOREIGN KEY (emission_type_key) REFERENCES dim_emission_type (emission_type_key),
    FOREIGN KEY (scope_key) REFERENCES dim_emission_scope (scope_key)
);
"""

SQLITE_INDEXES = """
CREATE INDEX idx_fact_sales_product_key ON fact_sales (product_key);
CREATE INDEX idx_fact_sales_location_key ON fact_sales (location_key);
CREATE INDEX idx_fact_sales_customer_key ON fact_sales (customer_key);
CREATE INDEX idx_fact_sales_sales_org_key ON fact_sales (sales_org_key);
CREATE INDEX idx_fact_sales_date_key ON fact_sales (date_key);
CREATE INDEX idx_fact_sales_sim_key ON fact_sales (sim_key);

CREATE INDEX idx_fact_pricing_product_key ON fact_pricing (product_key);
CREATE INDEX idx_fact_pricing_sales_org_key ON fact_pricing (sales_org_key);
CREATE INDEX idx_fact_pricing_date_key ON fact_pricing (date_key);
CREATE INDEX idx_fact_pricing_sim_key ON fact_pricing (sim_key);

CREATE INDEX idx_fact_carbon_sales_org_key ON fact_carbon (sales_org_key);
CREATE INDEX idx_fact_carbon_date_key ON fact_carbon (date_key);
CREATE INDEX idx_fact_carbon_sim_key ON fact_carbon (sim_key);
CREATE INDEX idx_fact_carbon_emission_type_key ON fact_carbon (emission_type_key);
CREATE INDEX idx_fact_carbon_scope_key ON fact_carbon (scope_key);
"""


def write_to_sqlite(tables: dict[str, pd.DataFrame], db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()  # fresh build every run

    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SQLITE_SCHEMA)

    # Write dimensions first so fact-table FK enforcement can run during load.
    dim_order = [
        "dim_product", "dim_location", "dim_customer",
        "dim_sales_org", "dim_date", "dim_simulation",
        "dim_emission_type", "dim_emission_scope",
    ]
    fact_order = ["fact_sales", "fact_pricing", "fact_carbon"]

    for name in dim_order + fact_order:
        df = tables[name]
        df.to_sql(name, con, if_exists="append", index=False)
        print(f"  OK {name:20s}  {len(df):>6,} rows  {len(df.columns):>3} cols")

    con.executescript(SQLITE_INDEXES)
    violations = con.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"SQLite foreign key check failed: {violations[:5]}")

    con.close()


# --- Validation queries -------------------------------------------------------

def validate(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    print("\n-- Validation ------------------------------------------------")

    checks = {
        "Total revenue (EUR)":
            "SELECT ROUND(SUM(NET_VALUE),2) FROM fact_sales",
        "Total profit (EUR)":
            "SELECT ROUND(SUM(CONTRIBUTION_MARGIN),2) FROM fact_sales",
        "Total units sold":
            "SELECT SUM(QUANTITY) FROM fact_sales",
        "Total CO2e emissions":
            "SELECT ROUND(SUM(TOTAL_CO2E_EMISSIONS),2) FROM fact_carbon",
        "Distinct products":
            "SELECT COUNT(*) FROM dim_product",
        "Distinct customers":
            "SELECT COUNT(*) FROM dim_customer",
        "Distinct locations":
            "SELECT COUNT(*) FROM dim_location",
        "Distinct emission types":
            "SELECT COUNT(*) FROM dim_emission_type",
        "Revenue by area":
            """SELECT l.AREA, ROUND(SUM(f.NET_VALUE),0) AS revenue
               FROM fact_sales f JOIN dim_location l USING(location_key)
               GROUP BY l.AREA ORDER BY revenue DESC""",
        "Revenue by product":
            """SELECT p.MATERIAL_DESCRIPTION, ROUND(SUM(f.NET_VALUE),0) AS revenue
               FROM fact_sales f JOIN dim_product p USING(product_key)
               GROUP BY p.MATERIAL_DESCRIPTION ORDER BY revenue DESC""",
        "Avg price by sim round":
            """SELECT s.SIM_ROUND, ROUND(AVG(fp.PRICE),2) AS avg_price
               FROM fact_pricing fp JOIN dim_simulation s USING(sim_key)
               GROUP BY s.SIM_ROUND ORDER BY s.SIM_ROUND""",
        "CO2e by emission type":
            """SELECT et.TYPE, ROUND(SUM(fc.TOTAL_CO2E_EMISSIONS),0) AS co2e
               FROM fact_carbon fc
               JOIN dim_emission_type et USING(emission_type_key)
               GROUP BY et.TYPE ORDER BY co2e DESC""",
    }

    for label, sql in checks.items():
        cur = con.execute(sql)
        rows = cur.fetchall()
        if len(rows) == 1 and len(rows[0]) == 1:
            print(f"  {label}: {rows[0][0]}")
        else:
            print(f"  {label}:")
            for row in rows:
                print(f"    {row}")

    fk_violations = con.execute("PRAGMA foreign_key_check").fetchall()
    index_count = con.execute("""
        SELECT COUNT(*)
        FROM sqlite_master
        WHERE type = 'index' AND name LIKE 'idx_fact_%'
    """).fetchone()[0]
    print(f"  Foreign key violations: {len(fk_violations)}")
    print(f"  Fact FK indexes: {index_count}")

    con.close()


# --- Main ---------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="SAIES Control Tower - Star Schema ETL")
    parser.add_argument("--sales",  default=str(DEFAULT_SALES),  help="Path to Sales.xlsx")
    parser.add_argument("--prices", default=str(DEFAULT_PRICES), help="Path to Prices.xlsx")
    parser.add_argument("--carbon", default=str(DEFAULT_CARBON), help="Path to Carbon Emissions.xlsx")
    parser.add_argument("--db",     default=str(DB_PATH),        help="Output SQLite path")
    args = parser.parse_args()

    sales_path  = Path(args.sales)
    prices_path = Path(args.prices)
    carbon_path = Path(args.carbon)
    db_path     = Path(args.db)

    print("\n-- Loading source files -------------------------------------")
    print(f"  Sales  : {sales_path}")
    print(f"  Prices : {prices_path}")
    print(f"  Carbon : {carbon_path}")

    sales  = load_excel(sales_path,  "Sales")
    prices = load_excel(prices_path, "Pricing_Conditions")
    carbon = load_excel(carbon_path, "Carbon_Emissions")

    sales["SIM_CALENDAR_DATE"]  = pd.to_datetime(sales["SIM_CALENDAR_DATE"])
    prices["SIM_CALENDAR_DATE"] = pd.to_datetime(prices["SIM_CALENDAR_DATE"])
    carbon["SIM_CALENDAR_DATE"] = pd.to_datetime(carbon["SIM_CALENDAR_DATE"])

    # Ensure MATERIAL_CODE / MATERIAL_SIZE / MATERIAL_LABEL exist (some sheets omit them)
    for col in ["MATERIAL_TYPE", "MATERIAL_CODE", "MATERIAL_LABEL"]:
        if col not in sales.columns:
            sales[col] = None

    print(
        f"  Loaded {len(sales):,} sales rows, "
        f"{len(prices):,} price rows, {len(carbon):,} carbon rows\n"
    )

    print("-- Building dimensions --------------------------------------")
    dim_product    = build_dim_product(sales, prices)
    dim_location   = build_dim_location(sales)
    dim_customer   = build_dim_customer(sales)
    dim_sales_org  = build_dim_sales_org(sales, carbon)
    dim_date       = build_dim_date(sales, prices, carbon)
    dim_simulation = build_dim_simulation(sales, prices, carbon)
    dim_emission_type = build_dim_emission_type(carbon)
    dim_emission_scope = build_dim_emission_scope(carbon)

    for name, dim in [
        ("dim_product",    dim_product),
        ("dim_location",   dim_location),
        ("dim_customer",   dim_customer),
        ("dim_sales_org",  dim_sales_org),
        ("dim_date",       dim_date),
        ("dim_simulation", dim_simulation),
        ("dim_emission_type", dim_emission_type),
        ("dim_emission_scope", dim_emission_scope),
    ]:
        print(f"  OK {name:20s}  {len(dim):>4} rows")

    print("\n-- Building fact tables -------------------------------------")
    fact_sales = build_fact_sales(
        sales, dim_product, dim_location, dim_customer,
        dim_sales_org, dim_date, dim_simulation
    )
    fact_pricing = build_fact_pricing(
        prices, dim_product, dim_sales_org, dim_date, dim_simulation
    )
    fact_carbon = build_fact_carbon(
        carbon, dim_sales_org, dim_date, dim_simulation,
        dim_emission_type, dim_emission_scope
    )
    print(f"  OK {'fact_sales':20s}  {len(fact_sales):>4} rows")
    print(f"  OK {'fact_pricing':20s}  {len(fact_pricing):>4} rows")
    print(f"  OK {'fact_carbon':20s}  {len(fact_carbon):>4} rows")

    print(f"\n-- Writing to SQLite -> {db_path.name} ----------------------")
    tables = {
        "dim_product":    dim_product,
        "dim_location":   dim_location,
        "dim_customer":   dim_customer,
        "dim_sales_org":  dim_sales_org,
        "dim_date":       dim_date,
        "dim_simulation": dim_simulation,
        "dim_emission_type": dim_emission_type,
        "dim_emission_scope": dim_emission_scope,
        "fact_sales":     fact_sales,
        "fact_pricing":   fact_pricing,
        "fact_carbon":    fact_carbon,
    }
    write_to_sqlite(tables, db_path)

    validate(db_path)

    print(f"\nDone - warehouse saved to: {db_path.resolve()}\n")


if __name__ == "__main__":
    main()
