from typing import Dict, List, Optional, Tuple
from pinwatch.models import PinDefinition, PinFunction, ElectricalRatings

class DatasheetExtractionAgent:
    def __init__(self, cached_specs: Optional[Dict[str, Dict]] = None):
        self._cache = cached_specs or {}

    def extract_component_specs(self, mpn: str, package: str) -> Tuple[List[PinDefinition], ElectricalRatings]:
        key = mpn.upper().strip()
        if key in self._cache:
            data = self._cache[key]
            pins = [
                PinDefinition(
                    pin_number=str(p["pin_number"]),
                    pin_name=p["pin_name"],
                    function=PinFunction(p.get("function", "PASSIVE")),
                    notes=p.get("notes")
                )
                for p in data.get("pins", [])
            ]
            elec = ElectricalRatings(**data.get("electrical", {}))
            return pins, elec
        return [], ElectricalRatings()
