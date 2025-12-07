"""
NewERP - Cost Engine
====================
Zunifikowany silnik kosztów dla zamówień/ofert cięcia laserowego.

Jedno źródło prawdy dla wszystkich kalkulacji kosztów - zgodne z costing.md.

Składniki kosztu:
1. Materiał: koszt arkusza(ów) alokowany na detale wg occupied_area
2. Cięcie: PLN/m × długość cięcia (wariant A) lub czas × PLN/h (wariant B)
3. Przebicia (piercing): liczba konturów × koszt przebicia
4. Usuwanie folii: dla INOX ≤5mm - powierzchnia × stawka
5. Gięcie: ilość gięć × stawka
6. Koszty operacyjne: per arkusz (domyślnie 40 PLN)
7. Koszty per zlecenie: technologia, opakowania, transport
8. Narzut procentowy
"""

import math
import time
import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Optional, Callable, Tuple
from dataclasses import dataclass, field

# Import from cost_models - single source of truth
from orders.cost_models import AllocationModel, CostVariant, CostParams

logger = logging.getLogger(__name__)


# Domyślne stawki (fallback gdy brak cenników)
DEFAULT_RATES = {
    'cutting_pln_per_m': {  # PLN/m cięcia
        'steel': {1.0: 0.8, 2.0: 1.0, 3.0: 1.2, 4.0: 1.5, 5.0: 1.8, 6.0: 2.2, 8.0: 3.0, 10.0: 4.0},
        'stainless': {1.0: 1.5, 2.0: 2.0, 3.0: 2.8, 4.0: 3.5, 5.0: 4.5, 6.0: 5.5, 8.0: 7.0, 10.0: 9.0},
        'aluminum': {1.0: 1.2, 2.0: 1.5, 3.0: 2.0, 4.0: 2.5, 5.0: 3.2, 6.0: 4.0, 8.0: 5.0, 10.0: 6.5},
    },
    'pierce_pln': {  # PLN/przebicie
        'steel': {1.0: 0.10, 2.0: 0.15, 3.0: 0.20, 4.0: 0.30, 5.0: 0.40, 6.0: 0.55, 8.0: 0.80, 10.0: 1.10},
        'stainless': {1.0: 0.15, 2.0: 0.25, 3.0: 0.40, 4.0: 0.60, 5.0: 0.85, 6.0: 1.10, 8.0: 1.50, 10.0: 2.00},
        'aluminum': {1.0: 0.12, 2.0: 0.18, 3.0: 0.25, 4.0: 0.35, 5.0: 0.50, 6.0: 0.70, 8.0: 1.00, 10.0: 1.40},
    },
    'foil_pln_per_m': 0.20,  # PLN/m usuwania folii (cięcie + grawer)
    'bending_pln_per_bend': 3.0,  # PLN/gięcie
    'engraving_pln_per_m': 2.5,  # PLN/m graweru
    'operational_per_sheet': 40.0,  # PLN/arkusz operacyjne
    'machine_pln_per_hour': 750.0,  # PLN/h (wariant B)
    'buffer_factor': 1.25,  # +25% bufor (wariant B)
}

# Gęstości materiałów [kg/m³]
MATERIAL_DENSITIES = {
    'S235': 7850, 'S355': 7850, 'DC01': 7850, 'DC04': 7850,
    '1.4301': 7900, '1.4404': 7950, 'INOX': 7900, 'INOX304': 7900,
    'ALU': 2700, 'ALUMINIUM': 2700, 'AL': 2700,
}

# Mapowanie materiałów na typy do cenników
MATERIAL_TYPE_MAP = {
    'S235': 'steel', 'S355': 'steel', 'DC01': 'steel', 'DC04': 'steel', 'FE': 'steel',
    '1.4301': 'stainless', '1.4404': 'stainless', 'INOX': 'stainless', 'INOX304': 'stainless', 'INOX316': 'stainless',
    'ALU': 'aluminum', 'AL': 'aluminum', 'ALUMINIUM': 'aluminum',
}


# ============================================================
# DATA CLASSES
# ============================================================

# CostParams imported from cost_models.py - single source of truth


@dataclass
class PartCostResult:
    """Wynik kalkulacji kosztu pojedynczej części"""
    part_name: str
    quantity: int = 1

    # Składniki kosztów jednostkowych
    material_cost: Decimal = Decimal('0.00')
    cutting_cost: Decimal = Decimal('0.00')   # L+M bez materiału
    engraving_cost: Decimal = Decimal('0.00')
    foil_cost: Decimal = Decimal('0.00')
    piercing_cost: Decimal = Decimal('0.00')
    bending_cost: Decimal = Decimal('0.00')
    additional_cost: Decimal = Decimal('0.00')

    # Flagi ręcznej edycji
    is_manual_lm: bool = False
    is_manual_bending: bool = False

    @property
    def lm_cost(self) -> Decimal:
        """Koszt L+M (cięcie + grawer + materiał)"""
        return self.cutting_cost + self.engraving_cost + self.material_cost

    @property
    def total_unit(self) -> Decimal:
        """Całkowity koszt jednostkowy (bez materiału - ten jest alokowany)"""
        return (
            self.cutting_cost +
            self.engraving_cost +
            self.foil_cost +
            self.piercing_cost +
            self.bending_cost +
            self.additional_cost
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def total_with_material(self) -> Decimal:
        """Całkowity koszt jednostkowy z materiałem"""
        return (self.total_unit + self.material_cost).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

    @property
    def total_line(self) -> Decimal:
        """Całkowity koszt linii (qty × total_with_material)"""
        return (self.total_with_material * self.quantity).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )


@dataclass
class OrderCostResult:
    """Wynik kalkulacji kosztów całego zamówienia"""
    # Koszty produkcji (suma z detali)
    total_material: Decimal = Decimal('0.00')
    total_cutting: Decimal = Decimal('0.00')
    total_engraving: Decimal = Decimal('0.00')
    total_foil: Decimal = Decimal('0.00')
    total_piercing: Decimal = Decimal('0.00')
    total_bending: Decimal = Decimal('0.00')
    total_additional: Decimal = Decimal('0.00')
    total_operational: Decimal = Decimal('0.00')

    # Suma produkcji
    production_subtotal: Decimal = Decimal('0.00')

    # Koszty per zlecenie
    tech_cost: Decimal = Decimal('0.00')
    packaging_cost: Decimal = Decimal('0.00')
    transport_cost: Decimal = Decimal('0.00')

    # Narzut
    markup_amount: Decimal = Decimal('0.00')
    markup_percent: Decimal = Decimal('0.00')

    # RAZEM
    grand_total: Decimal = Decimal('0.00')

    # Statystyki
    total_parts: int = 0
    total_quantity: int = 0
    total_sheets: int = 0
    average_efficiency: float = 0.0

    # Czas obliczeń
    calculation_time_ms: float = 0.0


# ============================================================
# COST ENGINE
# ============================================================

class CostEngine:
    """
    Zunifikowany silnik kosztów - jedno źródło prawdy.

    Obsługuje:
    - Kalkulację kosztów części (L+M, piercing, foil, bending)
    - Alokację kosztów materiału z arkusza
    - Koszty operacyjne per arkusz
    - Koszty per zlecenie
    - Narzut procentowy
    - Auto-recalculation callbacks

    Wymagania:
    - Przeliczenie < 0.1s dla 100 części
    """

    def __init__(self, pricing_tables=None):
        """
        Args:
            pricing_tables: Opcjonalny obiekt PricingTables z cenników
        """
        self.pricing_tables = pricing_tables
        self._callbacks: List[Callable] = []
        self._cache: Dict = {}

        # Załaduj cenniki jeśli nie podano
        if not self.pricing_tables:
            self._load_pricing_tables()

    def _load_pricing_tables(self):
        """Załaduj cenniki z modułu pricing"""
        try:
            from quotations.pricing.pricing_tables import get_pricing_tables
            self.pricing_tables = get_pricing_tables()
            logger.info("[CostEngine] Pricing tables loaded")
        except Exception as e:
            logger.warning(f"[CostEngine] Could not load pricing tables: {e}")
            self.pricing_tables = None

    # ============================================================
    # CALLBACKS
    # ============================================================

    def on_change(self, callback: Callable):
        """Zarejestruj callback wywoływany przy zmianie"""
        self._callbacks.append(callback)

    def notify_change(self):
        """Wywołaj callbacki"""
        for cb in self._callbacks:
            try:
                cb()
            except Exception as e:
                logger.error(f"[CostEngine] Callback error: {e}")

    # ============================================================
    # RATE LOOKUPS
    # ============================================================

    def _get_material_type(self, material: str) -> str:
        """Mapuj materiał na typ (steel/stainless/aluminum)"""
        material = material.upper().strip()

        # Bezpośrednie mapowanie
        if material in MATERIAL_TYPE_MAP:
            return MATERIAL_TYPE_MAP[material]

        # Heurystyka
        if material.startswith('1.4') or 'INOX' in material:
            return 'stainless'
        if material in ['AL', 'ALU'] or 'ALUMIN' in material:
            return 'aluminum'

        return 'steel'

    def _get_density(self, material: str) -> float:
        """Pobierz gęstość materiału [kg/m³]"""
        material = material.upper().strip()
        return MATERIAL_DENSITIES.get(material, 7850)

    def _get_cutting_rate(self, material: str, thickness: float) -> float:
        """Pobierz cenę cięcia [PLN/m]"""
        # Najpierw próbuj z PricingTables
        if self.pricing_tables:
            try:
                mat_type = self._get_material_type(material)
                rate = self.pricing_tables.get_cutting_rate(mat_type, thickness)
                if rate:
                    return rate.cost_per_meter
            except Exception:
                pass

        # Fallback do DEFAULT_RATES
        mat_type = self._get_material_type(material)
        rates = DEFAULT_RATES['cutting_pln_per_m'].get(mat_type, DEFAULT_RATES['cutting_pln_per_m']['steel'])

        # Znajdź najbliższą grubość
        thicknesses = sorted(rates.keys())
        closest = min(thicknesses, key=lambda x: abs(x - thickness))
        return rates[closest]

    def _get_pierce_rate(self, material: str, thickness: float) -> float:
        """Pobierz cenę przebicia [PLN/szt]"""
        mat_type = self._get_material_type(material)
        rates = DEFAULT_RATES['pierce_pln'].get(mat_type, DEFAULT_RATES['pierce_pln']['steel'])

        thicknesses = sorted(rates.keys())
        closest = min(thicknesses, key=lambda x: abs(x - thickness))
        return rates[closest]

    def _get_material_price(self, material: str, thickness: float) -> float:
        """Pobierz cenę materiału [PLN/kg]"""
        if self.pricing_tables:
            try:
                price = self.pricing_tables.get_material_price(material, thickness)
                if price:
                    return price.price_per_kg
            except Exception:
                pass

        # Fallback
        mat_type = self._get_material_type(material)
        default_prices = {'steel': 5.0, 'stainless': 18.0, 'aluminum': 12.0}
        return default_prices.get(mat_type, 5.0)

    def _get_bending_rate(self, thickness: float) -> float:
        """Pobierz cenę gięcia [PLN/gięcie]"""
        if self.pricing_tables:
            try:
                rate = self.pricing_tables.get_bending_rate(thickness)
                if rate:
                    return rate.cost_per_bend
            except Exception:
                pass

        return DEFAULT_RATES['bending_pln_per_bend']

    def _should_include_foil(self, material: str, thickness: float) -> bool:
        """Sprawdź czy włączyć usuwanie folii (INOX ≤5mm)"""
        mat_type = self._get_material_type(material)
        return mat_type == 'stainless' and thickness <= 5.0

    def _get_foil_rate(self) -> float:
        """
        Pobierz stawkę usuwania folii [PLN/m].

        Najpierw próbuje z Supabase (cost_config.foil_cost_per_meter),
        fallback do DEFAULT_RATES.
        """
        # Sprawdź cache
        if hasattr(self, '_foil_rate_cache') and self._foil_rate_cache is not None:
            return self._foil_rate_cache

        # Próbuj pobrać z Supabase
        try:
            from core.supabase_client import get_supabase_client
            client = get_supabase_client()
            response = client.table('cost_config').select('config_value').eq(
                'config_key', 'foil_cost_per_meter'
            ).limit(1).execute()

            if response.data:
                rate = float(response.data[0]['config_value'])
                self._foil_rate_cache = rate
                logger.debug(f"[CostEngine] Foil rate from Supabase: {rate} PLN/m")
                return rate
        except Exception as e:
            logger.warning(f"[CostEngine] Could not fetch foil rate from Supabase: {e}")

        # Fallback do DEFAULT_RATES
        self._foil_rate_cache = DEFAULT_RATES['foil_pln_per_m']
        return self._foil_rate_cache

    # ============================================================
    # PART COST CALCULATION
    # ============================================================

    def calculate_part_cost(
        self,
        part_data: Dict,
        params: CostParams,
        sheet_cost_allocated: Decimal = Decimal('0.00')
    ) -> PartCostResult:
        """
        Oblicz koszty dla pojedynczej części.

        Args:
            part_data: Dane części z polami:
                - name, material, thickness, quantity
                - cutting_len (mm), engraving_len (mm)
                - pierce_count / piercing_count
                - bends / bends_count
                - width, height (mm) - do obliczenia wagi
                - weight (kg) - opcjonalnie jeśli znana
            params: Parametry kalkulacji
            sheet_cost_allocated: Alokowany koszt materiału z arkusza

        Returns:
            PartCostResult z wszystkimi składnikami kosztów
        """
        result = PartCostResult(
            part_name=part_data.get('name', ''),
            quantity=int(part_data.get('quantity', 1) or 1)
        )

        material = str(part_data.get('material', '')).upper()
        thickness = float(part_data.get('thickness', 0) or 0)

        # === KOSZT MATERIAŁU ===
        if params.include_material:
            if sheet_cost_allocated > 0:
                # Użyj alokowanego kosztu z arkusza
                result.material_cost = sheet_cost_allocated
            else:
                # Oblicz z wagi
                weight_kg = self._get_part_weight(part_data)
                mat_price = self._get_material_price(material, thickness)
                result.material_cost = Decimal(str(weight_kg * mat_price)).quantize(
                    Decimal('0.01'), rounding=ROUND_HALF_UP
                )

        # === KOSZT CIĘCIA ===
        if params.include_cutting:
            cutting_len_mm = float(part_data.get('cutting_len', 0) or 0)
            cutting_len_m = cutting_len_mm / 1000.0

            cutting_rate = self._get_cutting_rate(material, thickness)
            result.cutting_cost = Decimal(str(cutting_len_m * cutting_rate)).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )

        # === KOSZT GRAWERU ===
        engraving_len_mm = float(part_data.get('engraving_len', 0) or 0)
        if engraving_len_mm > 0:
            engraving_len_m = engraving_len_mm / 1000.0
            engraving_rate = DEFAULT_RATES['engraving_pln_per_m']
            result.engraving_cost = Decimal(str(engraving_len_m * engraving_rate)).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )

        # === KOSZT PRZEBIĆ (PIERCING) ===
        if params.include_piercing:
            pierce_count = int(part_data.get('pierce_count', part_data.get('piercing_count', 1)) or 1)
            pierce_rate = self._get_pierce_rate(material, thickness)
            result.piercing_cost = Decimal(str(pierce_count * pierce_rate)).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )

        # === KOSZT USUWANIA FOLII ===
        # Obliczany na podstawie długości cięcia + graweru [PLN/m]
        if params.include_foil_removal and self._should_include_foil(material, thickness):
            cutting_len_mm = float(part_data.get('cutting_len', 0) or 0)
            engraving_len_mm = float(part_data.get('engraving_len', 0) or 0)
            total_len_m = (cutting_len_mm + engraving_len_mm) / 1000.0

            foil_rate = self._get_foil_rate()  # PLN/m z Supabase lub DEFAULT
            result.foil_cost = Decimal(str(total_len_m * foil_rate)).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )

        # === KOSZT GIĘCIA ===
        bends = int(part_data.get('bends', part_data.get('bends_count', 0)) or 0)
        if bends > 0:
            bending_rate = self._get_bending_rate(thickness)
            result.bending_cost = Decimal(str(bends * bending_rate)).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )

        # === KOSZTY DODATKOWE ===
        additional = float(part_data.get('additional', 0) or 0)
        result.additional_cost = Decimal(str(additional)).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )

        # === FLAGI MANUALNE ===
        result.is_manual_lm = part_data.get('_manual_lm_cost', False)
        result.is_manual_bending = part_data.get('_manual_bending_cost', False)

        return result

    def _get_part_weight(self, part_data: Dict) -> float:
        """Oblicz wagę części [kg]"""
        # Jeśli waga podana bezpośrednio
        weight = float(part_data.get('weight', 0) or 0)
        if weight > 0:
            return weight

        # Oblicz z wymiarów (bounding box)
        width_mm = float(part_data.get('width', 0) or 0)
        height_mm = float(part_data.get('height', 0) or 0)
        thickness_mm = float(part_data.get('thickness', 0) or 0)
        material = str(part_data.get('material', '')).upper()

        if width_mm <= 0 or height_mm <= 0 or thickness_mm <= 0:
            return 0.0

        # 100% powierzchni bounding box
        area_m2 = (width_mm * height_mm) / 1_000_000
        volume_m3 = area_m2 * (thickness_mm / 1000.0)
        density = self._get_density(material)

        return volume_m3 * density

    # ============================================================
    # ALLOCATION MODELS
    # ============================================================

    def allocate_material_cost(
        self,
        sheet_cost: Decimal,
        parts: List[Dict],
        model: AllocationModel
    ) -> List[Decimal]:
        """
        Alokuj koszt arkusza na części wg modelu.

        Args:
            sheet_cost: Całkowity koszt arkusza
            parts: Lista części z 'occupied_area' lub 'width'/'height'
            model: Model alokacji

        Returns:
            Lista kosztów materiału dla każdej części
        """
        if not parts:
            return []

        n_parts = len(parts)

        if model == AllocationModel.PER_UNIT:
            # Prostokąt otaczający: równo na każdą część
            cost_per_part = sheet_cost / n_parts
            return [cost_per_part.quantize(Decimal('0.01')) for _ in parts]

        elif model == AllocationModel.PER_SHEET:
            # Na arkusz: każdy detal ponosi pełny koszt
            return [sheet_cost.quantize(Decimal('0.01')) for _ in parts]

        else:  # PROPORTIONAL (domyślny)
            # Proporcjonalnie do occupied_area
            areas = []
            for p in parts:
                area = float(p.get('occupied_area', 0) or 0)
                if area <= 0:
                    # Fallback: bounding box
                    w = float(p.get('width', 0) or 0)
                    h = float(p.get('height', 0) or 0)
                    area = w * h
                areas.append(area)

            total_area = sum(areas)
            if total_area <= 0:
                # Fallback do równego podziału
                cost_per_part = sheet_cost / n_parts
                return [cost_per_part.quantize(Decimal('0.01')) for _ in parts]

            return [
                (sheet_cost * Decimal(str(area / total_area))).quantize(Decimal('0.01'))
                for area in areas
            ]

    # ============================================================
    # ORDER COST CALCULATION
    # ============================================================

    def calculate_order_cost(
        self,
        parts: List[Dict],
        params: CostParams,
        nesting_data: Dict = None
    ) -> OrderCostResult:
        """
        Oblicz koszty całego zamówienia.

        Wymaganie: < 0.1s dla 100 części

        Args:
            parts: Lista danych części
            params: Parametry kalkulacji
            nesting_data: Opcjonalne dane nestingu z arkuszami

        Returns:
            OrderCostResult z pełnym podsumowaniem
        """
        start_time = time.perf_counter()

        result = OrderCostResult()
        result.total_parts = len(parts)
        result.total_quantity = sum(int(p.get('quantity', 1) or 1) for p in parts)

        # === ALOKACJA KOSZTÓW MATERIAŁU ===
        if nesting_data and 'sheets' in nesting_data:
            # Alokuj z arkuszy
            sheets = nesting_data['sheets']
            result.total_sheets = len(sheets)

            # Suma efektywności
            efficiencies = [s.get('efficiency', 0) or s.get('utilization', 0) for s in sheets]
            result.average_efficiency = sum(efficiencies) / len(efficiencies) if efficiencies else 0

            # Dla uproszczenia: alokuj całkowity koszt materiału proporcjonalnie
            total_sheet_cost = sum(Decimal(str(s.get('material_cost', 0))) for s in sheets)

            material_allocations = self.allocate_material_cost(
                total_sheet_cost, parts, params.allocation_model
            )
        else:
            # Brak nestingu - oblicz materiał z wag
            material_allocations = [Decimal('0.00')] * len(parts)
            result.total_sheets = 1  # Zakładamy 1 arkusz

        # === OBLICZ KOSZTY KAŻDEJ CZĘŚCI ===
        for idx, part_data in enumerate(parts):
            qty = int(part_data.get('quantity', 1) or 1)
            mat_alloc = material_allocations[idx] if idx < len(material_allocations) else Decimal('0.00')

            # Sprawdź czy manualne koszty
            if part_data.get('_manual_lm_cost'):
                # Użyj ręcznej wartości L+M
                lm_cost = Decimal(str(part_data.get('lm_cost', 0) or 0))
                result.total_cutting += lm_cost * qty
            else:
                part_cost = self.calculate_part_cost(part_data, params, mat_alloc)
                result.total_material += part_cost.material_cost * qty
                result.total_cutting += part_cost.cutting_cost * qty
                result.total_engraving += part_cost.engraving_cost * qty
                result.total_foil += part_cost.foil_cost * qty
                result.total_piercing += part_cost.piercing_cost * qty

            # Gięcie
            if part_data.get('_manual_bending_cost'):
                bending = Decimal(str(part_data.get('bending_cost', 0) or 0))
            else:
                bends = int(part_data.get('bends', 0) or 0)
                thickness = float(part_data.get('thickness', 0) or 0)
                bending_rate = self._get_bending_rate(thickness)
                bending = Decimal(str(bends * bending_rate))

            result.total_bending += bending * qty

            # Dodatkowe
            additional = Decimal(str(part_data.get('additional', 0) or 0))
            result.total_additional += additional * qty

        # === KOSZTY OPERACYJNE ===
        if params.include_operational:
            result.total_operational = Decimal(str(params.operational_per_sheet)) * result.total_sheets

        # === SUMA PRODUKCJI ===
        result.production_subtotal = (
            result.total_material +
            result.total_cutting +
            result.total_engraving +
            result.total_foil +
            result.total_piercing +
            result.total_bending +
            result.total_additional +
            result.total_operational
        ).quantize(Decimal('0.01'))

        # === KOSZTY PER ZLECENIE ===
        result.tech_cost = Decimal(str(params.tech_cost))
        result.packaging_cost = Decimal(str(params.packaging_cost))
        result.transport_cost = Decimal(str(params.transport_cost))

        # === NARZUT ===
        result.markup_percent = Decimal(str(params.markup_percent))
        subtotal_for_markup = (
            result.production_subtotal +
            result.tech_cost +
            result.packaging_cost +
            result.transport_cost
        )
        result.markup_amount = (subtotal_for_markup * result.markup_percent / 100).quantize(
            Decimal('0.01')
        )

        # === GRAND TOTAL ===
        result.grand_total = (
            subtotal_for_markup + result.markup_amount
        ).quantize(Decimal('0.01'))

        # === CZAS OBLICZEŃ ===
        elapsed = (time.perf_counter() - start_time) * 1000
        result.calculation_time_ms = elapsed

        if elapsed > 100:
            logger.warning(f"[CostEngine] Calculation too slow: {elapsed:.1f}ms for {len(parts)} parts")
        else:
            logger.debug(f"[CostEngine] Calculated in {elapsed:.1f}ms for {len(parts)} parts")

        return result

    # ============================================================
    # RECALCULATION
    # ============================================================

    def recalculate_all(
        self,
        parts: List[Dict],
        params: CostParams,
        nesting_data: Dict = None
    ) -> Tuple[List[Dict], OrderCostResult]:
        """
        Przelicz wszystkie części i zwróć zaktualizowane dane.

        Args:
            parts: Lista danych części (modyfikowana in-place)
            params: Parametry kalkulacji
            nesting_data: Dane nestingu

        Returns:
            (zaktualizowane_części, wynik_kosztów)
        """
        start_time = time.perf_counter()

        # Oblicz koszty każdej części
        for part in parts:
            if not part.get('_manual_lm_cost'):
                # Oblicz L+M
                part_cost = self.calculate_part_cost(part, params)
                part['lm_cost'] = float(part_cost.lm_cost)
                part['cutting_cost'] = float(part_cost.cutting_cost)
                part['piercing_cost'] = float(part_cost.piercing_cost)
                part['foil_cost'] = float(part_cost.foil_cost)

            if not part.get('_manual_bending_cost'):
                # Oblicz gięcie
                bends = int(part.get('bends', 0) or 0)
                thickness = float(part.get('thickness', 0) or 0)
                bending_rate = self._get_bending_rate(thickness)
                part['bending_cost'] = bends * bending_rate

            # Total
            lm = float(part.get('lm_cost', 0) or 0)
            bending = float(part.get('bending_cost', 0) or 0)
            additional = float(part.get('additional', 0) or 0)
            part['total_unit'] = lm + bending + additional

        # Oblicz podsumowanie
        order_cost = self.calculate_order_cost(parts, params, nesting_data)

        elapsed = (time.perf_counter() - start_time) * 1000
        logger.debug(f"[CostEngine] Full recalc in {elapsed:.1f}ms")

        # Wywołaj callbacki
        self.notify_change()

        return parts, order_cost


# ============================================================
# SINGLETON
# ============================================================

_cost_engine: Optional[CostEngine] = None


def get_cost_engine() -> CostEngine:
    """Pobierz globalną instancję CostEngine"""
    global _cost_engine
    if _cost_engine is None:
        _cost_engine = CostEngine()
    return _cost_engine


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    engine = CostEngine()

    # Test data
    test_parts = [
        {
            'name': '11-066258_INOX_3mm',
            'material': '1.4301',
            'thickness': 3.0,
            'quantity': 2,
            'width': 120,
            'height': 120,
            'cutting_len': 500,
            'pierce_count': 1,
            'bends': 0,
        },
        {
            'name': '11-066253_INOX_3mm',
            'material': '1.4301',
            'thickness': 3.0,
            'quantity': 79,
            'width': 77,
            'height': 71,
            'cutting_len': 300,
            'pierce_count': 1,
            'bends': 0,
        },
    ]

    params = CostParams(
        include_material=True,
        include_cutting=True,
        include_foil_removal=True,
        include_piercing=True,
        operational_per_sheet=40.0,
        tech_cost=50.0,
        packaging_cost=100.0,
    )

    # Test
    parts, result = engine.recalculate_all(test_parts, params)

    print("\n=== WYNIKI ===")
    print(f"Materiał:     {result.total_material:>10.2f} PLN")
    print(f"Cięcie:       {result.total_cutting:>10.2f} PLN")
    print(f"Folia:        {result.total_foil:>10.2f} PLN")
    print(f"Piercing:     {result.total_piercing:>10.2f} PLN")
    print(f"Operacyjne:   {result.total_operational:>10.2f} PLN")
    print(f"---")
    print(f"Suma prod.:   {result.production_subtotal:>10.2f} PLN")
    print(f"+ Technologia:{result.tech_cost:>10.2f} PLN")
    print(f"+ Opakowania: {result.packaging_cost:>10.2f} PLN")
    print(f"---")
    print(f"RAZEM:        {result.grand_total:>10.2f} PLN")
    print(f"\nCzas obliczeń: {result.calculation_time_ms:.2f}ms")
