"""Diagnóstico de conexión con la API de WooCommerce."""
import os
import sys
from pathlib import Path

import requests
import urllib3
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

load_dotenv(Path(__file__).parent / ".env")

store_url = os.getenv("WOO_STORE_URL", "")
ck = os.getenv("WOO_CONSUMER_KEY", "")
cs = os.getenv("WOO_CONSUMER_SECRET", "")

print(f"URL: {store_url}")
print(f"CK: {ck[:6]}...{ck[-4:]} (len={len(ck)})")
print(f"CS: {cs[:6]}...{cs[-4:]} (len={len(cs)})")
print()

base = store_url.rstrip("/")
endpoints = [
    f"{base}/wp-json/wc/v3/products",
    f"{base}/?rest_route=/wc/v3/products",  # fallback si los permalinks no están en pretty
]

tests = [
    ("Basic auth + verify", lambda url: requests.get(url, auth=(ck, cs), timeout=30)),
    ("Basic auth sin verify", lambda url: requests.get(url, auth=(ck, cs), timeout=30, verify=False)),
    ("Query string", lambda url: requests.get(url, params={"consumer_key": ck, "consumer_secret": cs}, timeout=30, verify=False)),
]

for url in endpoints:
    print(f"--- Probando: {url.split('?')[0] if '?' in url else url}")
    for name, fn in tests:
        try:
            r = fn(url)
            body = ""
            try:
                j = r.json()
                if isinstance(j, list) and j:
                    body = f"OK - recibidos {len(j)} productos (primero id={j[0].get('id')})"
                elif isinstance(j, dict):
                    body = j.get("message", str(j)[:120])
            except Exception:
                body = r.text[:120]
            print(f"  [{name:<22}] HTTP {r.status_code}  ->  {body}")
            if r.status_code == 200 and "OK" in body:
                print("\n>>> ¡CONEXIÓN CORRECTA con este método!")
                sys.exit(0)
        except requests.exceptions.RequestException as e:
            print(f"  [{name:<22}] ERROR de red: {e.__class__.__name__}: {str(e)[:150]}")
    print()

print(">>> Ningún método funcionó. Revisa las claves en WooCommerce > Ajustes > Avanzado > API REST.")
