"""
NewERP - Cost Calculator
========================
Zaawansowany kalkulator kosztów dla nestingu i wycen.

Obsługuje:
- Koszt materiału (różne modele alokacji)
- Koszt cięcia (cennikowy i czasowy)
- Koszt usuwania folii
- Koszt przebicia (piercing)
- Koszty operacyjne per arkusz
- Koszty technologii
- Koszty opakowań
- Koszty transportu

Warianty wyceny:
- Wariant A: Cennikowy (deterministyczny)
- Wariant B: Czasowy (z buforem +25%)
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum

from .pricing_tables import get_pricing_tables, PricingTables

logger = logging.getLogger(__name__)


# ============================================================
# ENUMS I KONFIGURACJA
# ============================================================

class AllocationModel(Enum):
    """Model alokacji kosztu materiału"""
    LEGACY = "legacy"                    # Stary model (proporcjonalny do utilization)
    ACTUAL_AREA = "actual_area"          # Rzeczywista powierzchnia zużyta
    BOUNDING_BOX = "bounding_box"        # Bounding box po nestingu (zmniejszona oś Y)
    FULL_SHEET = "full_sheet"            # Pełny arkusz (bez optymalizacji)


class CostVariant(Enum):
    """Wariant kalkulacji kosztów"""
    PRICE_BASED = "A"     # Cennikowy (deterministyczny)
    TIME_BASED = "B"      # Czasowy (z buforem)


@dataclass
class FoilRemovalConfig:
    """Konfiguracja usuwania folii"""
    enabled: bool = True
    speed_m_per_min: float = 15.0         # Prędkość zdejmowania [m/min]
    hourly_rate: float = 120.0            # Stawka godzinowa [PLN/h]

    # Domyślne włączenie dla materiałów
    auto_enable_materials: List[str] = field(default_factory=lambda: [
        "1.4301", "1.4404", "1.4571", "INOX", "INOX304", "INOX316"
    ])
    auto_enable_max_thickness: float = 5.0  # Max grubość dla auto-włączenia [mm]


@dataclass
class PiercingConfig:
    """Konfiguracja kosztów przebicia"""
    enabled: bool = True

    # Czas przebicia per materiał i grubość [sekundy]
    # Format: (material_type, thickness_mm) -> time_s
    piercing_times: Dict[Tuple[str, float], float] = field(default_factory=dict)

    # Domyślne czasy jeśli brak w konfiguracji
    default_inox_base: float = 0.5     # Bazowy czas dla inox [s]
    default_inox_per_mm: float = 0.1   # Dodatkowy czas na mm grubości
    default_steel_base: float = 0.5    # Bazowy czas dla stali [s]
    default_steel_per_mm: float = 0.15 # Dodatkowy czas na mm grubości

    # Koszt za przebicie (zależny od materiału i grubości)
    cost_per_pierce: Dict[Tuple[str, float], float] = field(default_factory=dict)
    default_cost_per_pierce: float = 0.10  # Domyślny koszt [PLN]


@dataclass
class OperationalConfig:
    """Konfiguracja kosztów operacyjnych"""
    sheet_handling_cost: float = 40.0      # Koszt załadunku/rozładunku arkusza [PLN]
    setup_cost: float = 50.0               # Koszt przygotowania [PLN]
    programming_cost_per_part: float = 5.0 # Koszt programowania per detal [PLN]
    min_order_cost: float = 100.0          # Minimalny koszt zlecenia [PLN]


@dataclass
class CostConfig:
    """Pełna konfiguracja kosztów"""
    foil: FoilRemovalConfig = field(default_factory=FoilRemovalConfig)
    piercing: PiercingConfig = field(default_factory=PiercingConfig)
    operational: OperationalConfig = field(default_factory=OperationalConfig)

    allocation_model: AllocationModel = AllocationModel.BOUNDING_BOX
    time_buffer_percent: float = 25.0      # Bufor czasowy [%]

    # Koszty per zlecenie
    technology_cost: float = 0.0           # Koszty technologii [PLN]
    packaging_cost: float = 0.0            # Koszty opakowań [PLN]
    transport_cost: float = 0.0            # Koszty transportu [PLN]


# ============================================================
# WYNIKI KALKULACJI
# ============================================================

@dataclass
class PartCost:
    """Koszt pojedynczego detalu"""
    name: str
    quantity: int

    # Koszty jednostkowe
    material_cost: float = 0.0
    cutting_cost: float = 0.0
    foil_cost: float = 0.0
    piercing_cost: float = 0.0

    # Parametry
    cutting_length_m: float = 0.0
    cutting_time_min: float = 0.0
    pierce_count: int = 0
    weight_kg: float = 0.0
    area_m2: float = 0.0

    @property
    def total_unit_cost(self) -> float:
        """Całkowity koszt jednostkowy"""
        return self.material_cost + self.cutting_cost + self.foil_cost + self.piercing_cost

    @property
    def total_cost(self) -> float:
        """Całkowity koszt (qty × jednostkowy)"""
        return self.total_unit_cost * self.quantity


@dataclass
class SheetCost:
    """Koszt pojedynczego arkusza"""
    sheet_index: int
    material: str
    thickness_mm: float

    # Wymiary
    width_mm: float
    height_mm: float           # Pełna wysokość arkusza
    used_height_mm: float      # Rzeczywiście wykorzystana wysokość

    # Koszty
    material_cost: float = 0.0
    cutting_cost: float = 0.0
    foil_cost: float = 0.0
    piercing_cost: float = 0.0
    handling_cost: float = 0.0

    # Parametry
    total_cutting_length_m: float = 0.0
    total_cutting_time_min: float = 0.0
    total_pierce_count: int = 0
    efficiency: float = 0.0
    parts_count: int = 0

    @property
    def total_cost(self) -> float:
        """Całkowity koszt arkusza"""
        return (self.material_cost + self.cutting_cost + self.foil_cost +
                self.piercing_cost + self.handling_cost)


@dataclass
class NestingCostResult:
    """Pełny wynik kalkulacji kosztów nestingu"""
    # Koszty główne
    material_cost: float = 0.0
    cutting_cost: float = 0.0
    foil_cost: float = 0.0
    piercing_cost: float = 0.0
    operational_cost: float = 0.0

    # Koszty per zlecenie
    technology_cost: float = 0.0
    packaging_cost: float = 0.0
    transport_cost: float = 0.0
    setup_cost: float = 0.0

    # Szczegóły
    sheets: List[SheetCost] = field(default_factory=list)
    parts: List[PartCost] = field(default_factory=list)

    # Parametry
    total_sheets: int = 0
    total_parts: int = 0
    total_cutting_length_m: float = 0.0
    total_cutting_time_min: float = 0.0
    total_pierce_count: int = 0
    total_weight_kg: float = 0.0
    average_efficiency: float = 0.0

    # Warianty
    variant: CostVariant = CostVariant.PRICE_BASED
    allocation_model: AllocationModel = AllocationModel.BOUNDING_BOX

    @property
    def subtotal(self) -> float:
        """Suma kosztów produkcyjnych"""
        return (self.material_cost + self.cutting_cost + self.foil_cost +
                self.piercing_cost + self.operational_cost + self.setup_cost)

    @property
    def order_costs(self) -> float:
        """Koszty na zlecenie"""
        return self.technology_cost + self.packaging_cost + self.transport_cost

    @property
    def total_cost(self) -> float:
        """Całkowity koszt"""
        return self.subtotal + self.order_costs

    @property
    def total_time_hours(self) -> float:
        """Całkowity czas produkcji [h]"""
        return self.total_cutting_time_min / 60

    def to_dict(self) -> Dict:
        """Konwersja do słownika"""
        return {
            'material_cost': self.material_cost,
            'cutting_cost': self.cutting_cost,
            'foil_cost': self.foil_cost,
            'piercing_cost': self.piercing_cost,
            'operational_cost': self.operational_cost,
            'technology_cost': self.technology_cost,
            'packaging_cost': self.packaging_cost,
            'transport_cost': self.transport_cost,
            'setup_cost': self.setup_cost,
            'subtotal': self.subtotal,
            'order_costs': self.order_costs,
            'total_cost': self.total_cost,
            'total_sheets': self.total_sheets,
            'total_parts': self.total_parts,
            'total_cutting_length_m': self.total_cutting_length_m,
            'total_cutting_time_min': self.total_cutting_time_min,
            'total_time_hours': self.total_time_hours,
            'total_pierce_count': self.total_pierce_count,
            'total_weight_kg': self.total_weight_kg,
            'average_efficiency': self.average_efficiency,
            'variant': self.variant.value,
            'allocation_model': self.allocation_model.value,
        }


# ============================================================
# KALKULATOR KOSZTÓW
# ============================================================

class CostCalculator:
    """
    Zaawansowany kalkulator kosztów dla nestingu.

    Użycie:
        calc = CostCalculator()

        # Konfiguracja
        calc.config.foil.enabled = True
        calc.config.operational.sheet_handling_cost = 40.0

        # Kalkulacja
        result = calc.calculate_nesting_cost(nesting_result)

        # Wariant czasowy
        result_b = calc.calculate_nesting_cost(nesting_result, variant=CostVariant.TIME_BASED)
    """

    def __init__(self, pricing: PricingTables = None, config: CostConfig = None):
        self.pricing = pricing or get_pricing_tables()
        self.config = config or CostConfig()

    def calculate_nesting_cost(
        self,
        nesting_result: Any,
        material: str,
        thickness_mm: float,
        variant: CostVariant = CostVariant.PRICE_BASED,
        **kwargs
    ) -> NestingCostResult:
        """
        Oblicz koszty na podstawie wyniku nestingu.

        Args:
            nesting_result: Wynik z FastNester
            material: Materiał (np. "1.4301")
            thickness_mm: Grubość [mm]
            variant: Wariant kalkulacji (A/B)
            **kwargs: Nadpisanie kosztów (technology_cost, packaging_cost, transport_cost)

        Returns:
            NestingCostResult z pełnym rozbiciem kosztów
        """
        result = NestingCostResult(
            variant=variant,
            allocation_model=self.config.allocation_model
        )

        # Pobierz ceny
        mat_price = self.pricing.get_material_price(material, thickness_mm)
        cut_rate = self.pricing.get_cutting_rate(material, thickness_mm)

        if not mat_price:
            logger.warning(f"No material price for {material} {thickness_mm}mm")
        if not cut_rate:
            logger.warning(f"No cutting rate for {material} {thickness_mm}mm")

        # Sprawdź czy folia powinna być włączona
        foil_enabled = self._should_enable_foil(material, thickness_mm)

        # Przetwórz arkusze
        for idx, sheet in enumerate(nesting_result.sheets):
            sheet_cost = self._calculate_sheet_cost(
                sheet, idx, material, thickness_mm,
                mat_price, cut_rate, foil_enabled, variant
            )
            result.sheets.append(sheet_cost)

            # Sumuj koszty
            result.material_cost += sheet_cost.material_cost
            result.cutting_cost += sheet_cost.cutting_cost
            result.foil_cost += sheet_cost.foil_cost
            result.piercing_cost += sheet_cost.piercing_cost
            result.operational_cost += sheet_cost.handling_cost

            # Sumuj parametry
            result.total_cutting_length_m += sheet_cost.total_cutting_length_m
            result.total_cutting_time_min += sheet_cost.total_cutting_time_min
            result.total_pierce_count += sheet_cost.total_pierce_count

        # Statystyki
        result.total_sheets = len(nesting_result.sheets)
        result.total_parts = len(nesting_result.placed_parts)

        if result.sheets:
            result.average_efficiency = sum(s.efficiency for s in result.sheets) / len(result.sheets)

        # Waga całkowita
        if mat_price:
            total_area_m2 = sum(
                (s.width_mm / 1000) * (s.used_height_mm / 1000)
                for s in result.sheets
            )
            kg_per_m2 = (thickness_mm / 1000) * mat_price.density_kg_m3
            result.total_weight_kg = total_area_m2 * kg_per_m2

        # Koszty setup
        result.setup_cost = self.config.operational.setup_cost

        # Koszty na zlecenie (z kwargs lub config)
        result.technology_cost = kwargs.get('technology_cost', self.config.technology_cost)
        result.packaging_cost = kwargs.get('packaging_cost', self.config.packaging_cost)
        result.transport_cost = kwargs.get('transport_cost', self.config.transport_cost)

        # Bufor czasowy dla wariantu B
        if variant == CostVariant.TIME_BASED:
            buffer_factor = 1 + (self.config.time_buffer_percent / 100)
            result.cutting_cost *= buffer_factor
            result.foil_cost *= buffer_factor
            result.piercing_cost *= buffer_factor
            result.total_cutting_time_min *= buffer_factor

        return result

    def _calculate_sheet_cost(
        self,
        sheet: Any,
        sheet_index: int,
        material: str,
        thickness_mm: float,
        mat_price,
        cut_rate,
        foil_enabled: bool,
        variant: CostVariant
    ) -> SheetCost:
        """Oblicz koszt pojedynczego arkusza"""

        sheet_width = sheet.sheet_width if hasattr(sheet, 'sheet_width') else 3000
        sheet_height = sheet.sheet_height if hasattr(sheet, 'sheet_height') else 1500

        # Oblicz rzeczywiście wykorzystaną wysokość (bounding box)
        used_height = self._calculate_used_height(sheet)

        sheet_cost = SheetCost(
            sheet_index=sheet_index,
            material=material,
            thickness_mm=thickness_mm,
            width_mm=sheet_width,
            height_mm=sheet_height,
            used_height_mm=used_height,
            efficiency=sheet.efficiency if hasattr(sheet, 'efficiency') else 0,
            parts_count=len(sheet.placed_parts) if hasattr(sheet, 'placed_parts') else 0
        )

        # === KOSZT MATERIAŁU ===
        if mat_price:
            sheet_cost.material_cost = self._calculate_material_cost(
                sheet_width, sheet_height, used_height,
                mat_price, sheet_cost.efficiency
            )

        # === PARAMETRY CIĘCIA ===
        total_cutting_length = 0.0
        total_pierce_count = 0

        for part in sheet.placed_parts:
            # Długość cięcia
            perimeter = self._get_part_perimeter(part)
            total_cutting_length += perimeter

            # Liczba przebić (kontury + otwory)
            pierce_count = 1  # Główny kontur
            if hasattr(part, 'holes'):
                pierce_count += len(part.holes)
            elif hasattr(part, 'get_placed_holes'):
                pierce_count += len(part.get_placed_holes())
            total_pierce_count += pierce_count

        sheet_cost.total_cutting_length_m = total_cutting_length / 1000  # mm -> m
        sheet_cost.total_pierce_count = total_pierce_count

        # === KOSZT CIĘCIA ===
        if cut_rate:
            if variant == CostVariant.PRICE_BASED:
                # Wariant A: cennikowy (PLN/m)
                sheet_cost.cutting_cost = sheet_cost.total_cutting_length_m * cut_rate.cost_per_meter
            else:
                # Wariant B: czasowy
                cutting_time_min = (total_cutting_length / cut_rate.speed_mm_min)
                sheet_cost.total_cutting_time_min = cutting_time_min
                hourly_rate = cut_rate.cost_per_hour if cut_rate.cost_per_hour else self.pricing.laser_hourly_rate
                sheet_cost.cutting_cost = (cutting_time_min / 60) * hourly_rate

        # === KOSZT PRZEBICIA ===
        if self.config.piercing.enabled and cut_rate:
            pierce_time_s = self._get_pierce_time(material, thickness_mm)
            total_pierce_time_min = (total_pierce_count * pierce_time_s) / 60

            if variant == CostVariant.PRICE_BASED:
                pierce_cost = self.config.piercing.cost_per_pierce.get(
                    (material, thickness_mm),
                    self.config.piercing.default_cost_per_pierce
                )
                sheet_cost.piercing_cost = total_pierce_count * pierce_cost
            else:
                hourly_rate = cut_rate.cost_per_hour if cut_rate.cost_per_hour else self.pricing.laser_hourly_rate
                sheet_cost.piercing_cost = (total_pierce_time_min / 60) * hourly_rate
                sheet_cost.total_cutting_time_min += total_pierce_time_min

        # === KOSZT FOLII ===
        if foil_enabled and self.config.foil.enabled:
            # Szacuj długość folii jako obwód wszystkich detali
            foil_length_m = sheet_cost.total_cutting_length_m
            foil_time_min = foil_length_m / self.config.foil.speed_m_per_min
            sheet_cost.foil_cost = (foil_time_min / 60) * self.config.foil.hourly_rate

        # === KOSZT OBSŁUGI ARKUSZA ===
        sheet_cost.handling_cost = self.config.operational.sheet_handling_cost

        return sheet_cost

    def _calculate_material_cost(
        self,
        sheet_width: float,
        sheet_height: float,
        used_height: float,
        mat_price,
        efficiency: float
    ) -> float:
        """
        Oblicz koszt materiału według wybranego modelu alokacji.
        """
        model = self.config.allocation_model

        # Oblicz cenę za m²
        price_per_m2 = mat_price.price_per_m2_calculated

        if model == AllocationModel.FULL_SHEET:
            # Pełny arkusz
            area_m2 = (sheet_width / 1000) * (sheet_height / 1000)
            return area_m2 * price_per_m2

        elif model == AllocationModel.BOUNDING_BOX:
            # Zmniejszona wysokość (bounding box)
            area_m2 = (sheet_width / 1000) * (used_height / 1000)
            return area_m2 * price_per_m2

        elif model == AllocationModel.ACTUAL_AREA:
            # Rzeczywista powierzchnia (pełny arkusz × efficiency)
            full_area_m2 = (sheet_width / 1000) * (sheet_height / 1000)
            used_area_m2 = full_area_m2 * efficiency
            return used_area_m2 * price_per_m2

        elif model == AllocationModel.LEGACY:
            # Stary model: pełny arkusz z korektą utilization
            full_area_m2 = (sheet_width / 1000) * (sheet_height / 1000)
            # Jeśli utilization = 80%, to koszt = 100%/80% = 125%
            if efficiency > 0:
                return (full_area_m2 * price_per_m2) / efficiency
            return full_area_m2 * price_per_m2

        return 0.0

    def _calculate_used_height(self, sheet: Any) -> float:
        """
        Oblicz rzeczywiście wykorzystaną wysokość arkusza (max Y detali).
        """
        if not hasattr(sheet, 'placed_parts') or not sheet.placed_parts:
            return sheet.sheet_height if hasattr(sheet, 'sheet_height') else 1500

        max_y = 0.0
        for part in sheet.placed_parts:
            part_y = part.y if hasattr(part, 'y') else 0
            part_h = part.height if hasattr(part, 'height') else 0
            max_y = max(max_y, part_y + part_h)

        # Dodaj margines (np. 10mm)
        return max_y + 10

    def _get_part_perimeter(self, part: Any) -> float:
        """Pobierz obwód detalu [mm]"""
        if hasattr(part, 'perimeter') and part.perimeter:
            return part.perimeter

        if hasattr(part, 'get_placed_contour'):
            contour = part.get_placed_contour()
            if contour and len(contour) >= 3:
                perimeter = 0.0
                for i in range(len(contour)):
                    x1, y1 = contour[i]
                    x2, y2 = contour[(i + 1) % len(contour)]
                    perimeter += ((x2 - x1)**2 + (y2 - y1)**2) ** 0.5
                return perimeter

        # Fallback: przybliżenie prostokątne
        w = part.width if hasattr(part, 'width') else 100
        h = part.height if hasattr(part, 'height') else 100
        return 2 * (w + h)

    def _get_pierce_time(self, material: str, thickness_mm: float) -> float:
        """Pobierz czas przebicia [s]"""
        # Sprawdź konfigurację
        key = (material.upper(), thickness_mm)
        if key in self.config.piercing.piercing_times:
            return self.config.piercing.piercing_times[key]

        # Domyślne wartości
        material_upper = material.upper()
        is_inox = any(m in material_upper for m in ['1.43', '1.44', '1.45', 'INOX'])

        if is_inox:
            return self.config.piercing.default_inox_base + (thickness_mm * self.config.piercing.default_inox_per_mm)
        else:
            return self.config.piercing.default_steel_base + (thickness_mm * self.config.piercing.default_steel_per_mm)

    def _should_enable_foil(self, material: str, thickness_mm: float) -> bool:
        """Sprawdź czy folia powinna być domyślnie włączona"""
        if not self.config.foil.enabled:
            return False

        material_upper = material.upper()

        # Sprawdź czy materiał jest na liście auto-enable
        for mat in self.config.foil.auto_enable_materials:
            if mat.upper() in material_upper or material_upper in mat.upper():
                # Sprawdź grubość
                if thickness_mm <= self.config.foil.auto_enable_max_thickness:
                    return True

        return False

    def estimate_part_cost(
        self,
        part_data: Dict,
        material: str,
        thickness_mm: float,
        quantity: int = 1
    ) -> PartCost:
        """
        Szacuj koszt pojedynczego detalu (bez nestingu).

        Args:
            part_data: Słownik z danymi detalu (width, height, contour, holes)
            material: Materiał
            thickness_mm: Grubość
            quantity: Ilość

        Returns:
            PartCost z szacowanymi kosztami
        """
        mat_price = self.pricing.get_material_price(material, thickness_mm)
        cut_rate = self.pricing.get_cutting_rate(material, thickness_mm)

        part_cost = PartCost(
            name=part_data.get('name', 'Unknown'),
            quantity=quantity
        )

        width = part_data.get('width', 100)
        height = part_data.get('height', 100)

        # Powierzchnia
        part_cost.area_m2 = (width / 1000) * (height / 1000)

        # Waga
        if mat_price:
            kg_per_m2 = (thickness_mm / 1000) * mat_price.density_kg_m3
            part_cost.weight_kg = part_cost.area_m2 * kg_per_m2

            # Koszt materiału (z buforem 20% na odpady)
            part_cost.material_cost = part_cost.area_m2 * mat_price.price_per_m2_calculated * 1.2

        # Długość cięcia
        contour = part_data.get('contour', [])
        if contour and len(contour) >= 3:
            perimeter = 0.0
            for i in range(len(contour)):
                x1, y1 = contour[i]
                x2, y2 = contour[(i + 1) % len(contour)]
                perimeter += ((x2 - x1)**2 + (y2 - y1)**2) ** 0.5
            part_cost.cutting_length_m = perimeter / 1000
        else:
            part_cost.cutting_length_m = 2 * (width + height) / 1000

        # Liczba przebić
        holes = part_data.get('holes', [])
        part_cost.pierce_count = 1 + len(holes)

        # Koszt cięcia
        if cut_rate:
            part_cost.cutting_cost = part_cost.cutting_length_m * cut_rate.cost_per_meter
            part_cost.cutting_time_min = (part_cost.cutting_length_m * 1000) / cut_rate.speed_mm_min

        # Koszt przebicia
        pierce_cost = self.config.piercing.default_cost_per_pierce
        part_cost.piercing_cost = part_cost.pierce_count * pierce_cost

        # Koszt folii
        if self._should_enable_foil(material, thickness_mm):
            foil_time_min = part_cost.cutting_length_m / self.config.foil.speed_m_per_min
            part_cost.foil_cost = (foil_time_min / 60) * self.config.foil.hourly_rate

        return part_cost


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_cost_calculator() -> CostCalculator:
    """Pobierz globalną instancję kalkulatora"""
    return CostCalculator()


def calculate_quick_estimate(
    parts: List[Dict],
    material: str,
    thickness_mm: float
) -> Dict:
    """
    Szybka wycena bez pełnego nestingu.

    Returns:
        Dict z szacowanymi kosztami
    """
    calc = CostCalculator()

    total_material = 0.0
    total_cutting = 0.0
    total_piercing = 0.0
    total_foil = 0.0
    total_weight = 0.0
    total_area = 0.0
    total_cutting_length = 0.0

    for part_data in parts:
        qty = part_data.get('quantity', 1)
        part_cost = calc.estimate_part_cost(part_data, material, thickness_mm, qty)

        total_material += part_cost.material_cost * qty
        total_cutting += part_cost.cutting_cost * qty
        total_piercing += part_cost.piercing_cost * qty
        total_foil += part_cost.foil_cost * qty
        total_weight += part_cost.weight_kg * qty
        total_area += part_cost.area_m2 * qty
        total_cutting_length += part_cost.cutting_length_m * qty

    # Dodaj koszty operacyjne (szacowane arkusze)
    estimated_sheets = max(1, int(total_area / 4.5) + 1)  # ~4.5m² na arkusz
    operational = estimated_sheets * calc.config.operational.sheet_handling_cost

    subtotal = total_material + total_cutting + total_piercing + total_foil + operational

    return {
        'material_cost': total_material,
        'cutting_cost': total_cutting,
        'piercing_cost': total_piercing,
        'foil_cost': total_foil,
        'operational_cost': operational,
        'subtotal': subtotal,
        'total_weight_kg': total_weight,
        'total_area_m2': total_area,
        'total_cutting_length_m': total_cutting_length,
        'estimated_sheets': estimated_sheets,
        'note': 'Szacunek bez nestingu - rzeczywiste koszty mogą się różnić'
    }


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    calc = CostCalculator()

    # Test szacowania pojedynczego detalu
    test_part = {
        'name': 'Test_Plate',
        'width': 200,
        'height': 150,
        'contour': [(0, 0), (200, 0), (200, 150), (0, 150)],
        'holes': [[(50, 50), (70, 50), (70, 70), (50, 70)]]
    }

    cost = calc.estimate_part_cost(test_part, '1.4301', 2.0, quantity=10)

    print("="*60)
    print(f"Detal: {cost.name}")
    print(f"Ilość: {cost.quantity}")
    print(f"Powierzchnia: {cost.area_m2:.4f} m²")
    print(f"Waga: {cost.weight_kg:.2f} kg")
    print(f"Długość cięcia: {cost.cutting_length_m:.2f} m")
    print(f"Liczba przebić: {cost.pierce_count}")
    print("-"*60)
    print(f"Koszt materiału: {cost.material_cost:.2f} PLN")
    print(f"Koszt cięcia: {cost.cutting_cost:.2f} PLN")
    print(f"Koszt przebicia: {cost.piercing_cost:.2f} PLN")
    print(f"Koszt folii: {cost.foil_cost:.2f} PLN")
    print("-"*60)
    print(f"Koszt jednostkowy: {cost.total_unit_cost:.2f} PLN")
    print(f"Koszt całkowity ({cost.quantity} szt): {cost.total_cost:.2f} PLN")
    print("="*60)
