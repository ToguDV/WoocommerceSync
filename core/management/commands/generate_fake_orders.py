import random
from datetime import timedelta, timezone as dt_timezone

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import Product
from core.sync_service import build_client_from_settings, run_sync

FIRST_NAMES = [
    "María", "Juan", "Carlos", "Lucía", "Ana", "Pedro", "Sofía", "Diego",
    "Valentina", "Javier", "Carmen", "Andrés", "Elena", "Pablo", "Laura",
    "Miguel", "Marta", "Álvaro", "Paula", "Sergio", "Irene", "David",
    "Claudia", "Óscar", "Nuria", "Raúl", "Beatriz", "Alberto", "Rocío",
    "Hugo", "Alicia", "Fernando", "Daniela", "Jorge", "Silvia", "Rubén",
]
LAST_NAMES = [
    "García", "Rodríguez", "González", "Fernández", "López", "Martínez",
    "Sánchez", "Pérez", "Gómez", "Martín", "Jiménez", "Ruiz", "Hernández",
    "Díaz", "Moreno", "Álvarez", "Romero", "Alonso", "Gutiérrez", "Navarro",
    "Torres", "Domínguez", "Vázquez", "Ramos", "Gil", "Serrano", "Blanco",
    "Molina", "Morales", "Suárez", "Ortega", "Delgado", "Castro", "Rubio",
]
DOMAINS = ["gmail.com", "outlook.com", "hotmail.com", "yahoo.es", "proton.me"]

STATUS_WEIGHTS = [
    ("completed", 62), ("processing", 10), ("on-hold", 5),
    ("pending", 5), ("cancelled", 8), ("refunded", 10),
]

STREETS = ["Mayor", "Sol", "Rosa", "Luna", "Real", "Verde", "Nueva", "Carmen"]
CITIES = ["Madrid", "Barcelona", "Valencia", "Sevilla", "Zaragoza", "Bilbao", "Málaga", "Murcia"]


def _slug(text):
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ñ", "n")):
        text = text.replace(a, b)
    return text


def _make_customer(pool):
    if pool and random.random() < 0.65:
        return random.choice(pool)
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    suffix = f".{random.randint(1, 999)}" if random.random() < 0.5 else ""
    return {
        "first_name": first,
        "last_name": last,
        "email": f"{_slug(first.lower())}.{_slug(last.lower())}{suffix}@{random.choice(DOMAINS)}",
        "phone": f"6{random.randint(10000000, 99999999)}",
        "address_1": f"Calle {random.choice(STREETS)} {random.randint(1, 120)}",
        "address_2": "",
        "city": random.choice(CITIES),
        "state": "",
        "postcode": str(random.randint(10000, 52999)),
        "country": "ES",
        "company": "",
    }


def _build_line_items(products):
    count = random.randint(1, 3)
    chosen = random.sample(products, k=min(count, len(products)))
    items = []
    for p in chosen:
        item = {"product_id": p.woo_id, "quantity": random.randint(1, 4)}
        if p.product_type == "variable":
            variation = p.variations.first()
            if variation is None:
                continue
            item["variation_id"] = variation.woo_id
        items.append(item)
    return items


class Command(BaseCommand):
    help = "Crea pedidos ficticios variados en WooCommerce mediante la API REST"

    def add_arguments(self, parser):
        parser.add_argument("--count", type=int, default=100)
        parser.add_argument("--months", type=int, default=12)
        parser.add_argument("--seed", type=int, default=None)
        parser.add_argument("--no-sync", action="store_true")

    def handle(self, *args, **options):
        count = options["count"]
        months = options["months"]
        if options["seed"] is not None:
            random.seed(options["seed"])

        products = list(Product.objects.all())
        if not products:
            raise CommandError("No hay productos en la base local. Ejecuta primero una sincronización.")

        client = build_client_from_settings()
        recurring_pool = [_make_customer([]) for _ in range(30)]

        created = 0
        for i in range(count):
            customer = _make_customer(recurring_pool)
            created_at = timezone.now() - timedelta(
                days=random.uniform(0, months * 30),
                hours=random.uniform(0, 24),
                minutes=random.uniform(0, 60),
            )
            status = random.choices(
                [s for s, _ in STATUS_WEIGHTS], weights=[w for _, w in STATUS_WEIGHTS]
            )[0]
            paid = status in ("completed", "processing")
            paid_at = created_at + timedelta(minutes=random.randint(5, 720)) if paid else None

            def fmt(dt):
                return dt.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") if dt else None

            payload = {
                "status": status,
                "set_paid": paid,
                "date_created_gmt": fmt(created_at),
                "date_paid_gmt": fmt(paid_at),
                "payment_method": random.choice(["bacs", "cod", "paypal"]),
                "payment_method_title": "Transferencia bancaria",
                "billing": customer,
                "shipping": customer,
                "line_items": _build_line_items(products),
            }

            try:
                client.create_order(payload)
            except Exception as exc:
                self.stderr.write(f"[{i + 1}/{count}] ERROR: {exc}")
                continue
            created += 1
            if (i + 1) % 20 == 0:
                self.stdout.write(f"[{i + 1}/{count}] creados: {created}")

        self.stdout.write(self.style.SUCCESS(f"Pedidos ficticios creados en WooCommerce: {created}/{count}"))

        if not options["no_sync"] and created:
            self.stdout.write("Sincronizando a la base local...")
            log = run_sync(trigger="manual")
            self.stdout.write(
                self.style.SUCCESS(
                    f"Sync [{log.status}]: {log.products_synced} prod., {log.orders_synced} pedidos."
                )
            )
