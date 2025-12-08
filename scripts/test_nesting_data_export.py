"""
Test Nesting Data Export - Eksportuj dane nestingu do JSON.

Skrypt do testowania i weryfikacji struktury danych nestingu:
- Eksportuje wynik nestingu do pliku JSON
- Wyswietla informacje o maxY (used_height) dla reguly 94%
- Pokazuje kompletna strukture danych

Uruchom: python scripts/test_nesting_data_export.py
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional
from dataclasses import asdict

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def export_nested_part(part) -> Dict[str, Any]:
    """Eksportuj dane pojedynczego umieszczonego detalu"""
    return {
        'name': part.name,
        'source_part_name': part.source_part_name,
        'x': round(part.x, 2),
        'y': round(part.y, 2),
        'width': round(part.width, 2),
        'height': round(part.height, 2),
        'rotation': part.rotation,
        'contour_area_mm2': round(part.contour_area, 2),
        'weight_kg': round(part.weight_kg, 4),
        'material_cost_pln': round(part.material_cost, 2),
        'cut_length_mm': round(part.cut_length_mm, 2),
        'pierce_count': part.pierce_count,
        'cut_time_classic_s': round(part.cut_time_classic_s, 2),
        'cut_time_dynamic_s': round(part.cut_time_dynamic_s, 2),
        'sheet_index': part.sheet_index,
        'part_index': part.part_index,
        'filepath': part.filepath,
    }


def export_sheet_result(sheet) -> Dict[str, Any]:
    """Eksportuj dane arkusza"""
    return {
        'sheet_index': sheet.sheet_index,
        'sheet_width_mm': round(sheet.sheet_width, 2),
        'sheet_height_mm': round(sheet.sheet_height, 2),
        'used_width_mm': round(sheet.used_width, 2),
        'used_height_mm': round(sheet.used_height, 2),  # = maxY z nestingu
        'total_parts_area_mm2': round(sheet.total_parts_area, 2),
        'used_sheet_area_mm2': round(sheet.used_sheet_area, 2),
        'efficiency_percent': round(sheet.efficiency * 100, 2),
        'sheet_cost_pln': round(sheet.sheet_cost, 2),
        'used_sheet_cost_pln': round(sheet.used_sheet_cost, 2),
        'total_cut_length_mm': round(sheet.total_cut_length_mm, 2),
        'total_pierce_count': sheet.total_pierce_count,
        'cut_time_classic_s': round(sheet.cut_time_classic_s, 2),
        'cut_time_dynamic_s': round(sheet.cut_time_dynamic_s, 2),
        'placed_parts_count': len(sheet.placed_parts),
        'placed_parts': [export_nested_part(p) for p in sheet.placed_parts],
        # Regula 94%
        '_94_percent_rule': {
            'nominal_height_mm': round(sheet.sheet_height, 2),
            'used_height_mm': round(sheet.used_height, 2),
            'utilization_percent': round(sheet.used_height / sheet.sheet_height * 100, 2) if sheet.sheet_height > 0 else 0,
            'should_use_full_sheet': (sheet.used_height / sheet.sheet_height) >= 0.94 if sheet.sheet_height > 0 else True,
        }
    }


def export_nesting_result(result, filepath: str = None) -> Dict[str, Any]:
    """
    Eksportuj pelny wynik nestingu do struktury JSON.

    Args:
        result: NestingResult z fast_nester.py
        filepath: Sciezka do pliku JSON (opcjonalna)

    Returns:
        Slownik z danymi nestingu
    """
    data = {
        'export_timestamp': datetime.now().isoformat(),
        'summary': {
            'sheets_used': result.sheets_used,
            'total_efficiency_percent': round(result.total_efficiency * 100, 2),
            'total_placed_parts': len(result.placed_parts),
            'total_unplaced_parts': result.unplaced_count,
            'sheet_width_mm': round(result.sheet_width, 2),
            'sheet_height_mm': round(result.sheet_height, 2),
            'used_width_mm': round(result.used_width, 2),
            'used_height_mm': round(result.used_height, 2),  # = maxY
        },
        'sheets': [export_sheet_result(s) for s in result.sheets],
        'unplaced_parts': [
            {
                'name': p.name,
                'source_part_name': p.source_part_name,
                'width': round(p.width, 2),
                'height': round(p.height, 2),
                'contour_area_mm2': round(p.contour_area, 2),
                'reason': p.reason,
                'part_index': p.part_index,
            }
            for p in result.unplaced_parts
        ]
    }

    if filepath:
        output_path = Path(filepath)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Eksportowano dane nestingu do: {output_path}")

    return data


def analyze_94_percent_rule(result) -> None:
    """Analizuj regule 94% dla wszystkich arkuszy"""
    logger.info("\n" + "=" * 60)
    logger.info("ANALIZA REGULY 94%")
    logger.info("=" * 60)

    for sheet in result.sheets:
        if sheet.sheet_height > 0:
            utilization = sheet.used_height / sheet.sheet_height
            use_full = utilization >= 0.94

            logger.info(f"\nArkusz #{sheet.sheet_index + 1}:")
            logger.info(f"  Nominalna wysokosc: {sheet.sheet_height:.2f} mm")
            logger.info(f"  Uzyta wysokosc (maxY): {sheet.used_height:.2f} mm")
            logger.info(f"  Wykorzystanie: {utilization * 100:.2f}%")
            logger.info(f"  Decyzja: {'PELNY ARKUSZ' if use_full else 'CUT_TO_LENGTH'}")

            if use_full:
                logger.info(f"    -> Pozostaly pasek ({(1-utilization)*100:.1f}%) za maly do wykorzystania")
            else:
                saved = sheet.sheet_height - sheet.used_height - 10  # margines
                logger.info(f"    -> Mozna zaoszczedzic ~{saved:.0f} mm materialu")


def main():
    """Test eksportu danych nestingu"""
    print("\n" + "=" * 60)
    print("TEST NESTING DATA EXPORT")
    print("=" * 60)

    # Proba importu modulu nestingu
    try:
        from quotations.nesting.fast_nester import (
            FastNester, NestingResult, SheetResult, NestedPart
        )
        print("\n[OK] Modul fast_nester zaimportowany")
    except ImportError as e:
        print(f"\n[FAIL] Nie mozna zaimportowac fast_nester: {e}")
        print("Tworzenie przykladowych danych testowych...")

        # Utworz przykladowe dane testowe
        from dataclasses import dataclass, field
        from typing import List

        @dataclass
        class MockNestedPart:
            name: str = "TestPart"
            source_part_name: str = "TestPart"
            x: float = 0.0
            y: float = 0.0
            width: float = 100.0
            height: float = 100.0
            rotation: float = 0.0
            contour_area: float = 10000.0
            weight_kg: float = 0.5
            material_cost: float = 10.0
            cut_length_mm: float = 400.0
            pierce_count: int = 1
            cut_time_classic_s: float = 2.0
            cut_time_dynamic_s: float = 1.8
            sheet_index: int = 0
            part_index: int = 0
            filepath: str = ""

        @dataclass
        class MockSheetResult:
            sheet_index: int = 0
            placed_parts: List = field(default_factory=list)
            sheet_width: float = 1500.0
            sheet_height: float = 3000.0
            used_width: float = 1400.0
            used_height: float = 2850.0  # 95% - powinna uzyc pelny arkusz
            total_parts_area: float = 2000000.0
            used_sheet_area: float = 4200000.0
            efficiency: float = 0.476
            sheet_cost: float = 500.0
            used_sheet_cost: float = 475.0
            total_cut_length_mm: float = 50000.0
            total_pierce_count: int = 50
            cut_time_classic_s: float = 250.0
            cut_time_dynamic_s: float = 200.0

        @dataclass
        class MockNestingResult:
            sheets: List = field(default_factory=list)
            placed_parts: List = field(default_factory=list)
            unplaced_parts: List = field(default_factory=list)
            unplaced_count: int = 0
            sheets_used: int = 1
            total_efficiency: float = 0.476
            sheet_width: float = 1500.0
            sheet_height: float = 3000.0
            used_width: float = 1400.0
            used_height: float = 2850.0

        # Tworzenie testowych danych
        test_parts = [MockNestedPart(name=f"Part_{i+1}", x=100*i, y=100*i) for i in range(5)]
        test_sheet = MockSheetResult(placed_parts=test_parts)
        test_result = MockNestingResult(
            sheets=[test_sheet],
            placed_parts=test_parts,
        )

        # Eksportuj
        output_path = Path(__file__).parent.parent / "logs" / "nesting_export_test.json"
        data = export_nesting_result(test_result, str(output_path))

        # Analizuj regule 94%
        analyze_94_percent_rule(test_result)

        print("\n" + "=" * 60)
        print("STRUKTURA DANYCH NESTINGU (przyklad):")
        print("=" * 60)
        print(json.dumps(data, indent=2, ensure_ascii=False)[:2000] + "\n...")

        return 0

    # Tu mozna dodac prawdziwy test z rzeczywistym nestingiem
    print("\n[INFO] Aby przetestowac eksport z prawdziwymi danymi,")
    print("       wywolaj export_nesting_result(result, filepath)")
    print("       po wykonaniu nestingu w aplikacji.")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
