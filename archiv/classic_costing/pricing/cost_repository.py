"""
Cost Repository
===============
Operacje na bazie danych dla rozszerzonych tabel kosztów:
- foil_removal_rates (stawki usuwania folii)
- piercing_rates (stawki piercingu)
- operational_costs (koszty operacyjne)
- cost_config (konfiguracja kosztów)
- nesting_results (wyniki nestingu)
- order_costs (koszty zamówień)
"""

import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from decimal import Decimal
import uuid

logger = logging.getLogger(__name__)


class CostRepository:
    """Repository do operacji na tabelach kosztów w Supabase"""

    def __init__(self, supabase_client):
        self.client = supabase_client

    # ============================================================
    # Foil Removal Rates
    # ============================================================

    def get_foil_removal_rate(self, material: str, thickness: float) -> Optional[Dict]:
        """
        Pobierz stawkę usuwania folii dla materiału i grubości.

        Args:
            material: Typ materiału (np. '1.4301', 'stainless', 'aluminum')
            thickness: Grubość w mm

        Returns:
            Rekord stawki lub None
        """
        try:
            # Schemat tabeli: material_type, max_thickness, removal_speed_m_min, hourly_rate, auto_enable
            response = self.client.table('foil_removal_rates').select('*').eq(
                'material_type', material
            ).gte('max_thickness', thickness).limit(1).execute()

            if response.data:
                return response.data[0]

            # Fallback - szukaj po typie ogolnym (np. 'stainless' dla '1.4301')
            material_mapping = {
                '1.4301': 'stainless',
                '1.4404': 'stainless',
                '1.4571': 'stainless',
                'INOX': 'stainless',
                'AL': 'aluminum',
                'ALU': 'aluminum',
            }
            generic_type = material_mapping.get(material.upper(), material)

            if generic_type != material:
                response = self.client.table('foil_removal_rates').select('*').eq(
                    'material_type', generic_type
                ).gte('max_thickness', thickness).limit(1).execute()

                if response.data:
                    return response.data[0]

            return None

        except Exception as e:
            logger.error(f"Error fetching foil removal rate: {e}")
            return None

    def get_all_foil_removal_rates(self, material: str = None) -> List[Dict]:
        """Pobierz wszystkie stawki usuwania folii"""
        try:
            query = self.client.table('foil_removal_rates').select('*')

            if material:
                query = query.eq('material_type', material)

            query = query.order('material_type').order('max_thickness')

            response = query.execute()
            return response.data or []

        except Exception as e:
            logger.error(f"Error fetching foil removal rates: {e}")
            return []

    def should_auto_enable_foil_removal(self, material: str, thickness: float) -> bool:
        """
        Sprawdź czy folia powinna być automatycznie włączona.
        Zgodnie z regułą: INOX ≤5mm automatycznie włącza usuwanie folii.
        """
        rate = self.get_foil_removal_rate(material, thickness)
        if rate:
            return rate.get('auto_enable', False)
        return False

    def upsert_foil_removal_rate(self, data: Dict) -> Tuple[bool, Optional[str]]:
        """Dodaj lub zaktualizuj stawkę usuwania folii"""
        try:
            # Schemat: material_type, max_thickness, removal_speed_m_min, hourly_rate, auto_enable, note
            record = {
                'material_type': data.get('material_type') or data.get('material'),
                'max_thickness': float(data.get('max_thickness', data.get('thickness_to', 5.0))),
                'removal_speed_m_min': float(data.get('removal_speed_m_min', 15.0)),
                'hourly_rate': float(data.get('hourly_rate', 120.0)),
                'auto_enable': data.get('auto_enable', True),
                'note': data.get('note') or data.get('description'),
            }

            # Sprawdź czy istnieje
            existing = self.client.table('foil_removal_rates').select('id').eq(
                'material_type', record['material_type']
            ).eq('max_thickness', record['max_thickness']).limit(1).execute()

            if existing.data:
                record_id = existing.data[0]['id']
                record['updated_at'] = datetime.now().isoformat()
                self.client.table('foil_removal_rates').update(record).eq('id', record_id).execute()
                return True, record_id
            else:
                record['id'] = str(uuid.uuid4())
                record['created_at'] = datetime.now().isoformat()
                response = self.client.table('foil_removal_rates').insert(record).execute()
                if response.data:
                    return True, response.data[0]['id']
                return False, None

        except Exception as e:
            logger.error(f"Error upserting foil removal rate: {e}")
            return False, str(e)

    # ============================================================
    # Piercing Rates
    # ============================================================

    def get_piercing_rate(self, material: str, thickness: float) -> Optional[Dict]:
        """
        Pobierz stawkę piercingu dla materiału i grubości.
        """
        try:
            # Schemat: material_type, thickness, pierce_time_s, cost_per_pierce
            response = self.client.table('piercing_rates').select('*').eq(
                'material_type', material
            ).eq('thickness', thickness).limit(1).execute()

            if response.data:
                return response.data[0]

            # Fallback - mapowanie materialu na typ ogolny
            material_mapping = {
                '1.4301': 'stainless',
                '1.4404': 'stainless',
                '1.4571': 'stainless',
                'INOX': 'stainless',
                'INOX304': 'stainless',
                'S235': 'steel',
                'S355': 'steel',
                'DC01': 'steel',
                'AL': 'aluminum',
                'ALU': 'aluminum',
            }
            generic_type = material_mapping.get(material.upper(), material.lower())

            # Szukaj po typie ogolnym
            response = self.client.table('piercing_rates').select('*').eq(
                'material_type', generic_type
            ).eq('thickness', thickness).limit(1).execute()

            if response.data:
                return response.data[0]

            # Szukaj najbliższej grubości
            response = self.client.table('piercing_rates').select('*').eq(
                'material_type', generic_type
            ).order('thickness').execute()

            if response.data:
                closest = min(response.data,
                             key=lambda x: abs(float(x['thickness']) - thickness))
                return closest

            return None

        except Exception as e:
            logger.error(f"Error fetching piercing rate: {e}")
            return None

    def get_all_piercing_rates(self, material: str = None) -> List[Dict]:
        """Pobierz wszystkie stawki piercingu"""
        try:
            query = self.client.table('piercing_rates').select('*')

            if material:
                query = query.eq('material_type', material)

            query = query.order('material_type').order('thickness')

            response = query.execute()
            return response.data or []

        except Exception as e:
            logger.error(f"Error fetching piercing rates: {e}")
            return []

    def upsert_piercing_rate(self, data: Dict) -> Tuple[bool, Optional[str]]:
        """Dodaj lub zaktualizuj stawkę piercingu"""
        try:
            # Schemat: material_type, thickness, pierce_time_s, cost_per_pierce, note
            record = {
                'material_type': data.get('material_type') or data.get('material'),
                'thickness': float(data['thickness']),
                'cost_per_pierce': float(data.get('cost_per_pierce') or data.get('price_per_pierce', 0)),
                'pierce_time_s': float(data.get('pierce_time_s') or data.get('time_per_pierce_sec', 0)),
                'note': data.get('note') or data.get('description'),
            }

            existing = self.client.table('piercing_rates').select('id').eq(
                'material_type', record['material_type']
            ).eq('thickness', record['thickness']).limit(1).execute()

            if existing.data:
                record_id = existing.data[0]['id']
                record['updated_at'] = datetime.now().isoformat()
                self.client.table('piercing_rates').update(record).eq('id', record_id).execute()
                return True, record_id
            else:
                record['id'] = str(uuid.uuid4())
                record['created_at'] = datetime.now().isoformat()
                response = self.client.table('piercing_rates').insert(record).execute()
                if response.data:
                    return True, response.data[0]['id']
                return False, None

        except Exception as e:
            logger.error(f"Error upserting piercing rate: {e}")
            return False, str(e)

    # ============================================================
    # Operational Costs
    # ============================================================

    def get_operational_cost(self, cost_type: str) -> Optional[Dict]:
        """
        Pobierz koszt operacyjny.

        Args:
            cost_type: Typ kosztu (sheet_handling, setup_time, programming, etc.)
        """
        try:
            response = self.client.table('operational_costs').select('*').eq(
                'cost_type', cost_type
            ).eq('is_active', True).limit(1).execute()

            if response.data:
                return response.data[0]
            return None

        except Exception as e:
            logger.error(f"Error fetching operational cost: {e}")
            return None

    def get_all_operational_costs(self) -> List[Dict]:
        """Pobierz wszystkie koszty operacyjne"""
        try:
            response = self.client.table('operational_costs').select('*').eq(
                'is_active', True
            ).order('cost_type').execute()

            return response.data or []

        except Exception as e:
            logger.error(f"Error fetching operational costs: {e}")
            return []

    def get_sheet_handling_cost(self) -> float:
        """Pobierz koszt obsługi arkusza (domyślnie 40 PLN)"""
        cost = self.get_operational_cost('sheet_handling')
        if cost:
            return float(cost.get('cost_value', 40.0))
        return 40.0  # Wartość domyślna

    def upsert_operational_cost(self, data: Dict) -> Tuple[bool, Optional[str]]:
        """Dodaj lub zaktualizuj koszt operacyjny"""
        try:
            record = {
                'cost_type': data['cost_type'],
                'cost_value': float(data['cost_value']),
                'unit': data.get('unit', 'PLN'),
                'description': data.get('description'),
                'is_active': data.get('is_active', True)
            }

            existing = self.client.table('operational_costs').select('id').eq(
                'cost_type', record['cost_type']
            ).limit(1).execute()

            if existing.data:
                record_id = existing.data[0]['id']
                record['updated_at'] = datetime.now().isoformat()
                self.client.table('operational_costs').update(record).eq('id', record_id).execute()
                return True, record_id
            else:
                record['id'] = str(uuid.uuid4())
                record['created_at'] = datetime.now().isoformat()
                response = self.client.table('operational_costs').insert(record).execute()
                if response.data:
                    return True, response.data[0]['id']
                return False, None

        except Exception as e:
            logger.error(f"Error upserting operational cost: {e}")
            return False, str(e)

    # ============================================================
    # Cost Config
    # ============================================================

    def get_cost_config(self, config_key: str) -> Optional[str]:
        """
        Pobierz wartość konfiguracji.

        Args:
            config_key: Klucz konfiguracji
        """
        try:
            response = self.client.table('cost_config').select('config_value').eq(
                'config_key', config_key
            ).limit(1).execute()

            if response.data:
                return response.data[0].get('config_value')
            return None

        except Exception as e:
            logger.error(f"Error fetching cost config: {e}")
            return None

    def get_all_cost_configs(self) -> Dict[str, str]:
        """Pobierz wszystkie konfiguracje jako słownik"""
        try:
            response = self.client.table('cost_config').select('*').execute()

            configs = {}
            for row in (response.data or []):
                configs[row['config_key']] = row['config_value']

            return configs

        except Exception as e:
            logger.error(f"Error fetching cost configs: {e}")
            return {}

    def set_cost_config(self, config_key: str, config_value: str,
                        description: str = None) -> bool:
        """Ustaw wartość konfiguracji"""
        try:
            existing = self.client.table('cost_config').select('id').eq(
                'config_key', config_key
            ).limit(1).execute()

            if existing.data:
                record_id = existing.data[0]['id']
                self.client.table('cost_config').update({
                    'config_value': config_value,
                    'description': description,
                    'updated_at': datetime.now().isoformat()
                }).eq('id', record_id).execute()
            else:
                self.client.table('cost_config').insert({
                    'id': str(uuid.uuid4()),
                    'config_key': config_key,
                    'config_value': config_value,
                    'description': description,
                    'created_at': datetime.now().isoformat()
                }).execute()

            return True

        except Exception as e:
            logger.error(f"Error setting cost config: {e}")
            return False

    def get_time_buffer_percentage(self) -> float:
        """Pobierz bufor czasowy dla wariantu B (domyślnie 25%)"""
        value = self.get_cost_config('time_buffer_percentage')
        if value:
            return float(value)
        return 25.0

    def get_default_allocation_model(self) -> str:
        """Pobierz domyślny model alokacji materiału"""
        value = self.get_cost_config('default_allocation_model')
        return value or 'BOUNDING_BOX'

    # ============================================================
    # Nesting Results
    # ============================================================

    def save_nesting_result(self, data: Dict) -> Tuple[bool, Optional[str]]:
        """
        Zapisz wynik nestingu.

        Args:
            data: Dane wyniku nestingu:
                - context_type: 'quotation' lub 'order'
                - context_id: ID oferty lub zamówienia
                - material, thickness, sheet_format
                - sheets_used, utilization
                - total_cutting_length, total_pierces
                - nesting_data: JSON z pełnymi danymi
        """
        try:
            record = {
                'id': str(uuid.uuid4()),
                'context_type': data['context_type'],
                'context_id': data.get('context_id'),
                'material': data['material'],
                'thickness': float(data['thickness']),
                'sheet_format': data.get('sheet_format', '1500x3000'),
                'sheets_used': int(data['sheets_used']),
                'utilization': float(data['utilization']),
                'total_cutting_length': float(data.get('total_cutting_length', 0)),
                'total_pierces': int(data.get('total_pierces', 0)),
                'nesting_data': data.get('nesting_data'),  # JSON
                'created_at': datetime.now().isoformat()
            }

            response = self.client.table('nesting_results').insert(record).execute()

            if response.data:
                logger.info(f"Nesting result saved: {record['id']}")
                return True, response.data[0]['id']
            return False, None

        except Exception as e:
            logger.error(f"Error saving nesting result: {e}")
            return False, str(e)

    def get_nesting_results_for_context(self, context_type: str,
                                         context_id: str) -> List[Dict]:
        """Pobierz wyniki nestingu dla kontekstu (oferty/zamówienia)"""
        try:
            response = self.client.table('nesting_results').select('*').eq(
                'context_type', context_type
            ).eq('context_id', context_id).order('created_at', desc=True).execute()

            return response.data or []

        except Exception as e:
            logger.error(f"Error fetching nesting results: {e}")
            return []

    def get_latest_nesting_result(self, context_type: str,
                                   context_id: str) -> Optional[Dict]:
        """Pobierz najnowszy wynik nestingu dla kontekstu"""
        results = self.get_nesting_results_for_context(context_type, context_id)
        return results[0] if results else None

    # ============================================================
    # Order Costs
    # ============================================================

    def save_order_costs(self, data: Dict) -> Tuple[bool, Optional[str]]:
        """
        Zapisz koszty zamówienia/oferty.

        Args:
            data: Dane kosztów:
                - context_type: 'quotation' lub 'order'
                - context_id: ID
                - nesting_result_id: ID wyniku nestingu
                - cost_variant: 'A' lub 'B'
                - allocation_model: model alokacji
                - material_cost, cutting_cost, foil_removal_cost, etc.
                - total_cost
        """
        try:
            record = {
                'id': str(uuid.uuid4()),
                'context_type': data['context_type'],
                'context_id': data['context_id'],
                'nesting_result_id': data.get('nesting_result_id'),
                'cost_variant': data.get('cost_variant', 'A'),
                'allocation_model': data.get('allocation_model', 'BOUNDING_BOX'),
                'material_cost': float(data.get('material_cost', 0)),
                'cutting_cost': float(data.get('cutting_cost', 0)),
                'foil_removal_cost': float(data.get('foil_removal_cost', 0)),
                'piercing_cost': float(data.get('piercing_cost', 0)),
                'operational_cost': float(data.get('operational_cost', 0)),
                'technology_cost': float(data.get('technology_cost', 0)),
                'packaging_cost': float(data.get('packaging_cost', 0)),
                'transport_cost': float(data.get('transport_cost', 0)),
                'total_cost': float(data.get('total_cost', 0)),
                'cost_breakdown': data.get('cost_breakdown'),  # JSON
                'created_at': datetime.now().isoformat()
            }

            response = self.client.table('order_costs').insert(record).execute()

            if response.data:
                logger.info(f"Order costs saved: {record['id']}")
                return True, response.data[0]['id']
            return False, None

        except Exception as e:
            logger.error(f"Error saving order costs: {e}")
            return False, str(e)

    def get_order_costs(self, context_type: str, context_id: str) -> List[Dict]:
        """Pobierz historię kosztów dla kontekstu"""
        try:
            response = self.client.table('order_costs').select('*').eq(
                'context_type', context_type
            ).eq('context_id', context_id).order('created_at', desc=True).execute()

            return response.data or []

        except Exception as e:
            logger.error(f"Error fetching order costs: {e}")
            return []

    def get_latest_order_costs(self, context_type: str,
                                context_id: str) -> Optional[Dict]:
        """Pobierz najnowsze koszty dla kontekstu"""
        costs = self.get_order_costs(context_type, context_id)
        return costs[0] if costs else None

    # ============================================================
    # Bulk Operations & Initialization
    # ============================================================

    def initialize_default_costs(self) -> Dict[str, int]:
        """
        Inicjalizuj domyślne wartości kosztów jeśli tabele są puste.

        Returns:
            Słownik z liczbą dodanych rekordów per tabela
        """
        results = {
            'foil_removal_rates': 0,
            'piercing_rates': 0,
            'operational_costs': 0,
            'cost_config': 0
        }

        # Domyślne stawki usuwania folii
        default_foil_rates = [
            {'material': 'INOX', 'thickness_from': 0, 'thickness_to': 5,
             'price_per_m2': 15.0, 'auto_enable': True,
             'description': 'INOX ≤5mm - automatyczne usuwanie folii'},
            {'material': 'INOX', 'thickness_from': 5.01, 'thickness_to': 20,
             'price_per_m2': 20.0, 'auto_enable': False,
             'description': 'INOX >5mm - opcjonalne usuwanie folii'},
            {'material': 'AL', 'thickness_from': 0, 'thickness_to': 10,
             'price_per_m2': 12.0, 'auto_enable': False,
             'description': 'Aluminium - opcjonalne usuwanie folii'},
        ]

        for rate in default_foil_rates:
            existing = self.get_foil_removal_rate(rate['material'],
                                                   rate['thickness_from'])
            if not existing:
                success, _ = self.upsert_foil_removal_rate(rate)
                if success:
                    results['foil_removal_rates'] += 1

        # Domyślne stawki piercingu
        default_piercing_rates = [
            {'material': 'ST', 'thickness': 1, 'price_per_pierce': 0.10},
            {'material': 'ST', 'thickness': 2, 'price_per_pierce': 0.15},
            {'material': 'ST', 'thickness': 3, 'price_per_pierce': 0.20},
            {'material': 'ST', 'thickness': 5, 'price_per_pierce': 0.30},
            {'material': 'ST', 'thickness': 8, 'price_per_pierce': 0.50},
            {'material': 'ST', 'thickness': 10, 'price_per_pierce': 0.70},
            {'material': 'ST', 'thickness': 15, 'price_per_pierce': 1.00},
            {'material': 'ST', 'thickness': 20, 'price_per_pierce': 1.50},
            {'material': 'INOX', 'thickness': 1, 'price_per_pierce': 0.15},
            {'material': 'INOX', 'thickness': 2, 'price_per_pierce': 0.25},
            {'material': 'INOX', 'thickness': 3, 'price_per_pierce': 0.35},
            {'material': 'INOX', 'thickness': 5, 'price_per_pierce': 0.50},
            {'material': 'INOX', 'thickness': 8, 'price_per_pierce': 0.80},
            {'material': 'INOX', 'thickness': 10, 'price_per_pierce': 1.20},
            {'material': 'AL', 'thickness': 1, 'price_per_pierce': 0.08},
            {'material': 'AL', 'thickness': 2, 'price_per_pierce': 0.12},
            {'material': 'AL', 'thickness': 3, 'price_per_pierce': 0.18},
            {'material': 'AL', 'thickness': 5, 'price_per_pierce': 0.25},
            {'material': 'AL', 'thickness': 8, 'price_per_pierce': 0.40},
            {'material': 'AL', 'thickness': 10, 'price_per_pierce': 0.60},
        ]

        for rate in default_piercing_rates:
            existing = self.get_piercing_rate(rate['material'], rate['thickness'])
            if not existing:
                success, _ = self.upsert_piercing_rate(rate)
                if success:
                    results['piercing_rates'] += 1

        # Domyślne koszty operacyjne
        default_operational_costs = [
            {'cost_type': 'sheet_handling', 'cost_value': 40.0,
             'unit': 'PLN/arkusz', 'description': 'Koszt obsługi arkusza'},
            {'cost_type': 'setup_time', 'cost_value': 100.0,
             'unit': 'PLN', 'description': 'Koszt ustawienia maszyny'},
            {'cost_type': 'programming', 'cost_value': 50.0,
             'unit': 'PLN', 'description': 'Koszt programowania'},
        ]

        for cost in default_operational_costs:
            existing = self.get_operational_cost(cost['cost_type'])
            if not existing:
                success, _ = self.upsert_operational_cost(cost)
                if success:
                    results['operational_costs'] += 1

        # Domyślna konfiguracja
        default_configs = [
            ('time_buffer_percentage', '25', 'Bufor czasowy dla wariantu B (%)'),
            ('default_allocation_model', 'BOUNDING_BOX', 'Domyślny model alokacji materiału'),
            ('default_cost_variant', 'A', 'Domyślny wariant kosztów (A=cennikowy, B=czasowy)'),
        ]

        for key, value, desc in default_configs:
            existing = self.get_cost_config(key)
            if not existing:
                success = self.set_cost_config(key, value, desc)
                if success:
                    results['cost_config'] += 1

        logger.info(f"Default costs initialized: {results}")
        return results
