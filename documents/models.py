"""
Documents Models
================
Modele Pydantic definiujace strukture danych dla dokumentow.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import date
from decimal import Decimal


class CompanyInfo(BaseModel):
    """Dane firmy (sprzedawca/nabywca)"""
    name: str
    address: str
    nip: Optional[str] = None
    bank_account: Optional[str] = None
    logo_base64: Optional[str] = None  # Base64 obrazka logo
    phone: Optional[str] = None
    email: Optional[str] = None
    country: Optional[str] = "Polska"

    class Config:
        extra = "allow"


class DocumentItem(BaseModel):
    """Pozycja dokumentu"""
    position: int
    name: str
    quantity: float
    unit: str = "szt"
    price_net: Optional[Decimal] = None
    value_net: Optional[Decimal] = None
    vat_rate: Optional[int] = 23
    value_gross: Optional[Decimal] = None

    # Pola dodatkowe dla CMR/transportu
    weight: Optional[float] = None  # kg
    volume: Optional[float] = None  # m3
    hs_code: Optional[str] = None   # Kod HS dla celnikow
    package_type: Optional[str] = None  # paleta, karton, etc.

    # Pola dla identyfikacji wizualnej (thumbnails)
    thumbnail_base64: Optional[str] = None  # Base64 obrazka detalu
    thumbnail_url: Optional[str] = None  # URL do obrazka (alternatywnie)

    # Dane techniczne detalu (dla dokumentow produkcyjnych)
    material: Optional[str] = None  # np. "1.4301", "S235"
    thickness_mm: Optional[float] = None  # Grubosc w mm
    width_mm: Optional[float] = None  # Szerokosc detalu
    height_mm: Optional[float] = None  # Wysokosc detalu
    area_mm2: Optional[float] = None  # Pole powierzchni
    cutting_length_mm: Optional[float] = None  # Dlugosc ciecia

    # Dane kosztowe (dla raportow kosztowych)
    material_cost: Optional[Decimal] = None
    cutting_cost: Optional[Decimal] = None
    bending_cost: Optional[Decimal] = None
    other_cost: Optional[Decimal] = None

    # Identyfikator produktu
    product_id: Optional[str] = None
    product_code: Optional[str] = None
    file_2d: Optional[str] = None  # Sciezka do pliku DXF

    class Config:
        extra = "allow"


class DocumentContext(BaseModel):
    """
    Glowny kontekst przekazywany do silnika szablonow.
    Zawiera wszystkie dane potrzebne do wygenerowania dokumentu.
    """
    # Identyfikacja dokumentu
    doc_type: str
    doc_type_label: str  # Np. "OFERTA HANDLOWA"
    doc_number: str
    issue_date: date
    place: str = "Polska"

    # Strony transakcji
    seller: CompanyInfo
    buyer: CompanyInfo

    # Pozycje dokumentu
    items: List[DocumentItem] = []

    # Podsumowanie
    total_net: Optional[Decimal] = Field(default=Decimal('0.00'))
    total_gross: Optional[Decimal] = Field(default=Decimal('0.00'))
    total_vat: Optional[Decimal] = Field(default=Decimal('0.00'))
    currency: str = "PLN"

    # Dodatkowe pola tekstowe
    notes: Optional[str] = None
    footer_text: Optional[str] = None

    # Slownik na specyficzne dane (termin waznosci, warunki platnosci, etc.)
    extra_data: Dict[str, Any] = {}

    class Config:
        arbitrary_types_allowed = True
        extra = "allow"

    def to_template_dict(self) -> Dict[str, Any]:
        """
        Konwertuje kontekst do slownika dla Jinja2.
        Obsluguje specjalne typy (Decimal, date) dla szablonow.
        """
        data = self.model_dump()

        # Konwersja date na string
        if isinstance(data.get('issue_date'), date):
            data['issue_date'] = data['issue_date'].strftime('%Y-%m-%d')

        # Konwersja Decimal na float dla szablonow
        for key in ['total_net', 'total_gross', 'total_vat']:
            if data.get(key) is not None:
                data[key] = float(data[key])

        # Konwersja Decimal w pozycjach
        for item in data.get('items', []):
            for key in ['price_net', 'value_net', 'value_gross']:
                if item.get(key) is not None:
                    item[key] = float(item[key])

        return data


class TemplateConfig(BaseModel):
    """Konfiguracja szablonu dokumentu"""
    page_size: str = "A4"
    margin_top: str = "20mm"
    margin_bottom: str = "20mm"
    margin_left: str = "15mm"
    margin_right: str = "15mm"
    footer_enabled: bool = True
    supported_languages: List[str] = ["pl"]

    class Config:
        extra = "allow"


class DocumentMetadata(BaseModel):
    """Metadane dokumentu zapisywane w bazie"""
    id: Optional[str] = None
    doc_type: str
    doc_number_full: str
    year: int
    number_seq: int
    customer_id: Optional[str] = None
    related_table: Optional[str] = None
    related_id: Optional[str] = None
    storage_path: str
    created_at: Optional[str] = None
    created_by: Optional[str] = None
    is_deleted: bool = False
    template_version_id: Optional[str] = None
    file_size: Optional[int] = None
    content_type: str = "application/pdf"

    class Config:
        extra = "allow"
