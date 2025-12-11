"""
CMR Context Builder
===================
Builder kontekstu dla miedzynarodowych listow przewozowych CMR.
"""

from datetime import date
from decimal import Decimal
from typing import List
import logging

from .base import BaseContextBuilder
from ..models import DocumentContext, CompanyInfo, DocumentItem
from ..constants import DocumentType, DBTables, DOCUMENT_LABELS

logger = logging.getLogger(__name__)


class CMRContextBuilder(BaseContextBuilder):
    """
    Builder kontekstu dla dokumentu CMR (Miedzynarodowy List Przewozowy).

    CMR wymaga specyficznych danych transportowych:
    - Dane przewoznika
    - Waga towarow
    - Miejsce zaladunku/rozladunku
    - Kody HS dla towaru

    Pobiera dane z:
    - delivery_notes lub orders
    - customers
    - carriers (jesli istnieje)
    """

    def build(
        self,
        entity_id: str,
        doc_number: str,
        user_id: str = None
    ) -> DocumentContext:
        """
        Zbuduj kontekst dla CMR.

        Args:
            entity_id: ID dostawy lub zamowienia
            doc_number: Numer dokumentu CMR
            user_id: ID uzytkownika

        Returns:
            DocumentContext
        """
        # 1. Probuj pobrac jako delivery_note, fallback na order
        delivery = self._get_delivery_note(entity_id)
        if not delivery:
            delivery = self._get_order(entity_id)

        if not delivery:
            raise ValueError(f"Dostawa/zamowienie nie znalezione: {entity_id}")

        # 2. Pobierz pozycje
        items = self._get_items(entity_id, 'delivery_note' if delivery.get('delivery_note_id') else 'order')

        # 3. Dane nadawcy (my)
        sender = self.get_seller_info()

        # 4. Dane odbiorcy
        customer_data = delivery.get('customers', {})
        if not customer_data and delivery.get('customer_id'):
            receiver = self.get_customer_info(delivery['customer_id'])
        else:
            receiver = CompanyInfo(
                name=customer_data.get('name', 'Odbiorca'),
                address=self._format_customer_address(customer_data),
                nip=customer_data.get('nip', ''),
                country=customer_data.get('country', '')
            )

        # 5. Mapuj pozycje z danymi transportowymi
        doc_items = []
        total_weight = 0.0

        for idx, item in enumerate(items, 1):
            qty = self._safe_decimal(item.get('quantity', 0))
            weight_per_unit = self._safe_decimal(item.get('weight_kg', item.get('weight', 0)))
            item_weight = weight_per_unit * qty
            total_weight += item_weight

            doc_items.append(DocumentItem(
                position=idx,
                name=item.get('name', item.get('product_name', 'Towar')),
                quantity=qty,
                unit=item.get('package_type', item.get('unit', 'szt')),
                weight=item_weight,
                volume=self._safe_decimal(item.get('volume_m3', 0)),
                hs_code=item.get('hs_code', item.get('tariff_code', '')),
                package_type=item.get('package_type', 'karton')
            ))

        # 6. Dane przewoznika
        carrier_info = self._get_carrier_info(delivery)

        # 7. Dane dodatkowe dla CMR
        extra_data = {
            # Przewoznik
            'carrier_name': carrier_info.get('name', 'Transport wlasny'),
            'carrier_address': carrier_info.get('address', ''),
            'carrier_license': carrier_info.get('license_plate', ''),
            'carrier_phone': carrier_info.get('phone', ''),

            # Kolejni przewoznicy
            'successive_carriers': delivery.get('successive_carriers', ''),

            # Miejsca
            'loading_place': delivery.get('loading_place', sender.address),
            'delivery_place': delivery.get('delivery_place', receiver.address),

            # Dokumenty
            'attached_docs': delivery.get('attached_documents', 'WZ, Faktura'),

            # Uwagi
            'carrier_notes': delivery.get('carrier_notes', ''),
            'special_agreements': delivery.get('special_agreements', ''),

            # Podsumowanie
            'total_weight': f"{total_weight:.2f} kg",
            'total_packages': len(doc_items),

            # Referencje
            'order_ref': delivery.get('order_number', delivery.get('number', '')),
            'invoice_ref': delivery.get('invoice_number', ''),

            # CMR specyficzne pola
            'incoterms': delivery.get('incoterms', ''),
            'insurance': delivery.get('insurance_info', ''),
            'cod_amount': delivery.get('cod_amount', ''),  # Cash on Delivery
            'cod_currency': delivery.get('cod_currency', 'EUR'),
        }

        # 8. Zbuduj kontekst
        return DocumentContext(
            doc_type=DocumentType.CMR.value,
            doc_type_label=DOCUMENT_LABELS[DocumentType.CMR],
            doc_number=doc_number,
            issue_date=date.today(),
            place=delivery.get('loading_place', 'Polska'),
            seller=sender,  # Nadawca
            buyer=receiver,  # Odbiorca
            items=doc_items,
            # CMR nie ma podsumowania kwotowego
            total_net=None,
            total_vat=None,
            total_gross=None,
            currency=delivery.get('currency', 'EUR'),
            notes=delivery.get('cmr_notes', ''),
            footer_text='Przewoz podlega postanowieniom Konwencji CMR.',
            extra_data=extra_data
        )

    def _get_delivery_note(self, delivery_id: str) -> dict:
        """Pobierz dokument dostawy"""
        try:
            response = self.db.table(DBTables.DELIVERY_NOTES)\
                .select('*, customers(*), orders(*)')\
                .eq('id', delivery_id)\
                .single()\
                .execute()

            if response.data:
                data = response.data
                data['delivery_note_id'] = delivery_id
                return data
        except Exception as e:
            logger.debug(f"Delivery note {delivery_id} not found: {e}")

        return None

    def _get_order(self, order_id: str) -> dict:
        """Fallback - pobierz zamowienie"""
        try:
            response = self.db.table(DBTables.ORDERS)\
                .select('*, customers(*)')\
                .eq('id', order_id)\
                .single()\
                .execute()

            return response.data
        except Exception as e:
            logger.debug(f"Order {order_id} not found: {e}")
            return None

    def _get_items(self, entity_id: str, entity_type: str) -> List[dict]:
        """Pobierz pozycje"""
        try:
            if entity_type == 'delivery_note':
                table = DBTables.DELIVERY_NOTE_ITEMS
                key = 'delivery_note_id'
            else:
                table = DBTables.ORDER_ITEMS
                key = 'order_id'

            response = self.db.table(table)\
                .select('*')\
                .eq(key, entity_id)\
                .order('position')\
                .execute()

            return response.data or []
        except Exception as e:
            logger.error(f"Failed to get items: {e}")
            return []

    def _get_carrier_info(self, delivery: dict) -> dict:
        """Pobierz dane przewoznika"""
        # Sprawdz czy mamy carrier_id
        carrier_id = delivery.get('carrier_id')
        if carrier_id:
            try:
                response = self.db.table('carriers')\
                    .select('*')\
                    .eq('id', carrier_id)\
                    .single()\
                    .execute()

                if response.data:
                    return response.data
            except:
                pass

        # Dane inline z delivery
        return {
            'name': delivery.get('carrier_name', 'Transport wlasny'),
            'address': delivery.get('carrier_address', ''),
            'license_plate': delivery.get('license_plate', delivery.get('vehicle_number', '')),
            'phone': delivery.get('driver_phone', ''),
            'driver_name': delivery.get('driver_name', '')
        }
