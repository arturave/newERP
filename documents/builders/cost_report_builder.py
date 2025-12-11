"""
Cost Report Context Builder
===========================
Builder kontekstu dla raportow kosztowych.
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional, Dict, Any
import logging
import base64

from .base import BaseContextBuilder
from ..models import DocumentContext, CompanyInfo, DocumentItem
from ..constants import DocumentType, DBTables, DOCUMENT_LABELS

logger = logging.getLogger(__name__)


class CostReportContextBuilder(BaseContextBuilder):
    """
    Builder kontekstu dla dokumentu Raportu Kosztowego.

    Zawiera:
    - Szczegolowa kalkulacja kosztow dla kazdego detalu
    - Thumbnails dla identyfikacji wizualnej
    - Rozbicie na koszty: material, ciecie, giecie, inne
    - Informacje o nestingu i efektywnosci

    Moze byc zbudowany z:
    - orders + order_items: Zamowienie z kalkulacja
    - quotations: Wycena z kalkulacja
    - Dane przekazane bezposrednio (custom_context)
    """

    def build(
        self,
        entity_id: str,
        doc_number: str,
        user_id: str = None
    ) -> DocumentContext:
        """
        Zbuduj kontekst dla raportu kosztowego.

        Args:
            entity_id: ID zamowienia lub wyceny
            doc_number: Numer dokumentu
            user_id: ID uzytkownika

        Returns:
            DocumentContext
        """
        # Probuj pobrac jako zamowienie
        order = self._get_order_with_costs(entity_id)

        if order:
            return self._build_from_order(order, doc_number, user_id)

        # Probuj jako wycene
        quotation = self._get_quotation_with_costs(entity_id)

        if quotation:
            return self._build_from_quotation(quotation, doc_number, user_id)

        raise ValueError(f"Nie znaleziono danych kosztowych dla: {entity_id}")

    def _build_from_order(
        self,
        order: dict,
        doc_number: str,
        user_id: str
    ) -> DocumentContext:
        """Zbuduj raport z danych zamowienia"""
        # Pobierz pozycje z kosztami
        items = self._get_order_items_with_costs(order['id'])

        # Dane klienta
        customer_data = order.get('customers', {})
        buyer = self._build_buyer_info(customer_data, order.get('customer_id'))

        # Mapuj pozycje
        doc_items, totals = self._map_items_with_costs(items)

        # Informacje o nestingu
        nesting_info = self._get_nesting_info(order)

        # Dane dodatkowe
        extra_data = {
            'order_number': order.get('order_number', order.get('number', '')),
            'order_id': order['id'],
            'nesting': nesting_info,
            'total_cutting_length': totals.get('total_cutting_length', 0),
            'total_area': totals.get('total_area', 0),
            'total_weight': totals.get('total_weight', 0),
            'margin_info': self._get_margin_info(order),
            'cost_allocation': order.get('cost_allocation', 'proportional'),
            'calculated_at': order.get('cost_calculated_at', '')
        }

        return DocumentContext(
            doc_type=DocumentType.COST_REPORT.value,
            doc_type_label=DOCUMENT_LABELS[DocumentType.COST_REPORT],
            doc_number=doc_number,
            issue_date=date.today(),
            place='Polska',
            seller=self.get_seller_info(),
            buyer=buyer,
            items=doc_items,
            total_net=totals.get('total_cost', Decimal('0')),
            total_vat=Decimal('0'),
            total_gross=totals.get('total_cost', Decimal('0')),
            currency=order.get('currency', 'PLN'),
            notes=order.get('cost_notes', ''),
            footer_text='Raport wygenerowany automatycznie. Dane do uzytku wewnetrznego.',
            extra_data=extra_data
        )

    def _build_from_quotation(
        self,
        quotation: dict,
        doc_number: str,
        user_id: str
    ) -> DocumentContext:
        """Zbuduj raport z danych wyceny"""
        # Pobierz pozycje z kosztami
        items = self._get_quotation_items_with_costs(quotation['id'])

        # Dane klienta
        customer_data = quotation.get('customers', {})
        buyer = self._build_buyer_info(customer_data, quotation.get('customer_id'))

        # Mapuj pozycje
        doc_items, totals = self._map_items_with_costs(items)

        # Informacje o nestingu
        nesting_info = self._get_nesting_info(quotation)

        # Dane dodatkowe
        extra_data = {
            'quotation_number': quotation.get('quotation_number', quotation.get('number', '')),
            'quotation_id': quotation['id'],
            'nesting': nesting_info,
            'total_cutting_length': totals.get('total_cutting_length', 0),
            'total_area': totals.get('total_area', 0),
            'total_weight': totals.get('total_weight', 0),
            'margin_info': self._get_margin_info(quotation),
            'algorithm': quotation.get('nesting_algorithm', 'FAST')
        }

        return DocumentContext(
            doc_type=DocumentType.COST_REPORT.value,
            doc_type_label=DOCUMENT_LABELS[DocumentType.COST_REPORT],
            doc_number=doc_number,
            issue_date=date.today(),
            place='Polska',
            seller=self.get_seller_info(),
            buyer=buyer,
            items=doc_items,
            total_net=totals.get('total_cost', Decimal('0')),
            total_vat=Decimal('0'),
            total_gross=totals.get('total_cost', Decimal('0')),
            currency=quotation.get('currency', 'PLN'),
            notes=quotation.get('cost_notes', ''),
            footer_text='Raport wygenerowany automatycznie. Dane do uzytku wewnetrznego.',
            extra_data=extra_data
        )

    def _build_buyer_info(self, customer_data: dict, customer_id: str = None) -> CompanyInfo:
        """Zbuduj informacje o kliencie"""
        if not customer_data and customer_id:
            return self.get_customer_info(customer_id)

        return CompanyInfo(
            name=customer_data.get('name', 'Klient'),
            address=self._format_customer_address(customer_data),
            nip=customer_data.get('nip', ''),
            phone=customer_data.get('phone', ''),
            email=customer_data.get('email', ''),
            country=customer_data.get('country', 'Polska')
        )

    def _map_items_with_costs(self, items: List[dict]) -> tuple:
        """Mapuj pozycje z pelnym rozbiciem kosztow"""
        doc_items = []
        totals = {
            'total_cost': Decimal('0'),
            'total_material': Decimal('0'),
            'total_cutting': Decimal('0'),
            'total_bending': Decimal('0'),
            'total_other': Decimal('0'),
            'total_cutting_length': 0,
            'total_area': 0,
            'total_weight': 0
        }

        # Sortuj po materiale
        sorted_items = sorted(
            items,
            key=lambda x: (
                x.get('material', '') or '',
                x.get('thickness_mm', 0) or 0
            )
        )

        for idx, item in enumerate(sorted_items, 1):
            qty = self._safe_decimal(item.get('quantity', 0))

            # Koszty jednostkowe
            material_cost = Decimal(str(item.get('material_cost', 0) or 0))
            cutting_cost = Decimal(str(item.get('cutting_cost', 0) or 0))
            bending_cost = Decimal(str(item.get('bending_cost', 0) or 0))
            other_cost = Decimal(str(item.get('other_cost', item.get('additional_cost', 0)) or 0))

            unit_cost = material_cost + cutting_cost + bending_cost + other_cost
            total_value = unit_cost * Decimal(str(qty))

            # Pobierz thumbnail
            thumbnail_base64 = self._get_thumbnail(item)

            doc_items.append(DocumentItem(
                position=idx,
                name=item.get('name', item.get('product_name', 'Detal')),
                quantity=qty,
                unit=item.get('unit', 'szt'),
                price_net=unit_cost,
                value_net=total_value,
                # Thumbnail
                thumbnail_base64=thumbnail_base64,
                # Dane techniczne
                material=item.get('material', ''),
                thickness_mm=self._safe_decimal(item.get('thickness_mm')),
                width_mm=self._safe_decimal(item.get('width_mm')),
                height_mm=self._safe_decimal(item.get('height_mm')),
                area_mm2=self._safe_decimal(item.get('area_mm2', item.get('contour_area'))),
                cutting_length_mm=self._safe_decimal(item.get('cutting_length_mm', item.get('cutting_length'))),
                weight=self._safe_decimal(item.get('weight', item.get('weight_kg'))),
                # Koszty szczegolowe
                material_cost=material_cost,
                cutting_cost=cutting_cost,
                bending_cost=bending_cost,
                other_cost=other_cost,
                # Identyfikatory
                product_id=item.get('product_id'),
                product_code=item.get('product_code', item.get('sku', '')),
                file_2d=item.get('file_2d', item.get('dxf_file', ''))
            ))

            # Sumuj totale
            totals['total_cost'] += total_value
            totals['total_material'] += material_cost * Decimal(str(qty))
            totals['total_cutting'] += cutting_cost * Decimal(str(qty))
            totals['total_bending'] += bending_cost * Decimal(str(qty))
            totals['total_other'] += other_cost * Decimal(str(qty))

            if item.get('cutting_length_mm'):
                totals['total_cutting_length'] += item['cutting_length_mm'] * qty
            if item.get('area_mm2'):
                totals['total_area'] += item['area_mm2'] * qty
            if item.get('weight'):
                totals['total_weight'] += item['weight'] * qty

        return doc_items, totals

    def _get_order_with_costs(self, order_id: str) -> Optional[dict]:
        """Pobierz zamowienie z kosztami"""
        try:
            response = self.db.table(DBTables.ORDERS)\
                .select('*, customers(*)')\
                .eq('id', order_id)\
                .single()\
                .execute()

            return response.data
        except Exception as e:
            logger.debug(f"Not an order: {order_id}")
            return None

    def _get_quotation_with_costs(self, quotation_id: str) -> Optional[dict]:
        """Pobierz wycene z kosztami"""
        try:
            response = self.db.table(DBTables.QUOTATIONS)\
                .select('*, customers(*)')\
                .eq('id', quotation_id)\
                .single()\
                .execute()

            return response.data
        except Exception as e:
            logger.debug(f"Not a quotation: {quotation_id}")
            return None

    def _get_order_items_with_costs(self, order_id: str) -> List[dict]:
        """Pobierz pozycje zamowienia z kosztami"""
        try:
            response = self.db.table(DBTables.ORDER_ITEMS)\
                .select('*, products(*)')\
                .eq('order_id', order_id)\
                .order('position')\
                .execute()

            return self._enrich_items(response.data or [])
        except Exception as e:
            logger.error(f"Failed to get order items with costs: {e}")
            return []

    def _get_quotation_items_with_costs(self, quotation_id: str) -> List[dict]:
        """Pobierz pozycje wyceny z kosztami"""
        try:
            response = self.db.table(DBTables.QUOTATION_ITEMS)\
                .select('*, products(*)')\
                .eq('quotation_id', quotation_id)\
                .order('position')\
                .execute()

            return self._enrich_items(response.data or [])
        except Exception as e:
            logger.error(f"Failed to get quotation items with costs: {e}")
            return []

    def _enrich_items(self, items: List[dict]) -> List[dict]:
        """Wzbogac pozycje o dane z produktow"""
        enriched_items = []
        for item in items:
            product = item.get('products', {}) or {}
            enriched_item = {**item}

            # Dodaj dane z produktu
            for key in ['material', 'thickness_mm', 'width_mm', 'height_mm', 'weight_kg', 'sku']:
                if not enriched_item.get(key) and product.get(key):
                    if key == 'weight_kg':
                        enriched_item['weight'] = product[key]
                    elif key == 'sku':
                        enriched_item['product_code'] = product[key]
                    else:
                        enriched_item[key] = product[key]

            enriched_item['_product'] = product
            enriched_items.append(enriched_item)

        return enriched_items

    def _get_thumbnail(self, item: dict) -> Optional[str]:
        """Pobierz thumbnail dla pozycji"""
        if item.get('thumbnail_base64'):
            return item['thumbnail_base64']

        product = item.get('_product', {})
        if product.get('thumbnail_base64'):
            return product['thumbnail_base64']

        thumbnail_path = item.get('thumbnail_path') or product.get('thumbnail_path')
        if thumbnail_path:
            return self._download_thumbnail(thumbnail_path)

        return None

    def _download_thumbnail(self, path: str) -> Optional[str]:
        """Pobierz thumbnail z storage"""
        try:
            bucket = 'products' if path.startswith('products/') else 'thumbnails'
            response = self.db.storage.from_(bucket).download(path)
            if response:
                return base64.b64encode(response).decode('utf-8')
        except Exception as e:
            logger.debug(f"Could not download thumbnail {path}: {e}")
        return None

    def _get_nesting_info(self, entity: dict) -> Dict[str, Any]:
        """Pobierz informacje o nestingu"""
        return {
            'total_sheets': entity.get('total_sheets', 0),
            'utilization': entity.get('nesting_utilization', entity.get('utilization', 0)),
            'waste_area': entity.get('waste_area_m2', 0),
            'algorithm': entity.get('nesting_algorithm', 'FAST')
        }

    def _get_margin_info(self, entity: dict) -> Dict[str, Any]:
        """Pobierz informacje o marzy"""
        cost_net = entity.get('cost_net', entity.get('total_cost', 0)) or 0
        margin_percent = entity.get('margin_percent', 0) or 0
        margin_value = cost_net * margin_percent / 100 if margin_percent else 0
        sale_price = cost_net + margin_value

        return {
            'cost_net': cost_net,
            'margin_percent': margin_percent,
            'margin_value': margin_value,
            'sale_price': sale_price
        }
