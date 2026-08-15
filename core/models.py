from django.db import models


class TimeStampedModel(models.Model):
    woo_id = models.PositiveBigIntegerField(unique=True, db_index=True)
    date_created_gmt = models.DateTimeField(null=True, blank=True)
    date_modified_gmt = models.DateTimeField(null=True, blank=True)
    synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    def __str__(self):
        return f"#{self.woo_id} {self.name}"


class ProductCategory(TimeStampedModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, blank=True, default="")
    parent_woo_id = models.PositiveBigIntegerField(null=True, blank=True)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"
        ordering = ["name"]


class Product(TimeStampedModel):
    class Status(models.TextChoices):
        PUBLISH = "publish", "Publicado"
        DRAFT = "draft", "Borrador"
        PENDING = "pending", "Pendiente"
        PRIVATE = "private", "Privado"

    name = models.CharField(max_length=500)
    slug = models.SlugField(max_length=500, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PUBLISH)
    product_type = models.CharField(max_length=20, default="simple")
    sku = models.CharField(max_length=100, blank=True, default="")
    regular_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sale_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stock_quantity = models.IntegerField(null=True, blank=True)
    stock_status = models.CharField(max_length=20, blank=True, default="")
    total_sales = models.PositiveIntegerField(default=0)
    permalink = models.URLField(blank=True, default="")
    categories = models.ManyToManyField(ProductCategory, blank=True, related_name="products")
    image_url = models.URLField(blank=True, default="")

    class Meta:
        verbose_name = "Producto"
        verbose_name_plural = "Productos"
        ordering = ["-date_created_gmt"]


class ProductVariation(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variations")
    sku = models.CharField(max_length=100, blank=True, default="")
    regular_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    sale_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    stock_quantity = models.IntegerField(null=True, blank=True)
    stock_status = models.CharField(max_length=20, blank=True, default="")
    attributes = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Variación"
        verbose_name_plural = "Variaciones"
        unique_together = [("product", "woo_id")]


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        PROCESSING = "processing", "Procesando"
        ON_HOLD = "on-hold", "En espera"
        COMPLETED = "completed", "Completado"
        CANCELLED = "cancelled", "Cancelado"
        REFUNDED = "refunded", "Reembolsado"
        FAILED = "failed", "Fallido"

    number = models.CharField(max_length=50, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    currency = models.CharField(max_length=10, blank=True, default="")
    date_paid_gmt = models.DateTimeField(null=True, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    customer_email = models.EmailField(blank=True, default="")

    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"
        ordering = ["-date_paid_gmt"]

    def __str__(self):
        return f"Pedido {self.number or self.woo_id} ({self.status})"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    woo_id = models.PositiveBigIntegerField(null=True, blank=True, db_index=True)
    product_woo_id = models.PositiveBigIntegerField(null=True, blank=True)
    variation_woo_id = models.PositiveBigIntegerField(null=True, blank=True)
    name = models.CharField(max_length=500)
    quantity = models.PositiveIntegerField(default=0)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Línea de pedido"
        verbose_name_plural = "Líneas de pedido"


class SyncLog(models.Model):
    class Status(models.TextChoices):
        RUNNING = "running", "En curso"
        SUCCESS = "success", "Completada"
        ERROR = "error", "Error"

    class Trigger(models.TextChoices):
        INITIAL = "initial", "Inicial completa"
        INCREMENTAL = "incremental", "Incremental"
        MANUAL = "manual", "Manual"

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    trigger = models.CharField(max_length=15, choices=Trigger.choices, default=Trigger.INCREMENTAL)
    categories_synced = models.PositiveIntegerField(default=0)
    products_synced = models.PositiveIntegerField(default=0)
    variations_synced = models.PositiveIntegerField(default=0)
    orders_synced = models.PositiveIntegerField(default=0)
    message = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Registro de sincronización"
        verbose_name_plural = "Registros de sincronización"
        ordering = ["-started_at"]

    def __str__(self):
        return f"Sync #{self.id} [{self.status}] {self.started_at:%d/%m/%Y %H:%M}"

    @property
    def duration_seconds(self):
        if not self.finished_at:
            return None
        return round((self.finished_at - self.started_at).total_seconds(), 1)

    @property
    def is_running(self):
        return self.status == self.Status.RUNNING
