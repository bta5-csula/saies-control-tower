# AI Sales Intelligence Dashboard

A multi-page web dashboard that turns `Sales.xlsx` and `Prices.xlsx` into plain-English business recommendations. Built by the Society for AI in Enterprise Systems (SAIES) at California State University, Los Angeles.

**Live demo:** https://saies-sales-ai-dashboard.onrender.com/

## Features

- **Overview** — KPI summary, recommended product focus, and sales trend chart
- **Product Insights** — Per-product status (Healthy, Growth Opportunity, Needs Attention) with filters and search
- **Forecast** — Next-month revenue, profit, and unit predictions based on historical sales
- **Price Impact** — Slider-based simulator for testing price change scenarios
- **Ask Sales AI** — Plain-English Q&A grounded in the uploaded data, powered by Gemini with a Groq fallback
- **Data Upload** — Upload your own Sales and Prices files; preview the cleaned and matched data

## Data warehouse

The live dashboard reads from `saies_warehouse.db`, a SQLite warehouse rebuilt by:

```bash
python etl_star_schema.py
```

The ETL builds a star schema with explicit primary keys, foreign keys, and indexes on every fact-table foreign key. `dim_date` includes BI-friendly calendar attributes such as year, quarter, month name, week number, day of week, weekend flags, and period-end flags. Carbon emissions are loaded from `Carbon Emissions.xlsx` into `fact_carbon` during the same build, with emission type and scope normalized into dimensions.

SQLite is used for the local and Render demo because it ships as a single file with the app. MySQL design artifacts remain in `mysql/` for the advisor-facing ERD/schema package; use `mysql/saies_warehouse_schema.sql` if the deployment needs to be moved to a MySQL server.

Advisor-facing warehouse documentation:

- `docs/warehouse_erd.md`
- `docs/data_dictionary.md`
- `docs/validation_report.md`
- `mysql/saies_warehouse_schema.sql`
- `mysql/saies_warehouse_model.mwb`
- `mysql/saies_warehouse_erd_all_diagrams.pdf`

Optional MySQL load path:

```bash
pip install -r requirements-mysql.txt
python etl_star_schema.py
python scripts/load_mysql_warehouse.py --user root --password your_mysql_password
```

The MySQL loader recreates the `saies_warehouse` schema from `mysql/saies_warehouse_schema.sql`, copies the rows from `saies_warehouse.db`, and prints validation totals. The website still uses SQLite unless you intentionally change the runtime configuration.

## Prerequisites

- Python 3.9 or later
- The following packages:

```
pip install pandas openpyxl requests
```

## Setup

1. Clone the repository:

```bash
git clone https://github.com/bta5-csula/saies-control-tower.git
cd saies-control-tower
```

2. Create a `.env` file in the project root with your API keys:

```
GEMINI_API_KEY=your_gemini_key_here
GROQ_API_KEY=your_groq_key_here
```

The app works without API keys — keyword-based answers will still run. The AI chat falls back to Groq if Gemini is unavailable, and to keyword answers if neither key is set.

3. Run the server:

```bash
python server.py
```

Then open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

## Data format

| File | Required columns |
|---|---|
| `Sales.xlsx` | Date, Material/Product, Revenue, Cost, Quantity |
| `Prices.xlsx` | Date, Material/Product, Price, Distribution channel |
| `Carbon Emissions.xlsx` | Company code, simulation date/step, emission type, scope, total CO2e |

The app ships with default sample data. Use the Data Upload page to replace it with your own files for the current session.

## Deployment

The app is designed to run on [Render](https://render.com) as a Python web service:

- **Build command:** `pip install pandas openpyxl requests`
- **Start command:** `python server.py`
- **Environment variables:** Set `GEMINI_API_KEY` and `GROQ_API_KEY` in the Render dashboard

Render injects a `PORT` environment variable automatically; the server reads it on startup.
