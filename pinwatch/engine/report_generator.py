from tabulate import tabulate
from pinwatch.models import AuditDossier, CompatibilityVerdict

class AuditReportGenerator:
    @classmethod
    def generate_markdown(cls, dossier: AuditDossier) -> str:
        lines = [
            f"# Hardware Component Obsolescence & Pinout Substitution Audit Dossier",
            f"**Project:** {dossier.project_name} | **Analyzed:** {dossier.total_components_analyzed} | **Vulnerabilities:** {dossier.components_with_issues}\n",
            "---",
            "## Executive Summary\n"
        ]
        for idx, res in enumerate(dossier.results, 1):
            comp = res.target_component
            lines.append(f"### {idx}. Component Audit: `{comp.reference}` — {comp.value} ({comp.package})")
            lines.append(f"- **Inventory Status:** `{res.inventory_status.value}`")
            lines.append(f"- **Stock on Hand:** {res.inventory_record.stock_qty if res.inventory_record else 0} units\n")

            if not res.candidates:
                lines.append("*No replacement candidates found.*\n")
                continue

            headers = ["Candidate MPN", "Manufacturer", "Source", "Price", "Stock", "Verdict"]
            rows = [
                [f"`{c.mpn}`", c.manufacturer, c.source, f"${c.unit_cost_usd:.3f}", f"{c.stock_qty:,}", f"**{c.verdict.value}**"]
                for c in res.candidates
            ]
            lines.append(tabulate(rows, headers=headers, tablefmt="github") + "\n")

            rec = res.recommended_candidate
            if rec:
                lines.append(f"#### Recommended Replacement: `{rec.mpn}` ({rec.verdict.value})")
                lines.append(f"- **Stock:** {rec.stock_qty:,} via {rec.source}")
                lines.append(f"- **Efficiency:** {rec.efficiency_delta_notes}\n")
                lines.append("##### Pinout Alignment Matrix\n")
                p_headers = ["Pin #", "Original", "Candidate", "Status", "Notes"]
                p_rows = [
                    [p.pin_number, f"{p.original_pin_name} ({p.original_function})", f"{p.candidate_pin_name} ({p.candidate_function})", "PASS" if p.is_match else "FAIL", p.notes]
                    for p in rec.pin_comparisons
                ]
                lines.append(tabulate(p_rows, headers=p_headers, tablefmt="github") + "\n")
            lines.append("---\n")
        return "\n".join(lines)
