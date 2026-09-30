import os
import sys
from pathlib import Path

print("[*] Generating PinWatch directory tree and source files...")

BASE = Path("pinwatch")
PARSERS = BASE / "parsers"
SUPPLY = BASE / "supply_chain"
DATASHEET = BASE / "datasheet_agent"
ENGINE = BASE / "engine"
FIXTURES = BASE / "fixtures"
TESTS = Path("tests")

for d in [PARSERS, SUPPLY, DATASHEET, ENGINE, FIXTURES, TESTS]:
    d.mkdir(parents=True, exist_ok=True)

# 1. __init__.py
(BASE / "__init__.py").write_text('"""PinWatch Package"""\n__version__ = "0.1.0"\n', encoding="utf-8")
for sub in [PARSERS, SUPPLY, DATASHEET, ENGINE]:
    (sub / "__init__.py").write_text("", encoding="utf-8")

# 2. models.py
(BASE / "models.py").write_text('''from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

class StockStatus(str, Enum):
    IN_STOCK = "IN_STOCK"
    LOW_STOCK = "LOW_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    OBSOLETE = "OBSOLETE"
    NOT_FOUND = "NOT_FOUND"

class CompatibilityVerdict(str, Enum):
    DROP_IN_COMPATIBLE = "DROP_IN_COMPATIBLE"
    CONDITIONALLY_COMPATIBLE = "CONDITIONALLY_COMPATIBLE"
    REQUIRES_PCB_REWORK = "REQUIRES_PCB_REWORK"
    INCOMPATIBLE = "INCOMPATIBLE"

class PinFunction(str, Enum):
    POWER_IN = "POWER_IN"
    POWER_OUT = "POWER_OUT"
    GROUND = "GROUND"
    ENABLE = "ENABLE"
    SIGNAL_IN = "SIGNAL_IN"
    SIGNAL_OUT = "SIGNAL_OUT"
    BIDIRECTIONAL = "BIDIRECTIONAL"
    PASSIVE = "PASSIVE"
    NO_CONNECT = "NO_CONNECT"

class PinDefinition(BaseModel):
    pin_number: str
    pin_name: str
    function: PinFunction = PinFunction.PASSIVE
    connected_net: Optional[str] = None
    is_active_in_circuit: bool = True
    notes: Optional[str] = None

class ComponentType(str, Enum):
    VOLTAGE_REGULATOR = "VOLTAGE_REGULATOR"
    OP_AMP = "OP_AMP"
    MICROCONTROLLER = "MICROCONTROLLER"
    TRANSCEIVER = "TRANSCEIVER"
    GATE_DRIVER = "GATE_DRIVER"
    PASSIVE = "PASSIVE"
    OTHER = "OTHER"

class ElectricalRatings(BaseModel):
    input_voltage_min_v: Optional[float] = None
    input_voltage_max_v: Optional[float] = None
    output_voltage_v: Optional[float] = None
    output_current_max_ma: Optional[float] = None
    quiescent_current_ua: Optional[float] = None
    dropout_voltage_mv: Optional[float] = None
    operating_temp_min_c: Optional[float] = None
    operating_temp_max_c: Optional[float] = None
    power_dissipation_max_w: Optional[float] = None
    psrr_db: Optional[float] = None

class Component(BaseModel):
    reference: str
    value: str
    mpn: str
    manufacturer: Optional[str] = None
    package: str
    component_type: ComponentType = ComponentType.OTHER
    datasheet_url: Optional[str] = None
    pins: List[PinDefinition] = Field(default_factory=list)
    electrical: Optional[ElectricalRatings] = None
    description: Optional[str] = None

class InventoryRecord(BaseModel):
    mpn: str
    stock_qty: int
    warehouse_bin: Optional[str] = None
    lifecycle_status: StockStatus = StockStatus.IN_STOCK
    unit_cost_usd: float = 0.0
    moq: int = 1
    supplier: Optional[str] = None

class DistributorOffer(BaseModel):
    distributor: str
    sku: str
    mpn: str
    manufacturer: str
    stock_qty: int
    unit_price_usd: float
    moq: int = 1
    datasheet_url: Optional[str] = None
    packaging: str = "Reel"
    lifecycle_status: str = "Active"

class PinComparison(BaseModel):
    pin_number: str
    original_pin_name: str
    original_function: str
    candidate_pin_name: str
    candidate_function: str
    connected_net: Optional[str] = None
    is_match: bool
    notes: Optional[str] = None

class SubstitutionCandidate(BaseModel):
    mpn: str
    manufacturer: str
    package: str
    source: str
    stock_qty: int
    unit_cost_usd: float
    moq: int = 1
    datasheet_url: Optional[str] = None
    electrical: ElectricalRatings
    pins: List[PinDefinition] = Field(default_factory=list)
    verdict: CompatibilityVerdict = CompatibilityVerdict.INCOMPATIBLE
    pin_comparisons: List[PinComparison] = Field(default_factory=list)
    verdict_reasons: List[str] = Field(default_factory=list)
    efficiency_delta_notes: Optional[str] = None
    price_delta_percent: Optional[float] = None

class ComponentAuditResult(BaseModel):
    target_component: Component
    inventory_status: StockStatus
    inventory_record: Optional[InventoryRecord] = None
    candidates: List[SubstitutionCandidate] = Field(default_factory=list)
    recommended_candidate: Optional[SubstitutionCandidate] = None
    audit_summary: str = ""

class AuditDossier(BaseModel):
    project_name: str
    total_components_analyzed: int
    components_with_issues: int
    results: List[ComponentAuditResult] = Field(default_factory=list)
''', encoding="utf-8")

# 3. parsers/kicad_parser.py
(PARSERS / "kicad_parser.py").write_text('''import re
from typing import List, Dict, Any, Optional
from pinwatch.models import Component, PinDefinition, PinFunction, ComponentType

def parse_sexpr(text: str) -> List[Any]:
    tokens = []
    pattern = re.compile(r'\\(\vert{}\\)|"([^"\\\\]*(?:\\\\.[^"\\\\]*)*)"|([^\\s\\(\\)]+)')
    for match in pattern.finditer(text):
        if match.group(0) == '(':
            tokens.append('(')
        elif match.group(0) == ')':
            tokens.append(')')
        elif match.group(1) is not None:
            tokens.append(match.group(1).replace(r'\\"', '"').replace(r'\\\\', '\\\\'))
        else:
            tokens.append(match.group(2))

    stack: List[List[Any]] = [[]]
    for token in tokens:
        if token == '(':
            new_list: List[Any] = []
            stack[-1].append(new_list)
            stack.append(new_list)
        elif token == ')':
            if len(stack) > 1:
                stack.pop()
        else:
            stack[-1].append(token)
    return stack[0][0] if stack[0] else []

class KiCadSchematicParser:
    @staticmethod
    def _infer_component_type(value: str, ref: str) -> ComponentType:
        val_upper = value.upper()
        if any(reg in val_upper for reg in ["1117", "7805", "LDO", "REG", "AP2112", "LP5907", "MCP1700"]):
            return ComponentType.VOLTAGE_REGULATOR
        elif any(op in val_upper for op in ["LM358", "OPA", "TL072", "OPAMP"]):
            return ComponentType.OP_AMP
        elif any(mcu in val_upper for mcu in ["STM32", "ESP32", "ATMEGA", "RP2040"]):
            return ComponentType.MICROCONTROLLER
        elif ref.upper().startswith(("R", "C", "L")):
            return ComponentType.PASSIVE
        return ComponentType.OTHER

    @staticmethod
    def _infer_pin_function(name: str) -> PinFunction:
        n = name.upper().strip()
        if n in ["VCC", "VIN", "VDD", "VBAT", "3V3", "5V", "IN", "INPUT"]:
            return PinFunction.POWER_IN
        elif n in ["VOUT", "OUTPUT", "OUT", "3.3V"]:
            return PinFunction.POWER_OUT
        elif n in ["GND", "AGND", "PGND", "VSS", "GROUND", "ADJ/GND"]:
            return PinFunction.GROUND
        elif any(en in n for en in ["EN", "ENABLE", "SHDN"]):
            return PinFunction.ENABLE
        elif n in ["NC", "NO_CONNECT"]:
            return PinFunction.NO_CONNECT
        return PinFunction.PASSIVE

    def parse_content(self, content: str) -> List[Component]:
        ast = parse_sexpr(content)
        if not ast or not isinstance(ast, list) or ast[0] != "kicad_sch":
            return self._fallback_regex_parse(content)

        components: List[Component] = []
        for item in ast:
            if isinstance(item, list) and item and item[0] == "symbol":
                comp = self._parse_symbol(item)
                if comp and comp.reference and not comp.reference.startswith("#"):
                    components.append(comp)
        return components

    def _parse_symbol(self, symbol_node: List[Any]) -> Optional[Component]:
        properties: Dict[str, str] = {}
        pins: List[PinDefinition] = []
        for elem in symbol_node:
            if isinstance(elem, list) and elem:
                if elem[0] == "property" and len(elem) >= 3:
                    properties[str(elem[1])] = str(elem[2])
                elif elem[0] == "pin" and len(elem) >= 2:
                    pin_num = str(elem[1])
                    pin_name = f"Pin_{pin_num}"
                    for sub in elem:
                        if isinstance(sub, list) and sub and sub[0] == "name" and len(sub) >= 2:
                            pin_name = str(sub[1])
                    pins.append(PinDefinition(
                        pin_number=pin_num,
                        pin_name=pin_name,
                        function=self._infer_pin_function(pin_name)
                    ))

        ref = properties.get("Reference", "")
        val = properties.get("Value", "")
        footprint = properties.get("Footprint", "Unknown")
        if ":" in footprint:
            footprint = footprint.split(":", 1)[1]

        if not ref or ref.startswith("#"):
            return None

        return Component(
            reference=ref,
            value=val,
            mpn=properties.get("MPN", val),
            package=footprint,
            component_type=self._infer_component_type(val, ref),
            pins=pins
        )

    def _fallback_regex_parse(self, content: str) -> List[Component]:
        components = []
        blocks = re.findall(r'\\(symbol\\s+.*?\\n\\s*\\)', content, re.DOTALL)
        for b in blocks:
            r = re.search(r'\\(property\\s+"Reference"\\s+"([^"]+)"', b)
            v = re.search(r'\\(property\\s+"Value"\\s+"([^"]+)"', b)
            fp = re.search(r'\\(property\\s+"Footprint"\\s+"([^"]+)"', b)
            if r and v:
                pkg = fp.group(1).split(":")[-1] if fp else "Unknown"
                components.append(Component(
                    reference=r.group(1),
                    value=v.group(1),
                    mpn=v.group(1),
                    package=pkg,
                    component_type=self._infer_component_type(v.group(1), r.group(1))
                ))
        return components
''', encoding="utf-8")

# 4. supply_chain/inventory_client.py
(SUPPLY / "inventory_client.py").write_text('''import csv, io
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
''', encoding="utf-8")

# 5. supply_chain/catalog_search.py
(SUPPLY / "catalog_search.py").write_text('''import json
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
''', encoding="utf-8")

# 6. datasheet_agent/qwen_prompt.py
(DATASHEET / "qwen_prompt.py").write_text('''from typing import Dict, List, Optional, Tuple
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
''', encoding="utf-8")

# 7. engine/pin_matcher.py
(ENGINE / "pin_matcher.py").write_text('''from typing import List, Tuple
from pinwatch.models import PinDefinition, PinFunction, PinComparison

class PinCompatibilityMatcher:
    COMPATIBLE_FUNCTIONS = {
        PinFunction.POWER_IN: {PinFunction.POWER_IN},
        PinFunction.POWER_OUT: {PinFunction.POWER_OUT},
        PinFunction.GROUND: {PinFunction.GROUND},
        PinFunction.ENABLE: {PinFunction.ENABLE, PinFunction.POWER_IN},
        PinFunction.NO_CONNECT: {PinFunction.NO_CONNECT, PinFunction.PASSIVE},
        PinFunction.PASSIVE: {PinFunction.PASSIVE, PinFunction.NO_CONNECT},
        PinFunction.SIGNAL_IN: {PinFunction.SIGNAL_IN, PinFunction.BIDIRECTIONAL},
        PinFunction.SIGNAL_OUT: {PinFunction.SIGNAL_OUT, PinFunction.BIDIRECTIONAL},
        PinFunction.BIDIRECTIONAL: {PinFunction.BIDIRECTIONAL}
    }

    @classmethod
    def compare_pinouts(cls, orig_pins: List[PinDefinition], cand_pins: List[PinDefinition]) -> Tuple[List[PinComparison], bool, List[str]]:
        comparisons = []
        issues = []
        is_compat = True

        orig_map = {str(p.pin_number): p for p in orig_pins}
        cand_map = {str(p.pin_number): p for p in cand_pins}
        all_pins = sorted(list(set(orig_map.keys()) | set(cand_map.keys())), key=lambda x: int(x) if x.isdigit() else x)

        for p_num in all_pins:
            orig = orig_map.get(p_num)
            cand = cand_map.get(p_num)

            if not orig and cand:
                issues.append(f"Extra Pin {p_num} ({cand.pin_name}) on candidate")
                comparisons.append(PinComparison(
                    pin_number=p_num, original_pin_name="N/A", original_function="N/A",
                    candidate_pin_name=cand.pin_name, candidate_function=cand.function.value,
                    is_match=False, notes="Extra pin"
                ))
                is_compat = False
                continue

            if orig and not cand:
                issues.append(f"Missing Pin {p_num} on candidate")
                comparisons.append(PinComparison(
                    pin_number=p_num, original_pin_name=orig.pin_name, original_function=orig.function.value,
                    candidate_pin_name="MISSING", candidate_function="N/A",
                    is_match=False, notes="Missing pin"
                ))
                is_compat = False
                continue

            allowed = cls.COMPATIBLE_FUNCTIONS.get(orig.function, {orig.function})
            match = cand.function in allowed
            if not match:
                is_compat = False
                issues.append(f"Pin {p_num} mismatch: {orig.pin_name} vs {cand.pin_name}")

            comparisons.append(PinComparison(
                pin_number=p_num,
                original_pin_name=orig.pin_name, original_function=orig.function.value,
                candidate_pin_name=cand.pin_name, candidate_function=cand.function.value,
                is_match=match,
                notes="Pin matches" if match else f"Function mismatch ({orig.function.value} vs {cand.function.value})"
            ))
        return comparisons, is_compat, issues
''', encoding="utf-8")

# 8. engine/electrical_eval.py
(ENGINE / "electrical_eval.py").write_text('''from typing import List
from pinwatch.models import Component, SubstitutionCandidate, CompatibilityVerdict, ElectricalRatings

class ElectricalCompatibilityEvaluator:
    @classmethod
    def evaluate_candidate(cls, orig_comp: Component, candidate: SubstitutionCandidate, is_pin_compatible: bool, pin_issues: List[str]) -> SubstitutionCandidate:
        reasons = list(pin_issues)
        orig_e = orig_comp.electrical or ElectricalRatings()
        cand_e = candidate.electrical

        if not is_pin_compatible:
            candidate.verdict = CompatibilityVerdict.REQUIRES_PCB_REWORK
            candidate.verdict_reasons = reasons
            return candidate

        voltage_ok = True
        if orig_e.output_voltage_v and cand_e.output_voltage_v:
            if abs(orig_e.output_voltage_v - cand_e.output_voltage_v) > 0.05:
                voltage_ok = False
                reasons.append(f"Output voltage mismatch: {cand_e.output_voltage_v}V vs {orig_e.output_voltage_v}V")

        current_ok = True
        if orig_e.output_current_max_ma and cand_e.output_current_max_ma:
            if cand_e.output_current_max_ma < orig_e.output_current_max_ma:
                current_ok = False
                reasons.append(f"Insufficient current output: {cand_e.output_current_max_ma}mA vs {orig_e.output_current_max_ma}mA")

        eff = []
        if orig_e.quiescent_current_ua and cand_e.quiescent_current_ua:
            delta = cand_e.quiescent_current_ua - orig_e.quiescent_current_ua
            eff.append(f"Quiescent current delta: {delta:+.1f}uA")
        candidate.efficiency_delta_notes = "; ".join(eff) if eff else "Comparable efficiency"

        if not voltage_ok or not current_ok:
            candidate.verdict = CompatibilityVerdict.INCOMPATIBLE
        elif len(reasons) == 0:
            candidate.verdict = CompatibilityVerdict.DROP_IN_COMPATIBLE
            reasons.append("Exact 100% pin-compatible match; meets all electrical criteria.")
        else:
            candidate.verdict = CompatibilityVerdict.CONDITIONALLY_COMPATIBLE

        candidate.verdict_reasons = reasons
        return candidate
''', encoding="utf-8")

# 9. engine/report_generator.py
(ENGINE / "report_generator.py").write_text('''from tabulate import tabulate
from pinwatch.models import AuditDossier, CompatibilityVerdict

class AuditReportGenerator:
    @classmethod
    def generate_markdown(cls, dossier: AuditDossier) -> str:
        lines = [
            f"# Hardware Component Obsolescence & Pinout Substitution Audit Dossier",
            f"**Project:** {dossier.project_name} | **Analyzed:** {dossier.total_components_analyzed} | **Vulnerabilities:** {dossier.components_with_issues}\\n",
            "---",
            "## Executive Summary\\n"
        ]
        for idx, res in enumerate(dossier.results, 1):
            comp = res.target_component
            lines.append(f"### {idx}. Component Audit: `{comp.reference}` — {comp.value} ({comp.package})")
            lines.append(f"- **Inventory Status:** `{res.inventory_status.value}`")
            lines.append(f"- **Stock on Hand:** {res.inventory_record.stock_qty if res.inventory_record else 0} units\\n")

            if not res.candidates:
                lines.append("*No replacement candidates found.*\\n")
                continue

            headers = ["Candidate MPN", "Manufacturer", "Source", "Price", "Stock", "Verdict"]
            rows = [
                [f"`{c.mpn}`", c.manufacturer, c.source, f"${c.unit_cost_usd:.3f}", f"{c.stock_qty:,}", f"**{c.verdict.value}**"]
                for c in res.candidates
            ]
            lines.append(tabulate(rows, headers=headers, tablefmt="github") + "\\n")

            rec = res.recommended_candidate
            if rec:
                lines.append(f"#### Recommended Replacement: `{rec.mpn}` ({rec.verdict.value})")
                lines.append(f"- **Stock:** {rec.stock_qty:,} via {rec.source}")
                lines.append(f"- **Efficiency:** {rec.efficiency_delta_notes}\\n")
                lines.append("##### Pinout Alignment Matrix\\n")
                p_headers = ["Pin #", "Original", "Candidate", "Status", "Notes"]
                p_rows = [
                    [p.pin_number, f"{p.original_pin_name} ({p.original_function})", f"{p.candidate_pin_name} ({p.candidate_function})", "PASS" if p.is_match else "FAIL", p.notes]
                    for p in rec.pin_comparisons
                ]
                lines.append(tabulate(p_rows, headers=p_headers, tablefmt="github") + "\\n")
            lines.append("---\\n")
        return "\\n".join(lines)
''', encoding="utf-8")

# 10. orchestrator.py
(BASE / "orchestrator.py").write_text('''from typing import List, Optional
from pinwatch.models import Component, StockStatus, SubstitutionCandidate, CompatibilityVerdict, ComponentAuditResult, AuditDossier
from pinwatch.parsers.kicad_parser import KiCadSchematicParser
from pinwatch.supply_chain.inventory_client import InventoryClient
from pinwatch.supply_chain.catalog_search import CatalogSearchProvider
from pinwatch.datasheet_agent.qwen_prompt import DatasheetExtractionAgent
from pinwatch.engine.pin_matcher import PinCompatibilityMatcher
from pinwatch.engine.electrical_eval import ElectricalCompatibilityEvaluator

class PinWatchAgent:
    def __init__(self, inventory_client: InventoryClient, catalog_provider: CatalogSearchProvider, datasheet_agent: DatasheetExtractionAgent):
        self.inv = inventory_client
        self.cat = catalog_provider
        self.ds = datasheet_agent
        self.kicad = KiCadSchematicParser()

    def audit_schematic(self, schematic_content: str, project_name: str = "Hardware Project") -> AuditDossier:
        components = self.kicad.parse_content(schematic_content)
        results = []
        issues = 0
        for comp in components:
            if comp.reference.startswith(("R", "C", "L")):
                continue
            res = self.audit_single_part(comp)
            if res.inventory_status in [StockStatus.OUT_OF_STOCK, StockStatus.OBSOLETE, StockStatus.LOW_STOCK]:
                issues += 1
            results.append(res)
        return AuditDossier(project_name=project_name, total_components_analyzed=len(components), components_with_issues=issues, results=results)

    def audit_single_part(self, comp: Component) -> ComponentAuditResult:
        inv = self.inv.check_part(comp.mpn)
        if not comp.pins or not comp.electrical:
            pins, elec = self.ds.extract_component_specs(comp.mpn, comp.package)
            comp.pins = pins
            comp.electrical = elec

        candidates = []
        recommended = None
        if inv.lifecycle_status in [StockStatus.OUT_OF_STOCK, StockStatus.OBSOLETE, StockStatus.LOW_STOCK, StockStatus.NOT_FOUND]:
            for raw in self.cat.search_alternatives(comp):
                cand_mpn = raw.get("mpn", "")
                cand_pkg = raw.get("package", comp.package)
                c_pins, c_elec = self.ds.extract_component_specs(cand_mpn, cand_pkg)
                cand = SubstitutionCandidate(
                    mpn=cand_mpn, manufacturer=raw.get("manufacturer", "Unknown"), package=cand_pkg,
                    source=raw.get("distributor", "Distributor"), stock_qty=raw.get("stock_qty", 0),
                    unit_cost_usd=raw.get("unit_price_usd", 0.0), electrical=c_elec, pins=c_pins
                )
                comps, is_match, issues = PinCompatibilityMatcher.compare_pinouts(comp.pins, cand.pins)
                cand.pin_comparisons = comps
                cand = ElectricalCompatibilityEvaluator.evaluate_candidate(comp, cand, is_match, issues)
                candidates.append(cand)

            candidates.sort(key=lambda c: (0 if c.verdict == CompatibilityVerdict.DROP_IN_COMPATIBLE else 1, c.unit_cost_usd))
            if candidates and candidates[0].verdict != CompatibilityVerdict.INCOMPATIBLE:
                recommended = candidates[0]

        return ComponentAuditResult(target_component=comp, inventory_status=inv.lifecycle_status, inventory_record=inv, candidates=candidates, recommended_candidate=recommended)
''', encoding="utf-8")

# 11. cli.py
(BASE / "cli.py").write_text('''import argparse, json, sys
from pathlib import Path
from pinwatch.models import Component
from pinwatch.supply_chain.inventory_client import InventoryClient
from pinwatch.supply_chain.catalog_search import CatalogSearchProvider
from pinwatch.datasheet_agent.qwen_prompt import DatasheetExtractionAgent
from pinwatch.orchestrator import PinWatchAgent
from pinwatch.engine.report_generator import AuditReportGenerator

def main():
    parser = argparse.ArgumentParser(prog="pinwatch", description="PinWatch: Hardware PCB Component Obsolescence & Pinout Substitution Watchdog")
    subparsers = parser.add_subparsers(dest="command")

    sch_parser = subparsers.add_parser("audit-schematic")
    sch_parser.add_argument("--schematic", required=True)
    sch_parser.add_argument("--inventory", default="pinwatch/fixtures/inventory.csv")
    sch_parser.add_argument("--catalog", default="pinwatch/fixtures/distributor_catalog.json")

    part_parser = subparsers.add_parser("check-part")
    part_parser.add_argument("--mpn", required=True)
    part_parser.add_argument("--package", required=True)
    part_parser.add_argument("--inventory", default="pinwatch/fixtures/inventory.csv")
    part_parser.add_argument("--catalog", default="pinwatch/fixtures/distributor_catalog.json")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    inv = InventoryClient()
    if Path(args.inventory).exists():
        inv.load_csv(Path(args.inventory).read_text(encoding="utf-8"))

    cat = CatalogSearchProvider()
    if Path(args.catalog).exists():
        cat.load_json(Path(args.catalog).read_text(encoding="utf-8"))

    ds = DatasheetExtractionAgent()
    cache_file = Path("pinwatch/fixtures/datasheet_cache.json")
    if cache_file.exists():
        ds._cache = json.loads(cache_file.read_text(encoding="utf-8"))

    agent = PinWatchAgent(inv, cat, ds)

    if args.command == "audit-schematic":
        content = Path(args.schematic).read_text(encoding="utf-8")
        dossier = agent.audit_schematic(content, project_name=Path(args.schematic).stem)
        print(AuditReportGenerator.generate_markdown(dossier))
    elif args.command == "check-part":
        comp = Component(reference="U1", value=args.mpn, mpn=args.mpn, package=args.package)
        res = agent.audit_single_part(comp)
        from pinwatch.models import AuditDossier
        dossier = AuditDossier(project_name=f"Audit {args.mpn}", total_components_analyzed=1, components_with_issues=1 if res.inventory_status.value != "IN_STOCK" else 0, results=[res])
        print(AuditReportGenerator.generate_markdown(dossier))

if __name__ == "__main__":
    main()
''', encoding="utf-8")

# 12. Fixtures
(FIXTURES / "inventory.csv").write_text('''MPN,Stock_Qty,Bin,Status,Unit_Cost_USD,MOQ,Supplier
AMS1117-3.3,0,B2-14,OBSOLETE,0.18,100,LCSC
AP2112K-3.3,15,A1-04,LOW_STOCK,0.35,50,DigiKey
STM32F401CEU6,2500,C4-01,IN_STOCK,2.10,1,STDirect
''', encoding="utf-8")

(FIXTURES / "distributor_catalog.json").write_text('''[
  {"distributor": "LCSC", "mpn": "AZ1117CH-3.3TRG1", "manufacturer": "Diodes Inc", "package": "SOT-223-3", "stock_qty": 22000, "unit_price_usd": 0.22},
  {"distributor": "Mouser", "mpn": "MCP1700T-3302E/MB", "manufacturer": "Microchip", "package": "SOT-223-3", "stock_qty": 11000, "unit_price_usd": 0.45},
  {"distributor": "DigiKey", "mpn": "LP5907MFX-3.3/NOPB", "manufacturer": "Texas Instruments", "package": "SOT-23-5", "stock_qty": 45000, "unit_price_usd": 0.28}
]''', encoding="utf-8")

(FIXTURES / "datasheet_cache.json").write_text('''{
  "AMS1117-3.3": {
    "package": "SOT-223-3",
    "pins": [
      {"pin_number": "1", "pin_name": "ADJ/GND", "function": "GROUND"},
      {"pin_number": "2", "pin_name": "VOUT", "function": "POWER_OUT"},
      {"pin_number": "3", "pin_name": "VIN", "function": "POWER_IN"}
    ],
    "electrical": {"output_voltage_v": 3.3, "output_current_max_ma": 1000.0, "quiescent_current_ua": 5000.0}
  },
  "AZ1117CH-3.3TRG1": {
    "package": "SOT-223-3",
    "pins": [
      {"pin_number": "1", "pin_name": "ADJ/GND", "function": "GROUND"},
      {"pin_number": "2", "pin_name": "VOUT", "function": "POWER_OUT"},
      {"pin_number": "3", "pin_name": "VIN", "function": "POWER_IN"}
    ],
    "electrical": {"output_voltage_v": 3.3, "output_current_max_ma": 1000.0, "quiescent_current_ua": 4000.0}
  },
  "MCP1700T-3302E/MB": {
    "package": "SOT-223-3",
    "pins": [
      {"pin_number": "1", "pin_name": "GND", "function": "GROUND"},
      {"pin_number": "2", "pin_name": "VIN", "function": "POWER_IN"},
      {"pin_number": "3", "pin_name": "VOUT", "function": "POWER_OUT"}
    ],
    "electrical": {"output_voltage_v": 3.3, "output_current_max_ma": 250.0, "quiescent_current_ua": 1.6}
  }
}''', encoding="utf-8")

(FIXTURES / "sample_board.kicad_sch").write_text('''(kicad_sch (version 20231120)
  (symbol (lib_id "Reg:AMS1117") (property "Reference" "U1") (property "Value" "AMS1117-3.3") (property "Footprint" "SOT-223-3") (property "MPN" "AMS1117-3.3")
    (pin "1" (name "ADJ/GND")) (pin "2" (name "VOUT")) (pin "3" (name "VIN"))
  )
)''', encoding="utf-8")

print("[+] All PinWatch source modules and fixtures generated successfully!")