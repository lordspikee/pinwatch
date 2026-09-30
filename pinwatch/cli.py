import argparse, json, sys
from pathlib import Path
from pinwatch.models import Component
from pinwatch.supply_chain.inventory_client import InventoryClient
from pinwatch.supply_chain.catalog_search import CatalogSearchProvider
from pinwatch.datasheet_agent.qwen_prompt import DatasheetExtractionAgent
from pinwatch.orchestrator import PinWatchAgent
from pinwatch.engine.report_generator import AuditReportGenerator
from pinwatch.parsers.kicad_parser import KiCadSchematicParser

def main():
    parser = argparse.ArgumentParser(prog="pinwatch", description="PinWatch: Hardware PCB Component Obsolescence & Pinout Substitution Watchdog")
    subparsers = parser.add_subparsers(dest="command")

    # audit-schematic
    sch_parser = subparsers.add_parser("audit-schematic")
    sch_parser.add_argument("--schematic", required=True)
    sch_parser.add_argument("--inventory", default="pinwatch/fixtures/inventory.csv")
    sch_parser.add_argument("--catalog", default="pinwatch/fixtures/distributor_catalog.json")

    # check-part
    part_parser = subparsers.add_parser("check-part")
    part_parser.add_argument("--mpn", required=True)
    part_parser.add_argument("--package", required=True)
    part_parser.add_argument("--inventory", default="pinwatch/fixtures/inventory.csv")
    part_parser.add_argument("--catalog", default="pinwatch/fixtures/distributor_catalog.json")

    # patch-schematic
    patch_parser = subparsers.add_parser("patch-schematic")
    patch_parser.add_argument("--schematic", required=True, help="Path to .kicad_sch file")
    patch_parser.add_argument("--ref", required=True, help="Target component reference (e.g. U1)")
    patch_parser.add_argument("--substitute", required=True, help="Replacement MPN (e.g. AZ1117CH-3.3TRG1)")
    patch_parser.add_argument("--output", help="Optional output path (defaults to overwriting input schematic)")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "patch-schematic":
        sch_path = Path(args.schematic)
        if not sch_path.exists():
            print(f"[-] Error: Schematic file '{args.schematic}' not found.")
            sys.exit(1)
        content = sch_path.read_text(encoding="utf-8")
        try:
            patched_content, eco_diff = KiCadSchematicParser.patch_schematic_symbol(content, args.ref, args.substitute)
            out_path = Path(args.output) if args.output else sch_path
            out_path.write_text(patched_content, encoding="utf-8")
            print(eco_diff)
            print(f"\n[+] Successfully patched {args.ref} -> {args.substitute}")
            print(f"[+] Output written to: {out_path}")
        except Exception as e:
            print(f"[-] Failed to patch schematic: {e}")
            sys.exit(1)
        return

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
