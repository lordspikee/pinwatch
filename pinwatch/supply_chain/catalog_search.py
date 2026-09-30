import json
from typing import List, Optional
from pinwatch.models import Component

class CatalogSearchProvider:
    def __init__(self, catalog_data: Optional[List[dict]] = None):
        self._catalog: List[dict] = catalog_data or []

    def load_json(self, json_content: str):
        self._catalog = json.loads(json_content)

    def search_alternatives(self, component: Component, min_stock: int = 50) -> List[dict]:
        results = []
        target_pkg = self._normalize_package(component.package)

        for item in self._catalog:
            if item.get("mpn", "").upper() == component.mpn.upper():
                continue
            if item.get("stock_qty", 0) < min_stock:
                continue

            item_pkg = self._normalize_package(item.get("package", ""))
            if target_pkg == item_pkg or target_pkg in item_pkg or item_pkg in target_pkg:
                results.append(item)
        return results

    @staticmethod
    def _normalize_package(pkg: str) -> str:
        return pkg.upper().replace("-", "").replace("_", "").replace(" ", "")
