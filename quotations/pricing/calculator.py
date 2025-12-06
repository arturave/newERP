"""
NewERP - Pricing Calculator
===========================
Kalkulator kosztów cięcia laserowego i gięcia.

Składniki kosztu:
1. Materiał (cena za kg × zużycie)
2. Cięcie laserowe (czas × stawka maszynowa)
3. Gięcie (ilość gięć × stawka)
4. Przygotowanie (setup, programowanie)
5. Marża

Wzory:
- Czas cięcia = długość_konturu / prędkość_cięcia + przebiegi_jałowe
- Zużycie materiału = powierzchnia_arkuszy × grubość × gęstość
"""

import math
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class MaterialType(Enum):
    """Typy materiałów"""
    STEEL = "steel"           # Stal czarna
    STAINLESS = "stainless"   # Stal nierdzewna
    ALUMINUM = "aluminum"     # Aluminium
    COPPER = "copper"         # Miedź
    BRASS = "brass"           # Mosiądz


@dataclass
class MaterialSpec:
    """Specyfikacja materiału"""
    name: str
    type: MaterialType
    density_kg_m3: float      # Gęstość [kg/m³]
    price_per_kg: float       # Cena [PLN/kg]
    
    # Współczynniki cięcia (względem stali czarnej = 1.0)
    cutting_speed_factor: float = 1.0   # 1.0 = normalna prędkość
    cutting_cost_factor: float = 1.0    # Mnożnik kosztu cięcia
    
    # Opcjonalne
    grade: str = ""           # Gatunek np. "1.4301", "S355"


# Standardowe materiały
MATERIALS = {
    # Stale czarne
    "S235": MaterialSpec(
        name="S235JR", 
        type=MaterialType.STEEL,
        density_kg_m3=7850,
        price_per_kg=4.50,
        cutting_speed_factor=1.0,
        grade="S235JR"
    ),
    "S355": MaterialSpec(
        name="S355J2", 
        type=MaterialType.STEEL,
        density_kg_m3=7850,
        price_per_kg=5.00,
        cutting_speed_factor=0.95,
        grade="S355J2"
    ),
    "DC01": MaterialSpec(
        name="DC01", 
        type=MaterialType.STEEL,
        density_kg_m3=7850,
        price_per_kg=5.20,
        cutting_speed_factor=1.0,
        grade="DC01"
    ),
    
    # Stale nierdzewne
    "1.4301": MaterialSpec(
        name="1.4301 (AISI 304)", 
        type=MaterialType.STAINLESS,
        density_kg_m3=7900,
        price_per_kg=18.00,
        cutting_speed_factor=0.7,
        cutting_cost_factor=1.3,
        grade="1.4301"
    ),
    "1.4404": MaterialSpec(
        name="1.4404 (AISI 316L)", 
        type=MaterialType.STAINLESS,
        density_kg_m3=7950,
        price_per_kg=22.00,
        cutting_speed_factor=0.65,
        cutting_cost_factor=1.4,
        grade="1.4404"
    ),
    "INOX304": MaterialSpec(
        name="INOX 304", 
        type=MaterialType.STAINLESS,
        density_kg_m3=7900,
        price_per_kg=18.00,
        cutting_speed_factor=0.7,
        cutting_cost_factor=1.3,
        grade="1.4301"
    ),
    
    # Aluminium
    "ALU": MaterialSpec(
        name="Aluminium", 
        type=MaterialType.ALUMINUM,
        density_kg_m3=2700,
        price_per_kg=25.00,
        cutting_speed_factor=1.5,
        cutting_cost_factor=1.1,
        grade="EN AW-5754"
    ),
    
    # Corten
    "CORTEN": MaterialSpec(
        name="Corten A", 
        type=MaterialType.STEEL,
        density_kg_m3=7850,
        price_per_kg=8.00,
        cutting_speed_factor=0.9,
        grade="S355J2WP"
    ),
}


@dataclass
class CuttingRates:
    """Stawki cięcia laserowego [mm/min] dla różnych grubości"""
    
    # Stal czarna - CO2 laser
    steel_rates: Dict[float, float] = field(default_factory=lambda: {
        0.5: 12000, 0.8: 10000, 1.0: 9000, 1.5: 7500,
        2.0: 6000, 2.5: 5000, 3.0: 4200, 4.0: 3200,
        5.0: 2500, 6.0: 2000, 8.0: 1400, 10.0: 1000,
        12.0: 750, 15.0: 500, 20.0: 300, 25.0: 180
    })
    
    def get_rate(self, thickness_mm: float, material_type: MaterialType) -> float:
        """Pobierz prędkość cięcia dla danej grubości i materiału"""
        # Znajdź najbliższą grubość
        thicknesses = sorted(self.steel_rates.keys())
        
        closest = min(thicknesses, key=lambda t: abs(t - thickness_mm))
        base_rate = self.steel_rates[closest]
        
        # Interpolacja liniowa dla grubości pomiędzy
        if thickness_mm not in self.steel_rates:
            # Znajdź sąsiednie
            lower = max([t for t in thicknesses if t <= thickness_mm], default=closest)
            upper = min([t for t in thicknesses if t >= thickness_mm], default=closest)
            
            if lower != upper:
                ratio = (thickness_mm - lower) / (upper - lower)
                base_rate = self.steel_rates[lower] + ratio * (self.steel_rates[upper] - self.steel_rates[lower])
        
        # Korekta dla materiału
        factors = {
            MaterialType.STEEL: 1.0,
            MaterialType.STAINLESS: 0.7,
            MaterialType.ALUMINUM: 1.5,
            MaterialType.COPPER: 0.5,
            MaterialType.BRASS: 0.6,
        }
        
        return base_rate * factors.get(material_type, 1.0)


@dataclass
class MachineRates:
    """Stawki maszynowe"""
    laser_rate_per_hour: float = 350.0       # PLN/h - praca lasera
    bending_rate_per_hour: float = 200.0     # PLN/h - prasa krawędziowa
    bending_per_bend: float = 2.50           # PLN za pojedyncze gięcie
    setup_cost: float = 50.0                 # Koszt przygotowania zlecenia
    programming_per_part: float = 10.0       # Programowanie CAM za detal
    min_order_value: float = 100.0           # Minimalna wartość zlecenia


@dataclass
class PricingInput:
    """Dane wejściowe do kalkulacji"""
    # Identyfikacja
    part_name: str
    quantity: int
    
    # Wymiary
    width_mm: float
    height_mm: float
    thickness_mm: float
    
    # Materiał
    material_key: str  # Klucz do MATERIALS
    
    # Opcjonalne
    contour_length_mm: Optional[float] = None  # Długość konturu (jeśli znana)
    piercing_count: int = 1                    # Liczba przebić
    bending_count: int = 0                     # Liczba gięć
    
    # Wynik nestingu
    sheets_used: int = 1
    sheet_utilization: float = 0.5             # 0-1


@dataclass
class PricingBreakdown:
    """Szczegółowy rozkład kosztów"""
    # Składniki
    material_cost: float = 0.0
    cutting_cost: float = 0.0
    bending_cost: float = 0.0
    setup_cost: float = 0.0
    programming_cost: float = 0.0
    
    # Podsumowanie
    subtotal: float = 0.0
    margin_percent: float = 0.0
    margin_value: float = 0.0
    total: float = 0.0
    
    # Cena jednostkowa
    unit_price: float = 0.0
    
    # Szczegóły
    material_weight_kg: float = 0.0
    cutting_time_min: float = 0.0
    cutting_length_m: float = 0.0
    
    def __str__(self) -> str:
        return (
            f"=== KALKULACJA ===\n"
            f"Materiał:     {self.material_cost:>10.2f} PLN ({self.material_weight_kg:.2f} kg)\n"
            f"Cięcie:       {self.cutting_cost:>10.2f} PLN ({self.cutting_time_min:.1f} min)\n"
            f"Gięcie:       {self.bending_cost:>10.2f} PLN\n"
            f"Setup:        {self.setup_cost:>10.2f} PLN\n"
            f"Programowanie:{self.programming_cost:>10.2f} PLN\n"
            f"{'─'*35}\n"
            f"Suma netto:   {self.subtotal:>10.2f} PLN\n"
            f"Marża ({self.margin_percent:.0f}%): {self.margin_value:>10.2f} PLN\n"
            f"{'═'*35}\n"
            f"RAZEM:        {self.total:>10.2f} PLN\n"
            f"Cena/szt:     {self.unit_price:>10.2f} PLN"
        )


class PricingCalculator:
    """
    Kalkulator cen cięcia laserowego.
    
    Użycie:
        calc = PricingCalculator()
        result = calc.calculate(PricingInput(
            part_name="Płyta",
            quantity=10,
            width_mm=300,
            height_mm=200,
            thickness_mm=3.0,
            material_key="1.4301"
        ))
        print(result)
    """
    
    def __init__(
        self,
        cutting_rates: CuttingRates = None,
        machine_rates: MachineRates = None,
        default_margin: float = 0.25,  # 25%
        use_pricing_tables: bool = True  # Użyj cenników XLSX
    ):
        self.cutting_rates = cutting_rates or CuttingRates()
        self.machine_rates = machine_rates or MachineRates()
        self.default_margin = default_margin
        self.use_pricing_tables = use_pricing_tables
        
        # Pobierz globalne cenniki
        if use_pricing_tables:
            try:
                from quotations.pricing.pricing_tables import get_pricing_tables
                self.pricing_tables = get_pricing_tables()
            except ImportError:
                self.pricing_tables = None
        else:
            self.pricing_tables = None
    
    def get_material(self, key: str, thickness: float = None) -> Optional[MaterialSpec]:
        """Pobierz specyfikację materiału"""
        # Najpierw spróbuj z pricing_tables (XLSX)
        if self.pricing_tables and thickness:
            mat_price = self.pricing_tables.get_material_price(key, thickness)
            if mat_price:
                # Utwórz MaterialSpec z danych XLSX
                return MaterialSpec(
                    name=mat_price.material,
                    type=self._get_material_type(mat_price.material),
                    density_kg_m3=mat_price.density_kg_m3,
                    price_per_kg=mat_price.price_per_kg,
                    grade=mat_price.material
                )
        
        # Fallback do wbudowanych
        if key in MATERIALS:
            return MATERIALS[key]
        
        # Próbuj normalizacji
        key_upper = key.upper().replace(' ', '').replace('-', '')
        for mat_key, mat in MATERIALS.items():
            if mat_key.upper().replace(' ', '') == key_upper:
                return mat
            if mat.grade.upper().replace('.', '') == key_upper.replace('.', ''):
                return mat
        
        # Domyślnie stal czarna
        logger.warning(f"Unknown material '{key}', using S235")
        return MATERIALS.get("S235")
    
    def _get_material_type(self, material_name: str) -> MaterialType:
        """Określ typ materiału po nazwie"""
        name_upper = material_name.upper()
        if '1.4' in name_upper or 'INOX' in name_upper or '304' in name_upper or '316' in name_upper:
            return MaterialType.STAINLESS
        elif 'ALU' in name_upper:
            return MaterialType.ALUMINUM
        else:
            return MaterialType.STEEL
    
    def get_cutting_rate_from_tables(self, material: str, thickness: float) -> Optional[tuple]:
        """Pobierz stawkę cięcia z pricing_tables"""
        if not self.pricing_tables:
            return None
        
        cut_rate = self.pricing_tables.get_cutting_rate(material, thickness)
        if cut_rate:
            return (cut_rate.speed_mm_min, cut_rate.cost_per_meter)
        return None
    
    def estimate_contour_length(
        self,
        width_mm: float,
        height_mm: float,
        complexity_factor: float = 1.5
    ) -> float:
        """
        Oszacuj długość konturu na podstawie wymiarów.
        
        complexity_factor:
        - 1.0 = prosty prostokąt
        - 1.5 = typowy detal z otworami
        - 2.0+ = skomplikowany kontur
        """
        # Obwód prostokąta × współczynnik złożoności
        perimeter = 2 * (width_mm + height_mm)
        return perimeter * complexity_factor
    
    def calculate(
        self,
        input_data: PricingInput,
        margin_percent: Optional[float] = None,
        include_setup: bool = True
    ) -> PricingBreakdown:
        """
        Wykonaj pełną kalkulację ceny.
        
        Args:
            input_data: Dane wejściowe
            margin_percent: Marża (domyślnie self.default_margin)
            include_setup: Czy doliczyć koszty setup
            
        Returns:
            PricingBreakdown ze szczegółami
        """
        result = PricingBreakdown()
        margin = margin_percent if margin_percent is not None else self.default_margin
        
        # 1. Pobierz materiał (z pricing_tables jeśli dostępne)
        material = self.get_material(input_data.material_key, input_data.thickness_mm)
        if not material:
            logger.error(f"Material not found: {input_data.material_key}")
            return result
        
        # 2. Oblicz zużycie materiału
        # Powierzchnia detalu [m²]
        part_area_m2 = (input_data.width_mm * input_data.height_mm) / 1_000_000
        
        # Całkowita powierzchnia z uwzględnieniem arkuszy
        if input_data.sheets_used > 0 and input_data.sheet_utilization > 0:
            # Użyj rzeczywistego zużycia z nestingu
            total_area_m2 = part_area_m2 * input_data.quantity / input_data.sheet_utilization
        else:
            # Szacuj z naddatkiem 30%
            total_area_m2 = part_area_m2 * input_data.quantity * 1.3
        
        # Waga materiału [kg]
        thickness_m = input_data.thickness_mm / 1000
        volume_m3 = total_area_m2 * thickness_m
        weight_kg = volume_m3 * material.density_kg_m3
        
        result.material_weight_kg = weight_kg
        result.material_cost = weight_kg * material.price_per_kg
        
        # 3. Oblicz koszt cięcia
        # Długość konturu
        if input_data.contour_length_mm:
            contour_length = input_data.contour_length_mm
        else:
            contour_length = self.estimate_contour_length(
                input_data.width_mm,
                input_data.height_mm
            )
        
        total_cutting_length = contour_length * input_data.quantity
        result.cutting_length_m = total_cutting_length / 1000
        
        # Sprawdź czy mamy cennik cięcia z XLSX
        xlsx_cutting = self.get_cutting_rate_from_tables(input_data.material_key, input_data.thickness_mm)
        
        if xlsx_cutting:
            # Użyj ceny za metr z XLSX
            cutting_speed, cost_per_meter = xlsx_cutting
            result.cutting_cost = result.cutting_length_m * cost_per_meter
            
            # Oblicz czas cięcia dla informacji
            if cutting_speed > 0:
                result.cutting_time_min = total_cutting_length / cutting_speed
            else:
                result.cutting_time_min = result.cutting_length_m * 0.5  # Fallback
        else:
            # Fallback - użyj starej metody (czas × stawka)
            cutting_speed = self.cutting_rates.get_rate(
                input_data.thickness_mm,
                material.type
            ) * material.cutting_speed_factor
            
            # Czas cięcia [min]
            if cutting_speed > 0:
                cutting_time = total_cutting_length / cutting_speed
            else:
                cutting_time = total_cutting_length / 1000  # Fallback
            
            # Dodaj czas przebić (ok. 0.5-2s na przebicie zależnie od grubości)
            piercing_time = input_data.piercing_count * input_data.quantity * (0.5 + input_data.thickness_mm * 0.1) / 60
            
            result.cutting_time_min = cutting_time + piercing_time
            result.cutting_cost = (result.cutting_time_min / 60) * self.machine_rates.laser_rate_per_hour * material.cutting_cost_factor
        
        # 4. Koszt gięcia
        if input_data.bending_count > 0:
            total_bends = input_data.bending_count * input_data.quantity
            result.bending_cost = total_bends * self.machine_rates.bending_per_bend
            # Minimalny czas gięcia - 5 min na setup + czas gięcia
            bending_time = 5 + total_bends * 0.5  # 0.5 min na gięcie
            result.bending_cost = max(
                result.bending_cost,
                (bending_time / 60) * self.machine_rates.bending_rate_per_hour
            )
        
        # 5. Koszty setup
        if include_setup:
            result.setup_cost = self.machine_rates.setup_cost
            result.programming_cost = self.machine_rates.programming_per_part
        
        # 6. Suma i marża
        result.subtotal = (
            result.material_cost +
            result.cutting_cost +
            result.bending_cost +
            result.setup_cost +
            result.programming_cost
        )
        
        result.margin_percent = margin * 100
        result.margin_value = result.subtotal * margin
        result.total = result.subtotal + result.margin_value
        
        # Minimum
        result.total = max(result.total, self.machine_rates.min_order_value)
        
        # Cena jednostkowa
        result.unit_price = result.total / input_data.quantity if input_data.quantity > 0 else result.total
        
        return result
    
    def quick_estimate(
        self,
        width_mm: float,
        height_mm: float,
        thickness_mm: float,
        quantity: int,
        material_key: str = "S235"
    ) -> float:
        """
        Szybka wycena - zwraca tylko cenę końcową.
        """
        result = self.calculate(PricingInput(
            part_name="Quick",
            quantity=quantity,
            width_mm=width_mm,
            height_mm=height_mm,
            thickness_mm=thickness_mm,
            material_key=material_key
        ))
        return result.total


# ============================================================
# CLI Test
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("="*60)
    print("TEST KALKULATORA CEN")
    print("="*60)
    
    calc = PricingCalculator()
    
    # Test 1: Prosty detal ze stali czarnej
    print("\n--- Test 1: Stal czarna S235, 3mm ---")
    result = calc.calculate(PricingInput(
        part_name="Płyta testowa",
        quantity=10,
        width_mm=300,
        height_mm=200,
        thickness_mm=3.0,
        material_key="S235"
    ))
    print(result)
    
    # Test 2: Stal nierdzewna z gięciem
    print("\n--- Test 2: INOX 304, 2mm + gięcie ---")
    result = calc.calculate(PricingInput(
        part_name="Obudowa",
        quantity=5,
        width_mm=400,
        height_mm=250,
        thickness_mm=2.0,
        material_key="INOX304",
        bending_count=4
    ))
    print(result)
    
    # Test 3: Duża ilość małych detali
    print("\n--- Test 3: Małe detale, duża ilość ---")
    result = calc.calculate(PricingInput(
        part_name="Wspornik",
        quantity=100,
        width_mm=50,
        height_mm=80,
        thickness_mm=2.0,
        material_key="DC01",
        sheet_utilization=0.75  # 75% wykorzystanie z nestingu
    ))
    print(result)
    
    # Test szybkiej wyceny
    print("\n--- Quick estimate ---")
    price = calc.quick_estimate(200, 150, 2.0, 20, "S235")
    print(f"Szybka wycena: {price:.2f} PLN")
