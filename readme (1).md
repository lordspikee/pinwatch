# PinWatch: PCB Component Obsolescence & Substitution Agent

PinWatch is an autonomous hardware watchdog agent for electronics engineers, hardware startups, and PCB manufacturing teams. When microchips or active components experience supply chain shortages, end-of-life (EOL) obsolescence, or stockouts, PinWatch audits circuit schematics, queries distributor catalogs, verifies pin-for-pin alignment, and evaluates electrical operating envelopes to find safe drop-in replacements.

---

## 1. Problem Statement & Mission

In physical hardware design, substituting parts during supply chain disruptions carries significant risk:

* **The "Reversed Pin" Trap:** Components often share identical packages (e.g. SOT-223-3) and voltage ratings (e.g. 3.3V LDO) but feature reversed pinouts (e.g. AMS1117 has GND-VOUT-VIN, while MCP1700 has GND-VIN-VOUT). Swapping them without PCB routing changes causes an instant short circuit and destroys the board.
* **Datasheet Ingestion Bottleneck:** Parametric distributor databases only show high-level specs. Verifying true pin-for-pin parity requires engineers to manually read multi-page datasheets to check pin multiplexing, dropout curves, and thermal limits.
* **Supply Chain Volatility:** Component lead times fluctuate unpredictably. Engineering teams spend weeks searching distributor catalogs whenever an essential chip goes out of stock.

PinWatch automates this pipeline with deterministic safety verification to catch hardware incompatibilities before manufacturing.

---

## 2. Agent Architecture

```text
Hardware Designer / Procurement
  │  Uploads .kicad_sch or BOM CSV
  ▼
KiCad S-Expression / BOM Parser
  │  Extracts reference designators, package footprints, MPNs, and active netlist
  ▼
Supply Chain Inventory Client
  │  Flags OUT_OF_STOCK, LOW_STOCK, and OBSOLETE parts against catalogs
  ▼
Parametric Catalog Provider
  │  Queries candidate parts matching footprint (SOT-223, SOT-23-5, SOIC-8, etc.)
  ▼
Multimodal Datasheet Ingestion Engine
  │  Extracts pinout assignments and electrical ratings into structured schemas
  ▼
Deterministic Pin Safety Matcher
  │  Verifies functional pin-by-pin netlist alignment (POWER_IN, POWER_OUT, GND, EN)
  ▼
Electrical Operating Envelope Evaluator
  │  Calculates dropout delta, quiescent current, and voltage headroom
  ▼
Automated ECO & Schematic Patcher
  │  Outputs compatibility dossier (DROP_IN, CONDITIONALLY_COMPATIBLE, REQUIRES_REWORK)
  │  Directly patches KiCad schematic symbols and exports Engineering Change Orders
```

---

## 3. Core Engine Components

### 3.1 EDA Schematic & BOM Parser
* **Native KiCad Support:** Ingests KiCad v6, v7, and v8 (`.kicad_sch`) S-expression syntax to extract symbols, nets, and footprints.
* **Universal BOM Support:** Parses standard Bill of Materials CSV files exported from KiCad, Altium Designer, OrCAD, and Eagle.

### 3.2 Deterministic Pinout Safety Engine
* Classifies pin roles into discrete functional types: `POWER_IN`, `POWER_OUT`, `GROUND`, `ENABLE`, `SIGNAL_IN`, `SIGNAL_OUT`, `BIDIRECTIONAL`, and `NO_CONNECT`.
* Evaluates candidate pins against the original netlist to issue compatibility verdicts:
  * **DROP_IN_COMPATIBLE:** 100% pin function and footprint match; safe to assemble with zero layout changes.
  * **CONDITIONALLY_COMPATIBLE:** Pinout matches, but operating boundaries require design review (e.g. higher dropout voltage).
  * **REQUIRES_PCB_REWORK:** Footprint matches but pin assignments differ (e.g. swapped power/ground pins).
  * **INCOMPATIBLE:** Footprint or functional mismatch.

### 3.3 Electrical Envelope & Efficiency Evaluator
* Evaluates input voltage tolerance ($V_{IN}$) and maximum output current capacity ($I_{OUT}$).
* Computes dropout voltage delta ($\Delta V_{do}$) to guarantee adequate headroom in battery-powered circuits.
* Quantifies quiescent current delta ($\Delta I_q$) to assess battery life impact during sleep/standby modes.

---

## 4. Validated Component Substitution Example

Audit results from an environmental IoT sensor board fixture:

| Parameter | Original Target | Recommended Drop-In | Hazardous Candidate Flagged |
| :--- | :--- | :--- | :--- |
| **Part Number (MPN)** | `AMS1117-3.3` | `AZ1117CH-3.3TRG1` | `MCP1700T-3302E/MB` |
| **Manufacturer** | Advanced Monolithic Systems | Diodes Incorporated | Microchip Technology |
| **Package** | SOT-223-3 | SOT-223-3 | SOT-223-3 |
| **Stock Status** | `OBSOLETE` (0 units) | `IN_STOCK` (22,000 units) | `IN_STOCK` (11,000 units) |
| **Pin 1 / 2 / 3** | GND / VOUT / VIN | GND / VOUT / VIN | GND / VIN / VOUT *(Reversed)* |
| **Verdict** | Baseline Target | **DROP_IN_COMPATIBLE** | **REQUIRES_PCB_REWORK** |
| **Safety Notes** | EOL component | 100% pinout match; 1,000 µA lower quiescent current | Inverted power pins; causes an immediate short circuit |

---

## 5. User Interfaces & Tooling

### Web Application (`pinwatch-web`)
* **Interactive Drag-and-Drop:** Upload active `.kicad_sch` or `.csv` files directly in the browser.
* **Live Parity Verification:** Displays pin alignment matrices, stock quantity badges, and supplier pricing.
* **One-Click Schematic Patching:** Generates and downloads a patched `.kicad_sch` file with replacement MPNs.

### Command-Line Interface (`CLI`)
```bash
# Audit a complete KiCad schematic
python3 -m pinwatch.cli audit-schematic \
  --schematic fixtures/sample_board.kicad_sch \
  --inventory fixtures/inventory.csv \
  --catalog fixtures/distributor_catalog.json \
  --output audit_report.md

# Audit a specific hardware part number
python3 -m pinwatch.cli check-part \
  --mpn AMS1117-3.3 \
  --package SOT-223-3 \
  --inventory fixtures/inventory.csv \
  --catalog fixtures/distributor_catalog.json
```

---

## 6. Deliverables & Outputs

1. **Audit Dossier (`audit_report.md`):** Detailed Markdown breakdown of circuit components, supply chain risks, and vetted substitution candidates.
2. **Patched Schematics (`patched_*.kicad_sch`):** Ready-to-commit KiCad schematic with updated library identifiers and metadata.
3. **Engineering Change Order (`ECO.txt`):** Formal change-tracking record documenting replacement rationale, pinout compatibility, and supplier SKU allocations.