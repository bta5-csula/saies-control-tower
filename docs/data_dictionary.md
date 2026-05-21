# SAIES Warehouse Data Dictionary

The warehouse is a star schema built by `etl_star_schema.py` from `Sales.xlsx`, `Prices.xlsx`, and `Carbon Emissions.xlsx`.

## Table summary

| Table | Type | Rows | Grain / purpose |
|---|---:|---:|---|
| `dim_product` | Dimension | 42 | Product/material attributes used by sales and pricing facts. |
| `dim_location` | Dimension | 12 | Storage location and geography attributes. |
| `dim_customer` | Dimension | 12 | Customer number and distribution channel. |
| `dim_sales_org` | Dimension | 7 | Sales organization/company code. |
| `dim_date` | Dimension | 41 | Calendar date plus simulation period fields. |
| `dim_simulation` | Dimension | 41 | Simulation round, step, and elapsed step. |
| `dim_emission_type` | Dimension | 7 | Carbon emission type and subtype. |
| `dim_emission_scope` | Dimension | 3 | Carbon scope classification. |
| `fact_sales` | Fact | 2,568 | One sales order line item. |
| `fact_pricing` | Fact | 1,722 | One product/channel/date price condition. |
| `fact_carbon` | Fact | 2,397 | One carbon emissions activity event. |

## Dimensions

### `dim_product`

Primary key: `product_key`

| Column | Description |
|---|---|
| `product_key` | Surrogate product key. |
| `MATERIAL_NUMBER` | Source material identifier, such as `OO-T01`. |
| `MATERIAL_DESCRIPTION` | Product description, such as Milk or Cheese. |
| `MATERIAL_TYPE` | Source material type. |
| `MATERIAL_CODE` | Product family code, such as `T01`. |
| `MATERIAL_LABEL` | Source label/category for the material. |

### `dim_location`

Primary key: `location_key`

| Column | Description |
|---|---|
| `location_key` | Surrogate location key. |
| `STORAGE_LOCATION` | Source storage location code. |
| `REGION` | Region descriptor. |
| `AREA` | Area descriptor used for regional rollups. |
| `CITY` | City. |
| `COUNTRY` | Country. |
| `POSTAL_CODE` | Postal code. |

### `dim_customer`

Primary key: `customer_key`

| Column | Description |
|---|---|
| `customer_key` | Surrogate customer key. |
| `CUSTOMER_NUMBER` | Source customer number. |
| `DISTRIBUTION_CHANNEL` | Distribution channel associated with the customer. |

### `dim_sales_org`

Primary key: `sales_org_key`

| Column | Description |
|---|---|
| `sales_org_key` | Surrogate sales organization key. |
| `SALES_ORGANIZATION` | Sales organization/company code, such as `O3`. |

### `dim_date`

Primary key: `date_key`

| Column | Description |
|---|---|
| `date_key` | Surrogate date key. |
| `SIM_CALENDAR_DATE` | Source simulation calendar date. |
| `SIM_DATE` | ERPSIM simulation date label. |
| `SIM_PERIOD` | ERPSIM simulation period. |
| `calendar_date` | ISO calendar date string. |
| `year` | Calendar year. |
| `quarter` | Calendar quarter number. |
| `quarter_name` | Quarter label, such as `Q1`. |
| `month_number` | Calendar month number. |
| `month_name` | Calendar month name. |
| `month_abbrev` | Calendar month abbreviation. |
| `week_number` | ISO week number. |
| `day_of_month` | Day number in month. |
| `day_of_week` | Monday=1 through Sunday=7. |
| `day_name` | Calendar day name. |
| `is_weekend` | 1 if Saturday/Sunday, else 0. |
| `is_month_start` | 1 if first day of month, else 0. |
| `is_month_end` | 1 if final day of month, else 0. |
| `is_quarter_end` | 1 if final day of quarter, else 0. |
| `is_year_end` | 1 if final day of year, else 0. |

### `dim_simulation`

Primary key: `sim_key`

| Column | Description |
|---|---|
| `sim_key` | Surrogate simulation key. |
| `SIM_ROUND` | Simulation round. |
| `SIM_STEP` | Step within the simulation round. |
| `SIM_ELAPSED_STEPS` | Total elapsed simulation steps. |

### `dim_emission_type`

Primary key: `emission_type_key`

| Column | Description |
|---|---|
| `emission_type_key` | Surrogate emission type key. |
| `TYPE` | Emission category, such as Goods Movement or Overstock. |
| `SUBTYPE` | Emission subcategory, such as Deliveries or Purchased Energy. |

### `dim_emission_scope`

Primary key: `scope_key`

| Column | Description |
|---|---|
| `scope_key` | Surrogate emission scope key. |
| `SCOPE` | Numeric scope: 1, 2, or 3. |
| `SCOPE_NAME` | Human-readable scope label. |

## Facts

### `fact_sales`

Grain: one row per sales order line item.

Foreign keys: `product_key`, `location_key`, `customer_key`, `sales_org_key`, `date_key`, `sim_key`

Measures and degenerate identifiers:

| Column | Description |
|---|---|
| `ROW_ID` | Source row identifier and fact primary key. |
| `SALES_ORDER_NUMBER` | Degenerate sales order number. |
| `LINE_ITEM` | Degenerate sales order line number. |
| `QUANTITY` | Ordered quantity. |
| `QUANTITY_DELIVERED` | Delivered quantity. |
| `UNIT` | Unit of measure. |
| `NET_PRICE` | Net price. |
| `NET_VALUE` | Revenue/net sales value. |
| `COST` | Cost amount. |
| `CURRENCY` | Currency code. |
| `CONTRIBUTION_MARGIN` | Profit contribution. |
| `CONTRIBUTION_MARGIN_PCT` | Contribution margin percentage. |

### `fact_pricing`

Grain: one row per product, sales organization, distribution channel, and simulation date price condition.

Foreign keys: `product_key`, `sales_org_key`, `date_key`, `sim_key`

| Column | Description |
|---|---|
| `ROW_ID` | Source row identifier and fact primary key. |
| `DISTRIBUTION_CHANNEL` | Distribution channel. |
| `DC_NAME` | Distribution channel name. |
| `PRICE` | Product price. |
| `CURRENCY` | Currency code. |

### `fact_carbon`

Grain: one row per carbon emissions activity event.

Foreign keys: `sales_org_key`, `date_key`, `sim_key`, `emission_type_key`, `scope_key`

| Column | Description |
|---|---|
| `ROW_ID` | Source row identifier and fact primary key. |
| `ORIGIN` | Origin warehouse or vendor code. |
| `DESTINATION` | Destination warehouse code. |
| `PRODUCT` | Product family code when available. |
| `MATERIAL_DOCUMENT` | Source material document number. |
| `EMISSIONS` | Activity-level emissions value. |
| `TOTAL_CO2E_EMISSIONS` | Total CO2e emissions for the activity. |
