from typing import List, Optional
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
