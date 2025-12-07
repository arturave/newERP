# Model Obliczania Kosztow - NewERP
## Dokumentacja Techniczna v1.0

---

## 1. Przeglad Modelu

System obliczania kosztow dla wycen ciecia laserowego oparty jest na nastepujacych skladnikach:

### Skladniki Kosztu Produkcji (per detal)

| Skladnik | Jednostka | Zrodlo danych |
|----------|-----------|---------------|
| **Material** | PLN/kg | `materials_prices.xlsx` + gestosc |
| **Ciecie** | PLN/m | `cutting_prices.xlsx` |
| **Grawer** | PLN/m | DEFAULT_RATES (2.50 PLN/m) |
| **Usuwanie folii** | PLN/m | Supabase `cost_config` (0.20 PLN/m) |
| **Przebicia (piercing)** | PLN/szt | DEFAULT_RATES per material/grubosc |
| **Giecie** | PLN/giecie | DEFAULT_RATES (3.00 PLN/giecie) |

### Koszty Per Arkusz

| Skladnik | Wartosc domyslna | Opis |
|----------|------------------|------|
| **Operacyjne** | 40.00 PLN/arkusz | Załadunek/rozładunek arkusza |

### Koszty Per Zlecenie

| Skladnik | Wartosc domyslna | Opis |
|----------|------------------|------|
| **Technologia** | 50.00 PLN | Programowanie CNC |
| **Opakowania** | 100.00 PLN | Pakowanie |
| **Transport** | 0.00 PLN | Opcjonalny |

---

## 2. Formuly Obliczen

### 2.1 Koszt Materialu

```
koszt_materialu = waga_kg × cena_PLN_per_kg

gdzie:
  waga_kg = (szerokosc_mm × wysokosc_mm × grubosc_mm / 1e9) × gestosc_kg_m3
```

**Gestosci materialow:**
- Stal (S235, S355, DC01): 7850 kg/m³
- INOX (1.4301, 1.4404): 7900 kg/m³
- Aluminium: 2700 kg/m³

### 2.2 Koszt Ciecia

```
koszt_ciecia = dlugosc_ciecia_m × stawka_PLN_per_m
```

Stawki pobierane z `cutting_prices.xlsx` lub DEFAULT_RATES:
- Stal 3mm: ~1.20 PLN/m
- INOX 3mm: ~2.80 PLN/m
- Aluminium 3mm: ~2.00 PLN/m

### 2.3 Koszt Graweru

```
koszt_graweru = dlugosc_graweru_m × 2.50 PLN/m
```

### 2.4 Koszt Usuwania Folii (NOWE!)

**Warunki wlaczenia:**
- Material: INOX (1.4301, 1.4404, stainless)
- Grubosc: <= 5.0 mm
- Checkbox `include_foil_removal` = True

```
koszt_folii = (dlugosc_ciecia_m + dlugosc_graweru_m) × stawka_foil_PLN_per_m

gdzie:
  stawka_foil = 0.20 PLN/m (z Supabase cost_config.foil_cost_per_meter)
```

### 2.5 Koszt Przebic (Piercing)

```
koszt_przebic = liczba_przebic × stawka_PLN_per_przebicie
```

Liczba przebic = 1 (kontur glowny) + liczba_otworow

Stawki per material i grubosc (PLN):
| Grubosc | Stal | INOX | Aluminium |
|---------|------|------|-----------|
| 1mm | 0.10 | 0.15 | 0.12 |
| 2mm | 0.15 | 0.25 | 0.18 |
| 3mm | 0.20 | 0.40 | 0.25 |
| 5mm | 0.40 | 0.85 | 0.50 |
| 8mm | 0.80 | 1.50 | 1.00 |
| 10mm | 1.10 | 2.00 | 1.40 |

### 2.6 Koszt Giecia

```
koszt_giecia = liczba_giec × stawka_PLN_per_giecie

gdzie:
  stawka = 3.00 PLN/giecie (DEFAULT)
```

### 2.7 Koszt Operacyjny Per Arkusz

```
koszt_operacyjny = liczba_arkuszy × 40.00 PLN
```

### 2.8 Suma Calkowita

```
KOSZT_PRODUKCJI = suma(koszt_detali) + koszt_operacyjny

KOSZT_CALKOWITY = KOSZT_PRODUKCJI + technologia + opakowania + transport

KOSZT_Z_MARZA = KOSZT_CALKOWITY × (1 + marza_procent / 100)
```

---

## 3. Modele Alokacji Kosztu Materialu

Po nestingu koszt materialu arkusza moze byc alokowany na detale wg jednego z modeli:

### 3.1 Proporcjonalny (PROPORTIONAL) - domyslny

```
koszt_detalu = koszt_arkusza × (powierzchnia_detalu / suma_powierzchni)
```

### 3.2 Jednostkowy (PER_UNIT)

```
koszt_detalu = koszt_arkusza / liczba_detali
```

### 3.3 Na Arkusz (PER_SHEET)

```
koszt_detalu = koszt_arkusza  (kazdy detal ponosi pelny koszt)
```

---

## 4. Przyklady Wycen

### Przyklad 1: Prosty detal INOX

**Dane wejsciowe:**
- Material: 1.4301 (INOX)
- Grubosc: 2.0 mm
- Wymiary: 200 x 150 mm
- Dlugosc ciecia: 700 mm (obwod)
- Grawer: 0 mm
- Otwory: 2 (piercing = 3)
- Giecia: 0
- Ilosc: 10 szt

**Obliczenia jednostkowe:**

```
1. Material:
   waga = (0.2 × 0.15 × 0.002) × 7900 = 0.474 kg
   koszt = 0.474 × 18.0 PLN/kg = 8.53 PLN

2. Ciecie:
   koszt = 0.7m × 2.0 PLN/m = 1.40 PLN

3. Grawer:
   koszt = 0 PLN

4. Folia (INOX <= 5mm):
   koszt = 0.7m × 0.20 PLN/m = 0.14 PLN

5. Piercing:
   koszt = 3 × 0.25 PLN = 0.75 PLN

6. Giecie:
   koszt = 0 PLN

RAZEM jednostkowy: 8.53 + 1.40 + 0.14 + 0.75 = 10.82 PLN
RAZEM 10 szt: 108.20 PLN
```

**Koszty dodatkowe:**
```
Operacyjne (1 arkusz): 40.00 PLN
Technologia: 50.00 PLN
Opakowania: 100.00 PLN

KOSZT CALKOWITY: 108.20 + 40.00 + 50.00 + 100.00 = 298.20 PLN
```

---

### Przyklad 2: Zlozony detal stalowy z gieciem

**Dane wejsciowe:**
- Material: S355
- Grubosc: 3.0 mm
- Wymiary: 500 x 300 mm
- Dlugosc ciecia: 2500 mm
- Grawer: 200 mm (napis)
- Otwory: 10 (piercing = 11)
- Giecia: 4
- Ilosc: 5 szt

**Obliczenia jednostkowe:**

```
1. Material:
   waga = (0.5 × 0.3 × 0.003) × 7850 = 3.53 kg
   koszt = 3.53 × 5.0 PLN/kg = 17.65 PLN

2. Ciecie:
   koszt = 2.5m × 1.2 PLN/m = 3.00 PLN

3. Grawer:
   koszt = 0.2m × 2.5 PLN/m = 0.50 PLN

4. Folia (STAL - nie dotyczy):
   koszt = 0.00 PLN

5. Piercing:
   koszt = 11 × 0.20 PLN = 2.20 PLN

6. Giecie:
   koszt = 4 × 3.0 PLN = 12.00 PLN

RAZEM jednostkowy: 17.65 + 3.00 + 0.50 + 2.20 + 12.00 = 35.35 PLN
RAZEM 5 szt: 176.75 PLN
```

**Koszty dodatkowe:**
```
Operacyjne (1 arkusz): 40.00 PLN
Technologia: 50.00 PLN
Opakowania: 100.00 PLN

KOSZT CALKOWITY: 176.75 + 40.00 + 50.00 + 100.00 = 366.75 PLN
```

---

### Przyklad 3: Duze zamowienie z nestingiem

**Dane wejsciowe:**
- Material: 1.4301 (INOX)
- Grubosc: 3.0 mm
- Arkusz: 3000 x 1500 mm
- 3 rozne detale:
  - Detal A: 200x200mm, ciecie 800mm, 2 otwory, 0 giec, qty=50
  - Detal B: 150x100mm, ciecie 500mm, 1 otwor, 2 giecia, qty=100
  - Detal C: 300x250mm, ciecie 1100mm, 5 otworow, 0 giec, qty=25

**Wynik nestingu:**
- Zuzyte arkusze: 3
- Efektywnosc: 72%

**Obliczenia:**

```
=== DETAL A (50 szt) ===
Material: (0.2×0.2×0.003)×7900 × 18.0 = 4.27 PLN/szt
Ciecie: 0.8m × 2.8 PLN/m = 2.24 PLN/szt
Folia: 0.8m × 0.20 PLN/m = 0.16 PLN/szt
Piercing: 3 × 0.40 PLN = 1.20 PLN/szt
Giecie: 0 PLN
RAZEM A: (4.27+2.24+0.16+1.20) × 50 = 393.50 PLN

=== DETAL B (100 szt) ===
Material: (0.15×0.1×0.003)×7900 × 18.0 = 0.64 PLN/szt
Ciecie: 0.5m × 2.8 PLN/m = 1.40 PLN/szt
Folia: 0.5m × 0.20 PLN/m = 0.10 PLN/szt
Piercing: 2 × 0.40 PLN = 0.80 PLN/szt
Giecie: 2 × 3.0 PLN = 6.00 PLN/szt
RAZEM B: (0.64+1.40+0.10+0.80+6.00) × 100 = 894.00 PLN

=== DETAL C (25 szt) ===
Material: (0.3×0.25×0.003)×7900 × 18.0 = 3.20 PLN/szt
Ciecie: 1.1m × 2.8 PLN/m = 3.08 PLN/szt
Folia: 1.1m × 0.20 PLN/m = 0.22 PLN/szt
Piercing: 6 × 0.40 PLN = 2.40 PLN/szt
Giecie: 0 PLN
RAZEM C: (3.20+3.08+0.22+2.40) × 25 = 222.50 PLN

=== PODSUMOWANIE ===
Suma detali: 393.50 + 894.00 + 222.50 = 1510.00 PLN
Operacyjne (3 arkusze): 3 × 40.00 = 120.00 PLN
Technologia: 50.00 PLN
Opakowania: 100.00 PLN

RAZEM PRODUKCJA: 1510.00 + 120.00 = 1630.00 PLN
RAZEM ZLECENIE: 1630.00 + 50.00 + 100.00 = 1780.00 PLN

Z marza 10%: 1780.00 × 1.10 = 1958.00 PLN
```

---

## 5. Parametry Konfiguracyjne

### Supabase Tables

| Tabela | Klucz | Wartosc | Opis |
|--------|-------|---------|------|
| `cost_config` | `foil_cost_per_meter` | 0.20 | PLN/m usuwania folii |
| `cost_config` | `laser_hourly_rate` | 350 | PLN/h (wariant B) |
| `cost_config` | `bending_hourly_rate` | 200 | PLN/h giecia |
| `cost_config` | `time_buffer_percent` | 25 | % buforu czasowego |
| `cost_config` | `default_allocation_model` | bounding_box | Model alokacji |

### Pliki Excel

- `data/pricing/materials_prices.xlsx` - ceny materialow [PLN/kg]
- `data/pricing/cutting_prices.xlsx` - stawki ciecia [PLN/m]

---

## 6. Warianty Wyceny

### Wariant A: Cennikowy (deterministyczny)

Oparty na stalych stawkach PLN/m i PLN/szt.
Zalety: Przewidywalnosc, szybkosc obliczen.

### Wariant B: Czasowy (z buforem)

Oparty na czasie produkcji i stawce godzinowej + 25% buforu.
Zalety: Dokladniejsze dla zlozonych detali.

```
koszt_ciecia_B = (dlugosc_mm / predkosc_mm_min / 60) × stawka_PLN_h × 1.25
```

---

## 7. Historia Zmian

| Wersja | Data | Zmiany |
|--------|------|--------|
| 1.0 | 2025-12-07 | Poczatkowa dokumentacja |
| 1.0 | 2025-12-07 | Zmiana obliczen folii z PLN/m² na PLN/m |

---

*Dokumentacja wygenerowana automatycznie przez CostEngine v1.0*
