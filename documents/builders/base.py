"""
Base Context Builder
====================
Abstrakcyjna klasa bazowa dla builderow kontekstu dokumentow.
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging

from supabase import Client

from ..models import DocumentContext, CompanyInfo

logger = logging.getLogger(__name__)


class BaseContextBuilder(ABC):
    """
    Bazowa klasa dla builderow kontekstu.

    Kazdy builder odpowiada za:
    - Pobranie danych z bazy dla konkretnego typu dokumentu
    - Transformacje danych do modelu DocumentContext
    - Obsluge bledow i walidacje

    Subklasy musza zaimplementowac metode build().
    """

    def __init__(self, supabase_client: Client):
        """
        Inicjalizacja buildera.

        Args:
            supabase_client: Klient Supabase do pobierania danych
        """
        self.db = supabase_client

    @abstractmethod
    def build(
        self,
        entity_id: str,
        doc_number: str,
        user_id: str = None
    ) -> DocumentContext:
        """
        Zbuduj kontekst dokumentu.

        Args:
            entity_id: ID encji (zamowienia, oferty, etc.)
            doc_number: Wygenerowany numer dokumentu
            user_id: ID uzytkownika generujacego

        Returns:
            DocumentContext z danymi do szablonu

        Raises:
            ValueError: Jesli encja nie istnieje
            Exception: Inne bledy bazy danych
        """
        pass

    def get_seller_info(self) -> CompanyInfo:
        """
        Pobierz dane sprzedawcy (firmy wlasnej).

        Domyslna implementacja - subklasy moga nadpisac.

        Returns:
            CompanyInfo z danymi firmy
        """
        # Probuj pobrac z tabeli company_settings
        try:
            response = self.db.table('company_settings')\
                .select('*')\
                .eq('is_default', True)\
                .single()\
                .execute()

            if response.data:
                data = response.data
                return CompanyInfo(
                    name=data.get('name', 'Firma'),
                    address=self._format_address(data),
                    nip=data.get('nip', ''),
                    bank_account=data.get('bank_account', ''),
                    logo_base64=data.get('logo_base64'),
                    phone=data.get('phone', ''),
                    email=data.get('email', ''),
                    country=data.get('country', 'Polska')
                )
        except Exception as e:
            logger.debug(f"Could not load company settings: {e}")

        # Fallback - dane domyslne
        return CompanyInfo(
            name="NewERP Sp. z o.o.",
            address="ul. Przemyslowa 1, 00-001 Warszawa",
            nip="000-000-00-00",
            bank_account="PL 00 0000 0000 0000 0000 0000 0000",
            country="Polska"
        )

    def get_customer_info(self, customer_id: str) -> CompanyInfo:
        """
        Pobierz dane klienta.

        Args:
            customer_id: ID klienta

        Returns:
            CompanyInfo z danymi klienta
        """
        try:
            response = self.db.table('customers')\
                .select('*')\
                .eq('id', customer_id)\
                .single()\
                .execute()

            if response.data:
                data = response.data
                return CompanyInfo(
                    name=data.get('name', 'Klient'),
                    address=self._format_customer_address(data),
                    nip=data.get('nip', ''),
                    phone=data.get('phone', ''),
                    email=data.get('email', ''),
                    country=data.get('country', 'Polska')
                )
        except Exception as e:
            logger.warning(f"Could not load customer {customer_id}: {e}")

        # Fallback
        return CompanyInfo(
            name="Klient",
            address="",
            country="Polska"
        )

    def _format_address(self, data: dict) -> str:
        """Formatuj adres firmy"""
        parts = []

        if data.get('street'):
            street = data['street']
            if data.get('building_number'):
                street += f" {data['building_number']}"
            if data.get('apartment_number'):
                street += f"/{data['apartment_number']}"
            parts.append(street)

        if data.get('postal_code') or data.get('city'):
            city_line = ""
            if data.get('postal_code'):
                city_line = data['postal_code']
            if data.get('city'):
                city_line += f" {data['city']}" if city_line else data['city']
            parts.append(city_line)

        return ", ".join(parts) if parts else data.get('address', '')

    def _format_customer_address(self, data: dict) -> str:
        """Formatuj adres klienta"""
        parts = []

        # Adres glowny
        if data.get('address_street'):
            parts.append(data['address_street'])
        elif data.get('address'):
            parts.append(data['address'])

        # Miasto
        city_line = ""
        if data.get('address_postal'):
            city_line = data['address_postal']
        if data.get('address_city'):
            city_line += f" {data['address_city']}" if city_line else data['address_city']
        if city_line:
            parts.append(city_line)

        # Kraj
        if data.get('country') and data['country'] != 'Polska':
            parts.append(data['country'])

        return ", ".join(parts)

    def _safe_get(self, data: dict, key: str, default=None):
        """Bezpieczne pobieranie wartosci z dict"""
        try:
            return data.get(key, default)
        except:
            return default

    def _safe_decimal(self, value, default=0) -> float:
        """Bezpieczna konwersja na liczbe"""
        try:
            if value is None:
                return default
            return float(value)
        except:
            return default
