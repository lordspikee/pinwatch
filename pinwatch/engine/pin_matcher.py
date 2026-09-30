from typing import List, Tuple
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
