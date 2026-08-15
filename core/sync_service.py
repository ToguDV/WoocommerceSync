import logging
from datetime import datetime, timedelta, timezone

from django.db import transaction
from django.utils import timezone as dj_timezone

from .models import Order, OrderItem, Product, ProductCategory, ProductVariation, SyncLog
from .woo_client import WooClient

logger = logging.getLogger(__name__)

try:
    import urllib3

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    pass

ORDER_STATUSES_ALL = "any"


def _parse_gmt(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dj_timezone.is_naive(dt):
            dt = dj_timezone.make_aware(dt, timezone.utc)
        return dt
    except ValueError:
        return None


def _to_decimal(value):
    try:
        if value in (None, ""):
            return None
        from decimal import Decimal

        return Decimal(str(value))
    except Exception:
        return None


def build_client_from_settings():
    from django.conf import settings

    store_url = settings.WOO_STORE_URL
    key = settings.WOO_CONSUMER_KEY
    secret = settings.WOO_CONSUMER_SECRET
    if not store_url or not key or not secret:
        raise RuntimeError("Faltan credenciales. Configura WOO_STORE_URL, WOO_CONSUMER_KEY y WOO_CONSUMER_SECRET en el archivo .env")
    return WooClient(store_url, key, secret)


def get_last_sync_finished():
    return (
        SyncLog.objects.filter(status=SyncLog.Status.SUCCESS)
        .order_by("-finished_at")
        .values_list("finished_at", flat=True)
        .first()
    )


def sync_categories(client):
    count = 0
    for data in client.get_paginated("products/categories"):
        cat, _ = ProductCategory.objects.update_or_create(
            woo_id=data["id"],
            defaults={
                "name": data.get("name", ""),
                "slug": data.get("slug", ""),
                "parent_woo_id": data.get("parent") or None,
                "count": data.get("count") or 0,
                "date_created_gmt": _parse_gmt(data.get("date_created_gmt")),
                "date_modified_gmt": _parse_gmt(data.get("date_modified_gmt")),
            },
        )
        count += 1
    return count


def sync_products(client, modified_after=None):
    params = {}
    if modified_after:
        params["modified_after"] = modified_after.isoformat()
    count = 0
    variation_count = 0
    for data in client.get_paginated("products", params=params):
        with transaction.atomic():
            product, _ = Product.objects.update_or_create(
                woo_id=data["id"],
                defaults={
                    "name": data.get("name", ""),
                    "slug": data.get("slug", ""),
                    "status": data.get("status", "publish"),
                    "product_type": data.get("type", "simple"),
                    "sku": data.get("sku") or "",
                    "regular_price": _to_decimal(data.get("regular_price")),
                    "sale_price": _to_decimal(data.get("sale_price")),
                    "price": _to_decimal(data.get("price")),
                    "stock_quantity": data.get("stock_quantity"),
                    "stock_status": data.get("stock_status") or "",
                    "total_sales": data.get("total_sales") or 0,
                    "permalink": data.get("permalink") or "",
                    "date_created_gmt": _parse_gmt(data.get("date_created_gmt")),
                    "date_modified_gmt": _parse_gmt(data.get("date_modified_gmt")),
                    "image_url": (data.get("images") or [{}])[0].get("src", ""),
                },
            )
            cat_ids = [c["id"] for c in data.get("categories", [])]
            product.categories.set(ProductCategory.objects.filter(woo_id__in=cat_ids))

            if product.product_type == "variable":
                variation_count += sync_product_variations(client, product)
            else:
                ProductVariation.objects.filter(product=product).delete()
        count += 1
    return count, variation_count


def sync_product_variations(client, product):
    seen_var_ids = set()
    for v in client.get_variations(product.woo_id):
        seen_var_ids.add(v["id"])
        attrs = {}
        for a in v.get("attributes", []):
            key = a.get("name") or f"attr_{a.get('id')}"
            attrs[str(key)] = a.get("option", "")
        ProductVariation.objects.update_or_create(
            product=product,
            woo_id=v["id"],
            defaults={
                "sku": v.get("sku") or "",
                "regular_price": _to_decimal(v.get("regular_price")),
                "sale_price": _to_decimal(v.get("sale_price")),
                "price": _to_decimal(v.get("price")),
                "stock_quantity": v.get("stock_quantity"),
                "stock_status": v.get("stock_status") or "",
                "attributes": attrs,
                "date_created_gmt": _parse_gmt(v.get("date_created_gmt")),
                "date_modified_gmt": _parse_gmt(v.get("date_modified_gmt")),
            },
        )
    ProductVariation.objects.filter(product=product).exclude(woo_id__in=seen_var_ids).delete()
    return len(seen_var_ids)


def sync_orders(client, after=None):
    params = {"status": "any"}
    if after:
        params["after"] = after.isoformat()
    count = 0
    for data in client.get_paginated("orders", params=params):
        with transaction.atomic():
            order, _ = Order.objects.update_or_create(
                woo_id=data["id"],
                defaults={
                    "number": data.get("number") or "",
                    "status": data.get("status", "pending"),
                    "currency": data.get("currency") or "",
                    "date_created_gmt": _parse_gmt(data.get("date_created_gmt")),
                    "date_modified_gmt": _parse_gmt(data.get("date_modified_gmt")),
                    "date_paid_gmt": _parse_gmt(data.get("date_paid_gmt")),
                    "total": _to_decimal(data.get("total")) or 0,
                    "total_tax": _to_decimal(data.get("total_tax")) or 0,
                    "customer_email": (data.get("billing") or {}).get("email", "") or "",
                },
            )
            seen_items = []
            for item_data in data.get("line_items", []):
                seen_items.append(item_data.get("id"))
                OrderItem.objects.update_or_create(
                    order=order,
                    woo_id=item_data.get("id"),
                    defaults={
                        "product_woo_id": item_data.get("product_id") or None,
                        "variation_woo_id": item_data.get("variation_id") or None,
                        "name": item_data.get("name", ""),
                        "quantity": item_data.get("quantity") or 0,
                        "subtotal": _to_decimal(item_data.get("subtotal")) or 0,
                        "total": _to_decimal(item_data.get("total")) or 0,
                    },
                )
            order.items.exclude(woo_id__in=[i for i in seen_items if i]).delete()
        count += 1
    return count


def run_sync(trigger=SyncLog.Trigger.INCREMENTAL):
    log = SyncLog.objects.create(trigger=trigger)
    try:
        client = build_client_from_settings()
        client.ping()
        last = get_last_sync_finished()
        initial = last is None or trigger == SyncLog.Trigger.INITIAL

        log.categories_synced = sync_categories(client)

        since_products = None if initial else last - timedelta(minutes=5)
        log.products_synced, log.variations_synced = sync_products(client, modified_after=since_products)

        since_orders = None if initial else last - timedelta(minutes=5)
        log.orders_synced = sync_orders(client, after=since_orders)

        log.status = SyncLog.Status.SUCCESS
        log.message = (
            "Inicial completa" if initial else "Incremental"
        ) + f": {log.categories_synced} cat., {log.products_synced} prod., {log.orders_synced} pedidos."
    except Exception as exc:
        logger.exception("Error durante la sincronización")
        log.status = SyncLog.Status.ERROR
        log.message = str(exc)[:2000]
    finally:
        log.finished_at = dj_timezone.now()
        log.save(update_fields=["finished_at", "status", "message",
                                "categories_synced", "products_synced",
                                "variations_synced", "orders_synced"])
    return log
