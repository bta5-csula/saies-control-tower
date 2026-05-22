# SAIES Warehouse ERD — Sales & Pricing

This ERD covers the Sales and Pricing tables of the SAIES warehouse.
The full schema (including Carbon) is in `mysql/saies_warehouse_schema.sql`
and the `.mwb` MySQL Workbench model.

---

## Diagram 1 — Sales Star Schema

`fact_sales` sits at the centre. Each row is one sales order line item from `Sales.xlsx`.
Five dimensions describe who sold what, where, to whom, and when.

```mermaid
erDiagram
    dim_product    ||--o{ fact_sales : product_key
    dim_location   ||--o{ fact_sales : location_key
    dim_customer   ||--o{ fact_sales : customer_key
    dim_sales_org  ||--o{ fact_sales : sales_org_key
    dim_date       ||--o{ fact_sales : date_key
    dim_simulation ||--o{ fact_sales : sim_key

    dim_product {
        INTEGER product_key PK
        TEXT MATERIAL_NUMBER
        TEXT MATERIAL_DESCRIPTION
        TEXT MATERIAL_TYPE
        TEXT MATERIAL_CODE
        TEXT MATERIAL_LABEL
    }

    dim_location {
        INTEGER location_key PK
        TEXT STORAGE_LOCATION
        TEXT REGION
        TEXT AREA
        TEXT CITY
        TEXT COUNTRY
        INTEGER POSTAL_CODE
    }

    dim_customer {
        INTEGER customer_key PK
        INTEGER CUSTOMER_NUMBER
        INTEGER DISTRIBUTION_CHANNEL
    }

    dim_sales_org {
        INTEGER sales_org_key PK
        TEXT SALES_ORGANIZATION
    }

    dim_date {
        INTEGER date_key PK
        TEXT SIM_CALENDAR_DATE
        TEXT calendar_date
        INTEGER year
        INTEGER quarter
        INTEGER month_number
        TEXT month_name
        INTEGER week_number
        INTEGER day_of_week
        INTEGER is_weekend
        INTEGER is_month_end
    }

    dim_simulation {
        INTEGER sim_key PK
        INTEGER SIM_ROUND
        INTEGER SIM_STEP
        INTEGER SIM_ELAPSED_STEPS
    }

    fact_sales {
        INTEGER ROW_ID PK
        INTEGER product_key FK
        INTEGER location_key FK
        INTEGER customer_key FK
        INTEGER sales_org_key FK
        INTEGER date_key FK
        INTEGER sim_key FK
        INTEGER SALES_ORDER_NUMBER
        INTEGER LINE_ITEM
        REAL QUANTITY
        REAL NET_PRICE
        REAL NET_VALUE
        REAL COST
        REAL CONTRIBUTION_MARGIN
    }
```

---

## Diagram 2 — Pricing Star Schema

`fact_pricing` records the **selling/list price** for each product per sales organisation,
distribution channel, and simulation date — sourced from the `Pricing_Conditions` sheet.
This is the price the company charges customers, not the cost to produce the product
(cost is `COST` in `fact_sales`).

```mermaid
erDiagram
    dim_product    ||--o{ fact_pricing : product_key
    dim_sales_org  ||--o{ fact_pricing : sales_org_key
    dim_date       ||--o{ fact_pricing : date_key
    dim_simulation ||--o{ fact_pricing : sim_key

    dim_product {
        INTEGER product_key PK
        TEXT MATERIAL_NUMBER
        TEXT MATERIAL_DESCRIPTION
        TEXT MATERIAL_TYPE
        TEXT MATERIAL_CODE
        TEXT MATERIAL_LABEL
    }

    dim_sales_org {
        INTEGER sales_org_key PK
        TEXT SALES_ORGANIZATION
    }

    dim_date {
        INTEGER date_key PK
        TEXT SIM_CALENDAR_DATE
        TEXT calendar_date
        INTEGER year
        INTEGER quarter
        INTEGER month_number
        TEXT month_name
        INTEGER week_number
        INTEGER day_of_week
        INTEGER is_weekend
        INTEGER is_month_end
    }

    dim_simulation {
        INTEGER sim_key PK
        INTEGER SIM_ROUND
        INTEGER SIM_STEP
        INTEGER SIM_ELAPSED_STEPS
    }

    fact_pricing {
        INTEGER ROW_ID PK
        INTEGER product_key FK
        INTEGER sales_org_key FK
        INTEGER date_key FK
        INTEGER sim_key FK
        INTEGER DISTRIBUTION_CHANNEL
        TEXT DC_NAME
        REAL PRICE
    }
```

---

## Diagram 3 — Combined Sales & Pricing (How They Join)

`fact_sales` and `fact_pricing` share four dimensions and are joined by the application
on `MATERIAL_NUMBER + DISTRIBUTION_CHANNEL + SIM_CALENDAR_DATE` to match each sale
with its corresponding list price.

```mermaid
erDiagram
    dim_product    ||--o{ fact_sales    : product_key
    dim_product    ||--o{ fact_pricing  : product_key
    dim_sales_org  ||--o{ fact_sales    : sales_org_key
    dim_sales_org  ||--o{ fact_pricing  : sales_org_key
    dim_date       ||--o{ fact_sales    : date_key
    dim_date       ||--o{ fact_pricing  : date_key
    dim_simulation ||--o{ fact_sales    : sim_key
    dim_simulation ||--o{ fact_pricing  : sim_key
    dim_location   ||--o{ fact_sales    : location_key
    dim_customer   ||--o{ fact_sales    : customer_key

    fact_sales {
        INTEGER ROW_ID PK
        INTEGER product_key FK
        INTEGER location_key FK
        INTEGER customer_key FK
        INTEGER sales_org_key FK
        INTEGER date_key FK
        INTEGER sim_key FK
        REAL QUANTITY
        REAL NET_PRICE "Actual price per unit billed"
        REAL NET_VALUE "Total line revenue"
        REAL COST "Cost of goods sold"
        REAL CONTRIBUTION_MARGIN
    }

    fact_pricing {
        INTEGER ROW_ID PK
        INTEGER product_key FK
        INTEGER sales_org_key FK
        INTEGER date_key FK
        INTEGER sim_key FK
        INTEGER DISTRIBUTION_CHANNEL
        REAL PRICE "List/catalog selling price"
    }
```

---

## Price fields explained

| Field | Table | What it means |
|---|---|---|
| `PRICE` | `fact_pricing` | List/catalog selling price set in the ERP pricing conditions |
| `NET_PRICE` | `fact_sales` | Actual price per unit charged in a specific sales order |
| `COST` | `fact_sales` | Cost of goods sold per unit (not a selling price) |

`PRICE` and `NET_PRICE` are not redundant — `PRICE` is the reference price from the pricing
master, while `NET_PRICE` is what was actually billed (which can differ due to discounts).
`COST` is entirely separate and represents the production/acquisition cost, not a customer price.

---

## Fact grains

| Fact table | Grain |
|---|---|
| `fact_sales` | One row per sales order line item from `Sales.xlsx` |
| `fact_pricing` | One row per product, sales organisation, distribution channel, and simulation date from `Prices.xlsx` |
