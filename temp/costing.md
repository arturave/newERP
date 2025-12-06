1) Co jest „realne” w praktyce (wnioski z dostępnych rozwiązań)

Samo czas = długość_cięcia / prędkość jest za optymistyczne, bo większość trajektorii to krótkie odcinki/łuki i naroża → maszyna nie osiąga zadanej prędkości i musi zwalniać. W CAM / sterowaniach dzieje się to przez planowanie ruchu z ograniczeniami przyspieszeń oraz prędkości na złączach segmentów (junction / cornering). 
rockwellautomation.com
+2
klipper3d.org
+2

W praktyce ruch jest planowany jako profil trapezowy lub S-curve (trapez jest prostszy, S-curve lepiej oddaje jerk, ale na start trapez daje bardzo użyteczne przybliżenie). 
rockwellautomation.com
+1

Da się to dobrze zasymulować algorytmem „lookahead” używanym np. w kontrolerach typu GRBL / Klipper (pojęcia: junction deviation / square_corner_velocity jako prosty model ograniczania prędkości w narożach). 
tecnoroll.it
+2
klipper3d.org
+2

W literaturze i praktyce jest osobny wątek optymalizacji kolejności cięć (path planning), bo czasy przejazdów jałowych i liczba „startów” mają znaczenie, ale u Ciebie wejściem jest już wynik nestingu i lista detali per arkusz – więc na start lepiej skupić się na realistycznym czasie pojedynczej ścieżki niż na zmianie kolejności. 
MDPI
+1

2) Proponowany model czasu cięcia (Python + ezdxf) – wersja „użyteczna od razu”
2.1. Z czego składa się całkowity czas na arkusz

Dla każdego arkusza (materiał+grubość) liczysz:

T_total = T_cut_motion + T_rapids + N_pierce * t_pierce + N_contours * t_leadin_leadout + T_overheads

Gdzie:

T_cut_motion – czas ruchu przy laser ON (po ścieżkach cięcia)

T_rapids – czas przejazdów jałowych (laser OFF) między konturami (też z acc/dec)

N_pierce – liczba przebić (startów cięcia)

t_pierce – czas przebicia zależny od materiału i grubości (masz już widełki w głowie – to jest OK jako parametr tabelaryczny)

t_leadin_leadout – stały narzut na wejście/wyjście, mikromostki itp. (opcjonalnie)

T_overheads – gaz, autofocus, zmiany dyszy, itp. (na start jako stałe per arkusz / per program)

To podejście jest spójne z tym, że kontrolery realnie liczą osobno ruch roboczy i jałowy; a o tym, że sterownik rampuje i ogranicza prędkości w narożach, mówią wprost dokumentacje systemów typu LightBurn/GRBL/Klipper. 
lightburnsoftware.github.io
+2
tecnoroll.it
+2

2.2. Jak policzyć T_cut_motion realistycznie (bez G-code)

Masz DXF i ezdxf, więc generujesz „odcinki ruchu” w 2D:

LINE → segment

ARC/CIRCLE → łuk (parametry: promień, kąt)

LWPOLYLINE z bulge → segmenty + łuki

Potem robisz symulację prędkości po trajektorii z ograniczeniami:

v_max (dla danej grubości/materiału z cennika/prędkości cięcia)

a_max (maks przyspieszenie osi/gantry – wartość konfigurowalna, kalibrowana)

ograniczenie narożne (cornering) – tu masz dwie sensowne opcje:

Opcja A (prosta, robust): „square_corner_velocity” / „junction deviation”
To jest dokładnie ten typ parametru, którym sterowniki ograniczają prędkość w narożach; dla 90° masz stałą v_corner_90, a dla innych kątów funkcja skaluje prędkość – to daje świetne przybliżenie bez wchodzenia w promienie zaokrągleń. 
klipper3d.org
+1

Opcja B (bardziej fizyczna): ograniczenie krzywizny (a_lat)
Dla łuku o promieniu r: v ≤ sqrt(a_lat_max * r) (ograniczenia przeciążeń bocznych).
Dla „ostrych” naroży (r→0) model sam wymusza zwolnienie (prawie do zera).
To też jest sensowne, ale w praktyce sterowania robią „blending” i lookahead, więc i tak skończysz z czymś podobnym do A.

Krok kluczowy: lookahead forward-backward pass

Dzielisz ścieżkę na elementy o długości L_i oraz ograniczeniu prędkości na wejściu/wyjściu (z naroży).

Robisz przejście w przód (limit narastania prędkości przez a_max) i w tył (limit hamowania).

Dla każdego elementu liczysz czas z profilu trapezowego (acc → cruise → dec).
To jest dokładnie idea planowania w kontrolerach CNC/drukarek 3D. 
rockwellautomation.com
+2
tecnoroll.it
+2

W praktyce to podejście bardzo dobrze łapie efekt: „dużo małych kształtów = maszyna nie rozpędza się”. To jest dokładnie problem, który opisałeś. 
tecnoroll.it
+1

2.3. Lepsze oszacowanie N_pierce (przebić)

Dla DXF:

N_pierce ≈ liczba niezależnych konturów cięcia (zewnętrzne + otwory), z korektą jeśli łączysz kontury (common-line-cutting) – jeśli nie, to zwykle 1 przebicie na kontur.

A t_pierce jako tabela:

zależna od (materiał, grubość, gaz) – trzymasz to jako cennik technologiczny.

To jest standardowa praktyka (i w literaturze o procesie cięcia wprost widać, że parametry i prędkość mają ogromny wpływ). 
MDPI
+1

3) Rzeczywiste zużycie materiału na detal z nestingu (arkusz jest kosztem)

Masz 2 przypadki procesu (warto rozdzielić, bo to zmienia logikę):

3.1. Arkusz „stały” (np. kupujesz 1500×3000)

Koszt materiału joba = koszt całego arkusza(ów) użytych do nestingu
I rozbijasz na detale wg udziału w „zajętości arkusza”.

Najbardziej sensowna alokacja (praktyczna w firmach):

Udział detalu liczysz po „occupied area” (powierzchnia zewnętrznego obrysu detalu – bez odejmowania otworów), bo:

otwory nie zwalniają łatwo miejsca do gniazdowania (chyba że robisz „inside nesting”, rzadziej),

wycena ma odzwierciedlać „ile miejsca na arkuszu zabieram”, a nie „ile waży finalnie część”.

material_cost_part = sheet_cost * (occupied_area_part / Σ occupied_area_parts_on_sheet)

To jest „lepsze” od dzielenia po wadze netto, bo części ażurowe nie będą sztucznie tanie.

3.2. Arkusz „docinany” (np. z coil / docinasz długość w Y)

Wtedy możesz zrobić to, co proponujesz: po nestingu obcinasz Y do maxY + margines.

sheet_area_used = sheet_width * used_length_y
sheet_cost_used = sheet_area_used * cost_per_m2 (albo przez masę: area * thickness * density * PLN/kg)

I dalej dzielisz jak wyżej po occupied_area.

To wprost realizuje Twoje „zmniejsz arkusz w osi Y do realnego rozmiaru”.

3.3. Utylizacja (utilization) – jak to ująć poprawnie

utilization = Σ occupied_area / sheet_area_used

Twoja wcześniejsza heurystyka typu „waga / utilization” ma sens, ale:

użyj occupied_area zamiast net area (z uwagi na otwory),

i licz utilization od sheet_area_used (albo stałej wielkości arkusza).

Wtedy:
material_cost_part ≈ cost_of_occupied_area_part / utilization
(gdzie cost_of_occupied_area_part = occupied_area_part * (sheet_cost_used / sheet_area_used))

4) Jak to wdrożyć w Pythonie (moduły / IO)
4.1. Dane wejściowe (już je masz)

Wyniki nestingu:

arkusze: (material_id, thickness, width, length, utilization, image_preview, list of parts placements)

przypisanie detali do arkusza

DXF geometry (ezdxf)

Cenniki:

material: PLN/kg lub PLN/m2 (i gęstość)

cutting speed m/min (per materiał+grubość)

cutting cost PLN/m (opcjonalnie, drugi wariant wyceny)

pierce_time sec (materiał+grubość)

acceleration params (global lub per maszyna)

4.2. Proponowane „core” funkcje

extract_toolpath(dxf) -> List[Move] (segment/arc, length, corner_angle, radius)

estimate_motion_time(moves, v_max, a_max, corner_model) -> seconds

corner_model: square_corner_velocity (proste) albo a_lat_max (krzywizna)

estimate_cut_time(dxf, params) -> seconds, cut_length_m, pierces, rapids

allocate_sheet_material_cost(sheet_cost, parts_occupied_areas) -> Dict[part_id, cost]

estimate_sheet_total_cost(sheet, time_model, cost_model) -> breakdown

4.3. Dwa warianty wyceny (tak jak chcesz)

Wariant 1: cennikowy (PLN/m)
laser_cost = cut_length_m * price_per_m(material, thickness)

pierce_cost = pierces * price_per_pierce (opcjonalnie)

Wariant 2: czasowy (bardziej „prawdziwy”)
laser_cost = (estimated_cut_time_minutes / 60) * PLN_per_hour_machine

dodatki (foil removal, operational per sheet, etc.)

To daje Ci i „zgodność z cennikiem”, i „realizm operacyjny”.

5) ML jako „upgrade” (po zebraniu logów)

Jeśli masz lub możesz mieć:

rzeczywiste czasy wykonania programu / arkusza (z maszyny / operatora),
to robisz model regresyjny:
features: cut_length, pierces, sum_corner_angles, min_radius, ratio_short_segments, count_entities, thickness, material, utilization, total_parts, etc.
target: real_cut_time

To jest dokładnie to, co robi się w „smart machining / feedrate optimization” – tylko u Ciebie zamiast sił skrawania masz geometrię i parametry procesu. 
OUP Academic

6) Co ja proponuję jako „lepsze rozwiązanie” niż Twoja obecna heurystyka

Materiał: rozdzielaj koszt arkusza po occupied_area (obrys zewnętrzny), nie po wadze netto bez otworów.

Czas cięcia: wprowadź lookahead + trapez z parametrami a_max i square_corner_velocity/junction deviation jako „corner limiter”. To jest prosty, ale bardzo mocny skok jakościowy względem L/v. 
klipper3d.org
+2
tecnoroll.it
+2

Kalibracja: 2–3 testy (prosty detal vs ażurowy z setkami krótkich segmentów) i dobierasz a_max + v_corner_90 tak, żeby zgadzało się „średnio” – potem ML doszlifuje.

# NESTING_COSTING_SPEC.md
**Tech spec dla developera (Python + ezdxf + Supabase).**

> Cel: wdrożyć moduł, który z wyników nestingu (arkusze + przypisanie detali + utilization) oraz geometrii DXF (ezdxf) wyliczy:
> 1) realistyczny **czas cięcia** (acc/dec, naroża, małe kształty),
> 2) **rzeczywisty koszt materiału** (koszt arkusza użytego w nestingu rozłożony na detale),
> 3) kosztorys A/B (cennikowy vs czasowy) + breakdown do Supabase.

---

## 0) Terminologia
- **Sheet / Arkusz**: jedna blacha w nestingu (nominalna lub docinana).
- **Part / Detal**: typ detalu (produkt/pozycja).
- **PartInstance**: konkretne wystąpienie detalu na arkuszu (x,y,rot).
- **Occupied area**: powierzchnia „zajęta” na arkuszu = **obrys zewnętrzny** (bez odejmowania otworów).
- **Utilization**: Σ occupied_area / sheet_area_used.
- **Toolpath**: ścieżka ruchu (laser ON/OFF).
- **Pierce**: przebicie / start konturu.

---

## 1) Założenia (MVP)
1. `czas != długość/prędkość` → model ruchu z:
   - `v_max` (z cennika m/min),
   - `a_max` (profil maszyny),
   - ograniczeniem prędkości w narożach,
   - lookahead (forward-backward) + profil trapezowy.
2. Koszt materiału liczony jako **koszt arkusza(ów) użytych** w nestingu i alokowany na detale wg occupied_area.
3. Tryby arkusza:
   - **FIXED_SHEET**: stały format (np. 1500×3000).
   - **CUT_TO_LENGTH**: docinany w osi Y do realnego użycia + margines technologiczny.
4. Dwa warianty wyceny:
   - **A (cennikowy)**: PLN/m + pierce + folia + operacyjne + koszty na zlecenie
   - **B (czasowy)**: PLN/h * (czas cięcia + pierce + folia) + dodatki, z buforem **+25%**.
5. Parametry technologii trzymamy w Supabase (tabele stawek per materiał i grubość).

---

## 2) Kontrakt danych: `NestingResult` (JSON)
### 2.1. Minimalny format wejściowy/archiwizacyjny
```json
{
  "nesting_run_id": "uuid or null",
  "source_type": "order|quotation",
  "source_id": "uuid",
  "created_at": "ISO8601",
  "machine_profile_id": "uuid",

  "sheets": [
    {
      "sheet_id": "uuid or local-id",
      "sheet_mode": "FIXED_SHEET|CUT_TO_LENGTH",
      "material_id": "uuid",
      "thickness_mm": 2.0,

      "sheet_width_mm": 1500.0,
      "sheet_length_mm_nominal": 3000.0,

      "used_length_y_mm": 1870.0,
      "trim_margin_y_mm": 10.0,

      "sheet_area_used_mm2": 2805000.0,
      "occupied_area_mm2": 2210000.0,
      "utilization": 0.788,

      "preview_image_path": "storage/path/or/local",

      "parts": [
        {
          "part_id": "uuid",
          "instance_id": "uuid or local-id",
          "idx_code": "string",
          "name": "string",
          "qty_in_sheet": 1,

          "transform": { "x_mm": 123.4, "y_mm": 456.7, "rotation_deg": 90.0 },

          "dxf_storage_path": "product_files/cad/2d/<product_id>/file.dxf",

          "occupied_area_mm2": 12000.0,
          "net_area_mm2": 9500.0,

          "toolpath_stats": {
            "cut_length_mm": 3400.0,
            "rapid_length_mm": 0.0,

            "pierce_count": 6,
            "contour_count": 6,

            "entity_counts": { "LINE": 120, "ARC": 14, "CIRCLE": 2, "SPLINE": 0 },
            "short_segment_ratio": 0.12
          }
        }
      ]
    }
  ]
}

2.2. Minimum na toolpath_stats (jeśli brak — moduł liczy z DXF)

cut_length_mm

pierce_count (≈ liczba konturów)

entity_counts

short_segment_ratio (udział długości na segmentach < threshold, np. 5 mm)

3) Supabase – definicje tabel (SQL migracja)

Zapisz jako sql/nesting_costing_migration.sql.

3.1. Profile maszyn (dynamika)
create table if not exists public.machine_profiles (
  id uuid primary key default gen_random_uuid(),
  name text not null,

  max_accel_mm_s2 numeric not null default 2000,
  max_rapid_mm_s numeric not null default 500,

  square_corner_velocity_mm_s numeric not null default 50,
  junction_deviation_mm numeric not null default 0.05,
  use_junction_deviation boolean not null default false,

  created_at timestamptz not null default now()
);

3.2. Stawki przebicia (czas / koszt)
create table if not exists public.piercing_rates (
  id uuid primary key default gen_random_uuid(),
  material_id uuid not null references public.materials_dict(id),
  thickness_mm numeric(10,2) not null,

  pierce_time_s numeric(10,3) not null,
  pierce_cost_pln numeric(10,2) null,

  is_active boolean not null default true,
  unique(material_id, thickness_mm)
);

3.3. Usuwanie folii (domyślne + prędkość)
create table if not exists public.foil_removal_rates (
  id uuid primary key default gen_random_uuid(),
  material_id uuid not null references public.materials_dict(id),

  thickness_mm_max numeric(10,2) null,      -- null = wszystkie grubości
  default_enabled boolean not null default false,

  removal_speed_m_min numeric(10,2) not null default 15.0,
  cost_pln_per_min numeric(10,2) null,
  cost_pln_per_m2 numeric(10,2) null,

  is_active boolean not null default true
);


Reguła MVP (aplikacyjnie lub seed): inox (stainless) + thickness <= 5mm => default_enabled=true, reszta false.

3.4. Koszty „punch” (opcjonalnie, jeśli rozdzielasz od pierce)
create table if not exists public.punch_rates (
  id uuid primary key default gen_random_uuid(),
  material_id uuid not null references public.materials_dict(id),
  thickness_mm numeric(10,2) not null,

  cost_pln_per_punch numeric(10,2) not null default 0,
  default_enabled boolean not null default true,

  unique(material_id, thickness_mm)
);

3.5. Koszty na zlecenie/ofertę + per arkusz
create table if not exists public.job_cost_overrides (
  id uuid primary key default gen_random_uuid(),
  source_type text not null check (source_type in ('order','quotation')),
  source_id uuid not null,

  tech_cost_pln numeric(10,2) not null default 0,
  packaging_cost_pln numeric(10,2) not null default 0,
  transport_cost_pln numeric(10,2) not null default 0,

  operational_cost_per_sheet_pln numeric(10,2) not null default 40,

  include_piercing boolean not null default true,
  include_foil_removal boolean not null default false,
  include_punch boolean not null default false,

  updated_at timestamptz not null default now(),
  unique(source_type, source_id)
);

3.6. Rejestr uruchomień nestingu + wyników kosztowania
create table if not exists public.nesting_runs (
  id uuid primary key default gen_random_uuid(),

  source_type text not null check (source_type in ('order','quotation')),
  source_id uuid not null,
  machine_profile_id uuid not null references public.machine_profiles(id),

  created_at timestamptz not null default now(),
  created_by text null,

  nesting_result jsonb not null default '{}'::jsonb,
  preview_image_paths jsonb not null default '[]'::jsonb,

  cost_summary jsonb not null default '{}'::jsonb,
  is_active boolean not null default true
);

create index if not exists idx_nesting_runs_source
  on public.nesting_runs(source_type, source_id, created_at desc);

4) DXF (ezdxf): ekstrakcja geometrii i statystyk
4.1. Co liczymy (MVP)

cut_length_mm

pierce_count (≈ liczba konturów zamkniętych)

short_segment_ratio (np. threshold=5mm)

entity_counts (LINE/ARC/CIRCLE/SPLINE)

occupied_area_mm2 (obrys zewnętrzny bez otworów)

net_area_mm2 (opcjonalnie; masa gotowej części)

4.2. Flattening

SPLINE / bulge → wypłaszcz do odcinków z tolerancją 0.05–0.2mm.

Kontury: łącz endpointy w tolerancji ~0.1mm aby policzyć liczbę zamkniętych pętli.

5) Czas cięcia: lookahead + trapez + naroża (kopiuj-wklej)
5.1. Corner model (MVP)
import math

def corner_speed_limit(angle_deg: float, v_corner_90: float, v_max: float) -> float:
    # angle_deg: 0=zwrot wstecz, 180=prosto
    a = max(0.0, min(180.0, angle_deg))
    if a >= 179.0:
        return v_max
    # 90° => 1.0; 180° => 2.0 (clamp do v_max)
    scale = 1.0 + (a - 90.0) / 90.0
    return min(v_max, v_corner_90 * max(0.2, scale))

5.2. Forward-backward pass (lookahead)
import math

def plan_speeds(L, V_junction, v_max, a_max):
    """
    L: list[float] długości segmentów (mm), n segmentów
    V_junction: list[float] limity prędkości na węzłach (mm/s), długość n+1
    """
    n = len(L)
    V = [0.0] * (n + 1)
    V[0] = 0.0

    # forward (rozpędzanie)
    for k in range(1, n):
        V_reach = math.sqrt(V[k-1]**2 + 2*a_max*L[k-1])
        V[k] = min(V_reach, V_junction[k], v_max)

    V[n] = 0.0

    # backward (hamowanie)
    for k in reversed(range(0, n)):
        V_reach = math.sqrt(V[k+1]**2 + 2*a_max*L[k])
        V[k] = min(V[k], V_reach)

    return V

5.3. Czas segmentu – profil trapezowy
import math

def segment_time_trapezoid(L, Vs, Ve, v_max, a):
    v_peak_sq = a*L + 0.5*(Vs*Vs + Ve*Ve)
    v_peak = min(v_max, math.sqrt(max(0.0, v_peak_sq)))

    t1 = max(0.0, (v_peak - Vs) / a)
    t3 = max(0.0, (v_peak - Ve) / a)

    s1 = max(0.0, (v_peak*v_peak - Vs*Vs) / (2*a))
    s3 = max(0.0, (v_peak*v_peak - Ve*Ve) / (2*a))
    s2 = max(0.0, L - s1 - s3)

    t2 = s2 / max(1e-9, v_peak)
    return t1 + t2 + t3

5.4. Penalizacja „małych kształtów”
def effective_vmax(v_max, short_ratio, k=0.7):
    # short_ratio = sum(length where length<threshold)/sum(length)
    return max(0.3*v_max, v_max*(1.0 - k*short_ratio))

5.5. Czas całkowity arkusza (wariant B)
cut_time_s     = sum(segment_time_trapezoid(...))  // laser ON
pierce_time_s  = pierce_count * pierce_time_s(material, thickness)  // z DB
foil_time_s    = (foil_distance_m / foil_speed_m_min) * 60  (lub od m²)
total_time_s   = (cut_time_s + pierce_time_s + foil_time_s) * 1.25

6) Materiał: koszt arkusza i alokacja na detale
6.1. Sheet area used

FIXED_SHEET: area = width * length_nominal

CUT_TO_LENGTH: area = width * (used_length_y + trim_margin_y)

6.2. Koszt arkusza

Wspieraj oba:

PLN/m²: sheet_cost = area_m2 * price_pln_per_m2

PLN/kg: mass = area_m2 * thickness_m * density_kg_m3, sheet_cost = mass * price_pln_per_kg

6.3. Domyślna alokacja (REKOMENDOWANA)

Rozdzielaj koszt po occupied_area:

part_material_cost = sheet_cost * (occupied_area_part / Σ occupied_area_parts)

6.4. Legacy (utilization factor) – opcja
util = Σ occupied_area_parts / sheet_area_used
part_material_cost = (occupied_area_part * (sheet_cost / sheet_area_used)) / util

7) Kosztorys: wariant A / wariant B (wspólny output)
7.1. Variant A (cennikowy)

Per arkusz:

cut_cost_pln = cut_length_m * price_pln_per_m(material, thickness)

pierce_cost_pln = pierce_count * pierce_cost_pln (jeśli zdefiniowane)

foil_cost_pln (jeśli include_foil_removal)

operational_cost_pln = operational_cost_per_sheet_pln

Per zlecenie/oferta:

tech_cost_pln + packaging_cost_pln + transport_cost_pln

7.2. Variant B (czasowy)

Per arkusz:

laser_cost_pln = (total_time_s / 3600) * machine_rate_pln_per_h

plus jak w A (operacyjne / job costs)

7.3. Struktura cost_summary do nesting_runs.cost_summary

Wymagane pola:

allocation_model, buffer_factor, machine_profile_id

variant_a.total_pln, variant_b.total_pln

breakdown per sheet + per part_instance (dla audytu i UI)

8) Service layer (proponowane API)
class NestingCostingService:
    def compute_part_stats_from_dxf(self, dxf_bytes: bytes) -> dict: ...
    def estimate_sheet_times(self, sheet: dict, machine_profile: dict, tech_rates: dict) -> dict: ...
    def allocate_material_costs(self, sheet: dict, material_prices: dict, allocation_model: str = "OCCUPIED_AREA") -> dict: ...
    def compute_costing(self, nesting_result: dict, job_overrides: dict, pricing: dict) -> dict: ...

9) Testy akceptacyjne (MVP)

Alokacja materiału: suma kosztów detali == koszt arkusza (± 0.01 PLN).

Długi prosty kontur: czas ~ L/v_max (z małą różnicą na start/stop).

Detal ażurowy: czas >> L/v_max (short_segment_ratio wymusza spadek).

Pierce: rośnie liniowo z liczbą konturów.

Bufor: final time = base_time * 1.25.

Appendix A: jednostki

m/min → mm/s: v_mm_s = v_m_min * 1000 / 60

mm² → m²: area_m2 = area_mm2 / 1_000_000

mm → m: t_m = thickness_mm / 1000


Jeśli chcesz, w kolejnym kroku dopiszę do tego MD jeszcze **konkretną listę feature’ów do GUI Nesting (pola/checkboxy, struktura paneli)** i minimalny **contract między modułem nestingu a costingiem** (czyli co dokładnie `test_nesting_integration.py` ma zwracać, żeby costing działał bez dociągania DXF z Storage przy każdym przeliczeniu).
::contentReference[oaicite:0]{index=0}

Powiedziałeś(-aś):

Jeśli chcesz, w kolejnym kroku dopiszę do tego MD jeszcze **konkretną listę feature’ów do GUI Nesting (pola/checkboxy, struktura paneli)** i minimalny **contract między modułem nestingu a costingiem** (czyli co dokładnie test_nesting_integration.py ma zwracać, żeby costing działał bez dociągania DXF z Storage przy każdym przeliczeniu).
::contentReference[oaicite:0]{index=0}

TAK PROSZĘ - PRZYGOTUJ TO FORMIE JEDNEGO PLIKU DO POBRANIA
ChatGPT powiedział:
Myślał przez 10s
Wstrzymano analizę
Myślał przez 26s

Jasne — przygotowałem jeden, spójny plik MD (costing + GUI Nesting + kontrakt danych + cache bez pobierania DXF).
Nie mogę niestety wygenerować w tej sesji klikalnego pliku do pobrania (błąd narzędzia zapisu plików), ale poniżej masz gotową treść — zapisz ją jako NESTING_COSTING_GUI_AND_CONTRACT_SPEC.md.

# NESTING_COSTING_GUI_AND_CONTRACT_SPEC.md
**Jednolita specyfikacja: costing + GUI Nesting + kontrakt Nesting↔Costing (Python + ezdxf + Supabase)**  
Data: 2025-12-04

> Cel: wdrożyć moduł, który z wyników nestingu (arkusze + przypisanie detali + utilization) oraz geometrii DXF (ezdxf) wyliczy:
> 1) realistyczny **czas cięcia** (acc/dec, naroża, „małe kształty”),
> 2) **rzeczywisty koszt materiału** jako koszt arkusza użytego w nestingu rozłożony na detale,
> 3) dwa warianty wyceny (A: PLN/m, B: PLN/h z czasem) + pełny breakdown do Supabase,
> 4) GUI „Nesting” w głównym oknie, fullscreen, z parametrami kosztowymi i zapisaniem wyniku.

---

## 0) Terminologia
- **Sheet / Arkusz**: pojedyncza blacha w nestingu (nominalna lub docinana).
- **Part / Detal**: typ detalu (produkt/pozycja).
- **PartInstance**: konkretne wystąpienie detalu na arkuszu (x,y,rot).
- **Occupied area**: powierzchnia „zajęta” na arkuszu = **obrys zewnętrzny bez odejmowania otworów** (domyślny klucz alokacji materiału).
- **Utilization**: Σ occupied_area / sheet_area_used.
- **Toolpath stats**: statystyki cięcia liczone z DXF: długość cięcia, liczba konturów, przebicia, short-seg ratio.

---

## 1) Założenia (MVP, ale rozszerzalne)
1. `czas != długość/prędkość` → model ruchu:
   - `v_max` (m/min z cennika),
   - `a_max` (profil maszyny),
   - ograniczenie prędkości w narożach,
   - lookahead (forward-backward) + profil trapezowy.
2. Materiał: liczymy **koszt arkusza(ów) użytych** i rozdzielamy na detale wg occupied_area.
3. Arkusze: dwa tryby:
   - **FIXED_SHEET**: stały format (np. 1500×3000).
   - **CUT_TO_LENGTH**: docinany w osi Y do realnego użycia + margines (np. 10mm).
4. Dwa warianty wyceny:
   - **A (cennikowy)**: PLN/m + pierce + folia + operacyjne + koszty na zlecenie
   - **B (czasowy)**: PLN/h * (czas cięcia + pierce + folia) + dodatki z buforem **+25%**
5. Parametry technologii trzymamy w Supabase w tabelach stawek per (material_id, thickness).

---

## 2) Kontrakt danych: `NestingResult` (JSON)
### 2.1 Minimalny JSON (wejście do costingu + zapis do DB)
```json
{
  "nesting_run_id": "uuid or null",
  "source_type": "order|quotation",
  "source_id": "uuid",
  "created_at": "ISO8601",
  "machine_profile_id": "uuid",
  "sheets": [
    {
      "sheet_id": "uuid|local",
      "sheet_mode": "FIXED_SHEET|CUT_TO_LENGTH",
      "material_id": "uuid",
      "thickness_mm": 2.0,

      "sheet_width_mm": 1500.0,
      "sheet_length_mm_nominal": 3000.0,

      "used_length_y_mm": 1870.0,
      "trim_margin_y_mm": 10.0,

      "sheet_area_used_mm2": 2805000.0,
      "occupied_area_mm2": 2210000.0,
      "utilization": 0.788,

      "preview_image_path": "storage/path/or/local",
      "parts": [
        {
          "part_id": "uuid",
          "instance_id": "uuid|local",
          "idx_code": "string",
          "name": "string",
          "qty_in_sheet": 1,
          "transform": {"x_mm":123.4,"y_mm":456.7,"rotation_deg":90.0},

          "dxf_storage_path": "product_files/cad/2d/<product_id>/file.dxf",

          "occupied_area_mm2": 12000.0,
          "net_area_mm2": 9500.0,

          "toolpath_stats": {
            "cut_length_mm": 3400.0,
            "rapid_length_mm": 0.0,
            "pierce_count": 6,
            "contour_count": 6,
            "entity_counts": {"LINE":120,"ARC":14,"CIRCLE":2,"SPLINE":0},
            "short_segment_ratio": 0.12
          }
        }
      ]
    }
  ]
}

2.2 Minimalne wymagania na toolpath_stats

Jeśli nesting ich nie dostarcza — costing liczy z DXF i zapisuje do cache:

cut_length_mm, pierce_count, contour_count, short_segment_ratio

occupied_area_mm2 (obrys zewnętrzny)

entity_counts (pomocniczo)

3) Jak NIE pobierać DXF ze Storage przy każdym przeliczeniu (CACHE)
3.1 Zasada

DXF pobieramy tylko gdy:

pierwsze liczenie dla detalu (brak cache),

wykryliśmy zmianę pliku (hash),

użytkownik wymusi „Rebuild stats”.

3.2 Dwa poziomy danych (Tier 1 / Tier 2)

Tier 1 (MVP — zalecany):

przechowujemy tylko toolpath_stats (mały JSON) → wystarcza do A i do B w trybie lookahead-lite.

Tier 2 (opcjonalny, dokładniejszy):

przechowujemy dodatkowo „motion_inputs” do lookahead bez DXF:

segment_lengths_mm[]

junction_angles_deg[]

(opcjonalnie) histogramy długości segmentów / kątów zamiast surowych list.

3.3 Cache w DB (rekomendacja: osobna tabela)
create table if not exists public.product_toolpath_cache (
  id uuid primary key default gen_random_uuid(),
  product_id uuid not null references public.products_catalog(id),
  cad_2d_url text null,
  cad_2d_hash text null,                -- sha256
  computed_at timestamptz not null default now(),
  toolpath_stats jsonb not null default '{}'::jsonb,
  motion_inputs jsonb null,
  unique(product_id, cad_2d_hash)
);

3.4 Hash pliku

po pobraniu bytes DXF: licz sha256(bytes) i porównuj z cad_2d_hash

jeśli mismatch → przelicz stats i dopisz nowy rekord cache

4) Supabase: tabele stawek i wyników (SQL migracja)

Zapisz jako: sql/nesting_costing_migration.sql

4.1 Profile maszyn (dynamika)
create table if not exists public.machine_profiles (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  max_accel_mm_s2 numeric not null default 2000,
  max_rapid_mm_s numeric not null default 500,
  square_corner_velocity_mm_s numeric not null default 50,
  junction_deviation_mm numeric not null default 0.05,
  use_junction_deviation boolean not null default false,
  created_at timestamptz not null default now()
);

4.2 Stawki przebicia
create table if not exists public.piercing_rates (
  id uuid primary key default gen_random_uuid(),
  material_id uuid not null references public.materials_dict(id),
  thickness_mm numeric(10,2) not null,
  pierce_time_s numeric(10,3) not null,
  pierce_cost_pln numeric(10,2) null,
  is_active boolean not null default true,
  unique(material_id, thickness_mm)
);

4.3 Usuwanie folii
create table if not exists public.foil_removal_rates (
  id uuid primary key default gen_random_uuid(),
  material_id uuid not null references public.materials_dict(id),
  thickness_mm_max numeric(10,2) null,
  default_enabled boolean not null default false,
  removal_speed_m_min numeric(10,2) not null default 15.0,
  cost_pln_per_min numeric(10,2) null,
  cost_pln_per_m2 numeric(10,2) null,
  is_active boolean not null default true
);


Reguła default (MVP):

stainless + thickness<=5mm → default_enabled=true

inne → false

4.4 Punch (opcjonalnie)
create table if not exists public.punch_rates (
  id uuid primary key default gen_random_uuid(),
  material_id uuid not null references public.materials_dict(id),
  thickness_mm numeric(10,2) not null,
  cost_pln_per_punch numeric(10,2) not null default 0,
  default_enabled boolean not null default true,
  unique(material_id, thickness_mm)
);

4.5 Koszty na zlecenie/ofertę + per arkusz
create table if not exists public.job_cost_overrides (
  id uuid primary key default gen_random_uuid(),
  source_type text not null check (source_type in ('order','quotation')),
  source_id uuid not null,

  tech_cost_pln numeric(10,2) not null default 0,
  packaging_cost_pln numeric(10,2) not null default 0,
  transport_cost_pln numeric(10,2) not null default 0,

  operational_cost_per_sheet_pln numeric(10,2) not null default 40,

  include_piercing boolean not null default true,
  include_foil_removal boolean not null default false,
  include_punch boolean not null default false,

  updated_at timestamptz not null default now(),
  unique(source_type, source_id)
);

4.6 Rejestr uruchomień nestingu i wyników kosztowania
create table if not exists public.nesting_runs (
  id uuid primary key default gen_random_uuid(),
  source_type text not null check (source_type in ('order','quotation')),
  source_id uuid not null,
  machine_profile_id uuid not null references public.machine_profiles(id),

  created_at timestamptz not null default now(),
  created_by text null,

  nesting_result jsonb not null default '{}'::jsonb,
  preview_image_paths jsonb not null default '[]'::jsonb,

  cost_summary jsonb not null default '{}'::jsonb,
  is_active boolean not null default true
);

create index if not exists idx_nesting_runs_source
  on public.nesting_runs(source_type, source_id, created_at desc);

5) Czas cięcia (variant B): lookahead + trapez + naroża
5.1 Corner model (MVP)
import math

def corner_speed_limit(angle_deg: float, v_corner_90: float, v_max: float) -> float:
    # angle_deg: 0=zwrot wstecz, 180=prosto
    a = max(0.0, min(180.0, angle_deg))
    if a >= 179.0:
        return v_max
    scale = 1.0 + (a - 90.0) / 90.0   # 90° => 1.0; 180° => 2.0
    return min(v_max, v_corner_90 * max(0.2, scale))

5.2 Forward-backward pass
import math

def plan_speeds(L, V_junction, v_max, a_max):
    n = len(L)
    V = [0.0]*(n+1)
    V[0] = 0.0

    # forward
    for k in range(1, n):
        V_reach = math.sqrt(V[k-1]**2 + 2*a_max*L[k-1])
        V[k] = min(V_reach, V_junction[k], v_max)

    V[n] = 0.0

    # backward
    for k in reversed(range(0, n)):
        V_reach = math.sqrt(V[k+1]**2 + 2*a_max*L[k])
        V[k] = min(V[k], V_reach)

    return V

5.3 Czas segmentu trapezowego
import math

def segment_time_trapezoid(L, Vs, Ve, v_max, a):
    v_peak_sq = a*L + 0.5*(Vs*Vs + Ve*Ve)
    v_peak = min(v_max, math.sqrt(max(0.0, v_peak_sq)))

    t1 = max(0.0, (v_peak - Vs)/a)
    t3 = max(0.0, (v_peak - Ve)/a)

    s1 = max(0.0, (v_peak*v_peak - Vs*Vs)/(2*a))
    s3 = max(0.0, (v_peak*v_peak - Ve*Ve)/(2*a))
    s2 = max(0.0, L - s1 - s3)

    t2 = s2 / max(1e-9, v_peak)
    return t1 + t2 + t3

5.4 Penalizacja „małych segmentów”
def effective_vmax(v_max, short_ratio, k=0.7):
    return max(0.3*v_max, v_max*(1.0 - k*short_ratio))

5.5 Czas arkusza (B)
cut_time_s     = sum(segment_time_trapezoid(...))                      // laser ON
pierce_time_s  = pierce_count * piercing_rates.pierce_time_s
foil_time_s    = (foil_distance_m / foil_speed_m_min) * 60  (lub per m²)
total_time_s   = (cut_time_s + pierce_time_s + foil_time_s) * 1.25     // buffer
laser_cost_pln = (total_time_s/3600) * machine_rate_pln_per_h

6) Materiał: koszt arkusza i alokacja na detale
6.1 Sheet area used

FIXED_SHEET: area = width * length_nominal

CUT_TO_LENGTH: area = width * (used_length_y + trim_margin_y)

6.2 Koszt arkusza

Wspieraj (1) lub (2):

PLN/m²: sheet_cost = area_m2 * price_pln_per_m2

PLN/kg: mass = area_m2 * thickness_m * density_kg_m3, sheet_cost = mass * price_pln_per_kg

6.3 Rekomendowana alokacja (domyślna)
part_material_cost = sheet_cost * occupied_area_part / Σ occupied_area_parts

6.4 Legacy (utilization factor) – opcja
util = Σ occupied_area_parts / sheet_area_used
part_material_cost = (occupied_area_part * (sheet_cost/sheet_area_used)) / util

7) Kosztorys A/B: format output (cost_summary)

W nesting_runs.cost_summary zapisuj:

allocation_model, buffer_factor, machine_profile_id

variant_a i variant_b totals + breakdown per sheet + per part_instance

Przykład (fragment):

{
  "allocation_model": "OCCUPIED_AREA",
  "buffer_factor": 1.25,
  "variant_a": {"total_pln": 1234.56, "sheets":[...], "job_costs": {...}},
  "variant_b": {"total_pln": 1400.00, "sheets":[...], "job_costs": {...}},
  "per_part": {
    "instance_id_1": {"material_cost": 12.3, "cut_cost_a": 5.4, "cut_cost_b": 6.1},
    "instance_id_2": {"material_cost": 4.2, "cut_cost_a": 2.1, "cut_cost_b": 3.0}
  }
}

8) GUI „Nesting” w głównym oknie – komplet wymagań
8.1 Okno i nawigacja

Dodaj w głównym oknie pozycję menu / przycisk: Nesting

Widok Nesting uruchamia się fullscreen (100% ekranu); przycisk „Wyjdź z fullscreen” w prawym górnym rogu.

8.2 Układ 3-panelowy (zalecany)

[A] Lewy panel – Kontekst + lista detali

Przełącznik: Oferta / Zamówienie

Wybór konkretnego obiektu (dropdown + wyszukiwarka)

Lista pozycji:

miniatura 60×60 (jeśli jest)

idx_code, name

materiał, grubość, qty

status danych (OK / Braki)

Przyciski:

Odśwież pozycje

Usuń pozycję z nestingu (lokalnie)

(opcjonalnie) Eksport CSV pozycji

[B] Środkowy panel – Arkusze + podgląd

Lista arkuszy (accordion):

materiał / grubość / format

used_length_y (dla CUT_TO_LENGTH)

utilization

liczba detali

Podgląd arkusza (PNG)

Przyciski:

Run Nesting

Re-run Nesting

Zapisz obraz podglądu (opcjonalnie)

[C] Prawy panel – Parametry kosztów + wyniki

Checkboxy:

Uwzględnij przebicia (pierce) [default: TRUE]

Uwzględnij usuwanie folii [default: inox<=5mm TRUE, inaczej FALSE]

Uwzględnij punch [default: FALSE/TRUE wg firmy]

Koszty na zlecenie/ofertę:

Koszty technologii (PLN)

Koszty opakowań (PLN)

Koszty transportu (PLN)

Koszty per arkusz:

Operacyjne / arkusz (PLN) [default: 40]

Model alokacji materiału:

Occupied area (default)

Legacy utilization factor

Tryb arkusza:

FIXED_SHEET / CUT_TO_LENGTH

Margines Y [mm] (default: 10)

Buffer factor:

1.25 (default)

Wyniki:

Wariant A: total + breakdown

Wariant B: total + breakdown

Przyciski:

Przelicz koszty

Zapisz do Supabase (nesting_runs)

(opcjonalnie) Ustaw jako cenę oferty/zamówienia

8.3 UX i walidacje

Jeśli w pozycjach brak material_id lub thickness_mm → blokuj Run Nesting i pokaż listę braków.

Jeśli brak stawek w DB (piercing_rates) → ostrzeż i użyj fallbacku (np. interpolacja po grubości lub domyślna wartość).

Przeliczanie asynchroniczne (UI nie zawiesza się):

progressbar + log 1–2 linijki „co liczymy”.

9) Flow integracji Nesting ↔ Costing (bez DXF przy każdym przeliczeniu)

Load: user wybiera order/quotation → UI pobiera pozycje i grupuje wg (material, thickness).

Nesting: run_nesting() zwraca NestingResult + preview per sheet.

Cache stats:

dla każdego part_id sprawdź product_toolpath_cache po cad_2d_hash

jeśli brak → pobierz DXF, policz stats, zapisz do cache

Costing liczy A/B na podstawie NestingResult + cache + stawki + job_overrides.

UI pozwala zmieniać checkboxy/pola i przeliczać bez ponownego pobierania DXF.

Save: zapis do nesting_runs (nesting_result, preview_image_paths, cost_summary) + opcjonalnie update ceny order/quotation.

Appendix: jednostki

m/min → mm/s: v_mm_s = v_m_min * 1000 / 60

mm² → m²: area_m2 = area_mm2 / 1_000_000

mm → m: t_m = thickness_mm / 1000


