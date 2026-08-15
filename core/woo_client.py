import os

import requests


class WooAPIError(Exception):
    pass


class WooClient:
    def __init__(self, store_url, consumer_key, consumer_secret, timeout=60, verify_ssl=None):
        self.base_url = store_url.rstrip("/") + "/wp-json/wc/v3"
        self.timeout = timeout
        if verify_ssl is None:
            verify_ssl = os.getenv("WOO_VERIFY_SSL", "true").lower() not in ("0", "false", "no")
        self.session = requests.Session()
        self.session.auth = (consumer_key, consumer_secret)
        self.session.verify = verify_ssl

    def get_paginated(self, endpoint, params=None, max_pages=None):
        params = dict(params or {})
        params["per_page"] = 100
        params.setdefault("orderby", "id")
        params.setdefault("order", "asc")
        page = 1
        while True:
            params["page"] = page
            resp = self.session.get(f"{self.base_url}/{endpoint}", params=params, timeout=self.timeout)
            if resp.status_code != 200:
                raise WooAPIError(f"GET {endpoint} -> HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            if not data:
                break
            yield from data
            if len(data) < 100:
                break
            if max_pages and page >= max_pages:
                break
            page += 1

    def ping(self):
        resp = self.session.get(f"{self.base_url}/products", params={"per_page": 1}, timeout=self.timeout)
        if resp.status_code != 200:
            raise WooAPIError(f"No se pudo conectar: HTTP {resp.status_code} - {resp.text[:200]}")
        return True

    def create_order(self, payload):
        resp = self.session.post(f"{self.base_url}/orders", json=payload, timeout=self.timeout)
        if resp.status_code not in (200, 201):
            raise WooAPIError(f"POST orders -> HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def get_variations(self, product_woo_id, params=None):
        return self.get_paginated(f"products/{product_woo_id}/variations", params=params)
