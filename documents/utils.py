"""
Documents Utilities
===================
Funkcje pomocnicze do formatowania i konwersji danych.
"""

from decimal import Decimal
from typing import Optional
import re


def format_currency(value: Optional[Decimal], currency: str = "PLN") -> str:
    """
    Formatuje kwote do formatu polskiego: 1 234,56 PLN

    Args:
        value: Kwota do sformatowania
        currency: Kod waluty (domyslnie PLN)

    Returns:
        Sformatowany string z kwota
    """
    if value is None:
        return ""

    # Konwersja na Decimal jesli potrzeba
    if not isinstance(value, Decimal):
        value = Decimal(str(value))

    # Formatowanie: 1234.56 -> 1 234,56
    formatted = "{:,.2f}".format(float(value))
    # Zamiana separatorow (angielski -> polski)
    formatted = formatted.replace(",", " ")  # Separator tysiecy: spacja
    formatted = formatted.replace(".", ",")  # Separator dziesietny: przecinek

    return f"{formatted} {currency}"


def format_date_pl(date_obj) -> str:
    """
    Formatuje date do formatu polskiego: dd.mm.yyyy

    Args:
        date_obj: Obiekt date lub string

    Returns:
        Data w formacie polskim
    """
    if date_obj is None:
        return ""

    if hasattr(date_obj, 'strftime'):
        return date_obj.strftime('%d.%m.%Y')

    # Jesli to string w formacie ISO
    if isinstance(date_obj, str):
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(date_obj.replace('Z', '+00:00'))
            return dt.strftime('%d.%m.%Y')
        except:
            return date_obj

    return str(date_obj)


# Slownik dla liczb slownie (uproszczony)
JEDNOSCI = ['', 'jeden', 'dwa', 'trzy', 'cztery', 'piec', 'szesc', 'siedem', 'osiem', 'dziewiec']
NASTKI = ['dziesiec', 'jedenascie', 'dwanascie', 'trzynascie', 'czternascie',
          'pietnascie', 'szesnascie', 'siedemnascie', 'osiemnascie', 'dziewietnascie']
DZIESIATKI = ['', 'dziesiec', 'dwadziescia', 'trzydziesci', 'czterdziesci',
              'piecdziesiat', 'szescdziesiat', 'siedemdziesiat', 'osiemdziesiat', 'dziewiecdziesiat']
SETKI = ['', 'sto', 'dwiescie', 'trzysta', 'czterysta',
         'piecset', 'szescset', 'siedemset', 'osiemset', 'dziewiecset']


def _liczba_slownie_99(n: int) -> str:
    """Konwertuje liczbe 0-99 na slownie"""
    if n == 0:
        return ''
    elif n < 10:
        return JEDNOSCI[n]
    elif n < 20:
        return NASTKI[n - 10]
    else:
        d = n // 10
        j = n % 10
        if j == 0:
            return DZIESIATKI[d]
        return f"{DZIESIATKI[d]} {JEDNOSCI[j]}"


def _liczba_slownie_999(n: int) -> str:
    """Konwertuje liczbe 0-999 na slownie"""
    if n == 0:
        return ''
    s = n // 100
    reszta = n % 100

    if s == 0:
        return _liczba_slownie_99(reszta)
    elif reszta == 0:
        return SETKI[s]
    else:
        return f"{SETKI[s]} {_liczba_slownie_99(reszta)}"


def _odmiana(n: int, jeden: str, dwa_cztery: str, wiele: str) -> str:
    """Zwraca odpowiednia odmiane rzeczownika"""
    if n == 1:
        return jeden
    elif 2 <= n % 10 <= 4 and (n % 100 < 10 or n % 100 >= 20):
        return dwa_cztery
    else:
        return wiele


def number_to_text_pl(number: Decimal, currency: str = "PLN") -> str:
    """
    Konwertuje kwote na zapis slowny po polsku.

    Args:
        number: Kwota do konwersji
        currency: Kod waluty

    Returns:
        Kwota slownie, np. "jeden tysiac dwiescie trzydziesci cztery zlote 56/100"
    """
    if number is None:
        return ""

    # Konwersja na Decimal
    if not isinstance(number, Decimal):
        number = Decimal(str(number))

    # Rozdziel na czesc calkowita i grosze
    calkowita = int(number)
    grosze = int((number - calkowita) * 100)

    if calkowita == 0:
        slownie = "zero"
    else:
        czesci = []

        # Miliony
        miliony = calkowita // 1000000
        if miliony > 0:
            if miliony == 1:
                czesci.append("jeden milion")
            else:
                czesci.append(f"{_liczba_slownie_999(miliony)} {_odmiana(miliony, 'milion', 'miliony', 'milionow')}")
            calkowita %= 1000000

        # Tysiace
        tysiace = calkowita // 1000
        if tysiace > 0:
            if tysiace == 1:
                czesci.append("jeden tysiac")
            else:
                czesci.append(f"{_liczba_slownie_999(tysiace)} {_odmiana(tysiace, 'tysiac', 'tysiace', 'tysiecy')}")
            calkowita %= 1000

        # Reszta (0-999)
        if calkowita > 0:
            czesci.append(_liczba_slownie_999(calkowita))

        slownie = ' '.join(czesci)

    # Waluta
    if currency == "PLN":
        calkowita_original = int(number)
        waluta = _odmiana(calkowita_original, 'zloty', 'zlote', 'zlotych')
        return f"{slownie} {waluta} {grosze:02d}/100"
    elif currency == "EUR":
        return f"{slownie} euro {grosze:02d}/100"
    elif currency == "USD":
        return f"{slownie} dolarow {grosze:02d}/100"
    else:
        return f"{slownie} {currency} {grosze:02d}/100"


def sanitize_filename(filename: str) -> str:
    """
    Usuwa niedozwolone znaki z nazwy pliku.

    Args:
        filename: Nazwa pliku do oczyszczenia

    Returns:
        Bezpieczna nazwa pliku
    """
    # Zamien / na _
    filename = filename.replace('/', '_')
    # Usun inne niedozwolone znaki
    filename = re.sub(r'[<>:"|?*\\]', '', filename)
    # Usun podwojne spacje
    filename = re.sub(r'\s+', ' ', filename)
    return filename.strip()


def generate_document_path(doc_type: str, year: int, doc_number: str) -> str:
    """
    Generuje sciezke do pliku w storage.

    Args:
        doc_type: Typ dokumentu
        year: Rok
        doc_number: Numer dokumentu

    Returns:
        Sciezka w formacie: documents/QUOTATION/2025/QUOTATION_2025_000001.pdf
    """
    safe_number = sanitize_filename(doc_number)
    return f"documents/{doc_type}/{year}/{safe_number}.pdf"
