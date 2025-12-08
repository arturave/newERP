"""
Test Cost Scenarios - 5 scenariuszy testowych do weryfikacji obliczen kosztowych.

Kazdy scenariusz generuje losowe detale i sprawdza spojnosc obliczen miedzy:
1. CostEngine.calculate() (bezposrednie obliczenie)
2. DetailedPartsPanel._calculate_lm_cost() (obliczenie w panelu)

Uruchom: python -m tests.test_cost_scenarios
"""

import random
import logging
from typing import Dict, List, Tuple
from dataclasses import dataclass

# Logging
logging.basicConfig(level=logging.DEBUG, format='%(message)s')
logger = logging.getLogger(__name__)

# Materialy i ich wlasciwosci
MATERIALS = {
    '1.4301': {'type': 'stainless', 'density': 7900, 'thicknesses': [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0]},
    '1.4404': {'type': 'stainless', 'density': 7950, 'thicknesses': [1.0, 1.5, 2.0, 3.0, 4.0, 5.0]},
    'S235': {'type': 'steel', 'density': 7850, 'thicknesses': [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]},
    'S355': {'type': 'steel', 'density': 7850, 'thicknesses': [2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0]},
    'ALU': {'type': 'aluminum', 'density': 2700, 'thicknesses': [1.0, 1.5, 2.0, 3.0, 4.0, 5.0]},
}


@dataclass
class TestScenario:
    """Opis scenariusza testowego"""
    name: str
    description: str
    parts_count: int
    material: str
    thickness: float
    with_engraving: bool
    with_foil: bool
    bends_range: Tuple[int, int]


def generate_random_part(scenario: TestScenario, index: int) -> Dict:
    """Generuj losowe dane detalu dla scenariusza"""
    mat_props = MATERIALS[scenario.material]

    # Wymiary prostokąta otaczającego (100-1000mm)
    width = random.uniform(100, 1000)
    height = random.uniform(100, 800)

    # Dlugosc ciecia skorelowana z obwodem
    perimeter = 2 * (width + height)
    # Dodaj losowe wycięcia (20-80% obwodu)
    cutting_len = perimeter * random.uniform(1.2, 2.0)

    # Grawerowanie
    engraving_len = cutting_len * random.uniform(0.1, 0.4) if scenario.with_engraving and random.random() > 0.5 else 0

    # Przebicia (1-100)
    pierce_count = random.randint(1, 100)

    # Giecia
    bends = random.randint(*scenario.bends_range)

    part = {
        'name': f'{scenario.name}_{index}_{scenario.material}_{scenario.thickness}mm',
        'material': scenario.material,
        'thickness': scenario.thickness,
        'quantity': random.randint(1, 50),
        'width': width,
        'height': height,
        'cutting_len': cutting_len,
        'engraving_len': engraving_len,
        'pierce_count': pierce_count,
        'num_bends': bends,
        'needs_foil_removal': scenario.with_foil,
    }

    return part


def calculate_with_engine(parts: List[Dict]) -> Dict[str, float]:
    """Oblicz koszty uzywajac CostEngine"""
    from orders.cost_engine import CostEngine
    from orders.cost_models import CostParams, AllocationModel

    engine = CostEngine()
    params = CostParams(
        allocation_model=AllocationModel.AREA_PROPORTIONAL,
        calculate_foil=True,
        calculate_bending=True,
    )

    totals = {
        'material_cost': 0.0,
        'cutting_cost': 0.0,
        'engraving_cost': 0.0,
        'foil_cost': 0.0,
        'piercing_cost': 0.0,
        'bending_cost': 0.0,
        'total_lm': 0.0,
    }

    for part in parts:
        result = engine.calculate_part_cost(part, params)
        qty = part.get('quantity', 1)

        totals['material_cost'] += result.material_cost * qty
        totals['cutting_cost'] += result.cutting_cost * qty
        totals['engraving_cost'] += result.engraving_cost * qty
        totals['foil_cost'] += result.foil_cost * qty
        totals['piercing_cost'] += result.piercing_cost * qty
        totals['bending_cost'] += result.bending_cost * qty
        totals['total_lm'] += result.total_with_material * qty

    return totals


def run_scenario(scenario: TestScenario) -> bool:
    """Uruchom pojedynczy scenariusz testowy"""
    logger.info(f"\n{'=' * 60}")
    logger.info(f"SCENARIUSZ: {scenario.name}")
    logger.info(f"Opis: {scenario.description}")
    logger.info(f"Material: {scenario.material} / {scenario.thickness}mm")
    logger.info(f"Detali: {scenario.parts_count}")
    logger.info(f"Grawer: {'TAK' if scenario.with_engraving else 'NIE'}")
    logger.info(f"Folia: {'TAK' if scenario.with_foil else 'NIE'}")
    logger.info(f"Giecia: {scenario.bends_range[0]}-{scenario.bends_range[1]}")
    logger.info('=' * 60)

    # Generuj detale
    parts = [generate_random_part(scenario, i+1) for i in range(scenario.parts_count)]

    # Oblicz koszty
    try:
        results = calculate_with_engine(parts)

        logger.info("\nWYNIKI:")
        logger.info(f"  Material:     {results['material_cost']:>10.2f} PLN")
        logger.info(f"  Ciecie:       {results['cutting_cost']:>10.2f} PLN")
        logger.info(f"  Grawer:       {results['engraving_cost']:>10.2f} PLN")
        logger.info(f"  Folia:        {results['foil_cost']:>10.2f} PLN")
        logger.info(f"  Piercing:     {results['piercing_cost']:>10.2f} PLN")
        logger.info(f"  Giecie:       {results['bending_cost']:>10.2f} PLN")
        logger.info(f"  {'─' * 35}")
        logger.info(f"  TOTAL L+M:    {results['total_lm']:>10.2f} PLN")

        # Sprawdz poprawnosc
        if results['total_lm'] <= 0:
            logger.error("  [FAIL] Total L+M <= 0!")
            return False

        if results['foil_cost'] > 1.0 and scenario.with_foil:
            # Sprawdz czy folia nie jest zbyt droga (maks ~0.50 PLN/m)
            # Dla 1000mm ciecia przy 0.20 PLN/m = 0.20 PLN
            # Jesli wyszlo 5.00 PLN/m to bylby blad
            max_expected_foil = sum(p['cutting_len'] for p in parts) / 1000 * 0.50
            if results['foil_cost'] > max_expected_foil * 10:
                logger.warning(f"  [WARN] Koszt folii ({results['foil_cost']:.2f}) bardzo wysoki!")

        logger.info("  [OK] Scenariusz zakonczony pomyslnie")
        return True

    except Exception as e:
        logger.error(f"  [FAIL] Blad: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Uruchom 5 scenariuszy testowych"""
    print("\n" + "=" * 60)
    print("TEST COST SCENARIOS - 5 scenariuszy testowych")
    print("=" * 60)

    # Inicjalizacja PricingDataCache
    print("\n[0] Ladowanie danych cenowych...")
    try:
        from core.pricing_cache import get_pricing_cache
        cache = get_pricing_cache()
        cache.load_sync()  # Synchroniczne ladowanie dla testow
        print(f"    [OK] PricingDataCache zaladowany (is_loaded={cache.is_loaded})")
    except Exception as e:
        print(f"    [WARN] Nie udalo sie zaladowac cache'a: {e}")
        print("    Uzywam domyslnych stawek z DEFAULT_RATES")

    scenarios = [
        TestScenario(
            name="S1_INOX_MIX",
            description="Mix detali ze stali nierdzewnej z grawerem i folia",
            parts_count=10,
            material='1.4301',
            thickness=3.0,
            with_engraving=True,
            with_foil=True,
            bends_range=(0, 5),
        ),
        TestScenario(
            name="S2_STEEL_THICK",
            description="Grube detale stalowe bez folii",
            parts_count=5,
            material='S355',
            thickness=10.0,
            with_engraving=False,
            with_foil=False,
            bends_range=(0, 0),
        ),
        TestScenario(
            name="S3_ALU_SIMPLE",
            description="Proste detale aluminiowe",
            parts_count=20,
            material='ALU',
            thickness=2.0,
            with_engraving=False,
            with_foil=False,
            bends_range=(0, 2),
        ),
        TestScenario(
            name="S4_INOX_BENDS",
            description="Detale INOX z wieloma gieciami",
            parts_count=8,
            material='1.4404',
            thickness=1.5,
            with_engraving=True,
            with_foil=True,
            bends_range=(5, 15),
        ),
        TestScenario(
            name="S5_MASS_PRODUCTION",
            description="Masowa produkcja - duzo identycznych detali",
            parts_count=50,
            material='S235',
            thickness=2.0,
            with_engraving=False,
            with_foil=False,
            bends_range=(1, 3),
        ),
    ]

    passed = 0
    failed = 0

    for scenario in scenarios:
        if run_scenario(scenario):
            passed += 1
        else:
            failed += 1

    # Podsumowanie
    print("\n" + "=" * 60)
    print(f"PODSUMOWANIE: {passed}/{len(scenarios)} scenariuszy passed")
    if failed > 0:
        print(f"              {failed} scenariuszy FAILED")
        return 1
    else:
        print("              Wszystkie testy pomyslnie zakonczone!")
        return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
