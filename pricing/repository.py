"""
Pricing Repository
==================
Operacje na bazie danych dla cenników materiałów i cięcia.
"""

import logging
from typing import List, Dict, Optional, Tuple
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
            
            materials = self.get_materials_list()
            
            return {
                'material_prices_count': mat_response.count or 0,
                'cutting_prices_count': cut_response.count or 0,
                'materials_count': len(materials),
                'materials': materials
            }
        except Exception as e:
            logger.error(f"Error fetching statistics: {e}")
            return {
                'material_prices_count': 0,
                'cutting_prices_count': 0,
                'materials_count': 0,
                'materials': []
            }
