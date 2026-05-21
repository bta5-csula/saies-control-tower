# SAIES Warehouse Validation Report

Command used:

```bash
python etl_star_schema.py
```

## Source datasets

| Source | Rows loaded |
|---|---:|
| `Sales.xlsx` / `Sales` | 2,568 |
| `Prices.xlsx` / `Pricing_Conditions` | 1,722 |
| `Carbon Emissions.xlsx` / `Carbon_Emissions` | 2,397 |

## Warehouse table counts

| Table | Rows |
|---|---:|
| `dim_product` | 42 |
| `dim_location` | 12 |
| `dim_customer` | 12 |
| `dim_sales_org` | 7 |
| `dim_date` | 41 |
| `dim_simulation` | 41 |
| `dim_emission_type` | 7 |
| `dim_emission_scope` | 3 |
| `fact_sales` | 2,568 |
| `fact_pricing` | 1,722 |
| `fact_carbon` | 2,397 |

## Key totals

| Metric | Value |
|---|---:|
| Total revenue | EUR 4,634,023.01 |
| Total profit | EUR 386,108.69 |
| Total units sold | 102,898 |
| Total CO2e emissions | 421,694 |
| Warehouse date range | 2022-01-01 to 2022-02-10 |
| Dashboard sales date range | 2022-01-03 to 2022-02-09 |

## Integrity checks

| Check | Result |
|---|---|
| SQLite foreign key declarations exist on all fact tables | Pass |
| Every fact foreign key has an index | Pass |
| Fact foreign key index count | 15 |
| `PRAGMA foreign_key_check` | 0 violations |
| Dashboard reads from `saies_warehouse.db` | Pass |
| Dashboard sales/price match rate | 100% |
| `/api/carbon` summary available | Pass |

## CO2e by emission type

| Emission type | CO2e |
|---|---:|
| Overstock | 142,500 |
| Products Purchased | 124,244 |
| Goods Movement | 98,950 |
| Overhead | 56,000 |

## CO2e by scope

| Scope | CO2e |
|---|---:|
| Direct (Scope 1) | 234,250 |
| Indirect energy (Scope 2) | 28,000 |
| Value chain (Scope 3) | 159,444 |

## Reproducibility notes

- The ETL drops and recreates `saies_warehouse.db` on each run.
- The SQLite schema is created with explicit DDL before data is loaded.
- The MySQL production schema is maintained separately at `mysql/saies_warehouse_schema.sql`.
