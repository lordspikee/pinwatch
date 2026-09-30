import re
from typing import List, Dict, Any, Optional, Tuple
from pinwatch.models import Component, PinDefinition, PinFunction, ComponentType

def parse_sexpr(text: str) -> List[Any]:
    tokens = []
    pattern = re.compile(r'\(|\)|"([^"\\]*(?:\\.[^"\\]*)*)"|([^\s\(\)]+)')
    for match in pattern.finditer(text):
        if match.group(0) == '(':
            tokens.append('(')
        elif match.group(0) == ')':
            tokens.append(')')
        elif match.group(1) is not None:
            tokens.append(match.group(1).replace(r'\"', '"').replace(r'\\', '\\'))
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
        blocks = re.findall(r'\(symbol\s+.*?\n\s*\)', content, re.DOTALL)
        for b in blocks:
            r = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', b)
            v = re.search(r'\(property\s+"Value"\s+"([^"]+)"', b)
            fp = re.search(r'\(property\s+"Footprint"\s+"([^"]+)"', b)
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
            r'(\(\s*symbol[\s\S]*?\(property\s+"Reference"\s+"' + re.escape(reference) + r'"[\s\S]*?\n\s*\))'
        )
        match = symbol_pattern.search(content)
        if not match:
            raise ValueError(f"Component reference '{reference}' not found in schematic.")

        original_block = match.group(1)
        patched_block = original_block

        # Replace Value property
        val_match = re.search(r'\(property\s+"Value"\s+"([^"]+)"', original_block)
        old_val = val_match.group(1) if val_match else "UNKNOWN"
        patched_block = re.sub(
            r'(\(property\s+"Value"\s+)"[^"]+"',
            r'\1"' + new_mpn + '"',
            patched_block
        )

        # Replace or add MPN property
        if 'property "MPN"' in patched_block:
            patched_block = re.sub(
                r'(\(property\s+"MPN"\s+)"[^"]+"',
                r'\1"' + new_mpn + '"',
                patched_block
            )
        else:
            # Inject MPN property right after Value
            patched_block = re.sub(
                r'(\(property\s+"Value"\s+"[^"]+"[^\)]*\))',
                r'\1\n    (property "MPN" "' + new_mpn + '")',
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
