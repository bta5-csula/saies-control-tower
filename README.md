# AI Sales Intelligence Dashboard

A local multi-page web app that turns `Sales.xlsx` and `Prices.xlsx` into business-friendly product recommendations.

## Pages

- Overview Dashboard
- Product Insights
- Forecast
- Price Impact
- Ask Sales AI
- Data Upload / Data Preview

## Run

From this folder:

```powershell
python server.py 8000
```

Then open:

```text
http://127.0.0.1:8000
```

The app uses `Sales.xlsx` and `Prices.xlsx` by default. The Data Upload page can replace those files for the current running session.
