"""
Quotation Context Builder
=========================
Builder kontekstu dla ofert handlowych.
"""

from datetime import date
from decimal import Decimal
from typing import List
import logging

from .base import BaseContextBuilder
from ..models import DocumentContext, CompanyInfo, DocumentItem
from ..constants import DocumentType, DBTables, DOCUMENT_LABELS

logger = logging.getLogger(__name__)


class QuotationContextBuilder(BaseContextBuilder):
    """
    Builder kontekstu dla dokumentu Oferty Handlowej.

    Pobiera dane z:
    - quotations: Glowne dane oferty
    - quotation_items: Pozycje oferty
    - customers: Dane klienta
    """

    def build(
        self,
        entity_id: str,
        doc_number: str,
        user_id: str = None
    ) -> DocumentContext:
        """
        Zbuduj kontekst dla oferty.

        Args:
            entity_id: ID oferty (quotation_id)
            doc_number: Numer dokumentu
            user_id: ID uzytkownika

        Returns:
            DocumentContext
        """
        # 1. Pobierz dane oferty z klientem
        quotation = self._get_quotation(entity_id)
        if not quotation:
            raise ValueError(f"Oferta nie znaleziona: {entity_id}")

        # 2. Pobierz pozycje oferty
        items = self._get_quotation_items(entity_id)

        # 3. Dane klienta
        customer_data = quotation.get('customers', {})
        if not customer_data and quotation.get('customer_id'):
            buyer = self.get_customer_info(quotation['customer_id'])
        else:
            buyer = CompanyInfo(
                name=customer_data.get('name', 'Klient'),
                address=self._format_customer_address(customer_data),
                nip=customer_data.get('nip', ''),
                phone=customer_data.get('phone', ''),
                email=customer_data.get('email', ''),
                country=customer_data.get('country', 'Polska')
            )

        # 4. Mapuj pozycje
        doc_items = []
        total_net = Decimal('0')

        for idx, item in enumerate(items, 1):
            qty = self._safe_decimal(item.get('quantity', 0))
            price = Decimal(str(item.get('unit_price', 0) or 0))
            value = Decimal(str(qty)) * price

            doc_items.append(DocumentItem(
                position=idx,
                name=item.get('name', item.get('product_name', 'Produkt')),
                quantity=qty,
                unit=item.get('unit', 'szt'),
                price_net=price,
                value_net=value,
                vat_rate=item.get('vat_rate', 23)
            ))
            total_net += value

        # 5. Oblicz podsumowanie
        vat_rate = quotation.get('vat_rate', 23) or 23
        total_vat = total_net * Decimal(vat_rate) / Decimal(100)
        total_gross = total_net + total_vat

        # 6. Dane dodatkowe
        extra_data = {
            'valid_until': quotation.get('valid_until', '30 dni'),
            'payment_terms': quotation.get('payment_terms', 'Przelew 14 dni'),
            'delivery_time': quotation.get('delivery_time', 'Do ustalenia'),
            'quotation_id': entity_id,
            'status': quotation.get('status', 'draft')
        }

        # 7. Zbuduj kontekst
        return DocumentContext(
            doc_type=DocumentType.QUOTATION.value,
            doc_type_label=DOCUMENT_LABELS[DocumentType.QUOTATION],
            doc_number=doc_number,
            issue_date=date.today(),
            place=quotation.get('place', 'Polska'),
            seller=self.get_seller_info(),
            buyer=buyer,
            items=doc_items,
            total_net=total_net,
            total_vat=total_vat,
            total_gross=total_gross,
            currency=quotation.get('currency', 'PLN'),
            notes=quotation.get('notes', ''),
            footer_text=quotation.get('footer_text', ''),
            extra_data=extra_data
        )

    def _get_quotation(self, quotation_id: str) -> dict:
        """Pobierz oferte z klientem"""
        try:
            response = self.db.table(DBTables.QUOTATIONS)\
                .select('*, customers(*)')\
                .eq('id', quotation_id)\
                .single()\
                .execute()

            return response.data
        except Exception as e:
            logger.error(f"Failed to get quotation {quotation_id}: {e}")
            return None

    def _get_quotation_items(self, quotation_id: str) -> List[dict]:
        """Pobierz pozycje oferty"""
        try:
            response = self.db.table(DBTables.QUOTATION_ITEMS)\
                .select('*')\
                .eq('quotation_id', quotation_id)\
                .order('position')\
                .execute()

            return response.data or []
        except Exception as e:
            logger.error(f"Failed to get quotation items: {e}")
            return []
