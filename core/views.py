import threading

from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _

from . import analysis
from .models import OrderItem, Product, ProductCategory, SyncLog
from .sync_service import run_sync


def dashboard(request):
    last_sync = SyncLog.objects.first()
    data = analysis.dashboard_data()
    return render(request, "core/dashboard.html", {**data, "last_sync": last_sync})


def product_list(request):
    products = list(Product.objects.prefetch_related("categories").all())
    q = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "")
    if q:
        products = [
            p for p in products
            if q.lower() in p.name.lower() or q.lower() in (p.sku or "").lower()
        ]
    if category_id:
        products = [p for p in products if p.categories.filter(woo_id=category_id).exists()]

    sold_map = {
        r["product_woo_id"]: r["units"]
        for r in OrderItem.objects.values("product_woo_id").annotate(units=Sum("quantity"))
        if r["product_woo_id"]
    }
    for p in products:
        p.sold = sold_map.get(p.woo_id, 0)

    categories = ProductCategory.objects.all()
    return render(
        request,
        "core/products.html",
        {"products": products[:200], "categories": categories, "q": q, "selected_category": category_id},
    )


def customers(request):
    last_sync = SyncLog.objects.first()
    data = analysis.customers_data()
    return render(request, "core/customers.html", {**data, "last_sync": last_sync})


def trigger_sync(request):
    if request.method != "POST":
        return redirect("dashboard")

    running = SyncLog.objects.filter(status=SyncLog.Status.RUNNING).exists()
    if running:
        messages.warning(request, _("Ya hay una sincronización en curso."))
        return redirect(request.POST.get("next", "dashboard"))

    trigger = SyncLog.Trigger.INITIAL if request.POST.get("initial") else SyncLog.Trigger.MANUAL
    thread = threading.Thread(target=run_sync, kwargs={"trigger": trigger}, daemon=True)
    thread.start()
    messages.success(request, _("Sincronización iniciada en segundo plano."))
    return redirect(request.POST.get("next", "dashboard"))
