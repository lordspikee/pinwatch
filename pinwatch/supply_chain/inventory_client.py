import csv, io
from typing import Dict, Optional
from pinwatch.models import InventoryRecord, StockStatus

class InventoryClient:
    def __init__(self, csv_data: Optional[str] = None):
        self._inventory: Dict[str, InventoryRecord] = {}
        if csv_data:
            self.load_csv(csv_data)

    def load_csv(self, csv_content: str):
        reader = csv.DictReader(io.StringIO(csv_content.strip()))
        for row in reader:
            mpn = row.get("MPN", "").strip()
            if not mpn:
                continue
            qty = int(row.get("Stock_Qty", 0))
            status_str = row.get("Status", "IN_STOCK").upper().strip()
            status = StockStatus.IN_STOCK
            if status_str in StockStatus.__members__:
                status = StockStatus(status_str)
            elif qty <= 0:
                status = StockStatus.OUT_OF_STOCK
            elif qty < 50:
                status = StockStatus.LOW_STOCK

            self._inventory[mpn.upper()] = InventoryRecord(
                mpn=mpn,
                stock_qty=qty,
                warehouse_bin=row.get("Bin", "A1-01"),
                lifecycle_status=status,
                unit_cost_usd=float(row.get("Unit_Cost_USD", 0.0)),
                moq=int(row.get("MOQ", 1)),
                supplier=row.get("Supplier", "Direct")
            )

    def check_part(self, mpn: str) -> InventoryRecord:
        key = mpn.upper().strip()
        if key in self._inventory:
            return self._inventory[key]
        return InventoryRecord(
            mpn=mpn,
            stock_qty=0,
            warehouse_bin=None,
            lifecycle_status=StockStatus.NOT_FOUND,
            unit_cost_usd=0.0
        )
