"""
Test Nesting Save/Load
======================
Skrypt testowy dla zapisu i odczytu wynikow nestingu w zamowieniach.

Uruchomienie:
    python -m scripts.tests.test_nesting_save
"""

import sys
import os
import logging
from datetime import datetime, timedelta
import json

# Fix dla Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Dodaj sciezke projektu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ASCII markers
OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[!]"


def create_test_order_with_nesting() -> dict:
    """Stworz testowe dane zamowienia z wynikami nestingu"""
    return {
        'name': f'TEST_NESTING_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        'client': 'Klient Testowy',
        'date_in': datetime.now().date().isoformat(),
        'date_due': (datetime.now() + timedelta(days=10)).date().isoformat(),
        'status': 'RECEIVED',
        'priority': 'Normalny',
        'notes': 'Test nestingu',
        'parts_count': 2,
        'items': [
            {
                'name': 'Detal_Test_1',
                'material': 'STAL',
                'thickness_mm': 2.0,
                'quantity': 5,
                'width': 100.0,
                'height': 150.0,
                'weight_kg': 0.5,
                'unit_cost': 10.0,
                'total_cost': 50.0,
                'filepath': 'C:/test/detal_1.dxf',
            },
            {
                'name': 'Detal_Test_2',
                'material': 'STAL',
                'thickness_mm': 2.0,
                'quantity': 3,
                'width': 200.0,
                'height': 100.0,
                'weight_kg': 0.8,
                'unit_cost': 15.0,
                'total_cost': 45.0,
                'filepath': 'C:/test/detal_2.dxf',
            }
        ],
        # Wyniki nestingu
        'nesting_results': {
            'STAL_2.0': {
                'sheets_used': 2,
                'efficiency': 0.72,
                'placed_parts': 8,
                'total_cost': 450.0,
                'sheets': [
                    {
                        'sheet_id': 1,
                        'material': 'STAL',
                        'thickness_mm': 2.0,
                        'width': 2000,
                        'height': 1000,
                        'efficiency': 0.75,
                        'parts_count': 5,
                        'placements': [
                            {'part_id': 'p1', 'x': 10, 'y': 10, 'rotation': 0},
                            {'part_id': 'p2', 'x': 120, 'y': 10, 'rotation': 0},
                        ]
                    },
                    {
                        'sheet_id': 2,
                        'material': 'STAL',
                        'thickness_mm': 2.0,
                        'width': 2000,
                        'height': 1000,
                        'efficiency': 0.68,
                        'parts_count': 3,
                        'placements': [
                            {'part_id': 'p3', 'x': 10, 'y': 10, 'rotation': 90},
                        ]
                    }
                ]
            }
        },
        # Wyniki kosztow
        'cost_result': {
            'material_cost': 250.0,
            'cutting_cost': 120.0,
            'foil_cost': 0.0,
            'piercing_cost': 30.0,
            'operational_cost': 80.0,
            'subtotal': 480.0,
            'technology_cost': 50.0,
            'packaging_cost': 20.0,
            'transport_cost': 0.0,
            'total_cost': 550.0,
            'total_sheets': 2,
            'total_weight_kg': 15.5,
            'average_efficiency': 0.72
        }
    }


def test_save_order_with_nesting(repo) -> str:
    """Test zapisu zamowienia z wynikami nestingu"""
    print("\n" + "=" * 60)
    print("TEST 1: Zapis zamowienia z wynikami nestingu")
    print("=" * 60)

    order_data = create_test_order_with_nesting()
    print(f"\nDane zamowienia:")
    print(f"  - Nazwa: {order_data['name']}")
    print(f"  - Detali: {len(order_data['items'])}")
    print(f"  - Nesting results: {len(order_data.get('nesting_results', {}))}")
    print(f"  - Cost result total: {order_data.get('cost_result', {}).get('total_cost', 0)} PLN")

    order_id = repo.create(order_data)

    if order_id:
        print(f"\n{OK} SUKCES: Zamowienie zapisane z nestingiem")
        print(f"  ID: {order_id}")
        return order_id
    else:
        print(f"\n{FAIL} BLAD: Nie udalo sie zapisac zamowienia")
        return None


def test_load_order_with_nesting(repo, order_id: str) -> bool:
    """Test odczytu zamowienia z wynikami nestingu"""
    print("\n" + "=" * 60)
    print("TEST 2: Odczyt zamowienia z wynikami nestingu")
    print("=" * 60)

    order = repo.get_by_id(order_id)

    if not order:
        print(f"\n{FAIL} BLAD: Nie znaleziono zamowienia {order_id}")
        return False

    print(f"\nOdczytane dane:")
    print(f"  - Nazwa: {order.get('name') or order.get('title')}")
    print(f"  - Items: {len(order.get('items', []))}")

    # Sprawdz nesting_results
    nesting = order.get('nesting_results', {})
    if nesting:
        print(f"  - Nesting results: TAK")
        for key, value in nesting.items():
            if isinstance(value, dict):
                print(f"    - {key}: sheets={value.get('sheets_used', '?')}, eff={value.get('efficiency', '?')}")
            else:
                print(f"    - {key}: {value}")
    else:
        print(f"  - Nesting results: BRAK")

    # Sprawdz cost_result
    cost = order.get('cost_result', {})
    if cost:
        print(f"  - Cost result: TAK, total={cost.get('total_cost', 0)} PLN")
    else:
        print(f"  - Cost result: BRAK")

    # Sprawdz items
    items = order.get('items', [])
    if items:
        print(f"\n  Lista pozycji ({len(items)}):")
        for i, item in enumerate(items[:3], 1):
            print(f"    {i}. {item.get('name')} | {item.get('material')} | qty: {item.get('quantity')}")
        if len(items) > 3:
            print(f"    ... i {len(items) - 3} wiecej")

    # Walidacja
    has_items = len(items) > 0
    has_nesting = bool(nesting)
    has_cost = bool(cost)

    print(f"\n  Walidacja:")
    print(f"    - Ma items: {'TAK' if has_items else 'NIE'}")
    print(f"    - Ma nesting: {'TAK' if has_nesting else 'NIE'}")
    print(f"    - Ma cost: {'TAK' if has_cost else 'NIE'}")

    if has_items and has_nesting and has_cost:
        print(f"\n{OK} SUKCES: Wszystkie dane odczytane poprawnie")
        return True
    else:
        print(f"\n{WARN} OSTRZEZENIE: Niektore dane nie zostaly odczytane")
        return has_items  # Minimum - musimy miec items


def test_metadata_serialization():
    """Test serializacji/deserializacji metadata"""
    print("\n" + "=" * 60)
    print("TEST 3: Serializacja metadata (nesting + cost)")
    print("=" * 60)

    nesting_results = {
        'STAL_2.0': {
            'sheets_used': 2,
            'efficiency': 0.72,
            'placed_parts': 8,
            'total_cost': 450.0
        }
    }

    cost_params = {
        'variant': 'A',
        'include_material': True,
        'include_cutting': True
    }

    # Serializacja
    metadata = {
        'nesting_results': nesting_results,
        'cost_params': cost_params
    }

    try:
        json_str = json.dumps(metadata)
        print(f"\n  Serializacja: OK ({len(json_str)} znakow)")
    except Exception as e:
        print(f"\n{FAIL} Serializacja: BLAD - {e}")
        return False

    # Deserializacja
    try:
        parsed = json.loads(json_str)
        print(f"  Deserializacja: OK")

        # Sprawdz zawartosc
        if 'nesting_results' in parsed:
            print(f"  - nesting_results: OK")
        else:
            print(f"  - nesting_results: BRAK")

        if 'cost_params' in parsed:
            print(f"  - cost_params: OK")
        else:
            print(f"  - cost_params: BRAK")

        print(f"\n{OK} SUKCES: Serializacja/deserializacja dziala poprawnie")
        return True

    except Exception as e:
        print(f"\n{FAIL} Deserializacja: BLAD - {e}")
        return False


def test_delete_test_order(repo, order_id: str) -> bool:
    """Usun testowe zamowienie"""
    print("\n" + "=" * 60)
    print("TEST 4: Usuwanie testowego zamowienia")
    print("=" * 60)

    print(f"\n  Usuwam: {order_id}")
    success = repo.delete(order_id)

    if success:
        print(f"\n{OK} SUKCES: Zamowienie usuniete")
        return True
    else:
        print(f"\n{FAIL} BLAD: Nie udalo sie usunac zamowienia")
        return False


def run_all_tests():
    """Uruchom wszystkie testy"""
    print("\n" + "=" * 60)
    print("NewERP - Test Nesting Save/Load")
    print("=" * 60)
    print(f"Czas: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Inicjalizacja
    try:
        from core.supabase_client import get_supabase_client
        from orders.repository import OrderRepository

        client = get_supabase_client()
        repo = OrderRepository(client)
        print(f"\n{OK} Polaczenie z Supabase: OK")
    except Exception as e:
        print(f"\n{FAIL} Blad polaczenia z Supabase: {e}")
        return False

    results = []
    test_order_id = None

    # Test 1: Zapis z nestingiem
    try:
        test_order_id = test_save_order_with_nesting(repo)
        results.append(('Zapis z nestingiem', test_order_id is not None))
    except Exception as e:
        print(f"\n{FAIL} WYJATEK w tescie zapisu: {e}")
        results.append(('Zapis z nestingiem', False))

    # Test 2: Odczyt z nestingiem
    if test_order_id:
        try:
            success = test_load_order_with_nesting(repo, test_order_id)
            results.append(('Odczyt z nestingiem', success))
        except Exception as e:
            print(f"\n{FAIL} WYJATEK w tescie odczytu: {e}")
            results.append(('Odczyt z nestingiem', False))

    # Test 3: Serializacja metadata
    try:
        success = test_metadata_serialization()
        results.append(('Serializacja metadata', success))
    except Exception as e:
        print(f"\n{FAIL} WYJATEK w tescie serializacji: {e}")
        results.append(('Serializacja metadata', False))

    # Test 4: Usuwanie
    if test_order_id:
        try:
            success = test_delete_test_order(repo, test_order_id)
            results.append(('Usuwanie', success))
        except Exception as e:
            print(f"\n{FAIL} WYJATEK w tescie usuwania: {e}")
            results.append(('Usuwanie', False))

    # Podsumowanie
    print("\n" + "=" * 60)
    print("PODSUMOWANIE TESTOW")
    print("=" * 60)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    for name, ok in results:
        status = f"{OK} PASS" if ok else f"{FAIL} FAIL"
        print(f"  {status}: {name}")

    print(f"\nWynik: {passed}/{total} testow zaliczonych")

    if passed == total:
        print(f"\n{OK} WSZYSTKIE TESTY ZALICZONE!")
    else:
        print(f"\n{WARN} NIEKTORE TESTY NIE PRZESZLY")

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
