import re
from pathlib import Path

print("[*] Updating pinwatch with automated schematic patching...")

# 1. Update pinwatch/parsers/kicad_parser.py with patch_symbol functionality
kicad_parser_code = '''import re
from typing import List, Dict, Any, Optional, Tuple
from pinwatch.models import Component, PinDefinition, PinFunction, ComponentType

def parse_sexpr(text: str) -> List[Any]:
    tokens = []
    pattern = re.compile(r'\\(|\\)|"([^"\\\\]*(?:\\\\.[^"\\\\]*)*)"|([^\\s\\(\\)]+)')
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
                    pin_num = str(elem)
                    pin_name = f"Pin_{pin_num}"
                    for sub in elem:
                        if isinstance(sub, list) and sub and sub[0] == "name" and len(sub) >= 2:
                            pin_name = str(sub)
                    pins.append(PinDefinition(
                        pin_number=pin_num,
                        pin_name=pin_name,
                        function=self._infer_pin_function(pin_name)
                    ))

        ref = properties.get("Reference", "")
        val = properties.get("Value", "")
        footprint = properties.get("Footprint", "Unknown")
        if ":" in footprint:
            footprint = footprint.split(":", 1)

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

    @staticmethod
    def patch_schematic_symbol(content: str, reference: str, new_mpn: str) -> Tuple[str, str]:
        """
        Rewrites the specified symbol's Value and MPN in the KiCad S-expression.
        Preserves all coordinates, wire connections, and pin definitions.
        """
        # Find symbol block with target reference
        symbol_pattern = re.compile(
            r'(\\(\\s*symbol[\\s\\S]*?\\(property\\s+"Reference"\\s+"' + re.escape(reference) + r'"[\\s\\S]*?\\n\\s*\\))'
        )
        match = symbol_pattern.search(content)
        if not match:
            raise ValueError(f"Component reference '{reference}' not found in schematic.")

        original_block = match.group(1)
        patched_block = original_block

        # Replace Value property
        val_match = re.search(r'\\(property\\s+"Value"\\s+"([^"]+)"', original_block)
        old_val = val_match.group(1) if val_match else "UNKNOWN"
        patched_block = re.sub(
            r'(\\(property\\s+"Value"\\s+)"[^"]+"',
            r'\\1"' + new_mpn + '"',
            patched_block
        )

        # Replace or add MPN property
        if 'property "MPN"' in patched_block:
            patched_block = re.sub(
                r'(\\(property\\s+"MPN"\\s+)"[^"]+"',
                r'\\1"' + new_mpn + '"',
                patched_block
            )
        else:
            # Inject MPN property right after Value
            patched_block = re.sub(
                r'(\\(property\\s+"Value"\\s+"[^"]+"[^\)]*\\))',
                r'\\1\\n    (property "MPN" "' + new_mpn + '")',
                patched_block
            )

        new_content = content[:match.start()] + patched_block + content[match.end():]
        eco_diff = f"""=======================================================
ENGINEERING CHANGE ORDER (ECO) - SCHEMATIC IN-PLACE PATCH
=======================================================
Target Reference : {reference}
Previous Value   : {old_val}
Approved Sub MPN : {new_mpn}
Status           : KiCad Netlist & Wiring Preserved
======================================================="""
        return new_content, eco_diff
'''
Path("pinwatch/parsers/kicad_parser.py").write_text(kicad_parser_code, encoding="utf-8")

# 2. Update pinwatch/cli.py to add patch-schematic subcommand
cli_code = '''import argparse, json, sys
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
            print(f"\\n[+] Successfully patched {args.ref} -> {args.substitute}")
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
'''
Path("pinwatch/cli.py").write_text(cli_code, encoding="utf-8")

print("[+] pinwatch/parsers/kicad_parser.py and pinwatch/cli.py updated successfully!")