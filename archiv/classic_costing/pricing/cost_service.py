"""
Cost Service
============
Serwis łączący CostCalculator z CostRepository dla pełnej integracji z Supabase.

Odpowiada za:
- Ładowanie konfiguracji kosztów z bazy
- Kalkulacje kosztów z aktualnymi stawkami
- Zapisywanie wyników nestingu i kosztów
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import asdict
import json

from .cost_repository import CostRepository

logger = logging.getLogger(__name__)


class CostService:
    """
    Serwis kosztów integrujący kalkulator z bazą danych.

    Użycie:
        from core.supabase_client import get_supabase_client
        from pricing.cost_service import CostService

        client = get_supabase_client()
        service = CostService(client)

        # Załaduj konfigurację
        config = service.load_cost_config()

        # Oblicz koszty
        result = service.calculate_and_save_costs(nesting_result, context_type='order', context_id='...')
    """

    def __init__(self, supabase_client):
        self.client = supabase_client
        self.repository = CostRepository(supabase_client)
        self._calculator = None

    @property
    def calculator(self):
        """Lazy-load kalkulatora z aktualną konfiguracją"""
        if self._calculator is None:
            self._calculator = self._create_calculator()
        return self._calculator

    def _create_calculator(self):
        """Stwórz kalkulator z konfiguracją z bazy"""
        # Import lokalny aby uniknąć circular imports
        from quotations.pricing.cost_calculator import (
            CostCalculator, CostConfig, FoilRemovalConfig,
            PiercingConfig, OperationalConfig, AllocationModel
        )
        from quotations.pricing.pricing_tables import get_pricing_tables

        config = CostConfig()

        # Załaduj koszty operacyjne
        sheet_handling = self.repository.get_sheet_handling_cost()
        config.operational.sheet_handling_cost = sheet_handling

        setup_cost = self.repository.get_operational_cost('setup_time')
        if setup_cost:
            config.operational.setup_cost = float(setup_cost.get('cost_value', 50.0))

        programming = self.repository.get_operational_cost('programming')
        if programming:
            config.operational.programming_cost_per_part = float(programming.get('cost_value', 5.0))

        # Załaduj domyślny model alokacji
        default_model = self.repository.get_default_allocation_model()
        try:
            config.allocation_model = AllocationModel(default_model.lower())
        except ValueError:
            config.allocation_model = AllocationModel.BOUNDING_BOX

        # Załaduj bufor czasowy
        config.time_buffer_percent = self.repository.get_time_buffer_percentage()

        # Załaduj stawki piercingu do konfiguracji
        piercing_rates = self.repository.get_all_piercing_rates()
        for rate in piercing_rates:
            key = (rate['material'], float(rate['thickness']))
            config.piercing.cost_per_pierce[key] = float(rate['price_per_pierce'])
            if rate.get('time_per_pierce_sec'):
                config.piercing.piercing_times[key] = float(rate['time_per_pierce_sec'])

        # Załaduj materiały z auto-enable folii
        foil_rates = self.repository.get_all_foil_removal_rates()
        auto_enable_materials = []
        for rate in foil_rates:
            if rate.get('auto_enable'):
                if rate['material'] not in auto_enable_materials:
                    auto_enable_materials.append(rate['material'])

        if auto_enable_materials:
            config.foil.auto_enable_materials = auto_enable_materials

        return CostCalculator(get_pricing_tables(), config)

    def reload_config(self):
        """Przeładuj konfigurację z bazy"""
        self._calculator = None
        logger.info("Cost configuration reloaded")

    def load_cost_config(self) -> Dict[str, Any]:
        """
        Załaduj pełną konfigurację kosztów z bazy.

        Returns:
            Słownik z konfiguracją
        """
        return {
            'foil_removal_rates': self.repository.get_all_foil_removal_rates(),
            'piercing_rates': self.repository.get_all_piercing_rates(),
            'operational_costs': self.repository.get_all_operational_costs(),
            'cost_config': self.repository.get_all_cost_configs(),
            'time_buffer_percent': self.repository.get_time_buffer_percentage(),
            'default_allocation_model': self.repository.get_default_allocation_model(),
            'sheet_handling_cost': self.repository.get_sheet_handling_cost()
        }

    def calculate_nesting_cost(
        self,
        nesting_result: Any,
        material: str,
        thickness_mm: float,
        variant: str = 'A',
        **kwargs
    ) -> Dict:
        """
        Oblicz koszty nestingu.

        Args:
            nesting_result: Wynik z FastNester
            material: Materiał
            thickness_mm: Grubość
            variant: 'A' (cennikowy) lub 'B' (czasowy)
            **kwargs: technology_cost, packaging_cost, transport_cost

        Returns:
            Słownik z kosztami
        """
        from quotations.pricing.cost_calculator import CostVariant

        cost_variant = CostVariant.PRICE_BASED if variant == 'A' else CostVariant.TIME_BASED

        # Sprawdź czy folia powinna być auto-włączona
        auto_foil = self.repository.should_auto_enable_foil_removal(material, thickness_mm)
        if auto_foil and 'foil_enabled' not in kwargs:
            kwargs['foil_enabled'] = True

        result = self.calculator.calculate_nesting_cost(
            nesting_result, material, thickness_mm, cost_variant, **kwargs
        )

        return result.to_dict()

    def calculate_and_save_costs(
        self,
        nesting_result: Any,
        material: str,
        thickness_mm: float,
        context_type: str,
        context_id: str,
        variant: str = 'A',
        save_nesting: bool = True,
        **kwargs
    ) -> Dict:
        """
        Oblicz koszty i zapisz wyniki do bazy.

        Args:
            nesting_result: Wynik nestingu
            material: Materiał
            thickness_mm: Grubość
            context_type: 'quotation' lub 'order'
            context_id: ID oferty/zamówienia
            variant: 'A' lub 'B'
            save_nesting: Czy zapisać wyniki nestingu
            **kwargs: Dodatkowe koszty

        Returns:
            Słownik z kosztami i ID zapisanych rekordów
        """
        # Oblicz koszty
        costs = self.calculate_nesting_cost(
            nesting_result, material, thickness_mm, variant, **kwargs
        )

        result = {
            'costs': costs,
            'nesting_result_id': None,
            'order_cost_id': None
        }

        # Zapisz wynik nestingu
        if save_nesting:
            nesting_data = {
                'context_type': context_type,
                'context_id': context_id,
                'material': material,
                'thickness': thickness_mm,
                'sheet_format': kwargs.get('sheet_format', '1500x3000'),
                'sheets_used': costs.get('total_sheets', 0),
                'utilization': costs.get('average_efficiency', 0),
                'total_cutting_length': costs.get('total_cutting_length_m', 0),
                'total_pierces': costs.get('total_pierce_count', 0),
                'nesting_data': self._serialize_nesting_result(nesting_result)
            }

            success, nesting_id = self.repository.save_nesting_result(nesting_data)
            if success:
                result['nesting_result_id'] = nesting_id

        # Zapisz koszty
        cost_data = {
            'context_type': context_type,
            'context_id': context_id,
            'nesting_result_id': result['nesting_result_id'],
            'cost_variant': variant,
            'allocation_model': self.repository.get_default_allocation_model(),
            'material_cost': costs.get('material_cost', 0),
            'cutting_cost': costs.get('cutting_cost', 0),
            'foil_removal_cost': costs.get('foil_cost', 0),
            'piercing_cost': costs.get('piercing_cost', 0),
            'operational_cost': costs.get('operational_cost', 0),
            'technology_cost': costs.get('technology_cost', 0),
            'packaging_cost': costs.get('packaging_cost', 0),
            'transport_cost': costs.get('transport_cost', 0),
            'total_cost': costs.get('total_cost', 0),
            'cost_breakdown': json.dumps(costs)
        }

        success, cost_id = self.repository.save_order_costs(cost_data)
        if success:
            result['order_cost_id'] = cost_id

        return result

    def _serialize_nesting_result(self, nesting_result: Any) -> str:
        """Serializuj wynik nestingu do JSON"""
        try:
            # Podstawowa serializacja
            data = {
                'sheets_count': len(nesting_result.sheets) if hasattr(nesting_result, 'sheets') else 0,
                'total_parts': len(nesting_result.placed_parts) if hasattr(nesting_result, 'placed_parts') else 0,
                'sheets': []
            }

            if hasattr(nesting_result, 'sheets'):
                for i, sheet in enumerate(nesting_result.sheets):
                    sheet_data = {
                        'index': i,
                        'efficiency': sheet.efficiency if hasattr(sheet, 'efficiency') else 0,
                        'parts_count': len(sheet.placed_parts) if hasattr(sheet, 'placed_parts') else 0
                    }
                    data['sheets'].append(sheet_data)

            return json.dumps(data)

        except Exception as e:
            logger.error(f"Error serializing nesting result: {e}")
            return "{}"

    def get_foil_removal_rate(self, material: str, thickness: float) -> Optional[Dict]:
        """Pobierz stawkę usuwania folii"""
        return self.repository.get_foil_removal_rate(material, thickness)

    def get_piercing_rate(self, material: str, thickness: float) -> Optional[Dict]:
        """Pobierz stawkę piercingu"""
        return self.repository.get_piercing_rate(material, thickness)

    def get_latest_costs_for_context(self, context_type: str, context_id: str) -> Optional[Dict]:
        """Pobierz najnowsze koszty dla oferty/zamówienia"""
        return self.repository.get_latest_order_costs(context_type, context_id)

    def get_cost_history(self, context_type: str, context_id: str) -> List[Dict]:
        """Pobierz historię kosztów"""
        return self.repository.get_order_costs(context_type, context_id)

    def initialize_default_costs(self) -> Dict[str, int]:
        """Inicjalizuj domyślne wartości w tabelach kosztów"""
        return self.repository.initialize_default_costs()

    # === Metody do aktualizacji stawek ===

    def update_foil_removal_rate(self, data: Dict) -> bool:
        """Aktualizuj stawkę usuwania folii"""
        success, _ = self.repository.upsert_foil_removal_rate(data)
        if success:
            self.reload_config()
        return success

    def update_piercing_rate(self, data: Dict) -> bool:
        """Aktualizuj stawkę piercingu"""
        success, _ = self.repository.upsert_piercing_rate(data)
        if success:
            self.reload_config()
        return success

    def update_operational_cost(self, data: Dict) -> bool:
        """Aktualizuj koszt operacyjny"""
        success, _ = self.repository.upsert_operational_cost(data)
        if success:
            self.reload_config()
        return success

    def set_config(self, key: str, value: str, description: str = None) -> bool:
        """Ustaw wartość konfiguracji"""
        success = self.repository.set_cost_config(key, value, description)
        if success:
            self.reload_config()
        return success


def create_cost_service(supabase_client=None):
    """
    Factory function dla CostService.

    Args:
        supabase_client: Opcjonalny klient Supabase

    Returns:
        CostService instance
    """
    if supabase_client is None:
        try:
            from core.supabase_client import get_supabase_client
            supabase_client = get_supabase_client()
        except Exception as e:
            logger.error(f"Cannot create Supabase client: {e}")
            raise

    return CostService(supabase_client)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("Testing CostService...")

    try:
        service = create_cost_service()

        # Test ładowania konfiguracji
        config = service.load_cost_config()
        print(f"\nLoaded config:")
        print(f"  - Foil removal rates: {len(config['foil_removal_rates'])}")
        print(f"  - Piercing rates: {len(config['piercing_rates'])}")
        print(f"  - Operational costs: {len(config['operational_costs'])}")
        print(f"  - Time buffer: {config['time_buffer_percent']}%")
        print(f"  - Default allocation: {config['default_allocation_model']}")
        print(f"  - Sheet handling: {config['sheet_handling_cost']} PLN")

        # Test inicjalizacji domyślnych wartości
        print("\nInitializing default costs...")
        results = service.initialize_default_costs()
        print(f"  - Foil rates added: {results['foil_removal_rates']}")
        print(f"  - Piercing rates added: {results['piercing_rates']}")
        print(f"  - Operational costs added: {results['operational_costs']}")
        print(f"  - Config items added: {results['cost_config']}")

        print("\nCostService test completed!")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
