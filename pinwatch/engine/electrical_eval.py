from typing import List
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
