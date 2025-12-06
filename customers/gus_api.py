"""
NewERP - GUS API Integration
============================
Integracja z API Głównego Urzędu Statystycznego (BIR1).

Umożliwia pobieranie danych firmy na podstawie NIP, REGON lub KRS.

Rejestracja klucza API (darmowa):
    https://api.stat.gov.pl/Home/RegonApi

Dokumentacja:
    https://api.stat.gov.pl/Home/RegonApiDescription
"""

import re
import logging
from typing import Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum

import requests
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


class GUSEnvironment(Enum):
    """Środowisko API GUS"""
    PRODUCTION = "https://wyszukiwarkaregon.stat.gov.pl/wsBIR/UslugaBIRzewnPubl.svc"
    TEST = "https://wyszukiwarkaregontest.stat.gov.pl/wsBIR/UslugaBIRzewnPubl.svc"


@dataclass
class CompanyData:
    """Dane firmy z GUS"""
    nip: str
    regon: str
    name: str
    short_name: Optional[str] = None
    
    # Adres
    street: Optional[str] = None
    building_number: Optional[str] = None
    apartment_number: Optional[str] = None
    postal_code: Optional[str] = None
    city: Optional[str] = None
    voivodeship: Optional[str] = None  # województwo
    county: Optional[str] = None       # powiat
    commune: Optional[str] = None      # gmina
    
    # Dodatkowe
    krs: Optional[str] = None
    company_type: Optional[str] = None  # forma prawna
    pkd_main: Optional[str] = None      # główne PKD
    pkd_main_name: Optional[str] = None
    start_date: Optional[str] = None    # data rozpoczęcia działalności
    
    # Status
    is_active: bool = True
    termination_date: Optional[str] = None
    
    def to_customer_dict(self) -> Dict[str, Any]:
        """Konwertuj do formatu danych klienta NewERP"""
        return {
            'name': self.name,
            'short_name': self.short_name,
            'nip': self.nip,
            'regon': self.regon,
            'krs': self.krs,
            'address_street': self.street,
            'address_building': self.building_number,
            'address_apartment': self.apartment_number,
            'address_postal_code': self.postal_code,
            'address_city': self.city,
            'type': 'company',
        }


class GUSApiError(Exception):
    """Błąd API GUS"""
    pass


class GUSApi:
    """
    Klient API GUS (BIR1).
    
    Użycie:
        api = GUSApi(api_key="your-key")
        company = api.get_by_nip("1234567890")
        print(company.name, company.address_city)
    
    Klucz testowy (działa tylko na środowisku testowym):
        api_key = "abcde12345abcde12345"
    """
    
    # Klucz testowy GUS (publiczny, tylko do testów)
    TEST_API_KEY = "abcde12345abcde12345"
    
    # SOAP namespaces
    SOAP_NS = "http://schemas.xmlsoap.org/soap/envelope/"
    BIR_NS = "http://CIS/BIR/PUBL/2014/07"
    
    def __init__(
        self, 
        api_key: str = None,
        environment: GUSEnvironment = GUSEnvironment.PRODUCTION,
        timeout: int = 30
    ):
        """
        Inicjalizacja klienta GUS API.
        
        Args:
            api_key: Klucz API (zarejestruj na api.stat.gov.pl)
            environment: PRODUCTION lub TEST
            timeout: Timeout requestów w sekundach
        """
        self.api_key = api_key or self.TEST_API_KEY
        self.environment = environment
        self.timeout = timeout
        self.session_id: Optional[str] = None
        
        # Użyj środowiska testowego dla klucza testowego
        if self.api_key == self.TEST_API_KEY:
            self.environment = GUSEnvironment.TEST
            logger.info("[GUS] Using TEST environment with test API key")
        
        self.base_url = self.environment.value
    
    def _make_soap_request(self, action: str, body: str) -> str:
        """Wykonaj żądanie SOAP"""
        
        envelope = f'''<?xml version="1.0" encoding="utf-8"?>
        <soap:Envelope xmlns:soap="{self.SOAP_NS}" xmlns:ns="{self.BIR_NS}">
            <soap:Header xmlns:wsa="http://www.w3.org/2005/08/addressing">
                <wsa:Action>{action}</wsa:Action>
                <wsa:To>{self.base_url}</wsa:To>
            </soap:Header>
            <soap:Body>
                {body}
            </soap:Body>
        </soap:Envelope>'''
        
        headers = {
            'Content-Type': 'application/soap+xml; charset=utf-8',
        }
        
        # Dodaj session ID jeśli istnieje
        if self.session_id:
            headers['sid'] = self.session_id
        
        try:
            response = requests.post(
                self.base_url,
                data=envelope.encode('utf-8'),
                headers=headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            return response.text
            
        except RequestException as e:
            logger.error(f"[GUS] Request failed: {e}")
            raise GUSApiError(f"Błąd połączenia z GUS: {e}")
    
    def _extract_value(self, xml: str, tag: str) -> Optional[str]:
        """Wyciągnij wartość z XML (proste parsowanie bez lxml)"""
        # Szukaj tagu z namespace lub bez
        patterns = [
            f'<{tag}>([^<]*)</{tag}>',
            f'<[^:]+:{tag}>([^<]*)</[^:]+:{tag}>',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, xml, re.IGNORECASE)
            if match:
                return match.group(1).strip() or None
        
        return None
    
    def login(self) -> bool:
        """
        Zaloguj się do API i uzyskaj session ID.
        
        Returns:
            True jeśli logowanie udane
        """
        action = "http://CIS/BIR/PUBL/2014/07/IUslugaBIRzewnPubl/Zaloguj"
        body = f'<ns:Zaloguj><ns:pKluczUzytkownika>{self.api_key}</ns:pKluczUzytkownika></ns:Zaloguj>'
        
        try:
            response = self._make_soap_request(action, body)
            
            # Wyciągnij session ID
            session_id = self._extract_value(response, 'ZalogujResult')
            
            if session_id:
                self.session_id = session_id
                logger.info(f"[GUS] Logged in, session: {session_id[:8]}...")
                return True
            else:
                logger.error("[GUS] Login failed - no session ID")
                raise GUSApiError("Logowanie nieudane - sprawdź klucz API")
                
        except GUSApiError:
            raise
        except Exception as e:
            logger.error(f"[GUS] Login error: {e}")
            raise GUSApiError(f"Błąd logowania: {e}")
    
    def logout(self) -> bool:
        """Wyloguj z API"""
        if not self.session_id:
            return True
        
        action = "http://CIS/BIR/PUBL/2014/07/IUslugaBIRzewnPubl/Wyloguj"
        body = f'<ns:Wyloguj><ns:pIdentyfikatorSesji>{self.session_id}</ns:pIdentyfikatorSesji></ns:Wyloguj>'
        
        try:
            self._make_soap_request(action, body)
            self.session_id = None
            logger.info("[GUS] Logged out")
            return True
        except Exception as e:
            logger.warning(f"[GUS] Logout error: {e}")
            return False
    
    def _ensure_logged_in(self):
        """Upewnij się że jesteśmy zalogowani"""
        if not self.session_id:
            self.login()
    
    def _search(self, search_params: str) -> Optional[str]:
        """
        Wyszukaj podmiot w rejestrze.
        
        Args:
            search_params: Parametry wyszukiwania XML
            
        Returns:
            XML z wynikami lub None
        """
        self._ensure_logged_in()
        
        action = "http://CIS/BIR/PUBL/2014/07/IUslugaBIRzewnPubl/DaneSzukajPodmioty"
        body = f'''<ns:DaneSzukajPodmioty>
            <ns:pParametryWyszukiwania>
                {search_params}
            </ns:pParametryWyszukiwania>
        </ns:DaneSzukajPodmioty>'''
        
        response = self._make_soap_request(action, body)
        
        # Wyciągnij wynik
        result = self._extract_value(response, 'DaneSzukajPodmiotyResult')
        
        if not result or 'ErrorCode' in result:
            return None
        
        return result
    
    def _parse_company_data(self, xml: str) -> Optional[CompanyData]:
        """Parsuj dane firmy z XML"""
        
        # Podstawowe dane
        nip = self._extract_value(xml, 'Nip')
        regon = self._extract_value(xml, 'Regon')
        name = self._extract_value(xml, 'Nazwa')
        
        if not name:
            return None
        
        # Adres
        street = self._extract_value(xml, 'Ulica')
        building = self._extract_value(xml, 'NrNieruchomosci')
        apartment = self._extract_value(xml, 'NrLokalu')
        postal_code = self._extract_value(xml, 'KodPocztowy')
        city = self._extract_value(xml, 'Miejscowosc')
        voivodeship = self._extract_value(xml, 'Wojewodztwo')
        county = self._extract_value(xml, 'Powiat')
        commune = self._extract_value(xml, 'Gmina')
        
        # Dodatkowe
        krs = self._extract_value(xml, 'NumerWRejestrzeEwidencji')
        company_type = self._extract_value(xml, 'FormaPrawna')
        pkd_main = self._extract_value(xml, 'KodPkd')
        start_date = self._extract_value(xml, 'DataPowstania')
        termination_date = self._extract_value(xml, 'DataZakonczeniaDzialalnosci')
        
        # Status
        status = self._extract_value(xml, 'Status')
        is_active = status != 'Z' if status else True  # Z = zakończona działalność
        
        return CompanyData(
            nip=nip or '',
            regon=regon or '',
            name=name,
            short_name=self._generate_short_name(name),
            street=street,
            building_number=building,
            apartment_number=apartment,
            postal_code=postal_code,
            city=city,
            voivodeship=voivodeship,
            county=county,
            commune=commune,
            krs=krs,
            company_type=company_type,
            pkd_main=pkd_main,
            start_date=start_date,
            is_active=is_active,
            termination_date=termination_date
        )
    
    def _generate_short_name(self, name: str, max_length: int = 30) -> str:
        """Generuj krótką nazwę"""
        # Usuń typowe przyrostki
        suffixes = [
            r'\s+sp\.?\s*z\s*o\.?\s*o\.?',
            r'\s+sp\.?\s*j\.?',
            r'\s+s\.?\s*a\.?',
            r'\s+spółka\s+z\s+ograniczoną\s+odpowiedzialnością',
            r'\s+spółka\s+akcyjna',
            r'\s+spółka\s+jawna',
            r'\s+spółka\s+komandytowa',
            r'\s+sp\.?\s*k\.?',
        ]
        
        short = name
        for suffix in suffixes:
            short = re.sub(suffix, '', short, flags=re.IGNORECASE)
        
        short = short.strip()
        if len(short) > max_length:
            space_pos = short.rfind(' ', 0, max_length)
            if space_pos > 10:
                short = short[:space_pos]
            else:
                short = short[:max_length]
        
        return short.strip()
    
    # ============================================================
    # Public API Methods
    # ============================================================
    
    def get_by_nip(self, nip: str) -> Optional[CompanyData]:
        """
        Pobierz dane firmy po NIP.
        
        Args:
            nip: Numer NIP (10 cyfr, z lub bez myślników)
            
        Returns:
            CompanyData lub None jeśli nie znaleziono
        """
        # Normalizuj NIP
        nip = re.sub(r'[\s\-]', '', nip)
        
        if len(nip) != 10 or not nip.isdigit():
            raise GUSApiError(f"Nieprawidłowy NIP: {nip}")
        
        logger.info(f"[GUS] Searching by NIP: {nip}")
        
        search_params = f'<dat:Nip xmlns:dat="http://CIS/BIR/PUBL/2014/07/DataContract">{nip}</dat:Nip>'
        
        result = self._search(search_params)
        
        if not result:
            logger.info(f"[GUS] No results for NIP: {nip}")
            return None
        
        return self._parse_company_data(result)
    
    def get_by_regon(self, regon: str) -> Optional[CompanyData]:
        """
        Pobierz dane firmy po REGON.
        
        Args:
            regon: Numer REGON (9 lub 14 cyfr)
            
        Returns:
            CompanyData lub None jeśli nie znaleziono
        """
        # Normalizuj REGON
        regon = re.sub(r'[\s\-]', '', regon)
        
        if len(regon) not in (9, 14) or not regon.isdigit():
            raise GUSApiError(f"Nieprawidłowy REGON: {regon}")
        
        logger.info(f"[GUS] Searching by REGON: {regon}")
        
        if len(regon) == 9:
            search_params = f'<dat:Regon xmlns:dat="http://CIS/BIR/PUBL/2014/07/DataContract">{regon}</dat:Regon>'
        else:
            search_params = f'<dat:Regon14 xmlns:dat="http://CIS/BIR/PUBL/2014/07/DataContract">{regon}</dat:Regon14>'
        
        result = self._search(search_params)
        
        if not result:
            logger.info(f"[GUS] No results for REGON: {regon}")
            return None
        
        return self._parse_company_data(result)
    
    def get_by_krs(self, krs: str) -> Optional[CompanyData]:
        """
        Pobierz dane firmy po KRS.
        
        Args:
            krs: Numer KRS (10 cyfr)
            
        Returns:
            CompanyData lub None jeśli nie znaleziono
        """
        # Normalizuj KRS
        krs = re.sub(r'[\s\-]', '', krs)
        krs = krs.zfill(10)  # Uzupełnij zerami z przodu
        
        if len(krs) != 10 or not krs.isdigit():
            raise GUSApiError(f"Nieprawidłowy KRS: {krs}")
        
        logger.info(f"[GUS] Searching by KRS: {krs}")
        
        search_params = f'<dat:Krs xmlns:dat="http://CIS/BIR/PUBL/2014/07/DataContract">{krs}</dat:Krs>'
        
        result = self._search(search_params)
        
        if not result:
            logger.info(f"[GUS] No results for KRS: {krs}")
            return None
        
        return self._parse_company_data(result)
    
    def __enter__(self):
        """Context manager - login"""
        self.login()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager - logout"""
        self.logout()


# ============================================================
# Convenience Functions
# ============================================================

def fetch_company_by_nip(nip: str, api_key: str = None) -> Optional[CompanyData]:
    """
    Szybkie pobranie danych firmy po NIP.
    
    Args:
        nip: Numer NIP
        api_key: Klucz API (opcjonalny, użyje testowego)
        
    Returns:
        CompanyData lub None
        
    Użycie:
        company = fetch_company_by_nip("1234567890")
        if company:
            print(company.name, company.city)
    """
    with GUSApi(api_key=api_key) as api:
        return api.get_by_nip(nip)


def fetch_company_by_regon(regon: str, api_key: str = None) -> Optional[CompanyData]:
    """Szybkie pobranie danych firmy po REGON"""
    with GUSApi(api_key=api_key) as api:
        return api.get_by_regon(regon)


def fetch_company_by_krs(krs: str, api_key: str = None) -> Optional[CompanyData]:
    """Szybkie pobranie danych firmy po KRS"""
    with GUSApi(api_key=api_key) as api:
        return api.get_by_krs(krs)


# ============================================================
# Test
# ============================================================

if __name__ == "__main__":
    # Test z kluczem testowym
    logging.basicConfig(level=logging.INFO)
    
    print("Test GUS API")
    print("=" * 50)
    
    # Przykładowy NIP (Allegro)
    test_nip = "5252674798"
    
    print(f"\nSzukam NIP: {test_nip}")
    
    try:
        company = fetch_company_by_nip(test_nip)
        
        if company:
            print(f"\n✅ Znaleziono:")
            print(f"   Nazwa: {company.name}")
            print(f"   Nazwa skrócona: {company.short_name}")
            print(f"   NIP: {company.nip}")
            print(f"   REGON: {company.regon}")
            print(f"   Adres: {company.street} {company.building_number}")
            print(f"   Miasto: {company.postal_code} {company.city}")
            print(f"   Aktywna: {company.is_active}")
        else:
            print("❌ Nie znaleziono")
            
    except GUSApiError as e:
        print(f"❌ Błąd: {e}")
