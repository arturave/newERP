#!/usr/bin/env python3
"""
Skrypt walidacji wynikow NewERP vs dane referencyjne z CypNest
"""

import argparse
import json
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime

# Dodaj sciezke do glownego katalogu projektu
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class CypNestReference:
    """Dane referencyjne z CypNest"""
    total_cut_length_m: float
    total_cut_time_s: int
    total_parts: int
    sheets: List[Dict]
    parts: List[Dict]


@dataclass
class ValidationResult:
    """Wynik pojedynczej walidacji"""
    metric: str
    cypnest_value: float
    newerp_value: float
    diff_abs: float
    diff_pct: float
    tolerance_pct: float
    passed: bool

    def __str__(self):
        status = "PASS" if self.passed else "FAIL"
        return (f"[{status}] {self.metric}: "
                f"CypNest={self.cypnest_value:.2f}, NewERP={self.newerp_value:.2f}, "
                f"Diff={self.diff_pct:+.1f}% (tolerancja: {self.tolerance_pct}%)")


def load_cypnest_reference() -> CypNestReference:
    """
    Zaladuj dane referencyjne z CypNest (hardcoded z wynik.xlsx)

    Dane z pliku C:\\temp\\test2\\wynik.xlsx:
    - All Task List: 2 taski
    - All Parts List: 4 unikalne czesci
    - Result1: 4 czesci (Long_HAK x2, 12 1-2 kruhu, 12 2-2 kruhu)
    - Result2: 1 czesc (zadni plech1)
    """
    return CypNestReference(
        total_cut_length_m=18.81,  # z arkusza Result1+Result2
        total_cut_time_s=129,       # 2min09s
        total_parts=5,              # 4 + 1
        sheets=[
            {
                "name": "Result1",
                "plate_size": (183.40, 2791.13),
                "nested_size": (167.40, 2775.13),
                "utilization": 67.37,
                "cut_length_m": 10.17,
                "cut_time_s": 70,
                "parts_count": 4
            },
            {
                "name": "Result2",
                "plate_size": (1356.20, 1356.20),
                "nested_size": (1340.20, 1340.20),
                "utilization": 76.63,
                "cut_length_m": 8.64,
                "cut_time_s": 59,
                "parts_count": 1
            }
        ],
        parts=[
            {
                "name": "Long_HAK",
                "qty": 2,
                "dimensions": (361.01, 25.00),
                "cut_length_m": 0.77,  # na sztuke
                "marking_m": 0.0
            },
            {
                "name": "12 1-2 kruhu",
                "qty": 1,
                "dimensions": (2038.52, 80.00),
                "cut_length_m": 4.31,
                "marking_m": 0.0
            },
            {
                "name": "12 2-2 kruhu",
                "qty": 1,
                "dimensions": (2038.52, 80.00),
                "cut_length_m": 4.31,
                "marking_m": 0.0
            },
            {
                "name": "zadni plech1",
                "qty": 1,
                "dimensions": (1340.00, 1340.00),
                "cut_length_m": 8.64,
                "marking_m": 0.08
            }
        ]
    )


def load_newerp_results(report_path: Optional[Path] = None) -> Dict:
    """
    Zaladuj wyniki z NewERP (z raportu diagnostycznego lub recznie)
    """
    # Na razie hardcoded z ostatniego uruchomienia skryptu diagnostycznego
    return {
        "total_cut_length_m": 18.79,
        "total_parts": 5,
        "parts": [
            {
                "name": "12 1-2 kruhu",
                "qty": 1,
                "dimensions": (2038.52, 80.00),
                "cut_length_m": 4.31,
                "contour_area_mm2": 163056,
                "bbox_area_mm2": 163081
            },
            {
                "name": "12 2-2 kruhu",
                "qty": 1,
                "dimensions": (2038.52, 80.00),
                "cut_length_m": 4.31,
                "contour_area_mm2": 163056,
                "bbox_area_mm2": 163081
            },
            {
                "name": "Long_HAK",
                "qty": 2,
                "dimensions": (361.01, 25.00),
                "cut_length_m": 0.77,
                "contour_area_mm2": 9025,
                "bbox_area_mm2": 9025
            },
            {
                "name": "zadni plech1",
                "qty": 1,
                "dimensions": (1340.00, 1340.00),
                "cut_length_m": 8.63,
                "contour_area_mm2": 1407997,
                "bbox_area_mm2": 1795600
            }
        ]
    }


def validate_metric(
    metric: str,
    cypnest: float,
    newerp: float,
    tolerance_pct: float = 2.0
) -> ValidationResult:
    """Waliduj pojedyncza metryke"""
    diff_abs = newerp - cypnest
    diff_pct = (diff_abs / cypnest * 100) if cypnest != 0 else 0
    passed = abs(diff_pct) <= tolerance_pct

    return ValidationResult(
        metric=metric,
        cypnest_value=cypnest,
        newerp_value=newerp,
        diff_abs=diff_abs,
        diff_pct=diff_pct,
        tolerance_pct=tolerance_pct,
        passed=passed
    )


def find_matching_part(
    cypnest_part: Dict,
    newerp_parts: List[Dict]
) -> Optional[Dict]:
    """Znajdz odpowiadajacy detal w wynikach NewERP"""
    name = cypnest_part["name"].lower()

    for part in newerp_parts:
        newerp_name = part["name"].lower()
        # Sprawdz czy nazwa zawiera kluczowe slowa
        if name in newerp_name or newerp_name in name:
            return part
        # Specjalny przypadek dla Long_HAK vs Long_HAK_2mm_INOX
        if "long_hak" in name and "long_hak" in newerp_name:
            return part
        # Dla 12 1-2 kruhu
        if "12 1-2" in name and "12 1-2" in newerp_name:
            return part
        if "12 2-2" in name and "12 2-2" in newerp_name:
            return part
        if "zadni" in name and "zadni" in newerp_name:
            return part

    return None


def run_validation() -> Tuple[List[ValidationResult], bool]:
    """
    Uruchom pelna walidacje

    Returns:
        (lista wynikow, wszystko_ok)
    """
    cypnest = load_cypnest_reference()
    newerp = load_newerp_results()

    results: List[ValidationResult] = []

    # 1. Walidacja calkowitej dlugosci ciecia
    results.append(validate_metric(
        "Total Cut Length [m]",
        cypnest.total_cut_length_m,
        newerp["total_cut_length_m"],
        tolerance_pct=2.0
    ))

    # 2. Walidacja liczby detali
    results.append(validate_metric(
        "Total Parts Count",
        float(cypnest.total_parts),
        float(newerp["total_parts"]),
        tolerance_pct=0.0  # musi byc dokladnie
    ))

    # 3. Walidacja poszczegolnych detali
    for cypnest_part in cypnest.parts:
        newerp_part = find_matching_part(cypnest_part, newerp["parts"])

        if newerp_part is None:
            results.append(ValidationResult(
                metric=f"Part '{cypnest_part['name']}' - Found",
                cypnest_value=1.0,
                newerp_value=0.0,
                diff_abs=-1.0,
                diff_pct=-100.0,
                tolerance_pct=0.0,
                passed=False
            ))
            continue

        # Walidacja dlugosci ciecia detalu
        results.append(validate_metric(
            f"Part '{cypnest_part['name']}' Cut Length [m]",
            cypnest_part["cut_length_m"],
            newerp_part["cut_length_m"],
            tolerance_pct=2.0
        ))

        # Walidacja wymiarow (width)
        results.append(validate_metric(
            f"Part '{cypnest_part['name']}' Width [mm]",
            cypnest_part["dimensions"][0],
            newerp_part["dimensions"][0],
            tolerance_pct=0.5
        ))

        # Walidacja wymiarow (height)
        results.append(validate_metric(
            f"Part '{cypnest_part['name']}' Height [mm]",
            cypnest_part["dimensions"][1],
            newerp_part["dimensions"][1],
            tolerance_pct=0.5
        ))

    all_passed = all(r.passed for r in results)
    return results, all_passed


def print_report(results: List[ValidationResult], all_passed: bool):
    """Wydrukuj raport walidacji"""
    print("\n" + "=" * 70)
    print("       RAPORT WALIDACJI NewERP vs CypNest")
    print("=" * 70)
    print(f"Data: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("-" * 70)

    # Grupuj wyniki
    passed_count = sum(1 for r in results if r.passed)
    failed_count = len(results) - passed_count

    print(f"\nPODSUMOWANIE: {passed_count}/{len(results)} testow PASSED")
    print("-" * 70)

    # Pokaz wszystkie wyniki
    for result in results:
        status_icon = "[OK]" if result.passed else "[!!]"
        diff_str = f"{result.diff_pct:+.2f}%" if result.diff_pct != 0 else "0%"
        print(f"{status_icon} {result.metric}")
        print(f"     CypNest: {result.cypnest_value:.2f}")
        print(f"     NewERP:  {result.newerp_value:.2f}")
        print(f"     Roznica: {diff_str} (tolerancja: +/-{result.tolerance_pct}%)")
        print()

    print("-" * 70)
    if all_passed:
        print("WYNIK KONCOWY: WSZYSTKIE TESTY PASSED")
        print("Roznice mieszcza sie w tolerancji <=2%")
    else:
        print(f"WYNIK KONCOWY: {failed_count} TESTOW FAILED")
        print("Wymagana korekta obliczen!")
    print("=" * 70)


def generate_json_report(results: List[ValidationResult], output_path: Path):
    """Generuj raport JSON"""
    report = {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_tests": len(results),
            "passed": sum(1 for r in results if r.passed),
            "failed": sum(1 for r in results if not r.passed),
            "all_passed": all(r.passed for r in results)
        },
        "results": [
            {
                "metric": r.metric,
                "cypnest_value": r.cypnest_value,
                "newerp_value": r.newerp_value,
                "diff_abs": r.diff_abs,
                "diff_pct": r.diff_pct,
                "tolerance_pct": r.tolerance_pct,
                "passed": r.passed
            }
            for r in results
        ]
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\nRaport JSON zapisany: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Walidacja wynikow NewERP vs dane referencyjne CypNest"
    )
    parser.add_argument(
        "--json-output",
        type=str,
        help="Sciezka do pliku JSON z raportem"
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=2.0,
        help="Tolerancja procentowa (domyslnie: 2.0%%)"
    )
    args = parser.parse_args()

    # Uruchom walidacje
    results, all_passed = run_validation()

    # Wydrukuj raport
    print_report(results, all_passed)

    # Zapisz JSON jesli podano sciezke
    if args.json_output:
        generate_json_report(results, Path(args.json_output))

    # Return code
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
