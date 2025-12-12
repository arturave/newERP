"""
Pricing Service
===============
Logika biznesowa dla zarządzania cennikami.
"""

import os
import logging
from typing import List, Dict, Tuple, Optional
from datetime import date

from .repository import PricingRepository
from .xlsx_importer import ExcelPriceImporter, PriceExporter, ImportResult

logger = logging.getLogger(__name__)


class PricingService:
    """Serwis do zarządzania cennikami"""
    
    def __init__(self, supabase_client):
        self.repository = PricingRepository(supabase_client)
        self.importer = ExcelPriceImporter()
        self.exporter = PriceExporter()
    
    # ============================================================
    # Material Prices
    # ============================================================
    
    def get_material_prices(self, 
                            material: str = None,
                            thickness: float = None,
                            current_only: bool = True) -> List[Dict]:
        """Pobierz ceny materiałów"""
        return self.repository.get_all_material_prices(
            material=material,
            thickness=thickness,
            current_only=current_only
        )
    
    def get_material_price(self, material: str, thickness: float,
                           format: str = '1500x3000') -> Optional[float]:
        """Pobierz pojedynczą cenę materiału [PLN/kg]"""
        record = self.repository.get_material_price(material, thickness, format)
        if record:
            return float(record.get('price_per_kg', 0))
        return None
    
    def add_material_price(self, data: Dict) -> Tuple[bool, str]:
        """Dodaj cenę materiału"""
        required = ['material', 'thickness', 'price_per_kg']
        for field in required:
            if field not in data:
                return False, f"Brak wymaganego pola: {field}"
        
        success, result = self.repository.upsert_material_price(data)
        if success:
            return True, "Dodano cenę materiału"
        return False, result or "Błąd zapisu"
    
    def update_material_price(self, price_id: str, data: Dict) -> Tuple[bool, str]:
        """Aktualizuj cenę materiału"""
        data['id'] = price_id
        success, result = self.repository.upsert_material_price(data)
        if success:
            return True, "Zaktualizowano cenę"
        return False, result or "Błąd aktualizacji"
    
    def delete_material_price(self, price_id: str) -> Tuple[bool, str]:
        """Usuń cenę materiału"""
        if self.repository.delete_material_price(price_id):
            return True, "Usunięto cenę"
        return False, "Błąd usuwania"
    
    # ============================================================
    # Cutting Prices
    # ============================================================
    
    def get_cutting_prices(self,
                           material: str = None,
                           thickness: float = None,
                           gas: str = None,
                           current_only: bool = True) -> List[Dict]:
        """Pobierz ceny cięcia"""
        return self.repository.get_all_cutting_prices(
            material=material,
            thickness=thickness,
            gas=gas,
            current_only=current_only
        )
    
    def get_cutting_price(self, material: str, thickness: float,
                          gas: str = 'N') -> Optional[float]:
        """Pobierz pojedynczą cenę cięcia [PLN/m]"""
        record = self.repository.get_cutting_price(material, thickness, gas)
        if record:
            return float(record.get('price_per_meter', 0))
        return None
    
    def add_cutting_price(self, data: Dict) -> Tuple[bool, str]:
        """Dodaj cenę cięcia"""
        required = ['material', 'thickness']
        for field in required:
            if field not in data:
                return False, f"Brak wymaganego pola: {field}"
        
        success, result = self.repository.upsert_cutting_price(data)
        if success:
            return True, "Dodano cenę cięcia"
        return False, result or "Błąd zapisu"
    
    def update_cutting_price(self, price_id: str, data: Dict) -> Tuple[bool, str]:
        """Aktualizuj cenę cięcia"""
        data['id'] = price_id
        success, result = self.repository.upsert_cutting_price(data)
        if success:
            return True, "Zaktualizowano cenę"
        return False, result or "Błąd aktualizacji"
    
    def delete_cutting_price(self, price_id: str) -> Tuple[bool, str]:
        """Usuń cenę cięcia"""
        if self.repository.delete_cutting_price(price_id):
            return True, "Usunięto cenę"
        return False, "Błąd usuwania"
    
    # ============================================================
    # Import / Export
    # ============================================================
    
    def import_from_excel(self, filepath: str, 
                          price_type: str = None) -> ImportResult:
        """
        Importuj cennik z pliku Excel.
        
        Args:
            filepath: Ścieżka do pliku .xlsx
            price_type: 'materials' lub 'cutting' (auto-detect jeśli None)
        
        Returns:
            ImportResult z wynikami importu
        """
        if not os.path.exists(filepath):
            return ImportResult(success=False, errors=[f"Plik nie istnieje: {filepath}"])
        
        # Auto-detect typu
        if price_type is None:
            price_type = self.importer.detect_file_type(filepath)
            if price_type is None:
                return ImportResult(success=False, errors=["Nie rozpoznano typu cennika"])
        
        filename = os.path.basename(filepath)
        logger.info(f"Importing {price_type} from {filename}")
        
        # Wczytaj dane
        if price_type == 'materials':
            records, errors = self.importer.read_material_prices(filepath)
        elif price_type == 'cutting':
            records, errors = self.importer.read_cutting_prices(filepath)
        else:
            return ImportResult(success=False, errors=[f"Nieznany typ: {price_type}"])
        
        logger.info(f"Read {len(records)} records from {filename}, {len(errors)} errors")
        
        if not records:
            return ImportResult(
                success=False, 
                errors=errors or ["Brak danych do importu"]
            )
        
        # Zapisz do bazy
        if price_type == 'materials':
            inserted, updated, failed = self.repository.bulk_upsert_material_prices(records)
        else:
            inserted, updated, failed = self.repository.bulk_upsert_cutting_prices(records)
        
        # Określ status
        total = inserted + updated + failed
        if failed == total:
            status = 'failed'
        elif failed > 0:
            status = 'partial'
        else:
            status = 'success'
        
        # Zapisz log importu
        self.repository.log_import(
            import_type=price_type,
            filename=filename,
            imported=inserted,
            updated=updated,
            failed=failed,
            status=status,
            error='; '.join(errors) if errors else None
        )
        
        return ImportResult(
            success=(status != 'failed'),
            imported=inserted,
            updated=updated,
            failed=failed,
            errors=errors
        )
    
    def export_to_excel(self, filepath: str, price_type: str) -> Tuple[bool, str]:
        """
        Eksportuj cennik do pliku Excel.
        
        Args:
            filepath: Ścieżka docelowa
            price_type: 'materials' lub 'cutting'
        
        Returns:
            Tuple[success, message]
        """
        try:
            if price_type == 'materials':
                records = self.get_material_prices(current_only=True)
                success = self.exporter.export_material_prices(records, filepath)
            elif price_type == 'cutting':
                records = self.get_cutting_prices(current_only=True)
                success = self.exporter.export_cutting_prices(records, filepath)
            else:
                return False, f"Nieznany typ: {price_type}"
            
            if success:
                return True, f"Wyeksportowano {len(records)} rekordów"
            return False, "Błąd eksportu"
            
        except Exception as e:
            logger.error(f"Export error: {e}")
            return False, str(e)
    
    # ============================================================
    # Statistics & Helpers
    # ============================================================
    
    def get_statistics(self) -> Dict:
        """Pobierz statystyki cenników"""
        return self.repository.get_statistics()
    
    def get_materials_list(self) -> List[str]:
        """Pobierz listę dostępnych materiałów"""
        return self.repository.get_materials_list()
    
    def get_thicknesses_for_material(self, material: str) -> List[float]:
        """Pobierz dostępne grubości dla materiału"""
        return self.repository.get_thicknesses_for_material(material)
    
    def get_import_history(self, import_type: str = None) -> List[Dict]:
        """Pobierz historię importów"""
        return self.repository.get_import_history(import_type)

    # ============================================================
    # Piercing Rates
    # ============================================================

    def get_piercing_rates(self,
                           material_type: str = None,
                           thickness: float = None) -> List[Dict]:
        """Pobierz stawki przebijania"""
        return self.repository.get_all_piercing_rates(
            material_type=material_type,
            thickness=thickness
        )

    def get_piercing_rate(self, material_type: str, thickness: float) -> Optional[Dict]:
        """Pobierz pojedynczą stawkę przebijania"""
        return self.repository.get_piercing_rate(material_type, thickness)

    def add_piercing_rate(self, data: Dict) -> Tuple[bool, str]:
        """Dodaj stawkę przebijania"""
        required = ['material_type', 'thickness']
        for field in required:
            if field not in data:
                return False, f"Brak wymaganego pola: {field}"

        success, result = self.repository.upsert_piercing_rate(data)
        if success:
            return True, "Dodano stawkę przebijania"
        return False, result or "Błąd zapisu"

    def update_piercing_rate(self, rate_id: str, data: Dict) -> Tuple[bool, str]:
        """Aktualizuj stawkę przebijania"""
        data['id'] = rate_id
        success, result = self.repository.upsert_piercing_rate(data)
        if success:
            return True, "Zaktualizowano stawkę"
        return False, result or "Błąd aktualizacji"

    def delete_piercing_rate(self, rate_id: str) -> Tuple[bool, str]:
        """Usuń stawkę przebijania"""
        if self.repository.delete_piercing_rate(rate_id):
            return True, "Usunięto stawkę"
        return False, "Błąd usuwania"

    def get_piercing_material_types(self) -> List[str]:
        """Pobierz listę typów materiałów dla piercing"""
        return self.repository.get_piercing_material_types()

    # ============================================================
    # Foil Removal Rates
    # ============================================================

    def get_foil_rates(self, material_type: str = None) -> List[Dict]:
        """Pobierz stawki zdejmowania folii"""
        return self.repository.get_all_foil_rates(material_type=material_type)

    def get_foil_rate(self, material_type: str, max_thickness: float = None) -> Optional[Dict]:
        """Pobierz pojedynczą stawkę zdejmowania folii"""
        return self.repository.get_foil_rate(material_type, max_thickness)

    def add_foil_rate(self, data: Dict) -> Tuple[bool, str]:
        """Dodaj stawkę zdejmowania folii"""
        required = ['material_type']
        for field in required:
            if field not in data:
                return False, f"Brak wymaganego pola: {field}"

        success, result = self.repository.upsert_foil_rate(data)
        if success:
            return True, "Dodano stawkę folii"
        return False, result or "Błąd zapisu"

    def update_foil_rate(self, rate_id: str, data: Dict) -> Tuple[bool, str]:
        """Aktualizuj stawkę zdejmowania folii"""
        data['id'] = rate_id
        success, result = self.repository.upsert_foil_rate(data)
        if success:
            return True, "Zaktualizowano stawkę"
        return False, result or "Błąd aktualizacji"

    def delete_foil_rate(self, rate_id: str) -> Tuple[bool, str]:
        """Usuń stawkę zdejmowania folii"""
        if self.repository.delete_foil_rate(rate_id):
            return True, "Usunięto stawkę"
        return False, "Błąd usuwania"

    def get_foil_material_types(self) -> List[str]:
        """Pobierz listę typów materiałów dla folii"""
        return self.repository.get_foil_material_types()

    # ============================================================
    # Engraving Rates
    # ============================================================

    def get_engraving_rates(self, gas: str = None) -> List[Dict]:
        """Pobierz stawki grawerowania"""
        return self.repository.get_all_engraving_rates(gas=gas)

    def get_engraving_rate(self, gas: str = 'N', power_percent: float = None) -> Optional[Dict]:
        """Pobierz pojedynczą stawkę grawerowania"""
        return self.repository.get_engraving_rate(gas, power_percent)

    def get_default_engraving_rate(self) -> Optional[Dict]:
        """Pobierz domyślną stawkę grawerowania"""
        return self.repository.get_default_engraving_rate()

    def get_engraving_price_per_meter(self, gas: str = 'N') -> Optional[float]:
        """Pobierz cenę za metr grawerowania"""
        rate = self.repository.get_default_engraving_rate()
        if rate:
            return rate.get('price_per_meter')
        return None

    def add_engraving_rate(self, data: Dict) -> Tuple[bool, str]:
        """Dodaj stawkę grawerowania"""
        required = ['name', 'engraving_speed']
        for field in required:
            if field not in data:
                return False, f"Brak wymaganego pola: {field}"

        success, result = self.repository.upsert_engraving_rate(data)
        if success:
            return True, "Dodano stawkę grawerowania"
        return False, result or "Błąd zapisu"

    def update_engraving_rate(self, rate_id: str, data: Dict) -> Tuple[bool, str]:
        """Aktualizuj stawkę grawerowania"""
        data['id'] = rate_id
        success, result = self.repository.upsert_engraving_rate(data)
        if success:
            return True, "Zaktualizowano stawkę"
        return False, result or "Błąd aktualizacji"

    def delete_engraving_rate(self, rate_id: str) -> Tuple[bool, str]:
        """Usuń stawkę grawerowania"""
        if self.repository.delete_engraving_rate(rate_id):
            return True, "Usunięto stawkę"
        return False, "Błąd usuwania"

    def get_engraving_gas_types(self) -> List[str]:
        """Pobierz listę typów gazu dla grawerowania"""
        return self.repository.get_engraving_gas_types()

    # ============================================================
    # Cost Calculation Helpers
    # ============================================================
    
    def calculate_material_cost(self, material: str, thickness: float,
                                 weight_kg: float, format: str = '1500x3000') -> float:
        """
        Oblicz koszt materiału.
        
        Args:
            material: Nazwa materiału
            thickness: Grubość [mm]
            weight_kg: Waga [kg]
            format: Format arkusza
        
        Returns:
            Koszt [PLN]
        """
        price_per_kg = self.get_material_price(material, thickness, format)
        if price_per_kg is None:
            logger.warning(f"No price for {material} {thickness}mm")
            return 0.0
        
        return weight_kg * price_per_kg
    
    def calculate_cutting_cost(self, material: str, thickness: float,
                                cutting_length_m: float, gas: str = 'N') -> float:
        """
        Oblicz koszt cięcia.
        
        Args:
            material: Nazwa materiału
            thickness: Grubość [mm]
            cutting_length_m: Długość cięcia [m]
            gas: Typ gazu
        
        Returns:
            Koszt [PLN]
        """
        price_per_m = self.get_cutting_price(material, thickness, gas)
        if price_per_m is None:
            logger.warning(f"No cutting price for {material} {thickness}mm {gas}")
            return 0.0
        
        return cutting_length_m * price_per_m

    def calculate_engraving_cost(self, engraving_length_m: float, gas: str = 'N') -> float:
        """
        Oblicz koszt grawerowania.

        Args:
            engraving_length_m: Długość grawerowania [m]
            gas: Typ gazu (domyślnie N - azot)

        Returns:
            Koszt [PLN]
        """
        price_per_m = self.get_engraving_price_per_meter(gas)
        if price_per_m is None:
            logger.warning(f"No engraving price for gas {gas}")
            return 0.0

        return engraving_length_m * price_per_m

    def calculate_total_cost(self, material: str, thickness: float,
                              weight_kg: float, cutting_length_m: float,
                              format: str = '1500x3000', gas: str = 'N') -> Dict:
        """
        Oblicz całkowity koszt (materiał + cięcie).
        
        Returns:
            Dict z kosztami składowymi
        """
        material_cost = self.calculate_material_cost(material, thickness, weight_kg, format)
        cutting_cost = self.calculate_cutting_cost(material, thickness, cutting_length_m, gas)
        
        return {
            'material_cost': material_cost,
            'cutting_cost': cutting_cost,
            'total_cost': material_cost + cutting_cost,
            'weight_kg': weight_kg,
            'cutting_length_m': cutting_length_m
        }


def create_pricing_service(supabase_client=None):
    """Factory function do tworzenia PricingService"""
    if supabase_client is None:
        from core import get_supabase_client
        supabase_client = get_supabase_client()
    
    return PricingService(supabase_client)
