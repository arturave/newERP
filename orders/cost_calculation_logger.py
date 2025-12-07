"""
Logger obliczeń kosztów dla analityka finansowego.

Ten moduł zapewnia szczegółowe logowanie procesu kalkulacji kosztów zamówienia,
w tym użyte metody i składniki kosztowe.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
import os
import logging

logger = logging.getLogger(__name__)


@dataclass
class PartCostEntry:
    """Wpis kosztu dla jednego detalu"""
    name: str
    material: str
    thickness: float
    quantity: int

    # Składniki kosztowe (przed alokacją)
    material_cost: float = 0.0
    cutting_cost: float = 0.0
    engraving_cost: float = 0.0
    foil_cost: float = 0.0
    piercing_cost: float = 0.0
    bending_cost: float = 0.0
    additional_cost: float = 0.0

    # Formuły użyte do obliczeń
    material_formula: str = ""
    cutting_formula: str = ""
    foil_formula: str = ""

    # Po alokacji
    allocated_material_cost: float = 0.0

    @property
    def total_lm(self) -> float:
        """Całkowity koszt L+M (przed alokacją)"""
        return self.material_cost + self.cutting_cost + self.engraving_cost + self.foil_cost

    @property
    def total_lm_allocated(self) -> float:
        """Całkowity koszt L+M (po alokacji materiału)"""
        mat = self.allocated_material_cost if self.allocated_material_cost > 0 else self.material_cost
        return mat + self.cutting_cost + self.engraving_cost + self.foil_cost

    @property
    def total_unit(self) -> float:
        """Całkowity koszt jednostkowy (po alokacji)"""
        return self.total_lm_allocated + self.bending_cost + self.additional_cost


class CostCalculationLogger:
    """
    Logger obliczeń kosztów dla analityka finansowego.

    Zapisuje szczegółowy raport z procesu kalkulacji kosztów zamówienia,
    w tym użyte metody, formuły i składniki kosztowe.
    """

    def __init__(self, order_name: str = ""):
        self.order_name = order_name
        self.entries: List[PartCostEntry] = []
        self.allocation_model: str = "Proporcjonalny"
        self.timestamp = datetime.now()
        self._log_dir = os.path.join(os.path.dirname(__file__), '..', 'logs', 'costs')

    def start_calculation(self, allocation_model: str, order_name: str = ""):
        """Rozpocznij nową kalkulację"""
        self.entries.clear()
        self.allocation_model = allocation_model
        self.order_name = order_name or self.order_name
        self.timestamp = datetime.now()
        logger.info(f"[CostLogger] Rozpoczęto kalkulację dla: {self.order_name}, model: {allocation_model}")

    def log_part(self, entry: PartCostEntry):
        """Dodaj wpis kosztu dla detalu"""
        self.entries.append(entry)
        logger.debug(f"[CostLogger] Zalogowano detal: {entry.name}")

    def log_part_from_dict(self, part_data: Dict):
        """Dodaj wpis kosztu z danych słownikowych detalu"""
        entry = PartCostEntry(
            name=part_data.get('name', '?'),
            material=part_data.get('material', '?'),
            thickness=float(part_data.get('thickness', 0) or 0),
            quantity=int(part_data.get('quantity', 1) or 1),
            material_cost=float(part_data.get('base_material_cost', 0) or part_data.get('material_cost', 0) or 0),
            cutting_cost=float(part_data.get('cutting_cost', 0) or 0),
            engraving_cost=float(part_data.get('engraving_cost', 0) or 0),
            foil_cost=float(part_data.get('foil_cost', 0) or 0),
            piercing_cost=float(part_data.get('piercing_cost', 0) or 0),
            bending_cost=float(part_data.get('bending_cost', 0) or 0),
            additional_cost=float(part_data.get('additional', 0) or 0),
            material_formula=part_data.get('_material_formula', ''),
            cutting_formula=part_data.get('_cutting_formula', ''),
            foil_formula=part_data.get('_foil_formula', ''),
            allocated_material_cost=float(part_data.get('material_cost', 0) or 0),
        )
        self.entries.append(entry)

    def log_allocation(self, part_name: str, original: float, allocated: float):
        """Zapisz wynik alokacji dla detalu"""
        for e in self.entries:
            if e.name == part_name:
                e.allocated_material_cost = allocated
                logger.debug(f"[CostLogger] Alokacja {part_name}: {original:.2f} → {allocated:.2f}")
                break

    def get_formatted_report(self) -> str:
        """
        Zwraca sformatowany raport dla analityka finansowego.

        Raport zawiera:
        - Datę i parametry kalkulacji
        - Szczegółowe koszty każdego detalu z formułami
        - Informacje o alokacji materiału
        - Podsumowanie kosztów
        """
        lines = [
            "=" * 60,
            "RAPORT KALKULACJI KOSZTÓW ZAMÓWIENIA",
            "=" * 60,
            "",
            f"Data kalkulacji: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Zamówienie: {self.order_name}",
            f"Model alokacji materiału: {self.allocation_model}",
            "",
            "-" * 60,
            "SZCZEGÓŁY DETALI",
            "-" * 60,
        ]

        for i, e in enumerate(self.entries, 1):
            lines.extend([
                "",
                f"[{i}] {e.name}",
                f"    Materiał: {e.material}, Grubość: {e.thickness}mm, Ilość: {e.quantity}szt",
                "",
                "    SKŁADNIKI KOSZTOWE (jednostkowe):",
                f"      Materiał:     {e.material_cost:>10.2f} PLN  {e.material_formula}",
                f"      Cięcie:       {e.cutting_cost:>10.2f} PLN  {e.cutting_formula}",
                f"      Grawer:       {e.engraving_cost:>10.2f} PLN",
                f"      Folia:        {e.foil_cost:>10.2f} PLN  {e.foil_formula}",
                f"      ─────────────────────────────",
                f"      L+M (bazowe): {e.total_lm:>10.2f} PLN",
            ])

            # Pokaż zmianę po alokacji jeśli jest różnica
            if abs(e.allocated_material_cost - e.material_cost) > 0.01:
                lines.extend([
                    "",
                    f"    ALOKACJA MATERIAŁU ({self.allocation_model}):",
                    f"      Mat. przed:   {e.material_cost:>10.2f} PLN",
                    f"      Mat. po:      {e.allocated_material_cost:>10.2f} PLN",
                    f"      L+M (po alok):{e.total_lm_allocated:>10.2f} PLN",
                ])

            lines.extend([
                "",
                f"      Gięcie:       {e.bending_cost:>10.2f} PLN",
                f"      Dodatkowe:    {e.additional_cost:>10.2f} PLN",
                f"      ═════════════════════════════",
                f"      TOTAL/szt:    {e.total_unit:>10.2f} PLN",
                f"      TOTAL (×{e.quantity}):  {e.total_unit * e.quantity:>10.2f} PLN",
            ])

        # Podsumowanie
        total_mat_base = sum(e.material_cost for e in self.entries)
        total_mat_alloc = sum(e.allocated_material_cost or e.material_cost for e in self.entries)
        total_cutting = sum(e.cutting_cost for e in self.entries)
        total_engraving = sum(e.engraving_cost for e in self.entries)
        total_foil = sum(e.foil_cost for e in self.entries)
        total_bending = sum(e.bending_cost for e in self.entries)
        total_additional = sum(e.additional_cost for e in self.entries)

        # Sumy z ilością
        total_with_qty = sum(e.total_unit * e.quantity for e in self.entries)

        lines.extend([
            "",
            "-" * 60,
            "PODSUMOWANIE (sumy jednostkowe)",
            "-" * 60,
            "",
            f"  Materiał (bazowy):    {total_mat_base:>12.2f} PLN",
            f"  Materiał (po alokacji):{total_mat_alloc:>11.2f} PLN  ← {self.allocation_model}",
            f"  Cięcie (STAŁE):       {total_cutting:>12.2f} PLN",
            f"  Grawer (STAŁE):       {total_engraving:>12.2f} PLN",
            f"  Folia (STAŁE):        {total_foil:>12.2f} PLN",
            f"  Gięcie:               {total_bending:>12.2f} PLN",
            f"  Dodatkowe:            {total_additional:>12.2f} PLN",
            "",
            "=" * 60,
            f"  RAZEM (z ilościami):  {total_with_qty:>12.2f} PLN",
            "=" * 60,
            "",
            "UWAGI:",
            f"  - Model alokacji ({self.allocation_model}) wpływa TYLKO na koszt materiału",
            "  - Koszty cięcia, graweru i folii są STAŁE (zależą od geometrii)",
            "  - Koszty gięcia i dodatkowe są niezależne od alokacji",
        ])

        return "\n".join(lines)

    def save_to_file(self) -> str:
        """
        Zapisz raport do pliku w logs/costs/.

        Returns:
            Ścieżka do zapisanego pliku
        """
        os.makedirs(self._log_dir, exist_ok=True)

        timestamp = self.timestamp.strftime('%Y-%m-%d_%H-%M-%S')
        safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in self.order_name)
        filename = f"cost_calc_{timestamp}_{safe_name}.log"
        filepath = os.path.join(self._log_dir, filename)

        report = self.get_formatted_report()

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report)

        logger.info(f"[CostLogger] Zapisano raport do: {filepath}")
        return filepath

    def get_summary_dict(self) -> Dict:
        """Zwróć podsumowanie jako słownik (do GUI)"""
        total_mat_alloc = sum(e.allocated_material_cost or e.material_cost for e in self.entries)
        total_cutting = sum(e.cutting_cost for e in self.entries)
        total_foil = sum(e.foil_cost for e in self.entries)
        total_engraving = sum(e.engraving_cost for e in self.entries)

        return {
            'allocation_model': self.allocation_model,
            'material_cost': total_mat_alloc,
            'cutting_cost': total_cutting,
            'engraving_cost': total_engraving,
            'foil_cost': total_foil,
            'parts_count': len(self.entries),
            'timestamp': self.timestamp.isoformat(),
        }


# Globalna instancja loggera dla łatwego dostępu
_cost_logger: Optional[CostCalculationLogger] = None


def get_cost_logger(order_name: str = "") -> CostCalculationLogger:
    """Pobierz globalną instancję loggera kosztów"""
    global _cost_logger
    if _cost_logger is None:
        _cost_logger = CostCalculationLogger(order_name)
    elif order_name:
        _cost_logger.order_name = order_name
    return _cost_logger


def log_calculation_start(allocation_model: str, order_name: str = ""):
    """Rozpocznij logowanie nowej kalkulacji"""
    get_cost_logger(order_name).start_calculation(allocation_model, order_name)


def log_part_cost(part_data: Dict):
    """Zaloguj koszt detalu"""
    get_cost_logger().log_part_from_dict(part_data)


def save_cost_log() -> str:
    """Zapisz log do pliku i zwróć ścieżkę"""
    return get_cost_logger().save_to_file()


def get_cost_report() -> str:
    """Pobierz sformatowany raport"""
    return get_cost_logger().get_formatted_report()
