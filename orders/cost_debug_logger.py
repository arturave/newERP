"""
Cost Debug Logger - System logowania obliczen kosztow
======================================================
- Zapis do pliku logs/cost_debug_YYYY-MM-DD.log
- Wsparcie dla okna GUI z logami na zywo
- Szczegolowy rozklad obliczen kazdego skladnika kosztu
"""

import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Callable, Optional, Any
from dataclasses import dataclass
import threading

# Sciezka do logow
LOG_DIR = Path(__file__).parent.parent / "logs"


@dataclass
class CostCalculationEntry:
    """Pojedynczy wpis obliczenia kosztu"""
    timestamp: datetime
    part_name: str
    quantity: int
    material: str
    thickness: float
    width: float
    height: float
    components: Dict[str, Dict[str, Any]]
    total_lm: float


class CostDebugLogger:
    """
    Logger dla kalkulacji kosztow z pelnym rozkladem obliczen.

    Uzycie:
        logger = get_cost_debug_logger()
        logger.start_part("Part_001", qty=2, material="1.4301", thickness=3.0, width=100, height=50)
        logger.log_material(weight_kg=0.341, price_per_kg=18.0, cost=6.14, formula="...")
        logger.log_cutting(length_mm=500, price_per_m=2.8, cost=1.40)
        logger.log_engraving(length_mm=0, price_per_m=2.5, cost=0.0)
        logger.log_foil(area_m2=0.005, price_per_m2=5.0, cost=0.025, applicable=True)
        logger.end_part(total_lm=7.57)
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._initialized = True
        self._file_handler: Optional[logging.FileHandler] = None
        self._logger = logging.getLogger("cost_debug")
        self._callbacks: List[Callable[[str], None]] = []
        self._entries: List[CostCalculationEntry] = []
        self._current_part: Optional[Dict] = None
        self._paused = False

        self._setup_file_handler()

    def _setup_file_handler(self):
        """Konfiguruj handler pliku logowania"""
        LOG_DIR.mkdir(exist_ok=True)

        log_file = LOG_DIR / f"cost_debug_{date.today().isoformat()}.log"

        # Usun stare handlery
        self._logger.handlers.clear()

        # File handler
        self._file_handler = logging.FileHandler(log_file, encoding='utf-8')
        self._file_handler.setLevel(logging.DEBUG)
        self._file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(message)s',
            datefmt='%H:%M:%S'
        ))

        self._logger.addHandler(self._file_handler)
        self._logger.setLevel(logging.DEBUG)

        # Nie propaguj do root loggera
        self._logger.propagate = False

    def register_callback(self, callback: Callable[[str], None]):
        """Zarejestruj callback dla GUI (wywoływany przy kazdym logu)"""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unregister_callback(self, callback: Callable[[str], None]):
        """Wyrejestruj callback"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def pause(self):
        """Wstrzymaj logowanie do GUI (plik dalej dziala)"""
        self._paused = True

    def resume(self):
        """Wznow logowanie do GUI"""
        self._paused = False

    def _emit(self, message: str):
        """Wyslij log do pliku i callbackow"""
        # Zawsze do pliku
        self._logger.debug(message)

        # Do GUI tylko gdy nie wstrzymany
        if not self._paused:
            for callback in self._callbacks:
                try:
                    callback(message)
                except Exception:
                    pass

    def _separator(self, char: str = "=", length: int = 50):
        """Linia separatora"""
        return char * length

    # === API dla kalkulacji ===

    def start_part(self, part_name: str, quantity: int = 1,
                   material: str = "", thickness: float = 0,
                   width: float = 0, height: float = 0):
        """Rozpocznij logowanie dla czesci"""
        self._current_part = {
            'name': part_name,
            'quantity': quantity,
            'material': material,
            'thickness': thickness,
            'width': width,
            'height': height,
            'components': {}
        }

        self._emit(self._separator("="))
        self._emit(f"[PART] {part_name} (qty: {quantity})")
        self._emit(f"  Bounding Box: {width:.1f} x {height:.1f} mm")
        self._emit(f"  Material: {material}, thickness: {thickness:.1f}mm")
        self._emit(self._separator("-"))

    def log_material(self, weight_kg: float, price_per_kg: float, cost: float,
                     density: float = 7850, formula: str = ""):
        """Loguj obliczenie kosztu materialu"""
        if self._current_part is None:
            return

        self._current_part['components']['material'] = {
            'weight_kg': weight_kg,
            'price_per_kg': price_per_kg,
            'cost': cost,
            'density': density
        }

        part = self._current_part
        w, h, t = part['width'], part['height'], part['thickness']

        self._emit("  MATERIAL:")
        self._emit(f"    density = {density:.0f} kg/m3")
        self._emit(f"    weight = ({w:.1f} x {h:.1f})/1e6 x {t:.1f}/1000 x {density:.0f}")
        self._emit(f"    weight = {weight_kg:.4f} kg")
        self._emit(f"    cost = {weight_kg:.4f} x {price_per_kg:.2f} PLN/kg = {cost:.2f} PLN")

    def log_cutting(self, length_mm: float, price_per_m: float, cost: float):
        """Loguj obliczenie kosztu ciecia"""
        if self._current_part is None:
            return

        self._current_part['components']['cutting'] = {
            'length_mm': length_mm,
            'price_per_m': price_per_m,
            'cost': cost
        }

        length_m = length_mm / 1000.0
        self._emit("  CUTTING:")
        self._emit(f"    length = {length_mm:.1f} mm = {length_m:.3f} m")
        self._emit(f"    cost = {length_m:.3f} m x {price_per_m:.2f} PLN/m = {cost:.2f} PLN")

    def log_engraving(self, length_mm: float, price_per_m: float, cost: float):
        """Loguj obliczenie kosztu graweru"""
        if self._current_part is None:
            return

        self._current_part['components']['engraving'] = {
            'length_mm': length_mm,
            'price_per_m': price_per_m,
            'cost': cost
        }

        length_m = length_mm / 1000.0
        self._emit("  ENGRAVING:")
        self._emit(f"    length = {length_mm:.1f} mm = {length_m:.3f} m")
        if length_mm > 0:
            self._emit(f"    cost = {length_m:.3f} m x {price_per_m:.2f} PLN/m = {cost:.2f} PLN")
        else:
            self._emit(f"    cost = 0.00 PLN (brak graweru)")

    def log_foil(self, area_m2: float = 0, price: float = 0, cost: float = 0,
                 applicable: bool = False, reason: str = ""):
        """Loguj obliczenie kosztu usuwania folii"""
        if self._current_part is None:
            return

        self._current_part['components']['foil'] = {
            'area_m2': area_m2,
            'price': price,
            'cost': cost,
            'applicable': applicable
        }

        self._emit("  FOIL:")
        if applicable:
            self._emit(f"    (INOX <= 5mm - dotyczy)")
            self._emit(f"    cutting+engr length = {area_m2:.3f} m")
            self._emit(f"    cost = {area_m2:.3f} m x {price:.2f} PLN/m = {cost:.2f} PLN")
        else:
            reason_text = reason if reason else "material nie wymaga usuwania folii"
            self._emit(f"    (nie dotyczy - {reason_text})")
            self._emit(f"    cost = 0.00 PLN")

    def log_piercing(self, count: int, price_per_pierce: float, cost: float):
        """Loguj obliczenie kosztu przebic"""
        if self._current_part is None:
            return

        self._current_part['components']['piercing'] = {
            'count': count,
            'price_per_pierce': price_per_pierce,
            'cost': cost
        }

        self._emit("  PIERCING:")
        self._emit(f"    count = {count} (kontury + otwory)")
        self._emit(f"    cost = {count} x {price_per_pierce:.2f} PLN = {cost:.2f} PLN")

    def log_bending(self, count: int, price_per_bend: float, cost: float):
        """Loguj obliczenie kosztu giecia"""
        if self._current_part is None:
            return

        self._current_part['components']['bending'] = {
            'count': count,
            'price_per_bend': price_per_bend,
            'cost': cost
        }

        self._emit("  BENDING:")
        self._emit(f"    count = {count}")
        if count > 0:
            self._emit(f"    cost = {count} x {price_per_bend:.2f} PLN = {cost:.2f} PLN")
        else:
            self._emit(f"    cost = 0.00 PLN (brak giec)")

    def end_part(self, total_lm: float, bending_cost: float = 0, additional: float = 0):
        """Zakoncz logowanie dla czesci i pokaz podsumowanie"""
        if self._current_part is None:
            return

        self._emit(self._separator("-"))

        # Rozklad
        comps = self._current_part['components']
        mat = comps.get('material', {}).get('cost', 0)
        cut = comps.get('cutting', {}).get('cost', 0)
        eng = comps.get('engraving', {}).get('cost', 0)
        foil = comps.get('foil', {}).get('cost', 0)
        pierce = comps.get('piercing', {}).get('cost', 0)

        self._emit(f"  SUBTOTAL L+M: {total_lm:.2f} PLN")
        self._emit(f"    (mat:{mat:.2f} + cut:{cut:.2f} + engr:{eng:.2f} + foil:{foil:.2f} + pierce:{pierce:.2f})")

        if bending_cost > 0:
            self._emit(f"  + BENDING: {bending_cost:.2f} PLN")

        if additional > 0:
            self._emit(f"  + ADDITIONAL: {additional:.2f} PLN")

        total_unit = total_lm + bending_cost + additional
        self._emit(f"  TOTAL UNIT: {total_unit:.2f} PLN")

        qty = self._current_part['quantity']
        if qty > 1:
            self._emit(f"  TOTAL x{qty}: {total_unit * qty:.2f} PLN")

        self._emit(self._separator("="))

        # Zapisz wpis
        entry = CostCalculationEntry(
            timestamp=datetime.now(),
            part_name=self._current_part['name'],
            quantity=self._current_part['quantity'],
            material=self._current_part['material'],
            thickness=self._current_part['thickness'],
            width=self._current_part['width'],
            height=self._current_part['height'],
            components=self._current_part['components'],
            total_lm=total_lm
        )
        self._entries.append(entry)

        self._current_part = None

    def log_summary(self, total_parts: int, total_lm: float, total_bending: float,
                    total_additional: float, grand_total: float):
        """Loguj podsumowanie zamowienia"""
        self._emit("")
        self._emit(self._separator("*", 60))
        self._emit("  PODSUMOWANIE ZAMOWIENIA")
        self._emit(self._separator("*", 60))
        self._emit(f"  Liczba detali: {total_parts}")
        self._emit(f"  Suma L+M:      {total_lm:.2f} PLN")
        self._emit(f"  Suma Giecie:   {total_bending:.2f} PLN")
        self._emit(f"  Suma Dodatkowe:{total_additional:.2f} PLN")
        self._emit(self._separator("-"))
        self._emit(f"  RAZEM:         {grand_total:.2f} PLN")
        self._emit(self._separator("*", 60))
        self._emit("")

    def log_allocation(self, model: str, before_costs: List[float], after_costs: List[float]):
        """Loguj zastosowanie modelu alokacji"""
        self._emit("")
        self._emit(self._separator("~"))
        self._emit(f"[ALLOCATION] Model: {model}")
        self._emit(f"  Before: {[f'{c:.2f}' for c in before_costs]}")
        self._emit(f"  After:  {[f'{c:.2f}' for c in after_costs]}")
        self._emit(self._separator("~"))

    def log_info(self, message: str):
        """Loguj informacje ogolna"""
        self._emit(f"[INFO] {message}")

    def log_warning(self, message: str):
        """Loguj ostrzezenie"""
        self._emit(f"[WARN] {message}")

    def log_error(self, message: str):
        """Loguj blad"""
        self._emit(f"[ERROR] {message}")

    def clear(self):
        """Wyczysc wpisy (plik pozostaje)"""
        self._entries.clear()

    def get_entries(self) -> List[CostCalculationEntry]:
        """Pobierz wszystkie wpisy"""
        return self._entries.copy()

    def get_log_file_path(self) -> Path:
        """Pobierz sciezke do pliku logu"""
        return LOG_DIR / f"cost_debug_{date.today().isoformat()}.log"


# Singleton getter
_logger_instance: Optional[CostDebugLogger] = None

def get_cost_debug_logger() -> CostDebugLogger:
    """Pobierz singleton instancje loggera"""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = CostDebugLogger()
    return _logger_instance
