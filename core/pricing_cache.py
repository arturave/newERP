"""
Pricing Data Cache
==================
Centralna pamiec podreczna danych cenowych z Supabase.

Thread-safe singleton z asynchronicznym ladowaniem przy starcie aplikacji.
Zastepuje PricingTables (XLSX) jako jedyne zrodlo danych cenowych.

Uzycie:
    from core.pricing_cache import get_pricing_cache
    cache = get_pricing_cache()
    cache.load_async()  # Nieblokujace ladowanie w tle

    # Pobieranie stawek
    foil_rate = cache.get_foil_rate('stainless', 3.0)  # PLN/m
    pierce_rate = cache.get_piercing_rate('stainless', 3.0)  # PLN/szt
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Tuple, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Domyslne stawki (fallback gdy brak danych w Supabase)
DEFAULT_RATES = {
    'material_pln_per_kg': {
        'steel': 5.0,
        'stainless': 18.0,
        'aluminum': 12.0,
    },
    'cutting_pln_per_m': 2.50,
    'piercing_pln_per_pierce': 0.40,
    'foil_pln_per_m': 0.20,
    'bending_pln_per_bend': 3.0,
    'engraving_pln_per_m': 2.5,
}

# Mapowanie nazw materialow na typy
MATERIAL_TYPE_MAP = {
    # Stal
    'S235': 'steel', 'S355': 'steel', 'DC01': 'steel', 'DC03': 'steel',
    'DC04': 'steel', 'DX51D': 'steel', 'DX52D': 'steel', 'HARDOX': 'steel',
    # Stal nierdzewna
    '1.4301': 'stainless', '1.4307': 'stainless', '1.4404': 'stainless',
    '1.4541': 'stainless', '1.4571': 'stainless', 'INOX': 'stainless',
    'INOX304': 'stainless', 'INOX316': 'stainless',
    # Aluminium
    'AL': 'aluminum', 'ALU': 'aluminum', 'ALMG3': 'aluminum',
    '5754': 'aluminum', '5083': 'aluminum', '6082': 'aluminum',
}


@dataclass
class MaterialPriceRecord:
    """Rekord ceny materialu"""
    id: str
    material: str
    thickness: float
    price_per_kg: float
    format: str = '1500x3000'
    source: Optional[str] = None
    valid_from: Optional[str] = None


@dataclass
class CuttingPriceRecord:
    """Rekord ceny ciecia"""
    id: str
    material: str
    thickness: float
    gas: str
    price_per_meter: float
    cutting_speed: Optional[float] = None
    hour_price: Optional[float] = None
    valid_from: Optional[str] = None


@dataclass
class PiercingRateRecord:
    """Rekord stawki przebijania"""
    id: str
    material_type: str
    thickness: float
    pierce_time_s: float
    cost_per_pierce: float
    note: Optional[str] = None
    valid_from: Optional[str] = None


@dataclass
class FoilRateRecord:
    """Rekord stawki usuwania folii"""
    id: str
    material_type: str
    max_thickness: float
    removal_speed_m_min: float
    hourly_rate: float
    price_per_meter: float  # Obliczone: hourly_rate / (speed * 60) * 1.35
    auto_enable: bool = True
    note: Optional[str] = None
    valid_from: Optional[str] = None


class PricingDataCache:
    """
    Singleton cache danych cenowych z Supabase.

    Thread-safe z asynchronicznym ladowaniem.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._data_lock = threading.Lock()

        # Stan ladowania
        self._loaded = False
        self._loading = False
        self._load_error: Optional[str] = None
        self._last_load: Optional[datetime] = None

        # Callbacki na zakonczenie ladowania
        self._callbacks: List[Callable[[], None]] = []

        # Struktury danych - klucz to tuple (material, thickness) lub podobny
        self.material_prices: Dict[Tuple[str, float, str], MaterialPriceRecord] = {}
        self.cutting_prices: Dict[Tuple[str, float, str], CuttingPriceRecord] = {}
        self.piercing_rates: Dict[Tuple[str, float], PiercingRateRecord] = {}
        self.foil_rates: Dict[Tuple[str, float], FoilRateRecord] = {}

        # Supabase client (lazy init)
        self._client = None

        logger.info("[PricingCache] Zainicjalizowano cache cenowy")

    def _get_client(self):
        """Pobierz klienta Supabase (lazy init)"""
        if self._client is None:
            try:
                from core.supabase_client import get_supabase_client
                self._client = get_supabase_client()
            except Exception as e:
                logger.error(f"[PricingCache] Blad inicjalizacji klienta Supabase: {e}")
                self._client = None
        return self._client

    @property
    def is_loaded(self) -> bool:
        """Czy dane zostaly zaladowane"""
        return self._loaded

    @property
    def is_loading(self) -> bool:
        """Czy trwa ladowanie"""
        return self._loading

    def load_async(self, callback: Callable[[], None] = None) -> None:
        """
        Laduj dane asynchronicznie w tle.

        Args:
            callback: Opcjonalny callback po zakonczeniu ladowania
        """
        if callback:
            self._callbacks.append(callback)

        if self._loading:
            logger.debug("[PricingCache] Ladowanie juz trwa, pomijam")
            return

        if self._loaded:
            logger.debug("[PricingCache] Dane juz zaladowane")
            if callback:
                callback()
            return

        def load_thread():
            try:
                self._loading = True
                logger.info("[PricingCache] Rozpoczynam ladowanie danych cenowych z Supabase...")

                self._load_all_data()

                self._loaded = True
                self._load_error = None
                self._last_load = datetime.now()

                logger.info(f"[PricingCache] Zaladowano dane cenowe: "
                           f"{len(self.material_prices)} materialow, "
                           f"{len(self.cutting_prices)} cen ciecia, "
                           f"{len(self.piercing_rates)} stawek przebijania, "
                           f"{len(self.foil_rates)} stawek folii")

                # Wywolaj callbacki
                for cb in self._callbacks:
                    try:
                        cb()
                    except Exception as e:
                        logger.error(f"[PricingCache] Blad callbacka: {e}")
                self._callbacks.clear()

            except Exception as e:
                self._load_error = str(e)
                logger.error(f"[PricingCache] Blad ladowania danych: {e}")
            finally:
                self._loading = False

        thread = threading.Thread(target=load_thread, daemon=True, name="PricingCacheLoader")
        thread.start()

    def reload(self) -> None:
        """
        Przeladuj dane (synchronicznie).
        Wywolywane po zmianach w Ustawieniach.
        """
        logger.info("[PricingCache] Przeladowywanie danych cenowych...")

        with self._data_lock:
            self._loaded = False
            self.material_prices.clear()
            self.cutting_prices.clear()
            self.piercing_rates.clear()
            self.foil_rates.clear()

        try:
            self._load_all_data()
            self._loaded = True
            self._load_error = None
            self._last_load = datetime.now()
            logger.info("[PricingCache] Przeladowano dane cenowe")
        except Exception as e:
            self._load_error = str(e)
            logger.error(f"[PricingCache] Blad przeladowania: {e}")

    def _load_all_data(self) -> None:
        """Laduj wszystkie dane z Supabase"""
        client = self._get_client()
        if not client:
            raise RuntimeError("Brak polaczenia z Supabase")

        with self._data_lock:
            self._load_material_prices(client)
            self._load_cutting_prices(client)
            self._load_piercing_rates(client)
            self._load_foil_rates(client)

    def _load_material_prices(self, client) -> None:
        """Laduj ceny materialow"""
        try:
            response = client.table('material_prices').select('*').limit(5000).execute()
            for row in (response.data or []):
                key = (row['material'], float(row['thickness']), row.get('format', '1500x3000'))
                self.material_prices[key] = MaterialPriceRecord(
                    id=row['id'],
                    material=row['material'],
                    thickness=float(row['thickness']),
                    price_per_kg=float(row['price_per_kg']),
                    format=row.get('format', '1500x3000'),
                    source=row.get('source'),
                    valid_from=row.get('valid_from'),
                )
            logger.debug(f"[PricingCache] Zaladowano {len(self.material_prices)} cen materialow")
        except Exception as e:
            logger.warning(f"[PricingCache] Blad ladowania cen materialow: {e}")

    def _load_cutting_prices(self, client) -> None:
        """Laduj ceny ciecia"""
        try:
            response = client.table('cutting_prices').select('*').limit(5000).execute()
            for row in (response.data or []):
                key = (row['material'], float(row['thickness']), row.get('gas', 'N'))
                self.cutting_prices[key] = CuttingPriceRecord(
                    id=row['id'],
                    material=row['material'],
                    thickness=float(row['thickness']),
                    gas=row.get('gas', 'N'),
                    price_per_meter=float(row.get('price_per_meter', 0) or 0),
                    cutting_speed=float(row['cutting_speed']) if row.get('cutting_speed') else None,
                    hour_price=float(row['hour_price']) if row.get('hour_price') else None,
                    valid_from=row.get('valid_from'),
                )
            logger.debug(f"[PricingCache] Zaladowano {len(self.cutting_prices)} cen ciecia")
        except Exception as e:
            logger.warning(f"[PricingCache] Blad ladowania cen ciecia: {e}")

    def _load_piercing_rates(self, client) -> None:
        """Laduj stawki przebijania"""
        try:
            response = client.table('piercing_rates').select('*').limit(5000).execute()
            for row in (response.data or []):
                key = (row['material_type'], float(row['thickness']))
                self.piercing_rates[key] = PiercingRateRecord(
                    id=row['id'],
                    material_type=row['material_type'],
                    thickness=float(row['thickness']),
                    pierce_time_s=float(row.get('pierce_time_s', 0.5) or 0.5),
                    cost_per_pierce=float(row.get('cost_per_pierce', 0.10) or 0.10),
                    note=row.get('note'),
                    valid_from=row.get('valid_from'),
                )
            logger.debug(f"[PricingCache] Zaladowano {len(self.piercing_rates)} stawek przebijania")
        except Exception as e:
            logger.warning(f"[PricingCache] Blad ladowania stawek przebijania: {e}")

    def _load_foil_rates(self, client) -> None:
        """Laduj stawki usuwania folii (z widoku current_foil_rates)"""
        try:
            # Probuj widok z obliczonym price_per_meter
            try:
                response = client.table('current_foil_rates').select('*').limit(1000).execute()
            except:
                # Fallback do tabeli bazowej
                response = client.table('foil_removal_rates').select('*').limit(1000).execute()

            for row in (response.data or []):
                key = (row['material_type'], float(row.get('max_thickness', 5.0)))

                # Oblicz price_per_meter jesli nie ma
                hourly_rate = float(row.get('hourly_rate', 120) or 120)
                removal_speed = float(row.get('removal_speed_m_min', 15) or 15)
                price_per_meter = row.get('price_per_meter')

                if price_per_meter is None:
                    # Formula: hourly_rate / (speed * 60) * 1.35
                    price_per_meter = (hourly_rate / (removal_speed * 60)) * 1.35
                else:
                    price_per_meter = float(price_per_meter)

                self.foil_rates[key] = FoilRateRecord(
                    id=row['id'],
                    material_type=row['material_type'],
                    max_thickness=float(row.get('max_thickness', 5.0)),
                    removal_speed_m_min=removal_speed,
                    hourly_rate=hourly_rate,
                    price_per_meter=price_per_meter,
                    auto_enable=row.get('auto_enable', True),
                    note=row.get('note'),
                    valid_from=row.get('valid_from'),
                )
            logger.debug(f"[PricingCache] Zaladowano {len(self.foil_rates)} stawek folii")
        except Exception as e:
            logger.warning(f"[PricingCache] Blad ladowania stawek folii: {e}")

    # =========================================================================
    # GETTERY - metody pobierania stawek
    # =========================================================================

    def get_material_type(self, material: str) -> str:
        """Mapuj nazwe materialu na typ (steel/stainless/aluminum)"""
        material_upper = material.upper().strip()

        # Bezposrednie dopasowanie
        if material_upper in MATERIAL_TYPE_MAP:
            return MATERIAL_TYPE_MAP[material_upper]

        # Czesciowe dopasowanie
        for key, mat_type in MATERIAL_TYPE_MAP.items():
            if key in material_upper or material_upper in key:
                return mat_type

        # Domyslnie stal
        return 'steel'

    def get_material_price(self, material: str, thickness: float,
                           format: str = '1500x3000') -> Optional[float]:
        """
        Pobierz cene materialu [PLN/kg].

        Args:
            material: Nazwa materialu (np. '1.4301', 'S235')
            thickness: Grubosc [mm]
            format: Format arkusza (domyslnie '1500x3000')

        Returns:
            Cena PLN/kg lub None jesli brak danych
        """
        with self._data_lock:
            key = (material, thickness, format)
            if key in self.material_prices:
                return self.material_prices[key].price_per_kg

            # Probuj bez formatu
            for (mat, th, fmt), record in self.material_prices.items():
                if mat == material and abs(th - thickness) < 0.01:
                    return record.price_per_kg

            # Fallback do typu materialu
            mat_type = self.get_material_type(material)
            return DEFAULT_RATES['material_pln_per_kg'].get(mat_type)

    def get_cutting_price(self, material: str, thickness: float,
                          gas: str = 'N') -> Optional[float]:
        """
        Pobierz cene ciecia [PLN/m].

        Args:
            material: Nazwa materialu
            thickness: Grubosc [mm]
            gas: Typ gazu (N - azot, O2 - tlen)

        Returns:
            Cena PLN/m lub None
        """
        with self._data_lock:
            # Dokladne dopasowanie
            key = (material, thickness, gas)
            if key in self.cutting_prices:
                return self.cutting_prices[key].price_per_meter

            # Probuj bez gazu
            for (mat, th, g), record in self.cutting_prices.items():
                if mat == material and abs(th - thickness) < 0.01:
                    return record.price_per_meter

            # Szukaj najblizszej grubosci dla materialu
            closest_record = None
            min_diff = float('inf')
            for (mat, th, g), record in self.cutting_prices.items():
                if mat == material and abs(th - thickness) < min_diff:
                    min_diff = abs(th - thickness)
                    closest_record = record

            if closest_record:
                return closest_record.price_per_meter

            return DEFAULT_RATES['cutting_pln_per_m']

    def get_piercing_rate(self, material: str, thickness: float) -> Optional[float]:
        """
        Pobierz stawke przebijania [PLN/szt].

        Args:
            material: Nazwa materialu
            thickness: Grubosc [mm]

        Returns:
            Koszt PLN/przebicie lub None
        """
        mat_type = self.get_material_type(material)

        with self._data_lock:
            # Dokladne dopasowanie typu i grubosci
            key = (mat_type, thickness)
            if key in self.piercing_rates:
                return self.piercing_rates[key].cost_per_pierce

            # Szukaj najblizszej grubosci
            closest_record = None
            min_diff = float('inf')
            for (mtype, th), record in self.piercing_rates.items():
                if mtype == mat_type and abs(th - thickness) < min_diff:
                    min_diff = abs(th - thickness)
                    closest_record = record

            if closest_record:
                return closest_record.cost_per_pierce

            return DEFAULT_RATES['piercing_pln_per_pierce']

    def get_foil_rate(self, material: str, thickness: float) -> Optional[float]:
        """
        Pobierz stawke usuwania folii [PLN/m].

        UWAGA: Folia dotyczy tylko stali nierdzewnej (INOX) <= 5mm!

        Args:
            material: Nazwa materialu
            thickness: Grubosc [mm]

        Returns:
            Cena PLN/m lub None jesli nie dotyczy
        """
        mat_type = self.get_material_type(material)

        # Folia tylko dla stainless <= 5mm
        if mat_type != 'stainless' or thickness > 5.0:
            return None

        with self._data_lock:
            # Szukaj stawki dla max_thickness >= thickness
            best_record = None
            for (mtype, max_th), record in self.foil_rates.items():
                if mtype == mat_type and max_th >= thickness:
                    if best_record is None or max_th < best_record.max_thickness:
                        best_record = record

            if best_record:
                return best_record.price_per_meter

            return DEFAULT_RATES['foil_pln_per_m']

    def get_bending_rate(self, thickness: float) -> float:
        """
        Pobierz stawke giecia [PLN/giecie].

        TODO: Dodac tabele bending_rates do Supabase
        """
        return DEFAULT_RATES['bending_pln_per_bend']

    def get_engraving_rate(self) -> float:
        """Pobierz stawke grawerowania [PLN/m]"""
        return DEFAULT_RATES['engraving_pln_per_m']

    # =========================================================================
    # DEBUG / INFO
    # =========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Zwroc statystyki cache'a"""
        return {
            'loaded': self._loaded,
            'loading': self._loading,
            'last_load': self._last_load.isoformat() if self._last_load else None,
            'error': self._load_error,
            'material_prices_count': len(self.material_prices),
            'cutting_prices_count': len(self.cutting_prices),
            'piercing_rates_count': len(self.piercing_rates),
            'foil_rates_count': len(self.foil_rates),
        }

    def debug_print(self) -> None:
        """Wypisz zawartosc cache'a (debug)"""
        print(f"\n=== PricingDataCache Stats ===")
        print(f"Loaded: {self._loaded}, Loading: {self._loading}")
        print(f"Last load: {self._last_load}")
        print(f"Material prices: {len(self.material_prices)}")
        print(f"Cutting prices: {len(self.cutting_prices)}")
        print(f"Piercing rates: {len(self.piercing_rates)}")
        print(f"Foil rates: {len(self.foil_rates)}")

        if self.foil_rates:
            print("\nFoil rates (PLN/m):")
            for key, record in self.foil_rates.items():
                print(f"  {key}: {record.price_per_meter:.4f} PLN/m")


# Singleton getter
_pricing_cache_instance: Optional[PricingDataCache] = None


def get_pricing_cache() -> PricingDataCache:
    """
    Pobierz singleton PricingDataCache.

    Uzycie:
        cache = get_pricing_cache()
        cache.load_async()
        rate = cache.get_foil_rate('stainless', 3.0)
    """
    global _pricing_cache_instance
    if _pricing_cache_instance is None:
        _pricing_cache_instance = PricingDataCache()
    return _pricing_cache_instance


def reset_pricing_cache() -> None:
    """Reset singletona (do testow)"""
    global _pricing_cache_instance
    _pricing_cache_instance = None
