"""
Pricing Repository
==================
Operacje na bazie danych dla cenników materiałów i cięcia.

Optymalizacja:
- Batch upsert dla wielu rekordów (1 request zamiast N)
- Minimalne logowanie w operacjach batch
"""

import logging
import os
import uuid
from typing import List, Dict, Optional, Tuple, Callable
from datetime import date, datetime
from decimal import Decimal

logger = logging.getLogger(__name__)


class PricingRepository:
    """Repository do operacji na cennikach w Supabase"""
    
    def __init__(self, supabase_client):
        self.client = supabase_client
    
    # ============================================================
    # Material Prices
    # ============================================================
    
    def get_all_material_prices(self, 
                                 material: str = None,
                                 thickness: float = None,
                                 current_only: bool = True,
                                 limit: int = 1000) -> List[Dict]:
        """Pobierz ceny materiałów"""
        try:
            # Używamy bezpośrednio tabeli (widoki opcjonalne)
            query = self.client.table('material_prices').select('*')
            
            if material:
                query = query.eq('material', material)
            if thickness is not None:
                query = query.eq('thickness', thickness)
            
            query = query.order('material').order('thickness')
            
            if limit:
                query = query.limit(limit)
            
            response = query.execute()
            return response.data or []
            
        except Exception as e:
            logger.error(f"Error fetching material prices: {e}")
            return []
    
    def get_material_price(self, material: str, thickness: float, 
                           format: str = '1500x3000') -> Optional[Dict]:
        """Pobierz konkretną cenę materiału"""
        try:
            response = self.client.table('material_prices').select('*').eq(
                'material', material
            ).eq('thickness', thickness).eq('format', format).order(
                'valid_from', desc=True
            ).limit(1).execute()
            
            if response.data:
                return response.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Error fetching material price: {e}")
            return None
    
    def upsert_material_price(self, data: Dict) -> Tuple[bool, Optional[str]]:
        """Dodaj lub zaktualizuj cenę materiału"""
        try:
            import uuid
            from datetime import datetime
            
            # Przygotuj dane
            record = {
                'format': data.get('format', '1500x3000'),
                'material': data['material'],
                'thickness': float(data['thickness']),
                'price_per_kg': float(data['price_per_kg']),
                'source': data.get('source'),
                'note': data.get('note'),
                'valid_from': data.get('valid_from', date.today().isoformat()),
            }
            
            logger.debug(f"Upserting material: {record['material']} {record['thickness']}mm @ {record['price_per_kg']} PLN/kg")
            
            # Sprawdź czy istnieje
            existing = self.client.table('material_prices').select('id').eq(
                'material', record['material']
            ).eq('thickness', record['thickness']).eq(
                'format', record['format']
            ).limit(1).execute()
            
            if existing.data:
                # Update
                record_id = existing.data[0]['id']
                logger.debug(f"Updating existing record: {record_id}")
                self.client.table('material_prices').update(record).eq('id', record_id).execute()
                return True, record_id
            else:
                # Insert - generuj UUID i timestamp
                record['id'] = str(uuid.uuid4())
                record['created_at'] = datetime.now().isoformat()
                logger.debug(f"Inserting new record: {record['id']}")
                response = self.client.table('material_prices').insert(record).execute()
                if response.data:
                    logger.debug(f"Insert success: {response.data[0]['id']}")
                    return True, response.data[0]['id']
                else:
                    logger.error(f"Insert returned no data: {response}")
                return False, None
                
        except Exception as e:
            logger.error(f"Error upserting material price: {e}")
            return False, str(e)
    
    def delete_material_price(self, price_id: str) -> bool:
        """Usuń cenę materiału"""
        try:
            self.client.table('material_prices').delete().eq('id', price_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting material price: {e}")
            return False
    
    def bulk_upsert_material_prices(self, records: List[Dict]) -> Tuple[int, int, int]:
        """Bulk upsert cen materiałów. Zwraca (inserted, updated, failed)"""
        inserted = 0
        updated = 0
        failed = 0
        
        for record in records:
            try:
                success, result = self.upsert_material_price(record)
                if success:
                    if result and len(str(result)) == 36:  # UUID length
                        inserted += 1
                    else:
                        updated += 1
                else:
                    failed += 1
                    logger.error(f"Bulk upsert material failed: {record.get('material')} {record.get('thickness')}mm - {result}")
            except Exception as e:
                logger.error(f"Bulk upsert material error: {record.get('material')} {record.get('thickness')}mm - {e}")
                failed += 1
        
        logger.info(f"Bulk material upsert complete: {inserted} inserted, {updated} updated, {failed} failed")
        return inserted, updated, failed
    
    # ============================================================
    # Cutting Prices
    # ============================================================
    
    def get_all_cutting_prices(self,
                                material: str = None,
                                thickness: float = None,
                                gas: str = None,
                                current_only: bool = True,
                                limit: int = 1000) -> List[Dict]:
        """Pobierz ceny cięcia"""
        try:
            # Używamy bezpośrednio tabeli (widoki opcjonalne)
            query = self.client.table('cutting_prices').select('*')
            
            if material:
                query = query.eq('material', material)
            if thickness is not None:
                query = query.eq('thickness', thickness)
            if gas:
                query = query.eq('gas', gas)
            
            query = query.order('material').order('thickness')
            
            if limit:
                query = query.limit(limit)
            
            response = query.execute()
            return response.data or []
            
        except Exception as e:
            logger.error(f"Error fetching cutting prices: {e}")
            return []
    
    def get_cutting_price(self, material: str, thickness: float, 
                          gas: str = 'N') -> Optional[Dict]:
        """Pobierz konkretną cenę cięcia"""
        try:
            response = self.client.table('cutting_prices').select('*').eq(
                'material', material
            ).eq('thickness', thickness).eq('gas', gas).order(
                'valid_from', desc=True
            ).limit(1).execute()
            
            if response.data:
                return response.data[0]
            return None
            
        except Exception as e:
            logger.error(f"Error fetching cutting price: {e}")
            return None
    
    def upsert_cutting_price(self, data: Dict) -> Tuple[bool, Optional[str]]:
        """Dodaj lub zaktualizuj cenę cięcia"""
        try:
            import uuid
            from datetime import datetime
            
            record = {
                'material': data['material'],
                'thickness': float(data['thickness']),
                'gas': data.get('gas', 'N'),
                'cutting_speed': float(data.get('cutting_speed', 0)) if data.get('cutting_speed') else None,
                'hour_price': float(data.get('hour_price', 750)),
                'utilization': float(data.get('utilization', 0.65)),
                'price_per_meter': float(data.get('price_per_meter')) if data.get('price_per_meter') else None,
                'valid_from': data.get('valid_from', date.today().isoformat()),
            }
            
            # Oblicz price_per_meter jeśli nie podano
            if record['price_per_meter'] is None and record['cutting_speed'] and record['cutting_speed'] > 0:
                record['price_per_meter'] = record['hour_price'] / (record['cutting_speed'] * 60 * record['utilization'])
            
            logger.debug(f"Upserting cutting: {record['material']} {record['thickness']}mm {record['gas']} @ {record['price_per_meter']} PLN/m")
            
            # Sprawdź czy istnieje
            existing = self.client.table('cutting_prices').select('id').eq(
                'material', record['material']
            ).eq('thickness', record['thickness']).eq(
                'gas', record['gas']
            ).limit(1).execute()
            
            if existing.data:
                # Update
                record_id = existing.data[0]['id']
                logger.debug(f"Updating existing cutting record: {record_id}")
                self.client.table('cutting_prices').update(record).eq('id', record_id).execute()
                return True, record_id
            else:
                # Insert - generuj UUID i timestamp
                record['id'] = str(uuid.uuid4())
                record['created_at'] = datetime.now().isoformat()
                logger.debug(f"Inserting new cutting record: {record['id']}")
                response = self.client.table('cutting_prices').insert(record).execute()
                if response.data:
                    logger.debug(f"Insert cutting success: {response.data[0]['id']}")
                    return True, response.data[0]['id']
                else:
                    logger.error(f"Insert cutting returned no data: {response}")
                return False, None
                
        except Exception as e:
            logger.error(f"Error upserting cutting price: {e}")
            return False, str(e)
    
    def delete_cutting_price(self, price_id: str) -> bool:
        """Usuń cenę cięcia"""
        try:
            self.client.table('cutting_prices').delete().eq('id', price_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting cutting price: {e}")
            return False
    
    def bulk_upsert_cutting_prices(self, records: List[Dict]) -> Tuple[int, int, int]:
        """Bulk upsert cen cięcia. Zwraca (inserted, updated, failed)"""
        inserted = 0
        updated = 0
        failed = 0
        
        for record in records:
            try:
                success, result = self.upsert_cutting_price(record)
                if success:
                    if result and len(str(result)) == 36:
                        inserted += 1
                    else:
                        updated += 1
                else:
                    failed += 1
                    logger.error(f"Bulk upsert cutting failed: {record.get('material')} {record.get('thickness')}mm - {result}")
            except Exception as e:
                logger.error(f"Bulk upsert cutting error: {record.get('material')} {record.get('thickness')}mm - {e}")
                failed += 1
        
        logger.info(f"Bulk cutting upsert complete: {inserted} inserted, {updated} updated, {failed} failed")
        return inserted, updated, failed
    
    # ============================================================
    # Import History
    # ============================================================
    
    def log_import(self, import_type: str, filename: str,
                   imported: int, updated: int, failed: int,
                   status: str = 'success', error: str = None) -> Optional[str]:
        """Zapisz log importu (opcjonalne - tabela może nie istnieć)"""
        try:
            record = {
                'import_type': import_type,
                'filename': filename,
                'records_imported': imported,
                'records_updated': updated,
                'records_failed': failed,
                'status': status,
                'error_message': error
            }
            
            response = self.client.table('pricing_imports').insert(record).execute()
            if response.data:
                return response.data[0]['id']
            return None
            
        except Exception as e:
            # Tabela może nie istnieć - to OK, logowanie jest opcjonalne
            logger.warning(f"Could not log import (table may not exist): {e}")
            return None
    
    def get_import_history(self, import_type: str = None, limit: int = 50) -> List[Dict]:
        """Pobierz historię importów (opcjonalne - tabela może nie istnieć)"""
        try:
            query = self.client.table('pricing_imports').select('*')
            
            if import_type:
                query = query.eq('import_type', import_type)
            
            response = query.order('created_at', desc=True).limit(limit).execute()
            return response.data or []
            
        except Exception as e:
            # Tabela może nie istnieć - zwróć pustą listę
            logger.warning(f"Could not fetch import history (table may not exist): {e}")
            return []
    
    # ============================================================
    # Statistics
    # ============================================================
    
    def get_materials_list(self) -> List[str]:
        """Pobierz listę unikalnych materiałów"""
        try:
            response = self.client.table('material_prices').select('material').execute()
            materials = list(set(r['material'] for r in (response.data or []) if r.get('material')))
            return sorted(materials)
        except Exception as e:
            logger.error(f"Error fetching materials list: {e}")
            return []
    
    def get_thicknesses_for_material(self, material: str) -> List[float]:
        """Pobierz dostępne grubości dla materiału"""
        try:
            response = self.client.table('material_prices').select('thickness').eq(
                'material', material
            ).execute()
            thicknesses = list(set(float(r['thickness']) for r in (response.data or []) if r.get('thickness')))
            return sorted(thicknesses)
        except Exception as e:
            logger.error(f"Error fetching thicknesses: {e}")
            return []
    
    def get_statistics(self) -> Dict:
        """Pobierz statystyki cenników"""
        try:
            mat_response = self.client.table('material_prices').select('id', count='exact').execute()
            cut_response = self.client.table('cutting_prices').select('id', count='exact').execute()

            # Dodatkowe statystyki dla piercing i foil
            piercing_count = 0
            foil_count = 0
            try:
                piercing_response = self.client.table('piercing_rates').select('id', count='exact').execute()
                piercing_count = piercing_response.count or 0
            except:
                pass
            try:
                foil_response = self.client.table('foil_removal_rates').select('id', count='exact').execute()
                foil_count = foil_response.count or 0
            except:
                pass

            materials = self.get_materials_list()

            return {
                'material_prices_count': mat_response.count or 0,
                'cutting_prices_count': cut_response.count or 0,
                'piercing_rates_count': piercing_count,
                'foil_rates_count': foil_count,
                'materials_count': len(materials),
                'materials': materials
            }
        except Exception as e:
            logger.error(f"Error fetching statistics: {e}")
            return {
                'material_prices_count': 0,
                'cutting_prices_count': 0,
                'piercing_rates_count': 0,
                'foil_rates_count': 0,
                'materials_count': 0,
                'materials': []
            }

    # ============================================================
    # Piercing Rates
    # ============================================================

    def get_all_piercing_rates(self,
                               material_type: str = None,
                               thickness: float = None,
                               limit: int = 1000) -> List[Dict]:
        """Pobierz stawki przebijania"""
        try:
            query = self.client.table('piercing_rates').select('*')

            if material_type:
                query = query.eq('material_type', material_type)
            if thickness is not None:
                query = query.eq('thickness', thickness)

            query = query.order('material_type').order('thickness')

            if limit:
                query = query.limit(limit)

            response = query.execute()
            return response.data or []

        except Exception as e:
            logger.error(f"Error fetching piercing rates: {e}")
            return []

    def get_piercing_rate(self, material_type: str, thickness: float) -> Optional[Dict]:
        """Pobierz konkretną stawkę przebijania"""
        try:
            response = self.client.table('piercing_rates').select('*').eq(
                'material_type', material_type
            ).eq('thickness', thickness).order(
                'valid_from', desc=True
            ).limit(1).execute()

            if response.data:
                return response.data[0]
            return None

        except Exception as e:
            logger.error(f"Error fetching piercing rate: {e}")
            return None

    def upsert_piercing_rate(self, data: Dict) -> Tuple[bool, Optional[str]]:
        """Dodaj lub zaktualizuj stawkę przebijania"""
        try:
            import uuid
            from datetime import datetime

            record = {
                'material_type': data['material_type'],
                'thickness': float(data['thickness']),
                'pierce_time_s': float(data.get('pierce_time_s', 0.5)),
                'cost_per_pierce': float(data.get('cost_per_pierce', 0.10)),
                'note': data.get('note'),
                'valid_from': data.get('valid_from', date.today().isoformat()),
            }

            logger.debug(f"Upserting piercing: {record['material_type']} {record['thickness']}mm @ {record['cost_per_pierce']} PLN/szt")

            # Sprawdź czy istnieje
            existing = self.client.table('piercing_rates').select('id').eq(
                'material_type', record['material_type']
            ).eq('thickness', record['thickness']).limit(1).execute()

            if existing.data:
                # Update
                record_id = existing.data[0]['id']
                logger.debug(f"Updating existing piercing record: {record_id}")
                self.client.table('piercing_rates').update(record).eq('id', record_id).execute()
                return True, record_id
            else:
                # Insert
                record['id'] = str(uuid.uuid4())
                record['created_at'] = datetime.now().isoformat()
                logger.debug(f"Inserting new piercing record: {record['id']}")
                response = self.client.table('piercing_rates').insert(record).execute()
                if response.data:
                    return True, response.data[0]['id']
                return False, None

        except Exception as e:
            logger.error(f"Error upserting piercing rate: {e}")
            return False, str(e)

    def delete_piercing_rate(self, rate_id: str) -> bool:
        """Usuń stawkę przebijania"""
        try:
            self.client.table('piercing_rates').delete().eq('id', rate_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting piercing rate: {e}")
            return False

    def get_piercing_material_types(self) -> List[str]:
        """Pobierz listę typów materiałów dla piercing"""
        try:
            response = self.client.table('piercing_rates').select('material_type').execute()
            types = list(set(r['material_type'] for r in (response.data or []) if r.get('material_type')))
            return sorted(types)
        except Exception as e:
            logger.error(f"Error fetching piercing material types: {e}")
            return []

    # ============================================================
    # Foil Removal Rates
    # ============================================================

    def get_all_foil_rates(self,
                           material_type: str = None,
                           limit: int = 1000) -> List[Dict]:
        """Pobierz stawki zdejmowania folii (z widoku z price_per_meter)"""
        try:
            # Próbuj użyć widoku current_foil_rates (ma price_per_meter)
            try:
                query = self.client.table('current_foil_rates').select('*')
                if material_type:
                    query = query.eq('material_type', material_type)
                query = query.order('material_type').order('max_thickness')
                if limit:
                    query = query.limit(limit)
                response = query.execute()
                return response.data or []
            except:
                # Fallback do tabeli bazowej
                query = self.client.table('foil_removal_rates').select('*')
                if material_type:
                    query = query.eq('material_type', material_type)
                query = query.order('material_type').order('max_thickness')
                if limit:
                    query = query.limit(limit)
                response = query.execute()
                # Oblicz price_per_meter dla każdego rekordu
                data = response.data or []
                for r in data:
                    if r.get('hourly_rate') and r.get('removal_speed_m_min'):
                        r['price_per_meter'] = round(
                            (r['hourly_rate'] / (r['removal_speed_m_min'] * 60)) * 1.35, 4
                        )
                return data

        except Exception as e:
            logger.error(f"Error fetching foil rates: {e}")
            return []

    def get_foil_rate(self, material_type: str, max_thickness: float = None) -> Optional[Dict]:
        """Pobierz konkretną stawkę zdejmowania folii"""
        try:
            query = self.client.table('foil_removal_rates').select('*').eq(
                'material_type', material_type
            )
            if max_thickness is not None:
                query = query.eq('max_thickness', max_thickness)

            response = query.order('valid_from', desc=True).limit(1).execute()

            if response.data:
                r = response.data[0]
                # Oblicz price_per_meter
                if r.get('hourly_rate') and r.get('removal_speed_m_min'):
                    r['price_per_meter'] = round(
                        (r['hourly_rate'] / (r['removal_speed_m_min'] * 60)) * 1.35, 4
                    )
                return r
            return None

        except Exception as e:
            logger.error(f"Error fetching foil rate: {e}")
            return None

    def upsert_foil_rate(self, data: Dict) -> Tuple[bool, Optional[str]]:
        """Dodaj lub zaktualizuj stawkę zdejmowania folii"""
        try:
            import uuid
            from datetime import datetime

            record = {
                'material_type': data['material_type'],
                'max_thickness': float(data.get('max_thickness', 5.0)),
                'removal_speed_m_min': float(data.get('removal_speed_m_min', 15.0)),
                'hourly_rate': float(data.get('hourly_rate', 120.0)),
                'auto_enable': data.get('auto_enable', True),
                'note': data.get('note'),
                'valid_from': data.get('valid_from', date.today().isoformat()),
            }

            logger.debug(f"Upserting foil: {record['material_type']} max {record['max_thickness']}mm @ {record['hourly_rate']} PLN/h")

            # Sprawdź czy istnieje
            existing = self.client.table('foil_removal_rates').select('id').eq(
                'material_type', record['material_type']
            ).eq('max_thickness', record['max_thickness']).limit(1).execute()

            if existing.data:
                # Update
                record_id = existing.data[0]['id']
                logger.debug(f"Updating existing foil record: {record_id}")
                self.client.table('foil_removal_rates').update(record).eq('id', record_id).execute()
                return True, record_id
            else:
                # Insert
                record['id'] = str(uuid.uuid4())
                record['created_at'] = datetime.now().isoformat()
                logger.debug(f"Inserting new foil record: {record['id']}")
                response = self.client.table('foil_removal_rates').insert(record).execute()
                if response.data:
                    return True, response.data[0]['id']
                return False, None

        except Exception as e:
            logger.error(f"Error upserting foil rate: {e}")
            return False, str(e)

    def delete_foil_rate(self, rate_id: str) -> bool:
        """Usuń stawkę zdejmowania folii"""
        try:
            self.client.table('foil_removal_rates').delete().eq('id', rate_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting foil rate: {e}")
            return False

    def get_foil_material_types(self) -> List[str]:
        """Pobierz listę typów materiałów dla folii"""
        try:
            response = self.client.table('foil_removal_rates').select('material_type').execute()
            types = list(set(r['material_type'] for r in (response.data or []) if r.get('material_type')))
            return sorted(types)
        except Exception as e:
            logger.error(f"Error fetching foil material types: {e}")
            return []

    # ============================================================
    # Engraving Rates
    # ============================================================

    def get_all_engraving_rates(self,
                                gas: str = None,
                                active_only: bool = True,
                                limit: int = 1000) -> List[Dict]:
        """Pobierz stawki grawerowania (z widoku lub tabeli)"""
        try:
            # Próbuj użyć widoku current_engraving_rates
            try:
                query = self.client.table('current_engraving_rates').select('*')
                if gas:
                    query = query.eq('gas', gas)
                query = query.order('gas').order('power_percent')
                if limit:
                    query = query.limit(limit)
                response = query.execute()
                return response.data or []
            except:
                # Fallback do tabeli bazowej
                query = self.client.table('engraving_rates').select('*')
                if gas:
                    query = query.eq('gas', gas)
                if active_only:
                    query = query.eq('is_active', True)
                query = query.order('gas').order('power_percent')
                if limit:
                    query = query.limit(limit)
                response = query.execute()
                return response.data or []

        except Exception as e:
            logger.error(f"Error fetching engraving rates: {e}")
            return []

    def get_engraving_rate(self, gas: str = 'N', power_percent: float = None) -> Optional[Dict]:
        """Pobierz konkretną stawkę grawerowania"""
        try:
            query = self.client.table('engraving_rates').select('*').eq(
                'gas', gas
            ).eq('is_active', True)

            if power_percent is not None:
                query = query.eq('power_percent', power_percent)

            response = query.order('valid_from', desc=True).limit(1).execute()

            if response.data:
                return response.data[0]
            return None

        except Exception as e:
            logger.error(f"Error fetching engraving rate: {e}")
            return None

    def get_default_engraving_rate(self) -> Optional[Dict]:
        """Pobierz domyślną stawkę grawerowania"""
        try:
            response = self.client.table('engraving_rates').select('*').eq(
                'is_default', True
            ).eq('is_active', True).limit(1).execute()

            if response.data:
                return response.data[0]

            # Fallback - pierwsza aktywna stawka
            response = self.client.table('engraving_rates').select('*').eq(
                'is_active', True
            ).order('created_at').limit(1).execute()

            return response.data[0] if response.data else None

        except Exception as e:
            logger.error(f"Error fetching default engraving rate: {e}")
            return None

    def upsert_engraving_rate(self, data: Dict) -> Tuple[bool, Optional[str]]:
        """Dodaj lub zaktualizuj stawkę grawerowania"""
        try:
            record = {
                'name': data['name'],
                'gas': data.get('gas', 'N'),
                'power_percent': float(data.get('power_percent', 30.0)),
                'engraving_speed': float(data['engraving_speed']),
                'hour_price': float(data.get('hour_price', 200.0)),
                'description': data.get('description'),
                'is_default': data.get('is_default', False),
                'is_active': data.get('is_active', True),
                'valid_from': data.get('valid_from', date.today().isoformat()),
            }

            logger.debug(f"Upserting engraving: {record['name']} {record['gas']} @ {record['hour_price']} PLN/h")

            # Sprawdź czy istnieje po ID lub nazwie
            existing = None
            if data.get('id'):
                existing = self.client.table('engraving_rates').select('id').eq(
                    'id', data['id']
                ).limit(1).execute()
            else:
                existing = self.client.table('engraving_rates').select('id').eq(
                    'name', record['name']
                ).limit(1).execute()

            if existing and existing.data:
                # Update
                record_id = existing.data[0]['id']
                logger.debug(f"Updating existing engraving record: {record_id}")
                self.client.table('engraving_rates').update(record).eq('id', record_id).execute()
                return True, record_id
            else:
                # Insert
                record['id'] = str(uuid.uuid4())
                record['created_at'] = datetime.now().isoformat()
                logger.debug(f"Inserting new engraving record: {record['id']}")
                response = self.client.table('engraving_rates').insert(record).execute()
                if response.data:
                    return True, response.data[0]['id']
                return False, None

        except Exception as e:
            logger.error(f"Error upserting engraving rate: {e}")
            return False, str(e)

    def delete_engraving_rate(self, rate_id: str) -> bool:
        """Usuń stawkę grawerowania"""
        try:
            self.client.table('engraving_rates').delete().eq('id', rate_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting engraving rate: {e}")
            return False

    def get_engraving_gas_types(self) -> List[str]:
        """Pobierz listę typów gazu dla grawerowania"""
        try:
            response = self.client.table('engraving_rates').select('gas').eq('is_active', True).execute()
            types = list(set(r['gas'] for r in (response.data or []) if r.get('gas')))
            return sorted(types)
        except Exception as e:
            logger.error(f"Error fetching engraving gas types: {e}")
            return ['N', 'O', 'A']  # Domyślne

    # ============================================================
    # BATCH OPERATIONS (Delete + Insert - najszybsza metoda)
    # ============================================================

    def bulk_save_material_prices(self, records: List[Dict],
                                   progress_callback: Callable[[int, int], None] = None) -> Tuple[int, List[str]]:
        """
        Batch zapis cen materiałów (Delete + Insert).

        Strategia: Usuń istniejące rekordy po ID, wstaw wszystkie jako nowe.
        Jest to najszybsza metoda (~200ms dla 50 rekordów).

        Args:
            records: Lista rekordów do zapisu
            progress_callback: Opcjonalny callback(current, total) dla progress bar

        Returns:
            Tuple[int, List[str]]: (liczba zapisanych, lista błędów)
        """
        if not records:
            return 0, []

        errors = []
        prepared = []
        ids_to_delete = []

        for r in records:
            try:
                # Zbierz istniejące ID do usunięcia
                if r.get('id'):
                    ids_to_delete.append(r['id'])

                # Przygotuj rekord z nowym UUID
                record = {
                    'id': str(uuid.uuid4()),
                    'material': r['material'],
                    'thickness': float(r['thickness']),
                    'price_per_kg': float(r['price_per_kg']),
                    'format': r.get('format', '1500x3000'),
                    'source': r.get('source'),
                    'valid_from': r.get('valid_from', date.today().isoformat()),
                }
                prepared.append(record)
            except (KeyError, ValueError) as e:
                errors.append(f"Material {r.get('material', '?')}: {e}")

        if not prepared:
            return 0, errors

        try:
            # 1. Usuń istniejące rekordy po ID (jeśli są)
            if ids_to_delete:
                logger.info(f"Deleting {len(ids_to_delete)} existing material records...")
                self.client.table('material_prices').delete().in_('id', ids_to_delete).execute()

            # 2. Wstaw wszystkie jako nowe
            logger.info(f"Inserting {len(prepared)} material prices...")
            self.client.table('material_prices').insert(prepared).execute()

            logger.info(f"Batch save materials OK: {len(prepared)}")
            if progress_callback:
                progress_callback(len(prepared), len(prepared))
            return len(prepared), errors

        except Exception as e:
            logger.error(f"Batch save materials ERROR: {e}")
            errors.append(f"Batch error: {e}")
            return 0, errors

    def bulk_save_cutting_prices(self, records: List[Dict],
                                  progress_callback: Callable[[int, int], None] = None) -> Tuple[int, List[str]]:
        """
        Batch zapis cen cięcia (Delete + Insert).
        """
        if not records:
            return 0, []

        errors = []
        prepared = []
        ids_to_delete = []

        for r in records:
            try:
                if r.get('id'):
                    ids_to_delete.append(r['id'])

                record = {
                    'id': str(uuid.uuid4()),
                    'material': r['material'],
                    'thickness': float(r['thickness']),
                    'gas': r.get('gas', 'N'),
                    'hour_price': float(r.get('hour_price', 750)),
                    'valid_from': r.get('valid_from', date.today().isoformat()),
                }

                if r.get('cutting_speed'):
                    record['cutting_speed'] = float(r['cutting_speed'])
                if r.get('utilization'):
                    record['utilization'] = float(r['utilization'])
                if r.get('price_per_meter'):
                    record['price_per_meter'] = float(r['price_per_meter'])

                prepared.append(record)
            except (KeyError, ValueError) as e:
                errors.append(f"Cutting {r.get('material', '?')}: {e}")

        if not prepared:
            return 0, errors

        try:
            if ids_to_delete:
                logger.info(f"Deleting {len(ids_to_delete)} existing cutting records...")
                self.client.table('cutting_prices').delete().in_('id', ids_to_delete).execute()

            logger.info(f"Inserting {len(prepared)} cutting prices...")
            self.client.table('cutting_prices').insert(prepared).execute()

            logger.info(f"Batch save cutting OK: {len(prepared)}")
            if progress_callback:
                progress_callback(len(prepared), len(prepared))
            return len(prepared), errors

        except Exception as e:
            logger.error(f"Batch save cutting ERROR: {e}")
            errors.append(f"Batch error: {e}")
            return 0, errors

    def bulk_save_piercing_rates(self, records: List[Dict],
                                  progress_callback: Callable[[int, int], None] = None) -> Tuple[int, List[str]]:
        """
        Batch zapis stawek przebijania (Delete + Insert).
        """
        if not records:
            return 0, []

        errors = []
        prepared = []
        ids_to_delete = []

        for r in records:
            try:
                if r.get('id'):
                    ids_to_delete.append(r['id'])

                prepared.append({
                    'id': str(uuid.uuid4()),
                    'material_type': r['material_type'],
                    'thickness': float(r['thickness']),
                    'pierce_time_s': float(r.get('pierce_time_s', 0.5)),
                    'cost_per_pierce': float(r.get('cost_per_pierce', 0.10)),
                    'note': r.get('note'),
                    'valid_from': r.get('valid_from', date.today().isoformat()),
                })
            except (KeyError, ValueError) as e:
                errors.append(f"Piercing {r.get('material_type', '?')}: {e}")

        if not prepared:
            return 0, errors

        try:
            if ids_to_delete:
                logger.info(f"Deleting {len(ids_to_delete)} existing piercing records...")
                self.client.table('piercing_rates').delete().in_('id', ids_to_delete).execute()

            logger.info(f"Inserting {len(prepared)} piercing rates...")
            self.client.table('piercing_rates').insert(prepared).execute()

            logger.info(f"Batch save piercing OK: {len(prepared)}")
            if progress_callback:
                progress_callback(len(prepared), len(prepared))
            return len(prepared), errors

        except Exception as e:
            logger.error(f"Batch save piercing ERROR: {e}")
            errors.append(f"Batch error: {e}")
            return 0, errors

    def bulk_save_foil_rates(self, records: List[Dict],
                              progress_callback: Callable[[int, int], None] = None) -> Tuple[int, List[str]]:
        """
        Batch zapis stawek folii (Delete + Insert).
        """
        if not records:
            return 0, []

        errors = []
        prepared = []
        ids_to_delete = []

        for r in records:
            try:
                if r.get('id'):
                    ids_to_delete.append(r['id'])

                prepared.append({
                    'id': str(uuid.uuid4()),
                    'material_type': r['material_type'],
                    'max_thickness': float(r.get('max_thickness', 5.0)),
                    'removal_speed_m_min': float(r.get('removal_speed_m_min', 15.0)),
                    'hourly_rate': float(r.get('hourly_rate', 120.0)),
                    'auto_enable': r.get('auto_enable', True),
                    'note': r.get('note'),
                    'valid_from': r.get('valid_from', date.today().isoformat()),
                })
            except (KeyError, ValueError) as e:
                errors.append(f"Foil {r.get('material_type', '?')}: {e}")

        if not prepared:
            return 0, errors

        try:
            if ids_to_delete:
                logger.info(f"Deleting {len(ids_to_delete)} existing foil records...")
                self.client.table('foil_removal_rates').delete().in_('id', ids_to_delete).execute()

            logger.info(f"Inserting {len(prepared)} foil rates...")
            self.client.table('foil_removal_rates').insert(prepared).execute()

            logger.info(f"Batch save foil OK: {len(prepared)}")
            if progress_callback:
                progress_callback(len(prepared), len(prepared))
            return len(prepared), errors

        except Exception as e:
            logger.error(f"Batch save foil ERROR: {e}")
            errors.append(f"Batch error: {e}")
            return 0, errors

    def bulk_save_all(self, materials: List[Dict], cutting: List[Dict],
                      piercing: List[Dict], foil: List[Dict],
                      progress_callback: Callable[[int, int, str], None] = None) -> Dict:
        """
        Zapis wszystkich cenników w 4 requestach HTTP.

        Args:
            materials, cutting, piercing, foil: Listy rekordów
            progress_callback: callback(step, total_steps, step_name)

        Returns:
            Dict z wynikami: {'total': N, 'errors': [...], 'details': {...}}
        """
        total_saved = 0
        all_errors = []
        details = {}
        step = 0
        total_steps = 4

        # 1. Materiały
        if progress_callback:
            progress_callback(step, total_steps, "Zapisywanie cen materialow...")
        saved, errors = self.bulk_save_material_prices(materials)
        total_saved += saved
        all_errors.extend(errors)
        details['materials'] = {'saved': saved, 'errors': len(errors)}
        step += 1

        # 2. Cięcie
        if progress_callback:
            progress_callback(step, total_steps, "Zapisywanie cen ciecia...")
        saved, errors = self.bulk_save_cutting_prices(cutting)
        total_saved += saved
        all_errors.extend(errors)
        details['cutting'] = {'saved': saved, 'errors': len(errors)}
        step += 1

        # 3. Przebijanie
        if progress_callback:
            progress_callback(step, total_steps, "Zapisywanie stawek przebijania...")
        saved, errors = self.bulk_save_piercing_rates(piercing)
        total_saved += saved
        all_errors.extend(errors)
        details['piercing'] = {'saved': saved, 'errors': len(errors)}
        step += 1

        # 4. Folia
        if progress_callback:
            progress_callback(step, total_steps, "Zapisywanie stawek folii...")
        saved, errors = self.bulk_save_foil_rates(foil)
        total_saved += saved
        all_errors.extend(errors)
        details['foil'] = {'saved': saved, 'errors': len(errors)}
        step += 1

        if progress_callback:
            progress_callback(total_steps, total_steps, "Zakończono!")

        return {
            'total': total_saved,
            'errors': all_errors,
            'details': details
        }
