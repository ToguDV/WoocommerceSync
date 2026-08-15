from django.contrib import admin

from .models import Order, OrderItem, Product, ProductCategory, ProductVariation, SyncLog


class ProductVariationInline(admin.TabularInline):
    model = ProductVariation
    extra = 0


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "woo_id", "count")
    search_fields = ("name", "slug")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "price", "stock_quantity", "status", "total_sales")
    list_filter = ("status", "product_type", "categories")
    search_fields = ("name", "sku")
    inlines = [ProductVariationInline]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("number", "woo_id", "status", "total", "currency", "date_paid_gmt")
    list_filter = ("status", "currency")
    search_fields = ("number", "customer_email")
    inlines = [OrderItemInline]


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ("started_at", "status", "trigger", "products_synced", "orders_synced", "duration_seconds")
    list_filter = ("status", "trigger")
    readonly_fields = ("message",)
