"""
WZ Context Builder
==================
Builder kontekstu dla dokumentow WZ (Wydanie Zewnetrzne).
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


class WZContextBuilder(BaseContextBuilder):
    """
    Builder kontekstu dla dokumentu WZ (Wydanie Zewnetrzne).

    WZ nie zawiera cen - tylko informacje o wydawanych towarach.
    Zawiera thumbnails dla identyfikacji wizualnej detali.

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
        Zbuduj kontekst dla WZ.

        Args:
            entity_id: ID zamowienia (order_id)
            doc_number: Numer dokumentu WZ
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
                name=customer_data.get('name', 'Odbiorca'),
                address=self._format_customer_address(customer_data),
                nip=customer_data.get('nip', ''),
                phone=customer_data.get('phone', ''),
                email=customer_data.get('email', ''),
                country=customer_data.get('country', 'Polska')
            )

        # 4. Mapuj pozycje z thumbnailami (sortuj po materiale)
        doc_items = []
        total_weight = Decimal('0')

        # Sortuj po materiale i grubosci dla lepszej organizacji
        sorted_items = sorted(
            items,
            key=lambda x: (
                x.get('material', '') or '',
                x.get('thickness_mm', 0) or 0
            )
        )

        for idx, item in enumerate(sorted_items, 1):
            qty = self._safe_decimal(item.get('quantity', 0))
            weight = self._safe_decimal(item.get('weight', 0))

            # Pobierz thumbnail
            thumbnail_base64 = self._get_thumbnail(item)

            doc_items.append(DocumentItem(
                position=idx,
                name=item.get('name', item.get('product_name', 'Towar')),
                quantity=qty,
                unit=item.get('unit', 'szt'),
                # WZ nie ma cen
                price_net=None,
                value_net=None,
                # Thumbnail dla identyfikacji
                thumbnail_base64=thumbnail_base64,
                # Dane techniczne
                material=item.get('material', ''),
                thickness_mm=self._safe_decimal(item.get('thickness_mm')),
                width_mm=self._safe_decimal(item.get('width_mm')),
                height_mm=self._safe_decimal(item.get('height_mm')),
                weight=weight,
                # Identyfikatory
                product_id=item.get('product_id'),
                product_code=item.get('product_code', item.get('sku', '')),
                file_2d=item.get('file_2d', item.get('dxf_file', ''))
            ))

            if weight:
                total_weight += Decimal(str(weight)) * Decimal(str(qty))

        # 5. Dane dodatkowe
        extra_data = {
            'order_number': order.get('order_number', order.get('number', '')),
            'order_id': entity_id,
            'shipping_address': self._get_shipping_address(order),
            'delivery_date': order.get('delivery_date', ''),
            'notes': order.get('notes', ''),
            'issued_by': user_id,
            'receiver_name': '',
            'receiver_signature': '',
            'total_weight': float(total_weight),
            'release_notes': order.get('release_notes', '')
        }

        # 6. Zbuduj kontekst
        return DocumentContext(
            doc_type=DocumentType.WZ.value,
            doc_type_label=DOCUMENT_LABELS[DocumentType.WZ],
            doc_number=doc_number,
            issue_date=date.today(),
            place=order.get('place', 'Polska'),
            seller=self.get_seller_info(),
            buyer=buyer,
            items=doc_items,
            # WZ bez podsumowania kwotowego
            total_net=None,
            total_vat=None,
            total_gross=None,
            currency=order.get('currency', 'PLN'),
            notes=order.get('wz_notes', order.get('notes', '')),
            footer_text='Towar wydano zgodnie z zamowieniem.',
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

                # Zapisz produkt dla thumbnail
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

    def _get_shipping_address(self, order: dict) -> str:
        """Pobierz adres dostawy"""
        # Sprawdz czy jest oddzielny adres dostawy
        if order.get('shipping_address'):
            return order['shipping_address']

        # Uzyj adresu klienta
        customer = order.get('customers', {})
        if customer:
            return self._format_customer_address(customer)

        return ''
