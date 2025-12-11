"""
Order Confirmation Context Builder
==================================
Builder kontekstu dla dokumentow potwierdzenia zamowienia.
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional
import logging
import base64

from .base import BaseContextBuilder
from ..models import DocumentContext, CompanyInfo, DocumentItem
from ..constants import DocumentType, DBTables, DOCUMENT_LABELS

logger = logging.getLogger(__name__)


class OrderConfirmationContextBuilder(BaseContextBuilder):
    """
    Builder kontekstu dla dokumentu Potwierdzenia Zamowienia.

    Zawiera:
    - Dane zamowienia z pozycjami
    - Thumbnails detali dla identyfikacji wizualnej
    - Dane techniczne (material, wymiary)
    - Warunki realizacji i platnosci

    Pobiera dane z:
    - orders: Dane zamowienia
    - order_items: Pozycje zamowienia
    - customers: Dane klienta
    - products: Dane produktow z thumbnailami
    """

    def build(
        self,
        entity_id: str,
        doc_number: str,
        user_id: str = None
    ) -> DocumentContext:
        """
        Zbuduj kontekst dla potwierdzenia zamowienia.

        Args:
            entity_id: ID zamowienia (order_id)
            doc_number: Numer dokumentu
            user_id: ID uzytkownika

        Returns:
            DocumentContext
        """
        # 1. Pobierz dane zamowienia
        order = self._get_order(entity_id)
        if not order:
            raise ValueError(f"Zamowienie nie znalezione: {entity_id}")

        # 2. Pobierz pozycje z produktami
        items = self._get_order_items_with_products(entity_id)

        # 3. Dane klienta
        customer_data = order.get('customers', {})
        if not customer_data and order.get('customer_id'):
            buyer = self.get_customer_info(order['customer_id'])
        else:
            buyer = CompanyInfo(
                name=customer_data.get('name', 'Klient'),
                address=self._format_customer_address(customer_data),
                nip=customer_data.get('nip', ''),
                phone=customer_data.get('phone', ''),
                email=customer_data.get('email', ''),
                country=customer_data.get('country', 'Polska')
            )

        # 4. Mapuj pozycje z thumbnailami
        doc_items = []
        total_net = Decimal('0')

        for idx, item in enumerate(items, 1):
            qty = self._safe_decimal(item.get('quantity', 0))
            price = Decimal(str(item.get('unit_price', 0) or 0))
            value = Decimal(str(qty)) * price

            # Pobierz thumbnail
            thumbnail_base64 = self._get_thumbnail(item)

            doc_items.append(DocumentItem(
                position=idx,
                name=item.get('name', item.get('product_name', 'Produkt')),
                quantity=qty,
                unit=item.get('unit', 'szt'),
                price_net=price,
                value_net=value,
                vat_rate=item.get('vat_rate', 23),
                # Thumbnail
                thumbnail_base64=thumbnail_base64,
                # Dane techniczne
                material=item.get('material', ''),
                thickness_mm=self._safe_decimal(item.get('thickness_mm')),
                width_mm=self._safe_decimal(item.get('width_mm')),
                height_mm=self._safe_decimal(item.get('height_mm')),
                weight=self._safe_decimal(item.get('weight')),
                # Identyfikatory
                product_id=item.get('product_id'),
                product_code=item.get('product_code', item.get('sku', ''))
            ))
            total_net += value

        # 5. Oblicz podsumowanie
        vat_rate = order.get('vat_rate', 23) or 23
        total_vat = total_net * Decimal(vat_rate) / Decimal(100)
        total_gross = total_net + total_vat

        # 6. Dane dodatkowe
        extra_data = {
            'order_number': order.get('order_number', order.get('number', '')),
            'order_id': entity_id,
            'reference_number': order.get('reference_number', order.get('customer_reference', '')),
            'quotation_number': order.get('quotation_number', ''),
            # Terminy
            'production_deadline': order.get('production_deadline', ''),
            'delivery_date': order.get('delivery_date', order.get('expected_delivery', '')),
            'lead_time': order.get('lead_time', ''),
            # Warunki
            'payment_terms': order.get('payment_terms', 'Przelew 14 dni'),
            'delivery_terms': order.get('delivery_terms', 'EXW'),
            'incoterms': order.get('incoterms', 'EXW'),
            'packaging': order.get('packaging', 'Standardowe'),
            # Notatki
            'priority_note': order.get('priority_note', ''),
            'internal_notes': order.get('internal_notes', ''),
            'status': order.get('status', 'confirmed')
        }

        # 7. Zbuduj kontekst
        return DocumentContext(
            doc_type=DocumentType.ORDER_CONFIRMATION.value,
            doc_type_label=DOCUMENT_LABELS[DocumentType.ORDER_CONFIRMATION],
            doc_number=doc_number,
            issue_date=date.today(),
            place=order.get('place', 'Polska'),
            seller=self.get_seller_info(),
            buyer=buyer,
            items=doc_items,
            total_net=total_net,
            total_vat=total_vat,
            total_gross=total_gross,
            currency=order.get('currency', 'PLN'),
            notes=order.get('notes', ''),
            footer_text=order.get('footer_text', ''),
            extra_data=extra_data
        )

    def _get_order(self, order_id: str) -> dict:
        """Pobierz zamowienie z klientem"""
        try:
            response = self.db.table(DBTables.ORDERS)\
                .select('*, customers(*)')\
                .eq('id', order_id)\
                .single()\
                .execute()

            return response.data
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {e}")
            return None

    def _get_order_items_with_products(self, order_id: str) -> List[dict]:
        """Pobierz pozycje zamowienia z danymi produktow"""
        try:
            # Pobierz pozycje z produktami
            response = self.db.table(DBTables.ORDER_ITEMS)\
                .select('*, products(*)')\
                .eq('order_id', order_id)\
                .order('position')\
                .execute()

            items = response.data or []

            # Rozwin dane produktow do poziomu itema
            enriched_items = []
            for item in items:
                product = item.get('products', {}) or {}
                enriched_item = {**item}

                # Dodaj dane z produktu jesli brakuje
                if not enriched_item.get('material') and product.get('material'):
                    enriched_item['material'] = product['material']
                if not enriched_item.get('thickness_mm') and product.get('thickness_mm'):
                    enriched_item['thickness_mm'] = product['thickness_mm']
                if not enriched_item.get('width_mm') and product.get('width_mm'):
                    enriched_item['width_mm'] = product['width_mm']
                if not enriched_item.get('height_mm') and product.get('height_mm'):
                    enriched_item['height_mm'] = product['height_mm']
                if not enriched_item.get('weight') and product.get('weight_kg'):
                    enriched_item['weight'] = product['weight_kg']
                if not enriched_item.get('product_code') and product.get('sku'):
                    enriched_item['product_code'] = product['sku']

                # Thumbnail z produktu
                enriched_item['_product'] = product

                enriched_items.append(enriched_item)

            return enriched_items
        except Exception as e:
            logger.error(f"Failed to get order items: {e}")
            return []

    def _get_thumbnail(self, item: dict) -> Optional[str]:
        """
        Pobierz thumbnail dla pozycji.

        Probuje w kolejnosci:
        1. thumbnail_base64 z itema
        2. thumbnail z produktu
        3. Pobierz z storage jesli jest sciezka
        """
        # 1. Bezposrednio z itema
        if item.get('thumbnail_base64'):
            return item['thumbnail_base64']

        # 2. Z produktu
        product = item.get('_product', {})
        if product.get('thumbnail_base64'):
            return product['thumbnail_base64']

        # 3. Pobierz z storage
        thumbnail_path = item.get('thumbnail_path') or product.get('thumbnail_path')
        if thumbnail_path:
            return self._download_thumbnail(thumbnail_path)

        return None

    def _download_thumbnail(self, path: str) -> Optional[str]:
        """Pobierz thumbnail z storage i zakoduj do base64"""
        try:
            # Okresl bucket na podstawie sciezki
            if path.startswith('products/'):
                bucket = 'products'
            else:
                bucket = 'thumbnails'

            response = self.db.storage.from_(bucket).download(path)
            if response:
                return base64.b64encode(response).decode('utf-8')
        except Exception as e:
            logger.debug(f"Could not download thumbnail {path}: {e}")

        return None
