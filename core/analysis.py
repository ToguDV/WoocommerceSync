import datetime as dt

from django.db.models import Count, Max, Min, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone

from .models import Order, OrderItem, Product

REVENUE_STATUSES = ["completed", "processing"]
ACTIVE_DAYS = 60
CHURN_DAYS = 90

MONTHS_ES = {1: "ene", 2: "feb", 3: "mar", 4: "abr", 5: "may", 6: "jun",
             7: "jul", 8: "ago", 9: "sep", 10: "oct", 11: "nov", 12: "dic"}

STATUS_ES = {
    "pending": "Pendiente", "processing": "Procesando", "on-hold": "En espera",
    "completed": "Completado", "cancelled": "Cancelado",
    "refunded": "Reembolsado", "failed": "Fallido",
}

STATE_ES = {"activo": "Activo", "riesgo": "En riesgo", "perdido": "Perdido"}


def _f(dec):
    return float(dec) if dec is not None else 0.0


def paid_orders():
    return Order.objects.filter(status__in=REVENUE_STATUSES, date_paid_gmt__isnull=False)


def _last_months(n=12):
    now = timezone.now()
    y, m = now.year, now.month
    out = []
    for _ in range(n):
        out.append((y, m))
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


def kpis():
    now = timezone.now()
    d30 = now - dt.timedelta(days=30)
    tot = paid_orders().aggregate(rev=Sum("total"), n=Count("id"))
    last30 = paid_orders().filter(date_paid_gmt__gte=d30).aggregate(rev=Sum("total"), n=Count("id"))
    rev30, n30 = _f(last30["rev"]), last30["n"]
    return {
        "revenue_total": _f(tot["rev"]),
        "orders_total": tot["n"],
        "revenue_30d": rev30,
        "orders_30d": n30,
        "aov": round(rev30 / n30, 2) if n30 else 0,
    }


def revenue_by_day(days=30):
    since = timezone.now() - dt.timedelta(days=days)
    agg = {
        r["day"]: _f(r["total"])
        for r in paid_orders()
        .filter(date_paid_gmt__gte=since)
        .annotate(day=TruncDate("date_paid_gmt"))
        .values("day")
        .annotate(total=Sum("total"))
    }
    labels, values = [], []
    for i in range(days, -1, -1):
        d = (timezone.now() - dt.timedelta(days=i)).date()
        labels.append(d.strftime("%d/%m"))
        values.append(agg.get(d, 0))
    return {"labels": labels, "values": values}


def revenue_by_month(months=12):
    buckets = _last_months(months)
    agg = {
        (r["month"].year, r["month"].month): _f(r["total"])
        for r in paid_orders()
        .annotate(month=TruncMonth("date_paid_gmt"))
        .values("month")
        .annotate(total=Sum("total"))
    }
    labels = [f"{MONTHS_ES[m]} {str(y)[2:]}" for y, m in buckets]
    values = [agg.get(k, 0) for k in buckets]
    return {"labels": labels, "values": values}


def orders_by_status():
    counts = {r["status"]: r["n"] for r in Order.objects.values("status").annotate(n=Count("id"))}
    labels, values = [], []
    for code, label in STATUS_ES.items():
        if counts.get(code):
            labels.append(label)
            values.append(counts[code])
    return {"labels": labels, "values": values}


def top_products(n=5):
    rows = (
        OrderItem.objects.filter(order__status__in=REVENUE_STATUSES)
        .values("name")
        .annotate(units=Sum("quantity"), revenue=Sum("total"))
        .order_by("-revenue")[:n]
    )
    return [
        {"name": r["name"], "units": r["units"], "revenue": _f(r["revenue"])}
        for r in rows
    ]


def customer_rows():
    now = timezone.now()
    rows = (
        paid_orders()
        .exclude(customer_email="")
        .values("customer_email")
        .annotate(
            first_order=Min("date_paid_gmt"),
            last_order=Max("date_paid_gmt"),
            orders=Count("id"),
            spend=Sum("total"),
        )
    )
    out = []
    for r in rows:
        days_since = (now - r["last_order"]).days
        if days_since <= ACTIVE_DAYS:
            state = "activo"
        elif days_since <= CHURN_DAYS:
            state = "riesgo"
        else:
            state = "perdido"
        out.append({
            "email": r["customer_email"],
            "first_order": r["first_order"],
            "last_order": r["last_order"],
            "orders": r["orders"],
            "spend": _f(r["spend"]),
            "avg_order": round(_f(r["spend"]) / r["orders"], 2) if r["orders"] else 0,
            "days_since": days_since,
            "state": state,
            "state_label": STATE_ES[state],
        })
    return sorted(out, key=lambda r: -r["spend"])


def churn_summary():
    rows = customer_rows()
    total = len(rows)
    counts = {"activo": 0, "riesgo": 0, "perdido": 0}
    repeat = 0
    for r in rows:
        counts[r["state"]] += 1
        if r["orders"] > 1:
            repeat += 1
    churn_rate = counts["perdido"] / total * 100 if total else 0
    repeat_rate = repeat / total * 100 if total else 0
    avg_ltv = sum(r["spend"] for r in rows) / total if total else 0
    return {
        "total": total,
        "activos": counts["activo"],
        "riesgo": counts["riesgo"],
        "perdidos": counts["perdido"],
        "churn_rate": round(churn_rate, 1),
        "repeat_rate": round(repeat_rate, 1),
        "avg_ltv": round(avg_ltv, 2),
    }


def new_customers_by_month(months=12):
    buckets = _last_months(months)
    firsts = (
        paid_orders()
        .exclude(customer_email="")
        .values("customer_email")
        .annotate(first=Min("date_paid_gmt"))
    )
    counts = {}
    for r in firsts:
        key = (r["first"].year, r["first"].month)
        counts[key] = counts.get(key, 0) + 1
    labels = [f"{MONTHS_ES[m]} {str(y)[2:]}" for y, m in buckets]
    values = [counts.get(k, 0) for k in buckets]
    return {"labels": labels, "values": values}


def dashboard_data():
    churn = churn_summary()
    paid = paid_orders()
    return {
        "kpis": kpis(),
        "daily": revenue_by_day(30),
        "monthly": revenue_by_month(12),
        "status_chart": orders_by_status(),
        "top_products": top_products(5),
        "churn": churn,
        "low_stock": Product.objects.filter(stock_quantity__lte=5, stock_quantity__isnull=False)
        .order_by("stock_quantity")[:10],
        "avg_orders_per_customer": round(
            paid.count() / churn["total"], 1
        ) if churn["total"] else 0,
    }


def customers_data():
    churn = churn_summary()
    return {
        "churn": churn,
        "customers": customer_rows()[:50],
        "new_customers": new_customers_by_month(12),
    }
