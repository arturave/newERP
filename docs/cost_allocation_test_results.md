# Raport Testów Modeli Alokacji Kosztów

**Data:** 2025-12-09 17:06:29

## Modele wyceny

| Model | Opis |
|-------|------|
| **PRE-NESTING (BBox)** | Materiał = bounding box + 35% naddatek, bez nestingu |
| **POST-NESTING Proporcjonalny** | Arkusz przycięty do maxY, koszt proporcjonalnie do contour_area |
| **POST-NESTING BBox** | Arkusz przycięty do maxY, koszt równo na każdy detal |

## Wyniki testów

### Test 1: S235 2mm (5 detali)

- **Materiał:** S235 / 2.0mm
- **Detale:** 5 typów, 12 szt łącznie

- **Arkusze użyte:** 1
- **Efektywność:** 24.9%

| Składnik | PRE-NESTING | POST-PROP | POST-BBOX |
|----------|-------------|-----------|-----------|
| Materiał | 4.04 | 12.01 | 12.01 |
| Cięcie | 2.69 | 2.69 | 2.69 |
| Przebicia | 1.80 | 1.80 | 1.80 |
| Folia | - | - | - |
| Operacyjne | 40.00 | 40.00 | 40.00 |
| **RAZEM** | **48.53** | **56.50** | **56.50** |

**Oszczędność (proporcjonalny vs pre-nesting):** -7.97 PLN (-16.4%)
**Oszczędność (bbox vs pre-nesting):** -7.97 PLN (-16.4%)

#### Koszty jednostkowe (top 5)

| Detal | PRE-NESTING | POST-PROP | POST-BBOX | Różnica |
|-------|-------------|-----------|-----------|---------|
| Part_02_108x97 | 1.67 | 3.86 | 1.56 | +2.30 |
| Part_03_67x57 | 0.80 | 1.60 | 1.40 | +0.20 |
| Part_05_65x42 | 0.65 | 1.22 | 1.36 | -0.14 |
| Part_01_31x77 | 0.62 | 1.12 | 1.37 | -0.25 |
| Part_04_35x43 | 0.47 | 0.78 | 1.31 | -0.53 |

### Test 2: INOX 3mm (10 detali)

- **Materiał:** 1.4301 / 3.0mm
- **Detale:** 10 typów, 29 szt łącznie

- **Arkusze użyte:** 1
- **Efektywność:** 84.6%

| Składnik | PRE-NESTING | POST-PROP | POST-BBOX |
|----------|-------------|-----------|-----------|
| Materiał | 789.89 | 691.73 | 691.73 |
| Cięcie | 54.63 | 54.63 | 54.63 |
| Przebicia | 8.70 | 8.70 | 8.70 |
| Folia | 2.93 | 2.93 | 2.93 |
| Operacyjne | 40.00 | 40.00 | 40.00 |
| **RAZEM** | **896.15** | **797.99** | **797.99** |

**Oszczędność (proporcjonalny vs pre-nesting):** 98.16 PLN (11.0%)
**Oszczędność (bbox vs pre-nesting):** 98.16 PLN (11.0%)

#### Koszty jednostkowe (top 5)

| Detal | PRE-NESTING | POST-PROP | POST-BBOX | Różnica |
|-------|-------------|-----------|-----------|---------|
| Part_10_420x493 | 124.93 | 110.12 | 29.54 | +80.58 |
| Part_03_374x226 | 52.52 | 46.47 | 27.69 | +18.78 |
| Part_02_255x219 | 35.26 | 31.26 | 26.95 | +4.31 |
| Part_09_181x196 | 22.96 | 20.42 | 26.38 | -5.96 |
| Part_04_123x151 | 12.61 | 11.28 | 25.77 | -14.49 |

### Test 3: ALU 4mm (20 detali)

- **Materiał:** ALU / 4.0mm
- **Detale:** 20 typów, 60 szt łącznie

- **Arkusze użyte:** 3
- **Efektywność:** 85.2%

| Składnik | PRE-NESTING | POST-PROP | POST-BBOX |
|----------|-------------|-----------|-----------|
| Materiał | 1476.03 | 1283.23 | 1283.23 |
| Cięcie | 130.37 | 130.37 | 130.37 |
| Przebicia | 12.00 | 12.00 | 12.00 |
| Folia | - | - | - |
| Operacyjne | 40.00 | 120.00 | 120.00 |
| **RAZEM** | **1658.40** | **1545.60** | **1545.60** |

**Oszczędność (proporcjonalny vs pre-nesting):** 112.80 PLN (6.8%)
**Oszczędność (bbox vs pre-nesting):** 112.80 PLN (6.8%)

#### Koszty jednostkowe (top 5)

| Detal | PRE-NESTING | POST-PROP | POST-BBOX | Różnica |
|-------|-------------|-----------|-----------|---------|
| Part_02_906x955 | 159.02 | 124.00 | 26.43 | +97.58 |
| Part_01_994x738 | 135.47 | 110.04 | 26.42 | +83.62 |
| Part_07_916x673 | 114.41 | 103.77 | 27.38 | +76.39 |
| Part_14_821x518 | 79.96 | 70.15 | 25.87 | +44.28 |
| Part_09_602x681 | 77.06 | 96.66 | 74.74 | +21.91 |

### Test 4: S235 8mm (30 detali)

- **Materiał:** S235 / 8.0mm
- **Detale:** 30 typów, 78 szt łącznie

- **Arkusze użyte:** 4
- **Efektywność:** 89.9%

| Składnik | PRE-NESTING | POST-PROP | POST-BBOX |
|----------|-------------|-----------|-----------|
| Materiał | 6632.22 | 5464.07 | 5464.07 |
| Cięcie | 318.82 | 318.82 | 318.82 |
| Przebicia | 11.70 | 11.70 | 11.70 |
| Folia | - | - | - |
| Operacyjne | 40.00 | 160.00 | 160.00 |
| **RAZEM** | **7002.74** | **5954.59** | **5954.59** |

**Oszczędność (proporcjonalny vs pre-nesting):** 1048.14 PLN (15.0%)
**Oszczędność (bbox vs pre-nesting):** 1048.14 PLN (15.0%)

#### Koszty jednostkowe (top 5)

| Detal | PRE-NESTING | POST-PROP | POST-BBOX | Różnica |
|-------|-------------|-----------|-----------|---------|
| Part_19_988x840 | 362.92 | 281.82 | 59.81 | +222.01 |
| Part_20_995x770 | 335.51 | 260.64 | 59.43 | +201.21 |
| Part_13_925x803 | 325.38 | 267.08 | 98.65 | +168.43 |
| Part_01_861x826 | 311.74 | 260.99 | 166.59 | +94.39 |
| Part_22_708x924 | 287.25 | 223.32 | 58.63 | +164.69 |

### Test 5: INOX 1.5mm (15 detali)

- **Materiał:** 1.4301 / 1.5mm
- **Detale:** 15 typów, 46 szt łącznie

- **Arkusze użyte:** 3
- **Efektywność:** 78.1%

| Składnik | PRE-NESTING | POST-PROP | POST-BBOX |
|----------|-------------|-----------|-----------|
| Materiał | 2849.31 | 2701.98 | 2701.98 |
| Cięcie | 96.65 | 96.65 | 96.65 |
| Przebicia | 13.80 | 13.80 | 13.80 |
| Folia | 9.67 | 9.67 | 9.67 |
| Operacyjne | 40.00 | 120.00 | 120.00 |
| **RAZEM** | **3009.43** | **2942.09** | **2942.09** |

**Oszczędność (proporcjonalny vs pre-nesting):** 67.34 PLN (2.2%)
**Oszczędność (bbox vs pre-nesting):** 67.34 PLN (2.2%)

#### Koszty jednostkowe (top 5)

| Detal | PRE-NESTING | POST-PROP | POST-BBOX | Różnica |
|-------|-------------|-----------|-----------|---------|
| Part_14_907x958 | 256.66 | 201.02 | 41.98 | +159.04 |
| Part_05_950x901 | 252.88 | 235.90 | 65.86 | +170.04 |
| Part_10_958x856 | 242.42 | 289.27 | 202.00 | +87.27 |
| Part_12_507x883 | 133.80 | 105.13 | 40.41 | +64.72 |
| Part_02_747x567 | 126.60 | 128.26 | 124.25 | +4.01 |

## Walidacja ekonomiczna

✅ **Wszystkie testy przeszły walidację**

### Obserwacje
- Test 1: S235 2mm (5 detali): Małe zamówienie (12 szt) - PRE-NESTING tańszy o -7.97 PLN
- Test 1: S235 2mm (5 detali): Efektywność nestingu: 24.9%
- Test 1: S235 2mm (5 detali): UWAGA - post-nesting materiał droższy o 7.97 PLN
- Test 1: S235 2mm (5 detali): Alokacja OK - mały detal tańszy w proporcjonalnym
- Test 1: S235 2mm (5 detali): Alokacja OK - duży detal droższy w proporcjonalnym
- Test 2: INOX 3mm (10 detali): Efektywność nestingu: 84.6%
- Test 2: INOX 3mm (10 detali): Oszczędność materiału: 12.4%
- Test 2: INOX 3mm (10 detali): Alokacja OK - mały detal tańszy w proporcjonalnym
- Test 2: INOX 3mm (10 detali): Alokacja OK - duży detal droższy w proporcjonalnym
- Test 3: ALU 4mm (20 detali): Efektywność nestingu: 85.2%
- Test 3: ALU 4mm (20 detali): Oszczędność materiału: 13.1%
- Test 3: ALU 4mm (20 detali): Alokacja OK - mały detal tańszy w proporcjonalnym
- Test 3: ALU 4mm (20 detali): Alokacja OK - duży detal droższy w proporcjonalnym
- Test 4: S235 8mm (30 detali): Efektywność nestingu: 89.9%
- Test 4: S235 8mm (30 detali): Oszczędność materiału: 17.6%
- Test 4: S235 8mm (30 detali): Alokacja OK - mały detal tańszy w proporcjonalnym
- Test 4: S235 8mm (30 detali): Alokacja OK - duży detal droższy w proporcjonalnym
- Test 5: INOX 1.5mm (15 detali): Efektywność nestingu: 78.1%
- Test 5: INOX 1.5mm (15 detali): Oszczędność materiału: 5.2%
- Test 5: INOX 1.5mm (15 detali): Alokacja OK - mały detal tańszy w proporcjonalnym
- Test 5: INOX 1.5mm (15 detali): Alokacja OK - duży detal droższy w proporcjonalnym

## Wnioski

1. **Nesting znacząco redukuje koszty materiału** - przycięcie arkusza do maxY eliminuje odpad
2. **Model proporcjonalny** lepiej odzwierciedla rzeczywiste zużycie materiału dla detali o różnych rozmiarach
3. **Model bbox (równy podział)** faworyzuje duże detale kosztem małych
4. **Koszty cięcia są identyczne** między modelami - zależą tylko od geometrii
