"""
Initialize Cost Tables
======================
Skrypt do inicjalizacji tabel kosztów w Supabase.

Użycie:
    python scripts/init_cost_tables.py [--force]

Opcje:
    --force    Nadpisz istniejące wartości
"""

import sys
import os
import argparse
import logging

# Dodaj ścieżkę główną projektu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description='Initialize cost tables in Supabase')
    parser.add_argument('--force', action='store_true', help='Force overwrite existing values')
    parser.add_argument('--test', action='store_true', help='Test connection only')
    args = parser.parse_args()

    print("=" * 60)
    print("NewERP - Cost Tables Initialization")
    print("=" * 60)

    try:
        from core.supabase_client import get_supabase_client
        from pricing.cost_service import create_cost_service

        print("\n1. Connecting to Supabase...")
        client = get_supabase_client()
        print("   ✓ Connected successfully")

        if args.test:
            print("\n   Connection test completed. Exiting.")
            return 0

        print("\n2. Creating CostService...")
        service = create_cost_service(client)
        print("   ✓ CostService created")

        print("\n3. Loading current configuration...")
        config = service.load_cost_config()
        print(f"   - Foil removal rates: {len(config['foil_removal_rates'])}")
        print(f"   - Piercing rates: {len(config['piercing_rates'])}")
        print(f"   - Operational costs: {len(config['operational_costs'])}")

        print("\n4. Initializing default values...")
        results = service.initialize_default_costs()

        print("\n   Results:")
        print(f"   - Foil removal rates added: {results['foil_removal_rates']}")
        print(f"   - Piercing rates added: {results['piercing_rates']}")
        print(f"   - Operational costs added: {results['operational_costs']}")
        print(f"   - Config items added: {results['cost_config']}")

        total_added = sum(results.values())
        if total_added > 0:
            print(f"\n   ✓ Total {total_added} records initialized")
        else:
            print("\n   ℹ No new records added (tables already initialized)")

        print("\n5. Verifying configuration...")
        config = service.load_cost_config()
        print(f"   - Time buffer: {config['time_buffer_percent']}%")
        print(f"   - Default allocation model: {config['default_allocation_model']}")
        print(f"   - Sheet handling cost: {config['sheet_handling_cost']} PLN")

        print("\n" + "=" * 60)
        print("Cost tables initialization completed successfully!")
        print("=" * 60)

        return 0

    except ImportError as e:
        print(f"\n✗ Import error: {e}")
        print("\n  Make sure all dependencies are installed:")
        print("    pip install supabase")
        return 1

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def check_tables_exist():
    """Sprawdź czy tabele istnieją w bazie"""
    try:
        from core.supabase_client import get_supabase_client

        client = get_supabase_client()
        tables = [
            'foil_removal_rates',
            'piercing_rates',
            'operational_costs',
            'cost_config',
            'nesting_results',
            'order_costs'
        ]

        print("\nChecking required tables...")
        all_exist = True

        for table in tables:
            try:
                response = client.table(table).select('id').limit(1).execute()
                print(f"  ✓ {table}")
            except Exception as e:
                print(f"  ✗ {table} - {e}")
                all_exist = False

        return all_exist

    except Exception as e:
        print(f"Error checking tables: {e}")
        return False


def show_current_rates():
    """Wyświetl aktualne stawki"""
    try:
        from core.supabase_client import get_supabase_client
        from pricing.cost_service import create_cost_service

        client = get_supabase_client()
        service = create_cost_service(client)

        print("\n" + "=" * 60)
        print("Current Cost Rates")
        print("=" * 60)

        # Foil removal
        print("\n--- Foil Removal Rates ---")
        foil_rates = service.repository.get_all_foil_removal_rates()
        if foil_rates:
            for rate in foil_rates:
                auto = "AUTO" if rate.get('auto_enable') else ""
                print(f"  {rate['material']} {rate['thickness_from']}-{rate['thickness_to']}mm: "
                      f"{rate['price_per_m2']} PLN/m² {auto}")
        else:
            print("  No rates configured")

        # Piercing
        print("\n--- Piercing Rates ---")
        piercing_rates = service.repository.get_all_piercing_rates()
        if piercing_rates:
            current_mat = None
            for rate in piercing_rates:
                if rate['material'] != current_mat:
                    current_mat = rate['material']
                    print(f"\n  {current_mat}:")
                print(f"    {rate['thickness']}mm: {rate['price_per_pierce']} PLN/pierce")
        else:
            print("  No rates configured")

        # Operational
        print("\n--- Operational Costs ---")
        op_costs = service.repository.get_all_operational_costs()
        if op_costs:
            for cost in op_costs:
                print(f"  {cost['cost_type']}: {cost['cost_value']} {cost.get('unit', 'PLN')}")
        else:
            print("  No costs configured")

        # Config
        print("\n--- Configuration ---")
        config = service.repository.get_all_cost_configs()
        for key, value in config.items():
            print(f"  {key}: {value}")

        print("\n" + "=" * 60)

    except Exception as e:
        print(f"Error showing rates: {e}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == '--show':
        show_current_rates()
    elif len(sys.argv) > 1 and sys.argv[1] == '--check':
        check_tables_exist()
    else:
        sys.exit(main())
