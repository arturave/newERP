"""
Test Order Repository
=====================
Skrypt testowy dla operacji CRUD na zamowieniach.

Uruchomienie:
    python -m scripts.tests.test_order_repository
"""

import sys
import os
import logging
from datetime import datetime, timedelta

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

# ASCII markers zamiast Unicode
OK = "[OK]"
FAIL = "[FAIL]"
WARN = "[!]"


def create_test_order_data() -> dict:
    """Stworz testowe dane zamowienia"""
    return {
        'name': f'TEST_ORDER_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        'client': 'Klient Testowy Sp. z o.o.',
        'date_in': datetime.now().date().isoformat(),
        'date_due': (datetime.now() + timedelta(days=10)).date().isoformat(),
        'status': 'RECEIVED',
        'priority': 'Normalny',
        'notes': 'Zamowienie testowe - mozna usunac',
        'parts_count': 3,
        'items': [
            {
                'name': 'Detal_A',
                'material': 'STAL',
                'thickness_mm': 2.0,
                'quantity': 5,
                'width': 100.0,
                'height': 150.0,
                'weight_kg': 0.5,
                'unit_cost': 10.0,
                'total_cost': 50.0,
                'filepath': 'C:/test/detal_a.dxf',
                'contour': [[0, 0], [100, 0], [100, 150], [0, 150]],
                'holes': []
            },
            {
                'name': 'Detal_B',
                'material': 'STAL',
                'thickness_mm': 3.0,
                'quantity': 10,
                'width': 200.0,
                'height': 300.0,
                'weight_kg': 2.0,
                'unit_cost': 25.0,
                'total_cost': 250.0,
                'filepath': 'C:/test/detal_b.dxf',
                'contour': [[0, 0], [200, 0], [200, 300], [0, 300]],
                'holes': [{'type': 'circle', 'x': 100, 'y': 150, 'r': 20}]
            },
            {
                'name': 'Detal_C',
                'material': 'ALUMINIUM',
                'thickness_mm': 1.5,
                'quantity': 3,
                'width': 50.0,
                'height': 80.0,
                'weight_kg': 0.1,
                'unit_cost': 15.0,
                'total_cost': 45.0,
                'filepath': 'C:/test/detal_c.dxf',
                'contour': [[0, 0], [50, 0], [50, 80], [0, 80]],
                'holes': []
            }
        ]
    }


def test_create_order(repo) -> str:
    """Test tworzenia zamowienia"""
    print("\n" + "=" * 60)
    print("TEST 1: Tworzenie zamowienia z pozycjami (items)")
    print("=" * 60)

    order_data = create_test_order_data()
    print(f"\nDane zamowienia:")
    print(f"  - Nazwa: {order_data['name']}")
    print(f"  - Klient: {order_data['client']}")
    print(f"  - Liczba pozycji: {len(order_data['items'])}")

    order_id = repo.create(order_data)

    if order_id:
        print(f"\n{OK} SUKCES: Zamowienie utworzone")
        print(f"  ID: {order_id}")
        return order_id
    else:
        print("\n[X] BŁĄD: Nie udalo sie utworzyc zamowienia")
        return None


def test_get_order_with_items(repo, order_id: str) -> bool:
    """Test pobierania zamowienia z pozycjami"""
    print("\n" + "=" * 60)
    print("TEST 2: Pobieranie zamowienia z pozycjami (get_by_id)")
    print("=" * 60)

    order = repo.get_by_id(order_id)

    if not order:
        print(f"\n[X] BŁĄD: Nie znaleziono zamowienia {order_id}")
        return False

    print(f"\nPobrane dane zamowienia:")
    print(f"  - ID: {order.get('id')}")
    print(f"  - Nazwa: {order.get('name') or order.get('title')}")
    print(f"  - Klient: {order.get('client')}")
    print(f"  - Status: {order.get('status')}")
    print(f"  - Data wejscia: {order.get('date_in')}")
    print(f"  - Termin: {order.get('date_due')}")

    items = order.get('items', [])
    print(f"\n  Pozycje (items): {len(items)}")

    if items:
        print("\n  Lista pozycji:")
        for i, item in enumerate(items, 1):
            print(f"    {i}. {item.get('name')} | {item.get('material')} | "
                  f"{item.get('thickness_mm')}mm | qty: {item.get('quantity')} | "
                  f"sciezka: {item.get('filepath', 'brak')[:30]}...")

        print(f"\n[OK] SUKCES: Zamowienie pobrane z {len(items)} pozycjami")
        return True
    else:
        print("\n[X] PROBLEM: Zamowienie pobrane, ale BEZ pozycji!")
        print("  To jest glowny bug do naprawy.")
        return False


def test_update_order(repo, order_id: str) -> bool:
    """Test aktualizacji zamowienia"""
    print("\n" + "=" * 60)
    print("TEST 3: Aktualizacja zamowienia")
    print("=" * 60)

    # Pobierz aktualne dane
    order = repo.get_by_id(order_id)
    if not order:
        print(f"\n[X] BŁĄD: Nie znaleziono zamowienia {order_id}")
        return False

    # Zmien dane
    order['name'] = order.get('name', 'Test') + '_UPDATED'
    order['status'] = 'CONFIRMED'
    order['notes'] = 'Zaktualizowano w tescie'

    # Dodaj nowa pozycje
    order['items'] = order.get('items', [])
    order['items'].append({
        'name': 'Nowy_Detal',
        'material': 'INOX',
        'thickness_mm': 4.0,
        'quantity': 2,
        'width': 120.0,
        'height': 180.0,
        'weight_kg': 1.5,
        'unit_cost': 50.0,
        'total_cost': 100.0,
        'filepath': 'C:/test/nowy_detal.dxf',
    })

    print(f"\nAktualizuje zamowienie:")
    print(f"  - Nowa nazwa: {order['name']}")
    print(f"  - Nowy status: {order['status']}")
    print(f"  - Liczba pozycji: {len(order['items'])}")

    success = repo.update(order_id, order)

    if success:
        # Sprawdz czy zmiany zostaly zapisane
        updated = repo.get_by_id(order_id)
        if updated:
            updated_items = updated.get('items', [])
            print(f"\n[OK] SUKCES: Zamowienie zaktualizowane")
            print(f"  - Nowy status: {updated.get('status')}")
            print(f"  - Liczba pozycji po update: {len(updated_items)}")
            return True

    print("\n[X] BŁĄD: Nie udalo sie zaktualizowac zamowienia")
    return False


def test_get_all_orders(repo) -> bool:
    """Test pobierania listy zamowien"""
    print("\n" + "=" * 60)
    print("TEST 4: Pobieranie listy zamowien")
    print("=" * 60)

    orders = repo.get_all(limit=10)

    print(f"\nPobrano {len(orders)} zamowien:")
    for order in orders[:5]:  # Pokaz max 5
        name = order.get('name') or order.get('title', '?')
        client = order.get('client', '-')
        status = order.get('status', '-')
        print(f"  - {name[:30]} | {client[:20]} | {status}")

    if len(orders) > 5:
        print(f"  ... i {len(orders) - 5} wiecej")

    print(f"\n[OK] SUKCES: Lista zamowien pobrana")
    return True


def test_delete_order(repo, order_id: str) -> bool:
    """Test usuwania zamowienia"""
    print("\n" + "=" * 60)
    print("TEST 5: Usuwanie zamowienia testowego")
    print("=" * 60)

    print(f"\nUsuwam zamowienie: {order_id}")

    success = repo.delete(order_id)

    if success:
        # Sprawdz czy usuniete
        order = repo.get_by_id(order_id)
        if order is None:
            print(f"\n[OK] SUKCES: Zamowienie usuniete")
            return True
        else:
            print(f"\n[X] BŁĄD: Zamowienie nadal istnieje po usunieciu!")
            return False

    print(f"\n[X] BŁĄD: Nie udalo sie usunac zamowienia")
    return False


def run_all_tests():
    """Uruchom wszystkie testy"""
    print("\n" + "=" * 60)
    print("NewERP - Test Order Repository")
    print("=" * 60)
    print(f"Czas: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Inicjalizacja
    try:
        from core.supabase_client import get_supabase_client
        from orders.repository import OrderRepository

        client = get_supabase_client()
        repo = OrderRepository(client)
        print("\n[OK] Polaczenie z Supabase: OK")
    except Exception as e:
        print(f"\n[X] Blad polaczenia z Supabase: {e}")
        return False

    results = []
    test_order_id = None

    # Test 1: Tworzenie
    try:
        test_order_id = test_create_order(repo)
        results.append(('Tworzenie zamowienia', test_order_id is not None))
    except Exception as e:
        print(f"\n[X] WYJĄTEK w tescie tworzenia: {e}")
        results.append(('Tworzenie zamowienia', False))

    # Test 2: Pobieranie z items
    if test_order_id:
        try:
            success = test_get_order_with_items(repo, test_order_id)
            results.append(('Pobieranie z items', success))
        except Exception as e:
            print(f"\n[X] WYJĄTEK w tescie pobierania: {e}")
            results.append(('Pobieranie z items', False))

    # Test 3: Aktualizacja
    if test_order_id:
        try:
            success = test_update_order(repo, test_order_id)
            results.append(('Aktualizacja', success))
        except Exception as e:
            print(f"\n[X] WYJĄTEK w tescie aktualizacji: {e}")
            results.append(('Aktualizacja', False))

    # Test 4: Lista
    try:
        success = test_get_all_orders(repo)
        results.append(('Lista zamowien', success))
    except Exception as e:
        print(f"\n[X] WYJĄTEK w tescie listy: {e}")
        results.append(('Lista zamowien', False))

    # Test 5: Usuwanie (na koncu)
    if test_order_id:
        try:
            success = test_delete_order(repo, test_order_id)
            results.append(('Usuwanie', success))
        except Exception as e:
            print(f"\n[X] WYJĄTEK w tescie usuwania: {e}")
            results.append(('Usuwanie', False))

    # Podsumowanie
    print("\n" + "=" * 60)
    print("PODSUMOWANIE TESTÓW")
    print("=" * 60)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    for name, ok in results:
        status = "[OK] PASS" if ok else "[X] FAIL"
        print(f"  {status}: {name}")

    print(f"\nWynik: {passed}/{total} testow zaliczonych")

    if passed == total:
        print("\n[OK] WSZYSTKIE TESTY ZALICZONE!")
    else:
        print("\n[X] NIEKTÓRE TESTY NIE PRZESZŁY")

    return passed == total


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
