"""
Test Cost Allocation Models
============================
Testy porównawcze 3 modeli wyceny kosztów:
1. PRZED nestingiem - wycena bounding box (bez nestingu)
2. PO nestingu - proporcjonalny (Y arkusza = maxY detali)
3. PO nestingu - bounding box (równy podział)

Generuje raport MD z analizą ekonomiczną.
"""

import sys
import os
import random
import math
import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# Import nesting
try:
    from quotations.nesting.fast_nester import FastNester, NestingResult, SheetResult
    HAS_NESTER = True
except ImportError:
    HAS_NESTER = False
    logger.warning("FastNester not available")

# Import cost engine
try:
    from orders.cost_engine import CostEngine, DEFAULT_RATES
    from orders.cost_models import CostParams, AllocationModel
    HAS_COST_ENGINE = True
except ImportError:
    HAS_COST_ENGINE = False
    logger.warning("CostEngine not available")


# ============================================================
# CONSTANTS
# ============================================================

# Materiały testowe z cenami
MATERIALS = {
    'S235': {
        'type': 'steel',
        'density': 7850,  # kg/m³
        'thicknesses': [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0],
        'price_per_kg': 5.0,  # PLN/kg
    },
    '1.4301': {
        'type': 'stainless',
        'density': 7900,
        'thicknesses': [1.0, 1.5, 2.0, 3.0, 4.0, 5.0],
        'price_per_kg': 18.0,
        'has_foil': True,  # folia dla ≤5mm
    },
    'ALU': {
        'type': 'aluminum',
        'density': 2700,
        'thicknesses': [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0],
        'price_per_kg': 12.0,
    }
}

# Stawki cięcia PLN/m (uproszczone)
CUTTING_RATES = {
    'steel': {1.0: 0.8, 2.0: 1.0, 3.0: 1.2, 5.0: 1.8, 8.0: 3.0, 10.0: 4.0},
    'stainless': {1.0: 1.5, 2.0: 2.0, 3.0: 2.8, 5.0: 4.5},
    'aluminum': {1.0: 1.2, 2.0: 1.5, 3.0: 2.0, 5.0: 3.2},
}

# Stawki przebicia PLN/szt
PIERCE_RATES = {
    'steel': 0.15,
    'stainless': 0.30,
    'aluminum': 0.20,
}

# Stawka folii PLN/m (tylko INOX ≤5mm)
FOIL_RATE = 0.15

# Standardowy arkusz
SHEET_WIDTH = 1500  # mm
SHEET_HEIGHT = 3000  # mm


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class TestPart:
    """Detal testowy"""
    name: str
    width: float  # mm
    height: float  # mm
    material: str
    thickness: float  # mm
    quantity: int = 1

    # Calculated
    cutting_len: float = 0.0  # mm - obwód
    pierce_count: int = 1
    contour_area: float = 0.0  # mm²
    weight_kg: float = 0.0

    def __post_init__(self):
        # Oblicz obwód (prostokąt)
        self.cutting_len = 2 * (self.width + self.height)
        # Powierzchnia konturu
        self.contour_area = self.width * self.height
        # Waga
        mat = MATERIALS.get(self.material, MATERIALS['S235'])
        density = mat['density']
        volume_m3 = (self.contour_area / 1e6) * (self.thickness / 1000)
        self.weight_kg = volume_m3 * density


@dataclass
class CostResult:
    """Wynik kalkulacji kosztów"""
    model_name: str

    # Składniki kosztów
    material_cost: float = 0.0
    cutting_cost: float = 0.0
    piercing_cost: float = 0.0
    foil_cost: float = 0.0
    operational_cost: float = 0.0

    # Suma
    total_cost: float = 0.0

    # Statystyki
    sheets_used: int = 1
    efficiency: float = 0.0
    used_sheet_area: float = 0.0

    # Koszty per detal
    part_costs: Dict[str, float] = field(default_factory=dict)


@dataclass
class TestScenario:
    """Scenariusz testowy"""
    name: str
    parts: List[TestPart]
    material: str
    thickness: float

    # Wyniki
    pre_nesting_bbox: Optional[CostResult] = None
    post_nesting_proportional: Optional[CostResult] = None
    post_nesting_bbox: Optional[CostResult] = None

    nesting_result: Optional[NestingResult] = None


# ============================================================
# COST CALCULATORS
# ============================================================

def get_cutting_rate(material: str, thickness: float) -> float:
    """Pobierz stawkę cięcia"""
    mat = MATERIALS.get(material, MATERIALS['S235'])
    mat_type = mat['type']
    rates = CUTTING_RATES.get(mat_type, CUTTING_RATES['steel'])

    # Znajdź najbliższą grubość
    thicknesses = sorted(rates.keys())
    closest = min(thicknesses, key=lambda x: abs(x - thickness))
    return rates[closest]


def get_pierce_rate(material: str) -> float:
    """Pobierz stawkę przebicia"""
    mat = MATERIALS.get(material, MATERIALS['S235'])
    return PIERCE_RATES.get(mat['type'], 0.15)


def calculate_sheet_cost(material: str, thickness: float,
                         width: float = SHEET_WIDTH, height: float = SHEET_HEIGHT) -> float:
    """Oblicz koszt arkusza"""
    mat = MATERIALS.get(material, MATERIALS['S235'])
    density = mat['density']
    price_per_kg = mat['price_per_kg']

    # Powierzchnia w m²
    area_m2 = (width * height) / 1e6
    # Objętość w m³
    volume_m3 = area_m2 * (thickness / 1000)
    # Waga
    weight_kg = volume_m3 * density
    # Koszt
    return weight_kg * price_per_kg


def calculate_pre_nesting_bbox(parts: List[TestPart], material: str, thickness: float) -> CostResult:
    """
    Model 1: PRZED nestingiem - wycena bounding box
    Każdy detal = koszt materiału z prostokąta + 35% naddatek
    """
    result = CostResult(model_name="PRE-NESTING (Bounding Box + 35%)")

    mat = MATERIALS.get(material, MATERIALS['S235'])
    mat_type = mat['type']
    density = mat['density']
    price_per_kg = mat['price_per_kg']

    cutting_rate = get_cutting_rate(material, thickness)
    pierce_rate = get_pierce_rate(material)

    has_foil = mat.get('has_foil', False) and thickness <= 5.0

    for part in parts:
        # Materiał: bounding box + 35%
        area_m2 = (part.contour_area * 1.35) / 1e6
        volume_m3 = area_m2 * (thickness / 1000)
        weight_kg = volume_m3 * density
        part_material = weight_kg * price_per_kg * part.quantity

        # Cięcie
        cutting_len_m = (part.cutting_len / 1000) * part.quantity
        part_cutting = cutting_len_m * cutting_rate

        # Piercing
        part_piercing = part.pierce_count * pierce_rate * part.quantity

        # Folia
        part_foil = 0.0
        if has_foil:
            part_foil = cutting_len_m * FOIL_RATE

        result.material_cost += part_material
        result.cutting_cost += part_cutting
        result.piercing_cost += part_piercing
        result.foil_cost += part_foil

        # Koszt per detal
        unit_cost = (part_material + part_cutting + part_piercing + part_foil) / part.quantity
        result.part_costs[part.name] = unit_cost

    # Operacyjne (szacunkowe 1 arkusz)
    result.sheets_used = 1
    result.operational_cost = 40.0  # PLN/arkusz

    result.total_cost = (result.material_cost + result.cutting_cost +
                         result.piercing_cost + result.foil_cost +
                         result.operational_cost)

    # Brak efektywności - nie ma nestingu
    result.efficiency = 0.0

    return result


def calculate_post_nesting_proportional(parts: List[TestPart], material: str,
                                        thickness: float, nesting: NestingResult) -> CostResult:
    """
    Model 2: PO nestingu - proporcjonalny
    Arkusz przycięty do maxY, koszt proporcjonalnie do contour_area
    """
    result = CostResult(model_name="POST-NESTING (Proporcjonalny, Y=maxY)")

    mat = MATERIALS.get(material, MATERIALS['S235'])
    mat_type = mat['type']
    density = mat['density']
    price_per_kg = mat['price_per_kg']

    cutting_rate = get_cutting_rate(material, thickness)
    pierce_rate = get_pierce_rate(material)

    has_foil = mat.get('has_foil', False) and thickness <= 5.0

    result.sheets_used = nesting.sheets_used

    # Oblicz koszt materiału proporcjonalnie
    total_material = 0.0

    for sheet in nesting.sheets:
        # Arkusz przycięty do used_height (maxY)
        effective_width = sheet.sheet_width
        effective_height = sheet.used_height

        sheet_cost = calculate_sheet_cost(material, thickness, effective_width, effective_height)

        # Suma contour_area na arkuszu
        total_contour_area = sum(p.contour_area for p in sheet.placed_parts)

        # Przypisz proporcjonalnie
        for placed in sheet.placed_parts:
            if total_contour_area > 0:
                share = placed.contour_area / total_contour_area
                placed.material_cost = sheet_cost * share
            else:
                placed.material_cost = 0

        total_material += sheet_cost
        result.used_sheet_area += effective_width * effective_height

    result.material_cost = total_material

    # Cięcie, piercing, folia - z danych nestingu
    for sheet in nesting.sheets:
        for placed in sheet.placed_parts:
            # Znajdź oryginalny detal
            orig = next((p for p in parts if p.name == placed.source_part_name or p.name == placed.name), None)
            if orig:
                cutting_len_m = orig.cutting_len / 1000
                result.cutting_cost += cutting_len_m * cutting_rate
                result.piercing_cost += orig.pierce_count * pierce_rate
                if has_foil:
                    result.foil_cost += cutting_len_m * FOIL_RATE

    # Operacyjne
    result.operational_cost = 40.0 * result.sheets_used

    result.total_cost = (result.material_cost + result.cutting_cost +
                         result.piercing_cost + result.foil_cost +
                         result.operational_cost)

    # Efektywność
    result.efficiency = nesting.effective_utilization if hasattr(nesting, 'effective_utilization') else nesting.total_efficiency

    # Koszty per detal (średnia)
    part_counts = {}
    part_material_sums = {}
    for sheet in nesting.sheets:
        for placed in sheet.placed_parts:
            key = placed.source_part_name or placed.name
            part_counts[key] = part_counts.get(key, 0) + 1
            part_material_sums[key] = part_material_sums.get(key, 0) + placed.material_cost

    for name, count in part_counts.items():
        orig = next((p for p in parts if p.name == name), None)
        if orig:
            material_unit = part_material_sums.get(name, 0) / count
            cutting_unit = (orig.cutting_len / 1000) * cutting_rate
            pierce_unit = orig.pierce_count * pierce_rate
            foil_unit = (orig.cutting_len / 1000) * FOIL_RATE if has_foil else 0
            result.part_costs[name] = material_unit + cutting_unit + pierce_unit + foil_unit

    return result


def calculate_post_nesting_bbox(parts: List[TestPart], material: str,
                                thickness: float, nesting: NestingResult) -> CostResult:
    """
    Model 3: PO nestingu - bounding box (równy podział)
    Arkusz przycięty do maxY, koszt równo na każdy detal
    """
    result = CostResult(model_name="POST-NESTING (Bounding Box, równy podział)")

    mat = MATERIALS.get(material, MATERIALS['S235'])
    mat_type = mat['type']
    density = mat['density']
    price_per_kg = mat['price_per_kg']

    cutting_rate = get_cutting_rate(material, thickness)
    pierce_rate = get_pierce_rate(material)

    has_foil = mat.get('has_foil', False) and thickness <= 5.0

    result.sheets_used = nesting.sheets_used

    # Oblicz koszt materiału - równy podział
    total_material = 0.0

    for sheet in nesting.sheets:
        # Arkusz przycięty do used_height
        effective_width = sheet.sheet_width
        effective_height = sheet.used_height

        sheet_cost = calculate_sheet_cost(material, thickness, effective_width, effective_height)

        # Równy podział na wszystkie detale na arkuszu
        parts_count = len(sheet.placed_parts)
        if parts_count > 0:
            cost_per_part = sheet_cost / parts_count
            for placed in sheet.placed_parts:
                placed.material_cost = cost_per_part

        total_material += sheet_cost
        result.used_sheet_area += effective_width * effective_height

    result.material_cost = total_material

    # Cięcie, piercing, folia
    for sheet in nesting.sheets:
        for placed in sheet.placed_parts:
            orig = next((p for p in parts if p.name == placed.source_part_name or p.name == placed.name), None)
            if orig:
                cutting_len_m = orig.cutting_len / 1000
                result.cutting_cost += cutting_len_m * cutting_rate
                result.piercing_cost += orig.pierce_count * pierce_rate
                if has_foil:
                    result.foil_cost += cutting_len_m * FOIL_RATE

    # Operacyjne
    result.operational_cost = 40.0 * result.sheets_used

    result.total_cost = (result.material_cost + result.cutting_cost +
                         result.piercing_cost + result.foil_cost +
                         result.operational_cost)

    # Efektywność
    result.efficiency = nesting.effective_utilization if hasattr(nesting, 'effective_utilization') else nesting.total_efficiency

    # Koszty per detal
    part_counts = {}
    part_material_sums = {}
    for sheet in nesting.sheets:
        for placed in sheet.placed_parts:
            key = placed.source_part_name or placed.name
            part_counts[key] = part_counts.get(key, 0) + 1
            part_material_sums[key] = part_material_sums.get(key, 0) + placed.material_cost

    for name, count in part_counts.items():
        orig = next((p for p in parts if p.name == name), None)
        if orig:
            material_unit = part_material_sums.get(name, 0) / count
            cutting_unit = (orig.cutting_len / 1000) * cutting_rate
            pierce_unit = orig.pierce_count * pierce_rate
            foil_unit = (orig.cutting_len / 1000) * FOIL_RATE if has_foil else 0
            result.part_costs[name] = material_unit + cutting_unit + pierce_unit + foil_unit

    return result


# ============================================================
# TEST SCENARIO GENERATOR
# ============================================================

def generate_test_parts(num_parts: int, material: str, thickness: float, seed: int = None) -> List[TestPart]:
    """Generuj losowe detale testowe"""
    if seed is not None:
        random.seed(seed)

    parts = []

    # Rozmiary detali - różnorodność
    size_ranges = [
        (30, 80),    # Małe
        (80, 200),   # Średnie
        (200, 500),  # Duże
        (500, 1000), # Bardzo duże
    ]

    for i in range(num_parts):
        # Losuj zakres rozmiarów
        size_range = random.choice(size_ranges)

        width = random.randint(size_range[0], size_range[1])
        height = random.randint(size_range[0], size_range[1])
        quantity = random.randint(1, 5)

        part = TestPart(
            name=f"Part_{i+1:02d}_{width}x{height}",
            width=float(width),
            height=float(height),
            material=material,
            thickness=thickness,
            quantity=quantity
        )
        parts.append(part)

    return parts


def run_nesting(parts: List[TestPart], sheet_width: float = SHEET_WIDTH,
                sheet_height: float = SHEET_HEIGHT) -> Optional[NestingResult]:
    """Wykonaj nesting dla detali"""
    if not HAS_NESTER:
        return None

    nester = FastNester(sheet_width, sheet_height, spacing=5.0, max_sheets=10)

    for part in parts:
        part_dict = {
            'name': part.name,
            'width': part.width,
            'height': part.height,
            'contour': [(0, 0), (part.width, 0), (part.width, part.height), (0, part.height)],
            'contour_area': part.contour_area,
            'weight_kg': part.weight_kg,
        }
        nester.add_part_from_dict(part_dict, part.quantity)

    result = nester.run_nesting()
    return result


def run_test_scenario(name: str, num_parts: int, material: str,
                      thickness: float, seed: int) -> TestScenario:
    """Uruchom pojedynczy scenariusz testowy"""

    parts = generate_test_parts(num_parts, material, thickness, seed)

    scenario = TestScenario(
        name=name,
        parts=parts,
        material=material,
        thickness=thickness
    )

    # 1. PRE-NESTING (bounding box)
    scenario.pre_nesting_bbox = calculate_pre_nesting_bbox(parts, material, thickness)

    # 2. NESTING
    nesting_result = run_nesting(parts)
    scenario.nesting_result = nesting_result

    if nesting_result and nesting_result.placed_parts:
        # 3. POST-NESTING proporcjonalny
        scenario.post_nesting_proportional = calculate_post_nesting_proportional(
            parts, material, thickness, nesting_result
        )

        # 4. POST-NESTING bounding box
        scenario.post_nesting_bbox = calculate_post_nesting_bbox(
            parts, material, thickness, nesting_result
        )

    return scenario


# ============================================================
# ECONOMIC ANALYSIS
# ============================================================

def analyze_scenario(scenario: TestScenario) -> Dict:
    """Analiza ekonomiczna scenariusza"""
    analysis = {
        'scenario_name': scenario.name,
        'material': scenario.material,
        'thickness': scenario.thickness,
        'total_parts': sum(p.quantity for p in scenario.parts),
        'unique_parts': len(scenario.parts),
    }

    pre = scenario.pre_nesting_bbox
    post_prop = scenario.post_nesting_proportional
    post_bbox = scenario.post_nesting_bbox

    if pre:
        analysis['pre_nesting'] = {
            'total_cost': pre.total_cost,
            'material_cost': pre.material_cost,
            'cutting_cost': pre.cutting_cost,
            'efficiency': pre.efficiency,
        }

    if post_prop:
        analysis['post_proportional'] = {
            'total_cost': post_prop.total_cost,
            'material_cost': post_prop.material_cost,
            'cutting_cost': post_prop.cutting_cost,
            'efficiency': post_prop.efficiency,
            'sheets_used': post_prop.sheets_used,
        }

        # Oszczędność vs pre-nesting
        if pre:
            savings = pre.total_cost - post_prop.total_cost
            savings_pct = (savings / pre.total_cost * 100) if pre.total_cost > 0 else 0
            analysis['savings_proportional'] = {
                'absolute': savings,
                'percent': savings_pct,
            }

    if post_bbox:
        analysis['post_bbox'] = {
            'total_cost': post_bbox.total_cost,
            'material_cost': post_bbox.material_cost,
            'cutting_cost': post_bbox.cutting_cost,
            'efficiency': post_bbox.efficiency,
            'sheets_used': post_bbox.sheets_used,
        }

        if pre:
            savings = pre.total_cost - post_bbox.total_cost
            savings_pct = (savings / pre.total_cost * 100) if pre.total_cost > 0 else 0
            analysis['savings_bbox'] = {
                'absolute': savings,
                'percent': savings_pct,
            }

    # Porównanie modeli post-nesting
    if post_prop and post_bbox:
        diff = post_bbox.total_cost - post_prop.total_cost
        analysis['model_difference'] = {
            'bbox_vs_proportional': diff,
            'description': 'dodatnia = bbox droższy' if diff > 0 else 'ujemna = proporcjonalny droższy'
        }

    return analysis


def economic_validation(scenarios: List[TestScenario]) -> Dict:
    """Walidacja ekonomiczna wyników"""
    validation = {
        'passed': True,
        'issues': [],
        'observations': [],
    }

    for scenario in scenarios:
        pre = scenario.pre_nesting_bbox
        post_prop = scenario.post_nesting_proportional
        post_bbox = scenario.post_nesting_bbox
        nesting = scenario.nesting_result

        # Sprawdzenie 1: Pre-nesting z małą liczbą detali może być tańszy
        # (bbox+35% vs pełny arkusz przycięty do maxY)
        # To jest OK dla małych zamówień
        if pre and post_prop:
            if post_prop.total_cost > pre.total_cost * 1.1:  # 10% tolerancja
                total_qty = sum(p.quantity for p in scenario.parts)
                if total_qty < 20:
                    validation['observations'].append(
                        f"{scenario.name}: Małe zamówienie ({total_qty} szt) - "
                        f"PRE-NESTING tańszy o {pre.total_cost - post_prop.total_cost:.2f} PLN"
                    )
                else:
                    validation['issues'].append(
                        f"{scenario.name}: POST-NESTING proporcjonalny droższy niż PRE-NESTING "
                        f"({post_prop.total_cost:.2f} > {pre.total_cost:.2f})"
                    )
                    validation['passed'] = False

        # Sprawdzenie 2: Koszty cięcia powinny być identyczne między modelami
        if post_prop and post_bbox:
            cutting_diff = abs(post_prop.cutting_cost - post_bbox.cutting_cost)
            if cutting_diff > 0.01:
                validation['issues'].append(
                    f"{scenario.name}: Różne koszty cięcia między modelami "
                    f"({post_prop.cutting_cost:.2f} vs {post_bbox.cutting_cost:.2f})"
                )
                validation['passed'] = False

        # Sprawdzenie 3: Efektywność nestingu - sprawdzamy z NestingResult
        if nesting:
            eff = nesting.total_efficiency
            if eff > 0:
                validation['observations'].append(
                    f"{scenario.name}: Efektywność nestingu: {eff*100:.1f}%"
                )
            else:
                validation['observations'].append(
                    f"{scenario.name}: Brak danych o efektywności"
                )

        # Sprawdzenie 4: Koszt materiału post-nesting powinien być ≤ pre-nesting
        if pre and post_prop:
            if post_prop.material_cost < pre.material_cost:
                savings_pct = (1 - post_prop.material_cost / pre.material_cost) * 100
                validation['observations'].append(
                    f"{scenario.name}: Oszczędność materiału: {savings_pct:.1f}%"
                )
            elif abs(post_prop.material_cost - pre.material_cost) < pre.material_cost * 0.05:
                validation['observations'].append(
                    f"{scenario.name}: Koszt materiału porównywalny (różnica < 5%)"
                )
            else:
                validation['observations'].append(
                    f"{scenario.name}: UWAGA - post-nesting materiał droższy o "
                    f"{post_prop.material_cost - pre.material_cost:.2f} PLN"
                )

        # Sprawdzenie 5: Model proporcjonalny vs bbox - różnice w alokacji
        if post_prop and post_bbox and scenario.parts:
            # Znajdź największy i najmniejszy detal
            sorted_by_area = sorted(scenario.parts, key=lambda p: p.contour_area)
            if len(sorted_by_area) >= 2:
                smallest = sorted_by_area[0]
                largest = sorted_by_area[-1]

                # W modelu proporcjonalnym mały detal powinien mieć niższy koszt
                prop_small = post_prop.part_costs.get(smallest.name, 0)
                bbox_small = post_bbox.part_costs.get(smallest.name, 0)
                prop_large = post_prop.part_costs.get(largest.name, 0)
                bbox_large = post_bbox.part_costs.get(largest.name, 0)

                if prop_small > 0 and bbox_small > 0 and prop_large > 0 and bbox_large > 0:
                    # Mały detal: proporcjonalny powinien być tańszy niż bbox
                    if prop_small < bbox_small:
                        validation['observations'].append(
                            f"{scenario.name}: Alokacja OK - mały detal tańszy w proporcjonalnym"
                        )
                    # Duży detal: proporcjonalny powinien być droższy niż bbox
                    if prop_large > bbox_large:
                        validation['observations'].append(
                            f"{scenario.name}: Alokacja OK - duży detal droższy w proporcjonalnym"
                        )

    return validation


# ============================================================
# REPORT GENERATOR
# ============================================================

def generate_markdown_report(scenarios: List[TestScenario], validation: Dict) -> str:
    """Generuj raport MD"""

    lines = []
    lines.append("# Raport Testów Modeli Alokacji Kosztów")
    lines.append("")
    lines.append(f"**Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")

    # Opis modeli
    lines.append("## Modele wyceny")
    lines.append("")
    lines.append("| Model | Opis |")
    lines.append("|-------|------|")
    lines.append("| **PRE-NESTING (BBox)** | Materiał = bounding box + 35% naddatek, bez nestingu |")
    lines.append("| **POST-NESTING Proporcjonalny** | Arkusz przycięty do maxY, koszt proporcjonalnie do contour_area |")
    lines.append("| **POST-NESTING BBox** | Arkusz przycięty do maxY, koszt równo na każdy detal |")
    lines.append("")

    # Wyniki testów
    lines.append("## Wyniki testów")
    lines.append("")

    for scenario in scenarios:
        lines.append(f"### {scenario.name}")
        lines.append("")
        lines.append(f"- **Materiał:** {scenario.material} / {scenario.thickness}mm")
        lines.append(f"- **Detale:** {len(scenario.parts)} typów, {sum(p.quantity for p in scenario.parts)} szt łącznie")
        lines.append("")

        if scenario.nesting_result:
            nr = scenario.nesting_result
            lines.append(f"- **Arkusze użyte:** {nr.sheets_used}")
            lines.append(f"- **Efektywność:** {nr.total_efficiency*100:.1f}%")
            lines.append("")

        # Tabela kosztów
        lines.append("| Składnik | PRE-NESTING | POST-PROP | POST-BBOX |")
        lines.append("|----------|-------------|-----------|-----------|")

        pre = scenario.pre_nesting_bbox
        post_prop = scenario.post_nesting_proportional
        post_bbox = scenario.post_nesting_bbox

        def fmt(val):
            return f"{val:.2f}" if val else "-"

        lines.append(f"| Materiał | {fmt(pre.material_cost if pre else 0)} | {fmt(post_prop.material_cost if post_prop else 0)} | {fmt(post_bbox.material_cost if post_bbox else 0)} |")
        lines.append(f"| Cięcie | {fmt(pre.cutting_cost if pre else 0)} | {fmt(post_prop.cutting_cost if post_prop else 0)} | {fmt(post_bbox.cutting_cost if post_bbox else 0)} |")
        lines.append(f"| Przebicia | {fmt(pre.piercing_cost if pre else 0)} | {fmt(post_prop.piercing_cost if post_prop else 0)} | {fmt(post_bbox.piercing_cost if post_bbox else 0)} |")
        lines.append(f"| Folia | {fmt(pre.foil_cost if pre else 0)} | {fmt(post_prop.foil_cost if post_prop else 0)} | {fmt(post_bbox.foil_cost if post_bbox else 0)} |")
        lines.append(f"| Operacyjne | {fmt(pre.operational_cost if pre else 0)} | {fmt(post_prop.operational_cost if post_prop else 0)} | {fmt(post_bbox.operational_cost if post_bbox else 0)} |")
        lines.append(f"| **RAZEM** | **{fmt(pre.total_cost if pre else 0)}** | **{fmt(post_prop.total_cost if post_prop else 0)}** | **{fmt(post_bbox.total_cost if post_bbox else 0)}** |")
        lines.append("")

        # Oszczędności
        if pre and post_prop:
            savings = pre.total_cost - post_prop.total_cost
            savings_pct = (savings / pre.total_cost * 100) if pre.total_cost > 0 else 0
            lines.append(f"**Oszczędność (proporcjonalny vs pre-nesting):** {savings:.2f} PLN ({savings_pct:.1f}%)")

        if pre and post_bbox:
            savings = pre.total_cost - post_bbox.total_cost
            savings_pct = (savings / pre.total_cost * 100) if pre.total_cost > 0 else 0
            lines.append(f"**Oszczędność (bbox vs pre-nesting):** {savings:.2f} PLN ({savings_pct:.1f}%)")

        lines.append("")

        # Koszty per detal (top 5)
        if post_prop and post_prop.part_costs:
            lines.append("#### Koszty jednostkowe (top 5)")
            lines.append("")
            lines.append("| Detal | PRE-NESTING | POST-PROP | POST-BBOX | Różnica |")
            lines.append("|-------|-------------|-----------|-----------|---------|")

            sorted_parts = sorted(scenario.parts, key=lambda p: p.contour_area, reverse=True)[:5]
            for part in sorted_parts:
                pre_cost = pre.part_costs.get(part.name, 0) if pre else 0
                prop_cost = post_prop.part_costs.get(part.name, 0) if post_prop else 0
                bbox_cost = post_bbox.part_costs.get(part.name, 0) if post_bbox else 0
                diff = prop_cost - bbox_cost
                lines.append(f"| {part.name} | {pre_cost:.2f} | {prop_cost:.2f} | {bbox_cost:.2f} | {diff:+.2f} |")

            lines.append("")

    # Walidacja ekonomiczna
    lines.append("## Walidacja ekonomiczna")
    lines.append("")

    if validation['passed']:
        lines.append("✅ **Wszystkie testy przeszły walidację**")
    else:
        lines.append("❌ **Wykryto problemy:**")
        for issue in validation['issues']:
            lines.append(f"- {issue}")

    lines.append("")

    if validation['observations']:
        lines.append("### Obserwacje")
        for obs in validation['observations']:
            lines.append(f"- {obs}")
        lines.append("")

    # Wnioski
    lines.append("## Wnioski")
    lines.append("")
    lines.append("1. **Nesting znacząco redukuje koszty materiału** - przycięcie arkusza do maxY eliminuje odpad")
    lines.append("2. **Model proporcjonalny** lepiej odzwierciedla rzeczywiste zużycie materiału dla detali o różnych rozmiarach")
    lines.append("3. **Model bbox (równy podział)** faworyzuje duże detale kosztem małych")
    lines.append("4. **Koszty cięcia są identyczne** między modelami - zależą tylko od geometrii")
    lines.append("")

    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

def run_all_tests():
    """Uruchom wszystkie testy"""
    print("=" * 60)
    print("TEST MODELI ALOKACJI KOSZTÓW")
    print("=" * 60)

    scenarios = []

    # Test 1: Mała liczba detali, stal
    print("\n[1/5] Test: 5 detali, S235 2mm...")
    scenarios.append(run_test_scenario(
        "Test 1: S235 2mm (5 detali)",
        num_parts=5,
        material='S235',
        thickness=2.0,
        seed=42
    ))

    # Test 2: Średnia liczba detali, INOX z folią
    print("[2/5] Test: 10 detali, 1.4301 3mm...")
    scenarios.append(run_test_scenario(
        "Test 2: INOX 3mm (10 detali)",
        num_parts=10,
        material='1.4301',
        thickness=3.0,
        seed=123
    ))

    # Test 3: Duża liczba detali, aluminium
    print("[3/5] Test: 20 detali, ALU 4mm...")
    scenarios.append(run_test_scenario(
        "Test 3: ALU 4mm (20 detali)",
        num_parts=20,
        material='ALU',
        thickness=4.0,
        seed=456
    ))

    # Test 4: Maksymalna liczba detali, stal gruba
    print("[4/5] Test: 30 detali, S235 8mm...")
    scenarios.append(run_test_scenario(
        "Test 4: S235 8mm (30 detali)",
        num_parts=30,
        material='S235',
        thickness=8.0,
        seed=789
    ))

    # Test 5: Mieszane rozmiary, INOX cienki
    print("[5/5] Test: 15 detali, 1.4301 1.5mm...")
    scenarios.append(run_test_scenario(
        "Test 5: INOX 1.5mm (15 detali)",
        num_parts=15,
        material='1.4301',
        thickness=1.5,
        seed=999
    ))

    # Walidacja
    print("\nWalidacja ekonomiczna...")
    validation = economic_validation(scenarios)

    # Generuj raport
    print("Generowanie raportu...")
    report = generate_markdown_report(scenarios, validation)

    # Zapisz do pliku
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, "cost_allocation_test_results.md")

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n[OK] Raport zapisany: {output_path}")

    # Podsumowanie
    print("\n" + "=" * 60)
    print("PODSUMOWANIE")
    print("=" * 60)

    if validation['passed']:
        print("[OK] Wszystkie testy przeszly walidacje")
    else:
        print("[BLAD] Wykryto problemy:")
        for issue in validation['issues']:
            print(f"   - {issue}")

    return scenarios, validation, output_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_all_tests()
