import argparse, json, sys
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
