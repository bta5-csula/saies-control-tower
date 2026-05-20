"""
etl_star_schema.py
==================
SAIES Control Tower — Star Schema ETL
NSF Undergraduate Research Program, CSULA

Transforms Sales.xlsx and Prices.xlsx into a proper star-schema
data warehouse stored in SQLite (saies_warehouse.db).

Schema
------
Fact tables  : fact_sales, fact_pricing
Dimensions   : dim_product, dim_location, dim_customer,
               dim_sales_org, dim_date, dim_simulation

Usage
-----
    python etl_star_schema.py
    python etl_star_schema.py --sales path/to/Sales.xlsx --prices path/to/Prices.xlsx
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

# ── Paths ────────────────────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent
DB_PATH    = BASE_DIR / "saies_warehouse.db"

DEFAULT_SALES  = BASE_DIR / "Sales.xlsx"
DEFAULT_PRICES = BASE_DIR / "Prices.xlsx"

# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Build dimensions ──────────────────────────────────────────────────────────

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


def build_dim_sales_org(sales: pd.DataFrame) -> pd.DataFrame:
    cols = ["SALES_ORGANIZATION"]
    dim = make_surrogate(sales, cols, "sales_org_key")
    return dim


def build_dim_date(sales: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """
    Union all calendar dates from both sources.
    """
    sales_dates  = sales[["SIM_CALENDAR_DATE", "SIM_DATE", "SIM_PERIOD"]].copy()
    prices_dates = prices[["SIM_CALENDAR_DATE", "SIM_DATE", "SIM_PERIOD"]].copy()
    all_dates = (
        pd.concat([sales_dates, prices_dates])
        .drop_duplicates(subset=["SIM_CALENDAR_DATE"])
        .sort_values("SIM_CALENDAR_DATE")
        .reset_index(drop=True)
    )
    all_dates["SIM_CALENDAR_DATE"] = pd.to_datetime(all_dates["SIM_CALENDAR_DATE"])
    all_dates.insert(0, "date_key", range(1, len(all_dates) + 1))
    return all_dates


def build_dim_simulation(sales: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """
    All unique simulation coordinate combinations.
    """
    s_cols = ["SIM_ROUND", "SIM_STEP", "SIM_ELAPSED_STEPS"]
    p_cols = ["SIM_ROUND", "SIM_STEP", "SIM_ELAPSED_STEPS"]
    combined = pd.concat([sales[s_cols], prices[p_cols]]).drop_duplicates()
    dim = combined.sort_values(["SIM_ROUND", "SIM_STEP"]).reset_index(drop=True)
    dim.insert(0, "sim_key", range(1, len(dim) + 1))
    return dim


# ── Build fact tables ─────────────────────────────────────────────────────────

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
    return fact[fk_cols + measure_cols].reset_index(drop=True)


# ── Write to SQLite ───────────────────────────────────────────────────────────

def write_to_sqlite(tables: dict[str, pd.DataFrame], db_path: Path) -> None:
    if db_path.exists():
        db_path.unlink()  # fresh build every run

    con = sqlite3.connect(db_path)

    # Write dimensions first (no FK enforcement in SQLite, but good practice)
    dim_order = [
        "dim_product", "dim_location", "dim_customer",
        "dim_sales_org", "dim_date", "dim_simulation",
    ]
    fact_order = ["fact_sales", "fact_pricing"]

    for name in dim_order + fact_order:
        df = tables[name]
        df.to_sql(name, con, if_exists="replace", index=False)
        print(f"  ✓ {name:20s}  {len(df):>6,} rows  {len(df.columns):>3} cols")

    con.close()


# ── Validation queries ────────────────────────────────────────────────────────

def validate(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    print("\n── Validation ──────────────────────────────────────────────")

    checks = {
        "Total revenue (EUR)":
            "SELECT ROUND(SUM(NET_VALUE),2) FROM fact_sales",
        "Total profit (EUR)":
            "SELECT ROUND(SUM(CONTRIBUTION_MARGIN),2) FROM fact_sales",
        "Total units sold":
            "SELECT SUM(QUANTITY) FROM fact_sales",
        "Distinct products":
            "SELECT COUNT(*) FROM dim_product",
        "Distinct customers":
            "SELECT COUNT(*) FROM dim_customer",
        "Distinct locations":
            "SELECT COUNT(*) FROM dim_location",
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

    con.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="SAIES Control Tower — Star Schema ETL")
    parser.add_argument("--sales",  default=str(DEFAULT_SALES),  help="Path to Sales.xlsx")
    parser.add_argument("--prices", default=str(DEFAULT_PRICES), help="Path to Prices.xlsx")
    parser.add_argument("--db",     default=str(DB_PATH),        help="Output SQLite path")
    args = parser.parse_args()

    sales_path  = Path(args.sales)
    prices_path = Path(args.prices)
    db_path     = Path(args.db)

    print(f"\n── Loading source files ─────────────────────────────────────")
    print(f"  Sales  : {sales_path}")
    print(f"  Prices : {prices_path}")

    sales  = load_excel(sales_path,  "Sales")
    prices = load_excel(prices_path, "Pricing_Conditions")

    sales["SIM_CALENDAR_DATE"]  = pd.to_datetime(sales["SIM_CALENDAR_DATE"])
    prices["SIM_CALENDAR_DATE"] = pd.to_datetime(prices["SIM_CALENDAR_DATE"])

    # Ensure MATERIAL_CODE / MATERIAL_SIZE / MATERIAL_LABEL exist (some sheets omit them)
    for col in ["MATERIAL_TYPE", "MATERIAL_CODE", "MATERIAL_LABEL"]:
        if col not in sales.columns:
            sales[col] = None

    print(f"  Loaded {len(sales):,} sales rows, {len(prices):,} price rows\n")

    print(f"── Building dimensions ──────────────────────────────────────")
    dim_product    = build_dim_product(sales, prices)
    dim_location   = build_dim_location(sales)
    dim_customer   = build_dim_customer(sales)
    dim_sales_org  = build_dim_sales_org(sales)
    dim_date       = build_dim_date(sales, prices)
    dim_simulation = build_dim_simulation(sales, prices)

    for name, dim in [
        ("dim_product",    dim_product),
        ("dim_location",   dim_location),
        ("dim_customer",   dim_customer),
        ("dim_sales_org",  dim_sales_org),
        ("dim_date",       dim_date),
        ("dim_simulation", dim_simulation),
    ]:
        print(f"  ✓ {name:20s}  {len(dim):>4} rows")

    print(f"\n── Building fact tables ─────────────────────────────────────")
    fact_sales = build_fact_sales(
        sales, dim_product, dim_location, dim_customer,
        dim_sales_org, dim_date, dim_simulation
    )
    fact_pricing = build_fact_pricing(
        prices, dim_product, dim_sales_org, dim_date, dim_simulation
    )
    print(f"  ✓ {'fact_sales':20s}  {len(fact_sales):>4} rows")
    print(f"  ✓ {'fact_pricing':20s}  {len(fact_pricing):>4} rows")

    print(f"\n── Writing to SQLite → {db_path.name} ──────────────────────")
    tables = {
        "dim_product":    dim_product,
        "dim_location":   dim_location,
        "dim_customer":   dim_customer,
        "dim_sales_org":  dim_sales_org,
        "dim_date":       dim_date,
        "dim_simulation": dim_simulation,
        "fact_sales":     fact_sales,
        "fact_pricing":   fact_pricing,
    }
    write_to_sqlite(tables, db_path)

    validate(db_path)

    print(f"\n✅  Done — warehouse saved to: {db_path.resolve()}\n")


if __name__ == "__main__":
    main()
