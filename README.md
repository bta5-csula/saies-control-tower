# AI Sales Intelligence Dashboard

A multi-page web dashboard that turns `Sales.xlsx` and `Prices.xlsx` into plain-English business recommendations. Built by the Society for AI in Enterprise Systems (SAIES).

## Features

- **Overview** — KPI summary, recommended product focus, and sales trend chart
- **Product Insights** — Per-product status (Healthy, Growth Opportunity, Needs Attention) with filters and search
- **Forecast** — Next-month revenue, profit, and unit predictions based on historical sales
- **Price Impact** — Slider-based simulator for testing price change scenarios
- **Ask Sales AI** — Plain-English Q&A grounded in the uploaded data, powered by Gemini with a Groq fallback
- **Data Upload** — Upload your own Sales and Prices files; preview the cleaned and matched data

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

The app ships with default sample data. Use the Data Upload page to replace it with your own files for the current session.

## Deployment

The app is designed to run on [Render](https://render.com) as a Python web service:

- **Build command:** `pip install pandas openpyxl requests`
- **Start command:** `python server.py`
- **Environment variables:** Set `GEMINI_API_KEY` and `GROQ_API_KEY` in the Render dashboard

Render injects a `PORT` environment variable automatically; the server reads it on startup.
