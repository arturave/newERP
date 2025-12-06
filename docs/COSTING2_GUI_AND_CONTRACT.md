# COSTING2 — Specyfikacja GUI Nesting + kontrakt Nesting↔Costing (v1)

Ten dokument domyka 2 rzeczy:
1) Minimalny, ale sensowny GUI do strojenia wyceny opartej o nesting (Costing Lab → później integracja w ERP).
2) Contract danych Nesting↔Costing tak, żeby costing NIE musiał pobierać DXF z Storage przy każdym przeliczeniu.

---

## 1) GUI Nesting/Costing — MVP (do dopracowania algorytmu)

### Layout (100% ekranu, 3 kolumny)
**Lewy panel: Arkusze**
- Lista arkuszy (scroll)
- Wiersz: `Sheet S1 | <material> | t=2.0 | 1500×3000 | util=0.78`
- Przyciski:
  - Import JSON (file dialog)
  - Reload sample
  - Export wyników (JSON)

**Środkowy panel: Podgląd + detale arkusza**
- Podgląd grafiki arkusza (preview_image_path). Jeśli brak: placeholder.
- Lista detali na wybranym arkuszu jako „karty/wiersze”:
  - mini-thumb (opcjonalnie)
  - idx_code + name
  - qty
  - occupied_area_mm2 / net_area_mm2
  - cut_length_mm → m
  - pierce_count

**Prawy panel: Parametry kosztów (JobOverrides)**
- Checkboxy:
  - include_piercing
  - include_foil_removal
  - include_punch
- Pola:
  - operational_cost_per_sheet_pln (domyślnie 40)
  - tech_cost_pln (na zlecenie)
  - packaging_cost_pln (na zlecenie)
  - transport_cost_pln (na zlecenie)
  - buffer_factor (domyślnie 1.25)
- Przycisk: „Przelicz”
- Wynik:
  - Total A, Total B
  - preview breakdown JSON (text box)

---

## 2) Contract Nesting↔Costing (kluczowe)

### 2.1 NestingResult musi zawierać metryki
Costing ma działać bez ściągania DXF przy każdym „Przelicz”, więc NestingResult niesie metryki.

**PartInstance (minimum)**
- part_id, instance_id
- idx_code, name
- qty_in_sheet
- occupied_area_mm2 (do alokacji kosztu arkusza)
- net_area_mm2 (opcjonalnie, ale zalecane)
- toolpath_stats:
  - cut_length_mm
  - pierce_count
  - contour_count
  - short_segment_ratio (0–1)
- dxf_storage_path (opcjonalne, tylko debug)

**Sheet (minimum)**
- sheet_id
- material_id, thickness_mm
- sheet_width_mm, sheet_length_mm_nominal
- sheet_mode: FIXED_SHEET | CUT_TO_LENGTH
- used_length_y_mm (jeśli CUT_TO_LENGTH)
- trim_margin_y_mm
- utilization
- preview_image_path (w lab: local; w ERP: storage URL)

### 2.2 Minimalny contract z nesting/costing
Nesting zwraca NestingResult + (opcjonalnie) zapisuje JSON i preview PNG:
- Costing przelicza natychmiast na podstawie JSON, bez DXF.

---

## 3) Alokacja kosztu arkusza → detale (rekomendacja)
Domyślnie:
- licz koszt materiału jako koszt CAŁEGO arkusza (lub arkusza dociętego w Y)
- rozdzielaj koszt po detalach proporcjonalnie do occupied_area_mm2

Legacy “10/0.8” (utilization) zostaje jako tryb porównawczy, ale domyślnie OFF.

---

## 4) Definition of Done (MVP)
- `python -m tools.costing_lab.app` uruchamia GUI
- Import JSON działa
- Klik arkusza aktualizuje preview + listę detali
- Przelicz generuje CostSummary (może być jeszcze placeholder), ale w stabilnym formacie
- Export JSON zapisuje wynik do `tools/costing_lab/_outputs/`
