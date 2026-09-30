from enum import Enum
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
