"""
Utilization-Based Cost Calculator
=================================
Moduł kalkulacji kosztów materiałowych na podstawie utylizacji arkuszy
z wyników nestingu oraz wzoru narzutu kosztów dodatkowych.

Wzór na narzut kosztów dodatkowych (z dokumentacji):
- Z = sum(Xi) - Całkowita wartość zlecenia
- W = K_dod / Z = (T + O*L + D) / sum(Xi) - Współczynnik narzutu
- Ni = Xi * W / ni - Narzut na pojedynczą sztukę detalu i

Gdzie:
- T = Koszt cięcia [PLN]
- O = Koszt obsługi (stawka godzinowa)
- L = Łączny czas obsługi [h]
- D = Inne koszty bezpośrednie
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import json
from pathlib import Path

logger = logging.getLogger(__name__)

# Ścieżka do ustawień kosztowych
COST_CONFIG_PATH = Path(__file__).parent.parent / "config" / "cost_settings.json"


def load_cost_settings() -> Dict:
    """Wczytaj ustawienia kosztów z pliku JSON"""
    default = {
        "sheet_handling_cost": 40.0,
        "foil_removal_speed_m_min": 15.0,
        "foil_removal_hourly_rate": 80.0,
        "piercing_time_inox_base_s": 0.5,
        "piercing_time_inox_per_mm_s": 0.1,
        "piercing_time_steel_base_s": 0.5,
        "piercing_time_steel_per_mm_s": 0.3,
        "time_buffer_percent": 25.0,
        "default_markup_percent": 0.0
    }

    try:
        if COST_CONFIG_PATH.exists():
            with open(COST_CONFIG_PATH, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                for key in default:
                    if key not in settings:
                        settings[key] = default[key]
                return settings
    except Exception as e:
        logger.error(f"Błąd wczytywania ustawień kosztów: {e}")

    return default


@dataclass
class PartCostResult:
    """Wynik kalkulacji kosztów dla pojedynczego detalu"""
    part_name: str
    quantity: int

    # Koszty jednostkowe
    material_cost_unit: float = 0.0       # Koszt materiału na sztukę
    cutting_cost_unit: float = 0.0        # Koszt cięcia na sztukę
    piercing_cost_unit: float = 0.0       # Koszt przebić na sztukę
    marking_cost_unit: float = 0.0        # Koszt graweru na sztukę
    bending_cost_unit: float = 0.0        # Koszt gięcia na sztukę
    foil_removal_cost_unit: float = 0.0   # Koszt usuwania folii na sztukę
    overhead_cost_unit: float = 0.0       # Narzut kosztów dodatkowych na sztukę

    # Sumy
    total_unit_cost: float = 0.0          # Całkowity koszt jednostkowy
    total_cost: float = 0.0               # Całkowity koszt (qty * unit)

    # Dane z nestingu
    sheet_indices: List[int] = field(default_factory=list)  # Na których arkuszach
    avg_utilization: float = 0.0          # Średnia utylizacja arkuszy z tym detalem


@dataclass
class OrderCostResult:
    """Wynik kalkulacji kosztów dla całego zamówienia"""
    # Koszty materiałów
    total_material_cost: float = 0.0
    total_cutting_cost: float = 0.0
    total_piercing_cost: float = 0.0
    total_marking_cost: float = 0.0
    total_bending_cost: float = 0.0
    total_foil_removal_cost: float = 0.0

    # Koszty operacyjne
    total_sheet_handling_cost: float = 0.0
    sheets_used: int = 0

    # Koszty na zlecenie
    technology_cost: float = 0.0
    packaging_cost: float = 0.0
    transport_cost: float = 0.0

    # Narzut
    markup_percent: float = 0.0
    markup_amount: float = 0.0

    # Sumy
    subtotal: float = 0.0                 # Suma przed narzutem
    total: float = 0.0                    # Suma końcowa z narzutem

    # Szczegóły per detal
    parts_costs: List[PartCostResult] = field(default_factory=list)

    # Dodatkowe metryki
    total_cutting_length_m: float = 0.0
    total_marking_length_m: float = 0.0
    total_weight_kg: float = 0.0
    estimated_cutting_time_h: float = 0.0


class UtilizationCostCalculator:
    """
    Kalkulator kosztów z uwzględnieniem utylizacji arkuszy.

    Metody alokacji kosztu materiału:
    1. PROPORTIONAL - proporcjonalnie do pola powierzchni detalu
    2. UTILIZATION_WEIGHTED - ważony utylizacją arkusza
    3. LEGACY - stara metoda (arkusz / utylizacja * udział)
    """

    ALLOCATION_METHODS = ["PROPORTIONAL", "UTILIZATION_WEIGHTED", "LEGACY"]

    def __init__(self):
        self.settings = load_cost_settings()

    def calculate_order_cost(
        self,
        parts: List[Dict],
        nesting_results: Dict = None,
        material_prices: Dict[str, float] = None,
        cutting_speeds: Dict[str, float] = None,
        allocation_method: str = "PROPORTIONAL",
        include_foil_removal: bool = True,
        include_piercing: bool = True,
        technology_cost: float = 0.0,
        packaging_cost: float = 0.0,
        transport_cost: float = 0.0,
        markup_percent: float = None
    ) -> OrderCostResult:
        """
        Oblicz koszty dla całego zamówienia.

        Args:
            parts: Lista detali z danymi (name, quantity, weight_kg, cutting_length_mm, etc.)
            nesting_results: Wyniki nestingu {(material, thickness): NestingResult}
            material_prices: Ceny materiałów {material: PLN/kg}
            cutting_speeds: Prędkości cięcia {material: m/min}
            allocation_method: Metoda alokacji kosztów materiału
            include_foil_removal: Uwzględnij koszt usuwania folii
            include_piercing: Uwzględnij koszt przebić
            technology_cost: Koszty technologii na zlecenie
            packaging_cost: Koszty opakowań na zlecenie
            transport_cost: Koszty transportu na zlecenie
            markup_percent: Narzut procentowy (None = domyślny z ustawień)
        """
        result = OrderCostResult()

        # Domyślne ceny jeśli nie podano
        material_prices = material_prices or {
            'S355': 4.5, 'S235': 4.2, 'DC01': 5.0, 'DC04': 5.2,
            '1.4301': 18.0, '1.4404': 22.0, 'INOX': 18.0,
            'AL': 12.0, 'ALU': 12.0, 'ALUMINIUM': 12.0,
            'DEFAULT': 5.0
        }

        cutting_speeds = cutting_speeds or {
            'S355': 3.0, 'S235': 3.2, 'DC01': 3.5, 'DC04': 3.5,
            '1.4301': 2.5, '1.4404': 2.3, 'INOX': 2.5,
            'AL': 4.0, 'ALU': 4.0, 'ALUMINIUM': 4.0,
            'DEFAULT': 3.0
        }

        if markup_percent is None:
            markup_percent = self.settings.get('default_markup_percent', 0.0)

        result.markup_percent = markup_percent

        # Zbierz informacje o utylizacji z nestingu
        part_utilization_map = self._build_utilization_map(nesting_results) if nesting_results else {}

        # Oblicz koszty per detal
        for part in parts:
            part_cost = self._calculate_part_cost(
                part,
                part_utilization_map,
                material_prices,
                cutting_speeds,
                allocation_method,
                include_foil_removal,
                include_piercing
            )
            result.parts_costs.append(part_cost)

            # Sumuj koszty
            result.total_material_cost += part_cost.material_cost_unit * part_cost.quantity
            result.total_cutting_cost += part_cost.cutting_cost_unit * part_cost.quantity
            result.total_piercing_cost += part_cost.piercing_cost_unit * part_cost.quantity
            result.total_marking_cost += part_cost.marking_cost_unit * part_cost.quantity
            result.total_bending_cost += part_cost.bending_cost_unit * part_cost.quantity
            result.total_foil_removal_cost += part_cost.foil_removal_cost_unit * part_cost.quantity

            result.total_cutting_length_m += part.get('cutting_length_mm', 0) / 1000 * part_cost.quantity
            result.total_marking_length_m += part.get('marking_length_mm', 0) / 1000 * part_cost.quantity
            result.total_weight_kg += part.get('weight_kg', 0) * part_cost.quantity

        # Koszty operacyjne (obsługa arkuszy)
        if nesting_results:
            result.sheets_used = sum(
                r.sheets_used for r in nesting_results.values()
            ) if hasattr(list(nesting_results.values())[0], 'sheets_used') else 0
        else:
            # Szacuj liczbę arkuszy na podstawie wagi
            result.sheets_used = max(1, int(result.total_weight_kg / 50))  # ~50kg/arkusz

        result.total_sheet_handling_cost = (
            result.sheets_used * self.settings.get('sheet_handling_cost', 40.0)
        )

        # Koszty na zlecenie
        result.technology_cost = technology_cost
        result.packaging_cost = packaging_cost
        result.transport_cost = transport_cost

        # Szacuj czas cięcia (z buforem +25%)
        avg_speed = 3.0  # m/min
        cutting_time_min = result.total_cutting_length_m / avg_speed
        buffer = 1.0 + self.settings.get('time_buffer_percent', 25.0) / 100
        result.estimated_cutting_time_h = (cutting_time_min / 60) * buffer

        # Subtotal
        result.subtotal = (
            result.total_material_cost +
            result.total_cutting_cost +
            result.total_piercing_cost +
            result.total_marking_cost +
            result.total_bending_cost +
            result.total_foil_removal_cost +
            result.total_sheet_handling_cost +
            result.technology_cost +
            result.packaging_cost +
            result.transport_cost
        )

        # Narzut
        result.markup_amount = result.subtotal * (markup_percent / 100)
        result.total = result.subtotal + result.markup_amount

        # Oblicz narzut per detal wg wzoru z PDF
        self._calculate_overhead_distribution(result, parts)

        return result

    def _build_utilization_map(self, nesting_results: Dict) -> Dict[str, Dict]:
        """
        Zbuduj mapę utylizacji per detal.

        Returns:
            {part_name: {
                'sheet_indices': [0, 1, ...],
                'utilizations': [0.85, 0.72, ...],
                'avg_utilization': 0.785,
                'sheet_costs': [100.0, 100.0, ...]
            }}
        """
        part_map = {}

        for (material, thickness), nesting_result in nesting_results.items():
            if not hasattr(nesting_result, 'sheets'):
                continue

            for sheet_idx, sheet in enumerate(nesting_result.sheets):
                efficiency = getattr(sheet, 'efficiency', 0.5)

                if hasattr(sheet, 'placed_parts'):
                    for placed_part in sheet.placed_parts:
                        name = getattr(placed_part, 'name', '') or str(placed_part)

                        if name not in part_map:
                            part_map[name] = {
                                'sheet_indices': [],
                                'utilizations': [],
                                'avg_utilization': 0.0,
                                'material': material,
                                'thickness': thickness
                            }

                        part_map[name]['sheet_indices'].append(sheet_idx)
                        part_map[name]['utilizations'].append(efficiency)

        # Oblicz średnie utylizacje
        for name, data in part_map.items():
            if data['utilizations']:
                data['avg_utilization'] = sum(data['utilizations']) / len(data['utilizations'])

        return part_map

    def _calculate_part_cost(
        self,
        part: Dict,
        utilization_map: Dict[str, Dict],
        material_prices: Dict[str, float],
        cutting_speeds: Dict[str, float],
        allocation_method: str,
        include_foil_removal: bool,
        include_piercing: bool
    ) -> PartCostResult:
        """Oblicz koszty dla pojedynczego detalu"""
        name = part.get('name', '')
        quantity = int(part.get('quantity', 1))
        material = part.get('material', 'DEFAULT').upper()
        thickness_mm = float(part.get('thickness_mm', part.get('thickness', 0)) or 0)
        weight_kg = float(part.get('weight_kg', 0) or 0)
        cutting_length_mm = float(part.get('cutting_length_mm', part.get('cutting_len', 0)) or 0)
        marking_length_mm = float(part.get('marking_length_mm', 0) or 0)
        bending_length_mm = float(part.get('bending_length_mm', 0) or 0)
        piercing_count = int(part.get('piercing_count', 1) or 1)
        bends_count = int(part.get('bends', part.get('bends_count', 0)) or 0)

        result = PartCostResult(part_name=name, quantity=quantity)

        # Pobierz dane utylizacji
        util_data = utilization_map.get(name, {})
        result.sheet_indices = util_data.get('sheet_indices', [])
        result.avg_utilization = util_data.get('avg_utilization', 0.7)  # Domyślne 70%

        # 1. KOSZT MATERIAŁU
        mat_price = material_prices.get(material, material_prices.get('DEFAULT', 5.0))

        if allocation_method == "UTILIZATION_WEIGHTED" and result.avg_utilization > 0:
            # Koszt materiału ważony utylizacją
            # Im niższa utylizacja arkusza, tym wyższy koszt per detal
            result.material_cost_unit = weight_kg * mat_price / result.avg_utilization
        elif allocation_method == "LEGACY" and result.avg_utilization > 0:
            # Stara metoda: koszt = waga * cena / utylizacja
            result.material_cost_unit = weight_kg * mat_price / result.avg_utilization
        else:
            # PROPORTIONAL - prosty koszt wg wagi
            result.material_cost_unit = weight_kg * mat_price

        # 2. KOSZT CIĘCIA
        cut_speed = cutting_speeds.get(material, cutting_speeds.get('DEFAULT', 3.0))
        cutting_length_m = cutting_length_mm / 1000
        cutting_time_min = cutting_length_m / cut_speed if cut_speed > 0 else 0
        # Stawka 80 PLN/h = 1.33 PLN/min
        hourly_rate = 80.0
        result.cutting_cost_unit = cutting_time_min * (hourly_rate / 60)

        # 3. KOSZT PRZEBIĆ (PIERCING)
        if include_piercing and piercing_count > 0:
            is_inox = material.startswith('1.4') or 'INOX' in material

            if is_inox:
                base_time = self.settings.get('piercing_time_inox_base_s', 0.5)
                per_mm_time = self.settings.get('piercing_time_inox_per_mm_s', 0.1)
            else:
                base_time = self.settings.get('piercing_time_steel_base_s', 0.5)
                per_mm_time = self.settings.get('piercing_time_steel_per_mm_s', 0.3)

            piercing_time_s = (base_time + per_mm_time * thickness_mm) * piercing_count
            piercing_time_min = piercing_time_s / 60
            result.piercing_cost_unit = piercing_time_min * (hourly_rate / 60)

        # 4. KOSZT GRAWERU (MARKING)
        if marking_length_mm > 0:
            marking_speed = 5.0  # m/min (szybciej niż cięcie)
            marking_time_min = (marking_length_mm / 1000) / marking_speed
            result.marking_cost_unit = marking_time_min * (hourly_rate / 60)

        # 5. KOSZT GIĘCIA
        if bends_count > 0 or bending_length_mm > 0:
            # 3 PLN per gięcie (przykładowa stawka)
            result.bending_cost_unit = bends_count * 3.0

        # 6. KOSZT USUWANIA FOLII
        if include_foil_removal:
            # Domyślnie dla INOX do 5mm
            is_inox = material.startswith('1.4') or 'INOX' in material
            needs_foil = is_inox and thickness_mm <= 5.0

            if needs_foil:
                foil_speed = self.settings.get('foil_removal_speed_m_min', 15.0)
                foil_rate = self.settings.get('foil_removal_hourly_rate', 80.0)

                # Przybliżony obwód detalu
                perimeter_m = cutting_length_mm / 1000
                foil_time_min = perimeter_m / foil_speed if foil_speed > 0 else 0
                result.foil_removal_cost_unit = foil_time_min * (foil_rate / 60)

        # SUMA
        result.total_unit_cost = (
            result.material_cost_unit +
            result.cutting_cost_unit +
            result.piercing_cost_unit +
            result.marking_cost_unit +
            result.bending_cost_unit +
            result.foil_removal_cost_unit
        )

        result.total_cost = result.total_unit_cost * quantity

        return result

    def _calculate_overhead_distribution(self, result: OrderCostResult, parts: List[Dict]):
        """
        Oblicz dystrybucję narzutu wg wzoru z PDF:
        Ni = Xi * W / ni

        Gdzie:
        - Xi = łączna wartość serii detali i
        - W = współczynnik narzutu (K_dod / Z)
        - ni = liczba sztuk detalu i
        """
        if result.subtotal <= 0:
            return

        # Z = suma Xi (całkowita wartość zlecenia)
        Z = sum(pc.total_cost for pc in result.parts_costs)

        if Z <= 0:
            return

        # K_dod = koszty dodatkowe do rozłożenia
        K_dod = (
            result.total_sheet_handling_cost +
            result.technology_cost +
            result.packaging_cost +
            result.transport_cost +
            result.markup_amount
        )

        # W = współczynnik narzutu
        W = K_dod / Z

        # Rozłóż na detale
        for part_cost in result.parts_costs:
            if part_cost.quantity > 0:
                # Xi = total_cost dla tego detalu
                Xi = part_cost.total_cost
                # Ni = narzut na pojedynczą sztukę
                Ni = (Xi * W) / part_cost.quantity

                part_cost.overhead_cost_unit = Ni
                part_cost.total_unit_cost += Ni
                part_cost.total_cost = part_cost.total_unit_cost * part_cost.quantity


# === HELPER FUNCTIONS ===

def calculate_material_cost_with_utilization(
    part_weight_kg: float,
    material_price_per_kg: float,
    sheet_utilization: float = 0.7
) -> float:
    """
    Oblicz koszt materiału z uwzględnieniem utylizacji arkusza.

    Wzór: koszt = waga * cena / utylizacja

    Args:
        part_weight_kg: Waga detalu [kg]
        material_price_per_kg: Cena materiału [PLN/kg]
        sheet_utilization: Utylizacja arkusza (0.0 - 1.0)

    Returns:
        Koszt materiału [PLN]
    """
    if sheet_utilization <= 0:
        sheet_utilization = 0.7  # Domyślne 70%

    return part_weight_kg * material_price_per_kg / sheet_utilization


def get_part_utilization_from_nesting(
    part_name: str,
    nesting_results: Dict
) -> Tuple[float, List[int]]:
    """
    Pobierz średnią utylizację dla detalu z wyników nestingu.

    Returns:
        (avg_utilization, [sheet_indices])
    """
    utilizations = []
    sheet_indices = []

    for (material, thickness), nesting_result in nesting_results.items():
        if not hasattr(nesting_result, 'sheets'):
            continue

        for sheet_idx, sheet in enumerate(nesting_result.sheets):
            efficiency = getattr(sheet, 'efficiency', 0.5)

            if hasattr(sheet, 'placed_parts'):
                for placed_part in sheet.placed_parts:
                    name = getattr(placed_part, 'name', '') or str(placed_part)

                    if name == part_name:
                        utilizations.append(efficiency)
                        sheet_indices.append(sheet_idx)

    avg_util = sum(utilizations) / len(utilizations) if utilizations else 0.7
    return avg_util, sheet_indices


# === TEST ===
if __name__ == "__main__":
    calc = UtilizationCostCalculator()

    test_parts = [
        {
            'name': 'Płyta_A',
            'material': 'S355',
            'thickness_mm': 3.0,
            'quantity': 10,
            'weight_kg': 2.5,
            'cutting_length_mm': 1500,
            'piercing_count': 3
        },
        {
            'name': 'Wspornik_B',
            'material': '1.4301',
            'thickness_mm': 2.0,
            'quantity': 5,
            'weight_kg': 1.2,
            'cutting_length_mm': 800,
            'piercing_count': 2,
            'bends': 2
        }
    ]

    result = calc.calculate_order_cost(
        parts=test_parts,
        markup_percent=10.0,
        technology_cost=50.0,
        packaging_cost=20.0
    )

    print("=== WYNIK KALKULACJI ===")
    print(f"Materiał: {result.total_material_cost:.2f} PLN")
    print(f"Cięcie: {result.total_cutting_cost:.2f} PLN")
    print(f"Przebicia: {result.total_piercing_cost:.2f} PLN")
    print(f"Gięcie: {result.total_bending_cost:.2f} PLN")
    print(f"Folia: {result.total_foil_removal_cost:.2f} PLN")
    print(f"Obsługa arkuszy: {result.total_sheet_handling_cost:.2f} PLN")
    print(f"Technologia: {result.technology_cost:.2f} PLN")
    print(f"Opakowania: {result.packaging_cost:.2f} PLN")
    print("-" * 40)
    print(f"Subtotal: {result.subtotal:.2f} PLN")
    print(f"Narzut ({result.markup_percent}%): {result.markup_amount:.2f} PLN")
    print(f"RAZEM: {result.total:.2f} PLN")
    print()
    print("Per detal:")
    for pc in result.parts_costs:
        print(f"  {pc.part_name}: {pc.total_unit_cost:.2f} PLN/szt x {pc.quantity} = {pc.total_cost:.2f} PLN")
        print(f"    (mat:{pc.material_cost_unit:.2f} cut:{pc.cutting_cost_unit:.2f} "
              f"pierce:{pc.piercing_cost_unit:.2f} bend:{pc.bending_cost_unit:.2f} "
              f"overhead:{pc.overhead_cost_unit:.2f})")
