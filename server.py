from __future__ import annotations

import json
import math
import mimetypes
import os
import re
import sys
import threading
import time
from collections import defaultdict, deque
from email import policy
from email.parser import BytesParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SALES = BASE_DIR / "Sales.xlsx"
DEFAULT_PRICES = BASE_DIR / "Prices.xlsx"

_env_path = BASE_DIR / ".env"
if _env_path.exists():
    for _line in _env_path.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
            if _k and _k not in os.environ:
                os.environ[_k] = _v

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent?key="
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

_DEFAULT_DATA = None
_ACTIVE_DATA = None
_data_lock = threading.Lock()

_rate_limits: dict[str, deque] = defaultdict(deque)
_rate_lock = threading.Lock()
_RATE_WINDOW = 60
_RATE_MAX = 10


def _read_best_sheet(source, required_columns, preferred_sheet):
    workbook = pd.ExcelFile(source)
    sheet_names = []
    if preferred_sheet in workbook.sheet_names:
        sheet_names.append(preferred_sheet)
    sheet_names.extend([name for name in workbook.sheet_names if name not in sheet_names])

    for sheet_name in sheet_names:
        frame = pd.read_excel(workbook, sheet_name=sheet_name)
        if all(column in frame.columns for column in required_columns):
            return frame

    raise ValueError(
        f"Could not find a sheet with these columns: {', '.join(required_columns)}"
    )


def _safe_number(value, digits=2):
    if value is None:
        return 0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if math.isnan(number) or math.isinf(number):
        return 0
    return round(number, digits)


def _clean_text(value):
    if pd.isna(value):
        return ""
    return str(value)


def _date_text(value):
    if pd.isna(value):
        return ""
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def _records(frame, columns, limit=8):
    rows = []
    for _, row in frame.loc[:, columns].head(limit).iterrows():
        clean = {}
        for column in columns:
            value = row[column]
            if "DATE" in column or column == "date":
                clean[column] = _date_text(value)
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                clean[column] = _safe_number(value)
            else:
                clean[column] = _clean_text(value)
        rows.append(clean)
    return rows


def _linear_forecast(values, days=30):
    if not values:
        return [0] * days
    if len(values) == 1:
        return [max(0, values[0])] * days

    x_mean = (len(values) - 1) / 2
    y_mean = sum(values) / len(values)
    numerator = sum((i - x_mean) * (value - y_mean) for i, value in enumerate(values))
    denominator = sum((i - x_mean) ** 2 for i in range(len(values))) or 1
    slope = numerator / denominator

    recent = values[-14:] if len(values) >= 14 else values
    recent_avg = sum(recent) / len(recent)
    forecast = []
    for offset in range(1, days + 1):
        blended = (recent_avg * 0.7) + ((values[-1] + slope * offset) * 0.3)
        forecast.append(max(0, blended))
    return forecast


def _status_for_product(margin_pct, trend_pct, profit):
    if profit < 0 or margin_pct < 0.04:
        return (
            "Needs Attention",
            "Sales are not turning into enough profit. Review price, cost, or discounting before pushing more volume.",
            "Review price and cost",
        )
    if trend_pct >= 0.18 and margin_pct >= 0.08:
        return (
            "Growth Opportunity",
            "Sales momentum is improving while profit remains healthy. This product may deserve more focus.",
            "Consider a focused promotion",
        )
    return (
        "Healthy",
        "Sales and profit look steady enough to keep supporting this product.",
        "Keep monitoring",
    )


def _product_insights(sales, prices, merged):
    max_date = sales["SIM_CALENDAR_DATE"].max()
    recent_start = max_date - pd.Timedelta(days=13)
    previous_start = recent_start - pd.Timedelta(days=14)

    product_group = sales.groupby(["MATERIAL_NUMBER", "MATERIAL_DESCRIPTION"], dropna=False)
    latest_prices = (
        prices.sort_values("SIM_CALENDAR_DATE")
        .groupby("MATERIAL_NUMBER", dropna=False)
        .tail(1)
        .set_index("MATERIAL_NUMBER")["PRICE"]
        .to_dict()
    )

    products = []
    for (material, description), group in product_group:
        revenue = group["NET_VALUE"].sum()
        profit = group["CONTRIBUTION_MARGIN"].sum()
        quantity = group["QUANTITY"].sum()
        cost = group["COST"].sum()
        avg_price = revenue / quantity if quantity else 0
        margin_pct = profit / revenue if revenue else 0

        recent_qty = group.loc[group["SIM_CALENDAR_DATE"] >= recent_start, "QUANTITY"].sum()
        previous_qty = group.loc[
            (group["SIM_CALENDAR_DATE"] >= previous_start)
            & (group["SIM_CALENDAR_DATE"] < recent_start),
            "QUANTITY",
        ].sum()
        trend_pct = (recent_qty - previous_qty) / previous_qty if previous_qty else 0

        status, explanation, action = _status_for_product(margin_pct, trend_pct, profit)
        products.append(
            {
                "material": _clean_text(material),
                "description": _clean_text(description),
                "name": f"{_clean_text(description)} ({_clean_text(material)})",
                "revenue": _safe_number(revenue),
                "profit": _safe_number(profit),
                "quantity": _safe_number(quantity, 0),
                "cost": _safe_number(cost),
                "avgPrice": _safe_number(avg_price),
                "currentPrice": _safe_number(latest_prices.get(material, avg_price)),
                "marginPct": _safe_number(margin_pct, 4),
                "trendPct": _safe_number(trend_pct, 4),
                "status": status,
                "explanation": explanation,
                "recommendedAction": action,
            }
        )

    products.sort(key=lambda row: row["revenue"], reverse=True)
    return products


def _ai_insights(products):
    needs_attention = [row for row in products if row["status"] == "Needs Attention"]
    growth = [row for row in products if row["status"] == "Growth Opportunity"]
    healthy = [row for row in products if row["status"] == "Healthy"]

    insights = []
    if needs_attention:
        product = sorted(needs_attention, key=lambda row: row["profit"])[0]
        insights.append(
            {
                "label": "Needs attention",
                "title": f"{product['description']} needs a margin check",
                "body": f"{product['name']} is generating sales, but profit is weak. This may mean costs are rising faster than prices.",
                "action": "Compare its latest price against cost before increasing promotion.",
            }
        )

    if growth:
        product = sorted(growth, key=lambda row: row["trendPct"], reverse=True)[0]
        insights.append(
            {
                "label": "Growth opportunity",
                "title": f"{product['description']} is gaining momentum",
                "body": f"{product['name']} has stronger recent demand and still keeps a healthy profit margin.",
                "action": "Consider extra attention from sales or a short promotion.",
            }
        )

    if healthy:
        product = sorted(healthy, key=lambda row: row["profit"], reverse=True)[0]
        insights.append(
            {
                "label": "Healthy",
                "title": f"{product['description']} is currently dependable",
                "body": f"{product['name']} has steady sales and strong profit, so it is a reliable product right now.",
                "action": "Keep monitoring and protect availability.",
            }
        )

    fallback = [
        {
            "label": "Business insight",
            "title": "Revenue and profit should be reviewed together",
            "body": "A product can sell well but still need attention if the profit it brings in is falling.",
            "action": "Use profit as the tie-breaker when deciding what to prioritize.",
        },
        {
            "label": "Prediction",
            "title": "Recent sales are the best short-term signal",
            "body": "The next-month estimate gives more weight to recent daily sales so the view stays practical.",
            "action": "Check the forecast weekly as new sales arrive.",
        },
        {
            "label": "Recommended action",
            "title": "Price changes should be tested carefully",
            "body": "Products with strong demand can often handle a small price increase better than products with weak sales.",
            "action": "Start with products that have healthy profit and steady demand.",
        },
    ]
    insights.extend(fallback)
    return insights[:3]


def _forecast(sales):
    daily = (
        sales.groupby("SIM_CALENDAR_DATE")
        .agg(revenue=("NET_VALUE", "sum"), quantity=("QUANTITY", "sum"), profit=("CONTRIBUTION_MARGIN", "sum"))
        .sort_index()
    )
    all_dates = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(all_dates, fill_value=0)

    revenue_forecast = _linear_forecast(daily["revenue"].tolist(), 30)
    quantity_forecast = _linear_forecast(daily["quantity"].tolist(), 30)
    profit_forecast = _linear_forecast(daily["profit"].tolist(), 30)

    series = []
    for date, row in daily.iterrows():
        series.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "label": date.strftime("%b %d"),
                "actual": _safe_number(row["revenue"]),
                "forecast": None,
            }
        )

    last_date = daily.index.max()
    for index, value in enumerate(revenue_forecast, start=1):
        date = last_date + pd.Timedelta(days=index)
        series.append(
            {
                "date": date.strftime("%Y-%m-%d"),
                "label": date.strftime("%b %d"),
                "actual": None,
                "forecast": _safe_number(value),
            }
        )

    monthly = (
        sales.assign(month=sales["SIM_CALENDAR_DATE"].dt.strftime("%b %Y"))
        .groupby("month", sort=False)
        .agg(revenue=("NET_VALUE", "sum"), profit=("CONTRIBUTION_MARGIN", "sum"), quantity=("QUANTITY", "sum"))
        .reset_index()
    )
    monthly_rows = [
        {
            "month": row["month"],
            "revenue": _safe_number(row["revenue"]),
            "profit": _safe_number(row["profit"]),
            "quantity": _safe_number(row["quantity"], 0),
        }
        for _, row in monthly.iterrows()
    ]

    expected_revenue = sum(revenue_forecast)
    expected_units = sum(quantity_forecast)
    expected_profit = sum(profit_forecast)
    return {
        "series": series,
        "monthly": monthly_rows,
        "expectedRevenue": _safe_number(expected_revenue),
        "expectedUnits": _safe_number(expected_units, 0),
        "expectedProfit": _safe_number(expected_profit),
        "summary": f"Based on past sales trends, AI expects about {_safe_number(expected_units, 0):,.0f} units next month.",
    }


def _price_impact(sales, merged, products):
    product_daily = (
        merged.groupby(["MATERIAL_NUMBER", "MATERIAL_DESCRIPTION", "SIM_CALENDAR_DATE"], dropna=False)
        .agg(quantity=("QUANTITY", "sum"), price=("PRICE", "mean"), revenue=("NET_VALUE", "sum"), profit=("CONTRIBUTION_MARGIN", "sum"))
        .reset_index()
    )

    by_product = []
    scatter = []
    elasticity_values = []

    for (material, description), group in product_daily.groupby(["MATERIAL_NUMBER", "MATERIAL_DESCRIPTION"], dropna=False):
        clean_group = group.dropna(subset=["price"])
        if clean_group.empty:
            continue

        median_price = clean_group["price"].median()
        low = clean_group[clean_group["price"] <= median_price]
        high = clean_group[clean_group["price"] > median_price]

        if len(low) >= 2 and len(high) >= 2 and low["price"].mean() > 0 and low["quantity"].mean() > 0:
            price_change = (high["price"].mean() - low["price"].mean()) / low["price"].mean()
            qty_change = (high["quantity"].mean() - low["quantity"].mean()) / low["quantity"].mean()
            elasticity = qty_change / price_change if abs(price_change) > 0.01 else -0.45
        else:
            price_change = 0
            qty_change = 0
            elasticity = -0.45

        if elasticity > 0:
            elasticity = -0.3
        elasticity = min(-0.05, max(-2.2, elasticity))
        elasticity_values.append(elasticity)

        impact_pct = elasticity * 0.05
        latest = clean_group.sort_values("SIM_CALENDAR_DATE").tail(1).iloc[0]
        total_revenue = clean_group["revenue"].sum()
        total_profit = clean_group["profit"].sum()
        total_units = clean_group["quantity"].sum()
        expected_revenue_change = total_revenue * ((1.05 * (1 + impact_pct)) - 1)
        signal = "Careful price move"
        if impact_pct > -0.03:
            signal = "Likely manageable"
        elif impact_pct < -0.08:
            signal = "Demand may soften"

        by_product.append(
            {
                "material": _clean_text(material),
                "description": _clean_text(description),
                "name": f"{_clean_text(description)} ({_clean_text(material)})",
                "avgPrice": _safe_number(clean_group["price"].mean()),
                "latestPrice": _safe_number(latest["price"]),
                "priceChangePct": _safe_number(price_change, 4),
                "volumeChangePct": _safe_number(qty_change, 4),
                "priceSensitivity": _safe_number(elasticity, 4),
                "totalRevenue": _safe_number(total_revenue),
                "totalProfit": _safe_number(total_profit),
                "totalUnits": _safe_number(total_units, 0),
                "expectedUnitChangePct": _safe_number(impact_pct, 4),
                "expectedRevenueChange": _safe_number(expected_revenue_change),
                "signal": signal,
            }
        )

        for _, row in clean_group.sample(min(len(clean_group), 4), random_state=7).iterrows():
            scatter.append(
                {
                    "product": f"{_clean_text(description)} ({_clean_text(material)})",
                    "price": _safe_number(row["price"]),
                    "quantity": _safe_number(row["quantity"], 0),
                }
            )

    by_product.sort(key=lambda row: abs(row["expectedRevenueChange"]), reverse=True)
    revenue = sales["NET_VALUE"].sum()
    quantity = sales["QUANTITY"].sum()
    cost = sales["COST"].sum()
    current_profit = sales["CONTRIBUTION_MARGIN"].sum()
    avg_price = revenue / quantity if quantity else 0
    avg_cost = cost / quantity if quantity else 0
    elasticity = sum(elasticity_values) / len(elasticity_values) if elasticity_values else -0.45
    expected_unit_change_pct = elasticity * 0.05
    expected_units = quantity * (1 + expected_unit_change_pct)
    expected_revenue = expected_units * avg_price * 1.05
    expected_profit = expected_revenue - (expected_units * avg_cost)

    return {
        "scatter": scatter[:80],
        "byProduct": by_product,
        "whatIf": {
            "priceChangePct": 0.05,
            "currentRevenue": _safe_number(revenue),
            "expectedRevenue": _safe_number(expected_revenue),
            "revenueChange": _safe_number(expected_revenue - revenue),
            "currentProfit": _safe_number(current_profit),
            "expectedProfit": _safe_number(expected_profit),
            "profitChange": _safe_number(expected_profit - current_profit),
            "currentUnits": _safe_number(quantity, 0),
            "expectedUnits": _safe_number(expected_units, 0),
            "expectedUnitChangePct": _safe_number(expected_unit_change_pct, 4),
        },
        "summary": "When prices rise, sales volume may soften. The estimate below balances the higher price against the expected unit change.",
    }


def build_dashboard(sales_source, prices_source, source_names=None):
    sales = _read_best_sheet(
        sales_source,
        ["MATERIAL_NUMBER", "SIM_CALENDAR_DATE", "QUANTITY", "NET_VALUE", "COST"],
        "Sales",
    )
    prices = _read_best_sheet(
        prices_source,
        ["MATERIAL_NUMBER", "SIM_CALENDAR_DATE", "PRICE"],
        "Pricing_Conditions",
    )

    sales = sales.copy()
    prices = prices.copy()
    sales["SIM_CALENDAR_DATE"] = pd.to_datetime(sales["SIM_CALENDAR_DATE"])
    prices["SIM_CALENDAR_DATE"] = pd.to_datetime(prices["SIM_CALENDAR_DATE"])

    for column in ["QUANTITY", "NET_PRICE", "NET_VALUE", "COST", "CONTRIBUTION_MARGIN"]:
        if column in sales.columns:
            sales[column] = pd.to_numeric(sales[column], errors="coerce").fillna(0)

    if "CONTRIBUTION_MARGIN" not in sales.columns:
        sales["CONTRIBUTION_MARGIN"] = sales["NET_VALUE"] - sales["COST"]

    prices["PRICE"] = pd.to_numeric(prices["PRICE"], errors="coerce")

    merge_keys = ["MATERIAL_NUMBER", "DISTRIBUTION_CHANNEL", "SIM_CALENDAR_DATE"]
    prices_daily = prices.drop_duplicates(merge_keys)
    merged = sales.merge(
        prices_daily[merge_keys + ["PRICE"]],
        on=merge_keys,
        how="left",
        suffixes=("", "_LIST"),
    )
    matched_rows = int(merged["PRICE"].notna().sum())

    products = _product_insights(sales, prices, merged)
    forecast = _forecast(sales)
    price_impact = _price_impact(sales, merged, products)

    revenue = sales["NET_VALUE"].sum()
    profit = sales["CONTRIBUTION_MARGIN"].sum()
    units = sales["QUANTITY"].sum()
    avg_price = revenue / units if units else 0

    source_names = source_names or {"sales": DEFAULT_SALES.name, "prices": DEFAULT_PRICES.name}

    preview_sales_columns = [
        "SIM_CALENDAR_DATE",
        "MATERIAL_NUMBER",
        "MATERIAL_DESCRIPTION",
        "DISTRIBUTION_CHANNEL",
        "QUANTITY",
        "NET_PRICE",
        "NET_VALUE",
        "CONTRIBUTION_MARGIN",
    ]
    preview_price_columns = [
        "SIM_CALENDAR_DATE",
        "MATERIAL_NUMBER",
        "MATERIAL_DESCRIPTION",
        "DISTRIBUTION_CHANNEL",
        "PRICE",
        "CURRENCY",
    ]
    preview_merged_columns = [
        "SIM_CALENDAR_DATE",
        "MATERIAL_NUMBER",
        "MATERIAL_DESCRIPTION",
        "DISTRIBUTION_CHANNEL",
        "QUANTITY",
        "NET_PRICE",
        "PRICE",
        "NET_VALUE",
        "CONTRIBUTION_MARGIN",
    ]

    return {
        "source": {
            "salesFile": source_names.get("sales", "Sales.xlsx"),
            "pricesFile": source_names.get("prices", "Prices.xlsx"),
            "salesRows": int(len(sales)),
            "priceRows": int(len(prices)),
            "matchedRows": matched_rows,
            "matchRate": _safe_number(matched_rows / len(sales), 4) if len(sales) else 0,
            "matchedSuccessfully": matched_rows == len(sales) and len(sales) > 0,
            "dateRange": f"{sales['SIM_CALENDAR_DATE'].min().strftime('%b %d, %Y')} to {sales['SIM_CALENDAR_DATE'].max().strftime('%b %d, %Y')}",
        },
        "kpis": {
            "totalRevenue": _safe_number(revenue),
            "totalProfit": _safe_number(profit),
            "unitsSold": _safe_number(units, 0),
            "averageSellingPrice": _safe_number(avg_price),
            "predictedNextMonthSales": forecast["expectedRevenue"],
            "predictedNextMonthUnits": forecast["expectedUnits"],
            "productCount": len(products),
        },
        "insights": _ai_insights(products),
        "products": products,
        "forecast": forecast,
        "priceImpact": price_impact,
        "preview": {
            "sales": _records(sales, preview_sales_columns),
            "prices": _records(prices, preview_price_columns),
            "matched": _records(merged, preview_merged_columns),
        },
    }


def _fetch_usd_rate():
    try:
        req = Request("https://open.er-api.com/v6/latest/EUR", method="GET")
        with urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            return {"ok": True, "rate": data["rates"]["USD"]}
    except Exception as exc:
        print(f"[Rates] {exc}", file=sys.stderr)
        return {"ok": False, "rate": None}


def get_dashboard_data():
    global _DEFAULT_DATA
    with _data_lock:
        if _ACTIVE_DATA is not None:
            return _ACTIVE_DATA
        if _DEFAULT_DATA is None:
            _DEFAULT_DATA = build_dashboard(DEFAULT_SALES, DEFAULT_PRICES)
        return _DEFAULT_DATA


def _parse_upload(headers, body):
    content_type = headers.get("Content-Type", "")
    message = BytesParser(policy=policy.default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode()
        + body
    )
    files = {}
    if not message.is_multipart():
        return files
    for part in message.iter_parts():
        field_name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        if field_name and filename:
            files[field_name] = {
                "filename": filename,
                "content": BytesIO(part.get_payload(decode=True)),
            }
    return files


def _format_money(value):
    return f"EUR {_safe_number(value):,.0f}"


def _format_units(value):
    return f"{_safe_number(value, 0):,.0f}"


def _format_pct(value):
    return f"{_safe_number(value * 100, 1):,.1f}%"


def _find_product(question, products):
    question_text = question.lower()
    for product in products:
        if product["material"].lower() in question_text:
            return product

    matches = [
        product
        for product in products
        if product["description"].lower() in question_text
        or product["name"].lower() in question_text
    ]
    if matches:
        return sorted(matches, key=lambda row: row["revenue"], reverse=True)[0]
    return None


def _product_summary(product):
    return (
        f"{product['description']} ({product['material']}) is marked {product['status']}. "
        f"It has {_format_money(product['revenue'])} in revenue, "
        f"{_format_money(product['profit'])} in profit, "
        f"{_format_units(product['quantity'])} units sold, and a recent trend of "
        f"{_format_pct(product['trendPct'])}. Recommended action: "
        f"{product['recommendedAction']}."
    )


def _extract_price_change(question):
    q = question.lower()
    match = re.search(r"(-?\d+(?:\.\d+)?)\s*%", q)
    amount = float(match.group(1)) / 100 if match else 0.05
    if amount > 0 and any(term in q for term in ["decrease", "discount", "lower", "reduce", "cut"]):
        amount *= -1
    return max(-0.1, min(0.1, amount))


def _price_scenario(what_if, price_change_pct):
    current_revenue = what_if["currentRevenue"]
    current_profit = what_if["currentProfit"]
    current_units = what_if["currentUnits"]
    sensitivity = (
        what_if["expectedUnitChangePct"] / what_if["priceChangePct"]
        if what_if["priceChangePct"]
        else -0.45
    )
    expected_unit_change_pct = sensitivity * price_change_pct
    unit_factor = max(0, 1 + expected_unit_change_pct)
    price_factor = max(0, 1 + price_change_pct)
    avg_price = current_revenue / current_units if current_units else 0
    avg_cost = (current_revenue - current_profit) / current_units if current_units else 0
    expected_units = current_units * unit_factor
    expected_revenue = expected_units * avg_price * price_factor
    expected_profit = expected_revenue - (expected_units * avg_cost)
    return {
        "priceChangePct": price_change_pct,
        "expectedUnitChangePct": expected_unit_change_pct,
        "expectedRevenue": expected_revenue,
        "expectedProfit": expected_profit,
        "expectedUnits": expected_units,
        "revenueChange": expected_revenue - current_revenue,
        "profitChange": expected_profit - current_profit,
    }


def _price_move_phrase(price_change_pct):
    amount = abs(price_change_pct)
    if price_change_pct > 0:
        return f"increase by {_format_pct(amount)}"
    if price_change_pct < 0:
        return f"decrease by {_format_pct(amount)}"
    return "stay the same"


def _check_rate_limit(ip):
    now = time.time()
    with _rate_lock:
        timestamps = _rate_limits[ip]
        while timestamps and timestamps[0] < now - _RATE_WINDOW:
            timestamps.popleft()
        if len(timestamps) >= _RATE_MAX:
            return False
        timestamps.append(now)
        return True


def _build_system_prompt(data):
    kpis = data["kpis"]
    source = data["source"]
    forecast = data["forecast"]
    products = data["products"][:20]
    product_lines = "\n".join(
        f"  - {p['name']}: {p['status']}, revenue=EUR {p['revenue']:,.0f}, "
        f"profit=EUR {p['profit']:,.0f}, margin={p['marginPct']:.1%}, "
        f"trend={p['trendPct']:+.1%}, action: {p['recommendedAction']}"
        for p in products
    )
    return (
        "You are a sales intelligence assistant. Answer using only the data below. "
        "Be concise (2-4 sentences). If the data is insufficient to answer, say so.\n\n"
        f"Files: {source['salesFile']} + {source['pricesFile']}\n"
        f"Date range: {source['dateRange']}\n"
        f"Match rate: {source['matchRate']:.1%} ({source['matchedRows']:,} of {source['salesRows']:,} rows)\n\n"
        f"KPIs:\n"
        f"  Revenue: EUR {kpis['totalRevenue']:,.0f}\n"
        f"  Profit: EUR {kpis['totalProfit']:,.0f}\n"
        f"  Units sold: {kpis['unitsSold']:,.0f}\n"
        f"  Avg selling price: EUR {kpis['averageSellingPrice']:,.2f}\n"
        f"  Predicted next-month revenue: EUR {kpis['predictedNextMonthSales']:,.0f}\n\n"
        f"Products (top {len(products)} by revenue):\n{product_lines}\n\n"
        f"Forecast:\n"
        f"  Expected next-month revenue: EUR {forecast['expectedRevenue']:,.0f}\n"
        f"  Expected next-month units: {forecast['expectedUnits']:,.0f}\n"
        f"  Expected next-month profit: EUR {forecast['expectedProfit']:,.0f}\n"
    )


def _gemini_answer(question, data):
    if not GEMINI_API_KEY:
        return None
    payload = json.dumps({
        "contents": [{"parts": [{"text": question}]}],
        "systemInstruction": {"parts": [{"text": _build_system_prompt(data)}]},
        "generationConfig": {"maxOutputTokens": 300, "temperature": 0.2},
    }).encode("utf-8")
    req = Request(
        _GEMINI_URL + GEMINI_API_KEY,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception as exc:
        print(f"[Gemini] {exc}", file=sys.stderr)
        return None


def _groq_answer(question, data):
    if not GROQ_API_KEY:
        return None
    payload = json.dumps({
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": _build_system_prompt(data)},
            {"role": "user", "content": question},
        ],
        "max_tokens": 300,
        "temperature": 0.2,
    }).encode("utf-8")
    req = Request(
        _GROQ_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {GROQ_API_KEY}"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        print(f"[Groq] {exc}", file=sys.stderr)
        return None


def _chat_answer(question, data):
    products = data["products"]
    q = (question or "").strip()
    q_lower = q.lower()
    product = _find_product(q_lower, products)

    needs_attention = [row for row in products if row["status"] == "Needs Attention"]
    growth = [row for row in products if row["status"] == "Growth Opportunity"]
    healthy = [row for row in products if row["status"] == "Healthy"]
    _attention_product = sorted(needs_attention, key=lambda r: r["revenue"], reverse=True)[0] if needs_attention else None
    _attention_suggestion = (
        f"Why is {_attention_product['description']} marked Needs Attention?"
        if _attention_product
        else "Which products need attention?"
    )
    suggestions = [
        "Which products should we prioritize?",
        _attention_suggestion,
        "Which products are good promotion candidates?",
        "What happens if prices decrease by 5%?",
        "Were the files matched correctly?",
    ]

    if not q:
        return {
            "answer": "Ask a business question about sales, profit, product status, forecast, price impact, or file matching.",
            "products": [],
            "cards": [],
            "suggestions": suggestions,
        }

    if product and ("why" in q_lower or "marked" in q_lower or "status" in q_lower or product["material"].lower() in q_lower):
        return {
            "answer": _product_summary(product),
            "products": [product],
            "cards": [
                {"label": "AI status", "value": product["status"], "note": product["explanation"]},
                {"label": "Recommended action", "value": product["recommendedAction"], "note": "Use this as the next business step."},
            ],
            "suggestions": suggestions,
        }

    if any(term in q_lower for term in ["prioritize", "focus", "what products", "which products", "top products"]):
        attention_top = sorted(needs_attention, key=lambda row: row["revenue"], reverse=True)[:2]
        growth_top = sorted(growth, key=lambda row: row["trendPct"], reverse=True)[:2]
        names = [f"{row['description']} ({row['material']})" for row in attention_top + growth_top]
        return {
            "answer": (
                "Prioritize products marked Needs Attention first, then review Growth Opportunity products. "
                f"Start with {', '.join(names)}. The first group needs a price or cost review; "
                "the growth group may be useful for focused campaigns."
            ),
            "products": attention_top + growth_top,
            "cards": [
                {"label": "Needs Attention", "value": str(len(needs_attention)), "note": "Review price, cost, or trend before promoting."},
                {"label": "Growth Opportunity", "value": str(len(growth)), "note": "Recent sales are improving and profit is acceptable."},
                {"label": "Healthy", "value": str(len(healthy)), "note": "Keep monitoring and protect availability."},
            ],
            "suggestions": suggestions,
        }

    if any(term in q_lower for term in ["promotion", "campaign", "grow", "growth"]):
        growth_top = sorted(growth, key=lambda row: row["trendPct"], reverse=True)[:4]
        names = [f"{row['description']} ({row['material']})" for row in growth_top]
        return {
            "answer": (
                f"Good promotion candidates are {', '.join(names)}. "
                "They have recent sales momentum and acceptable profit, so they are safer candidates than low-profit products."
            ),
            "products": growth_top,
            "cards": [],
            "suggestions": suggestions,
        }

    if any(term in q_lower for term in ["price change", "price impact", "price increase", "price decrease", "5%", "what if", "if prices", "if we raise", "if we lower", "if we cut", "discount"]):
        scenario = _price_scenario(data["priceImpact"]["whatIf"], _extract_price_change(q_lower))
        move_phrase = _price_move_phrase(scenario["priceChangePct"])
        return {
            "answer": (
                f"If prices {move_phrase}, the estimate expects revenue to change by "
                f"{_format_money(scenario['revenueChange'])}, profit to change by "
                f"{_format_money(scenario['profitChange'])}, and units to change by "
                f"{_format_pct(scenario['expectedUnitChangePct'])}. A lower price may increase units sold but shrink "
                "profit per unit; a higher price may improve profit per unit but soften demand."
            ),
            "products": data["priceImpact"]["byProduct"][:4],
            "cards": [
                {"label": "Expected revenue change", "value": _format_money(scenario["revenueChange"]), "note": "Selected price move balanced against unit changes."},
                {"label": "Expected profit change", "value": _format_money(scenario["profitChange"]), "note": "Profit depends on both price and units sold."},
                {"label": "Expected unit change", "value": _format_pct(scenario["expectedUnitChangePct"]), "note": "Estimated change in quantity sold."},
            ],
            "suggestions": suggestions,
        }

    if any(term in q_lower for term in ["forecast", "next month", "expected sales", "prediction"]):
        forecast = data["forecast"]
        return {
            "answer": (
                f"Based on past sales trends, expected next-month revenue is {_format_money(forecast['expectedRevenue'])}, "
                f"expected units are {_format_units(forecast['expectedUnits'])}, and expected profit is "
                f"{_format_money(forecast['expectedProfit'])}. This is an early estimate based on "
                f"{data['source']['dateRange']}, so use it as a directional planning signal."
            ),
            "products": [],
            "cards": [
                {"label": "Expected revenue", "value": _format_money(forecast["expectedRevenue"]), "note": "Estimated sales value for the next month."},
                {"label": "Expected units", "value": _format_units(forecast["expectedUnits"]), "note": "Estimated quantity sold next month."},
                {"label": "Confidence", "value": "Early estimate", "note": data["source"]["dateRange"]},
            ],
            "suggestions": suggestions,
        }

    if any(term in q_lower for term in ["matched", "match rate", "files matched", "upload"]):
        source = data["source"]
        return {
            "answer": (
                f"The files matched successfully. {source['matchedRows']:,} of {source['salesRows']:,} sales rows "
                f"matched to price records, for a match rate of {_format_pct(source['matchRate'])}. "
                "The match uses product, channel, and date."
            ),
            "products": [],
            "cards": [
                {"label": "Sales rows", "value": f"{source['salesRows']:,}", "note": source["salesFile"]},
                {"label": "Price rows", "value": f"{source['priceRows']:,}", "note": source["pricesFile"]},
                {"label": "Match rate", "value": _format_pct(source["matchRate"]), "note": "Matched by product, channel, and date."},
            ],
            "suggestions": suggestions,
        }

    if any(term in q_lower for term in ["low profit", "low margin", "loss", "losing money", "unprofitable", "poor margin", "worst profit", "least profitable"]):
        low_profit = sorted(needs_attention, key=lambda row: row["profit"])[:4]
        names = [f"{row['description']} ({row['material']})" for row in low_profit]
        return {
            "answer": (
                f"The low-profit products to review first are {', '.join(names)}. "
                "These products should be checked for price, cost, or discounting issues before promotion."
            ),
            "products": low_profit,
            "cards": [],
            "suggestions": suggestions,
        }

    top_products = sorted(products, key=lambda row: row["revenue"], reverse=True)[:3]
    llm_answer = _gemini_answer(q, data) or _groq_answer(q, data)
    if llm_answer:
        return {
            "answer": llm_answer,
            "products": top_products,
            "cards": [],
            "suggestions": suggestions,
        }
    return {
        "answer": (
            "I can answer questions about product priority, product status, forecast, price impact, profit concerns, "
            "and file matching. For a quick starting point, ask which products should be prioritized."
        ),
        "products": top_products,
        "cards": [
            {"label": "Total revenue", "value": _format_money(data["kpis"]["totalRevenue"]), "note": "From the sales file."},
            {"label": "Total profit", "value": _format_money(data["kpis"]["totalProfit"]), "note": "After product cost."},
            {"label": "Products reviewed", "value": str(data["kpis"]["productCount"]), "note": "From matched sales and prices."},
        ],
        "suggestions": suggestions,
    }


class DashboardHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/dashboard":
            self._send_json(get_dashboard_data())
            return
        if parsed.path == "/api/rates":
            self._send_json(_fetch_usd_rate())
            return
        if parsed.path == "/api/reset":
            global _ACTIVE_DATA
            with _data_lock:
                _ACTIVE_DATA = None
            self._send_json({"ok": True, "message": "Default workbook data restored."})
            return
        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        global _ACTIVE_DATA
        parsed = urlparse(self.path)
        if parsed.path == "/api/chat":
            if not _check_rate_limit(self.client_address[0]):
                self._send_json({"ok": False, "error": "Too many requests. Please wait a moment."}, status=429)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                payload = json.loads(body.decode("utf-8") or "{}")
                answer = _chat_answer(payload.get("question", ""), get_dashboard_data())
                self._send_json({"ok": True, **answer})
            except Exception as exc:
                self._send_json({"ok": False, "error": str(exc)}, status=500)
            return

        if parsed.path != "/api/upload":
            self.send_error(404, "Not found")
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            files = _parse_upload(self.headers, body)
            if "sales" not in files or "prices" not in files:
                self._send_json(
                    {"ok": False, "error": "Please upload both Sales.xlsx and Prices.xlsx."},
                    status=400,
                )
                return

            data = build_dashboard(
                files["sales"]["content"],
                files["prices"]["content"],
                {"sales": files["sales"]["filename"], "prices": files["prices"]["filename"]},
            )
            with _data_lock:
                _ACTIVE_DATA = data
            self._send_json({"ok": True, "data": data})
        except Exception as exc:
            self._send_json({"ok": False, "error": str(exc)}, status=500)

    def guess_type(self, path):
        if path.endswith(".js"):
            return "text/javascript"
        if path.endswith(".css"):
            return "text/css"
        return mimetypes.guess_type(path)[0] or "application/octet-stream"

    def _send_json(self, payload, status=200):
        raw = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main():
    port = int(os.environ.get("PORT", sys.argv[1] if len(sys.argv) > 1 else 8000))
    host = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(f"AI Sales Intelligence Dashboard running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
