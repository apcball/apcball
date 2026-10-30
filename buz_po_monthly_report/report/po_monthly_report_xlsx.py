import io
from datetime import datetime, time, timedelta

import pytz
import xlsxwriter

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError
from odoo.tools import html2plaintext


class PurchaseOrderMonthlyXlsx(models.AbstractModel):
    _name = 'buz.po.monthly.report.xlsx.generator'
    _description = 'Purchase Order Monthly XLSX Report'

    HEADERS = [
        'ลำดับ', 'เลขที่เอกสาร', 'วันที่เปิดPO', 'รหัสผู้จำหน่าย',
        'ชื่อผู้จำหน่าย', 'Ref', 'กำหนดส่ง', 'วันที่ Approve', 'หมายเหตุ',
        'ชื่อ', 'ราคา', 'จำนวน', 'AMOUNT', 'รับ', 'คงเหลือ', 'สถานที่ส่ง',
        'CREDIT',
    ]

    def _local_date_to_utc(self, value):
        """แปลงขอบเขตวันตาม timezone ผู้ใช้เป็นเวลา UTC สำหรับค้นหา Datetime."""
        user_tz = pytz.timezone(self.env.user.tz or 'UTC')
        local_dt = user_tz.localize(datetime.combine(value, time.min))
        return local_dt.astimezone(pytz.UTC).replace(tzinfo=None)

    def _purchase_order_domain(self, wizard):
        domain = [('state', '!=', 'cancel')]
        if wizard.po_date_from:
            domain.append((
                'date_order', '>=', self._local_date_to_utc(wizard.po_date_from),
            ))
        if wizard.po_date_to:
            next_day = wizard.po_date_to + timedelta(days=1)
            domain.append((
                'date_order', '<', self._local_date_to_utc(next_day),
            ))

        return domain

    @staticmethod
    def _selected_pr_states(wizard):
        state_fields = {
            'pr_state_draft': 'draft',
            'pr_state_waiting_head_approval': 'waiting_head_approval',
            'pr_state_waiting_purchase_approval': 'waiting_purchase_approval',
            'pr_state_approved': 'approved',
            'pr_state_purchase_order_created': 'purchase_order_created',
            'pr_state_received': 'received',
            'pr_state_cancelled': 'cancelled',
        }
        return [
            state for field_name, state in state_fields.items()
            if getattr(wizard, field_name, False)
        ]

    def _get_requisitions_by_name(self, purchase_orders, selected_states=None):
        pr_names = {
            order.pr_number or order.requisition_order
            for order in purchase_orders
            if order.pr_number or order.requisition_order
        }
        if not pr_names:
            return {}
        try:
            domain = [('name', 'in', list(pr_names))]
            if selected_states:
                domain.append(('state', 'in', selected_states))
            requisitions = self.env['employee.purchase.requisition'].search(domain)
        except AccessError as error:
            raise UserError(_(
                'You need access to Purchase Requisitions to include PR data in this report.'
            )) from error
        return {requisition.name: requisition for requisition in requisitions}

    def _date_value(self, value, tz=None):
        if not value:
            return False
        if isinstance(value, datetime):
            if tz is None:
                return fields.Datetime.context_timestamp(self, value).date()
            return pytz.utc.localize(value).astimezone(tz).date()
        return fields.Date.to_date(value)

    def _write_date(self, sheet, row, col, value, cell_format, tz=None):
        date_value = self._date_value(value, tz)
        if date_value:
            sheet.write_datetime(
                row, col, datetime.combine(date_value, time.min), cell_format,
            )
        else:
            sheet.write_blank(row, col, None, cell_format)

    @staticmethod
    def _date_range_label(date_from, date_to):
        if not date_from and not date_to:
            return '-'
        date_from = fields.Date.to_string(date_from) if date_from else '...'
        date_to = fields.Date.to_string(date_to) if date_to else '...'
        return '%s - %s' % (date_from, date_to)

    def generate_xlsx(self, wizard):
        if not wizard or not wizard.exists():
            raise UserError(_('The report wizard could not be found.'))

        orders = self.env['purchase.order'].search(
            self._purchase_order_domain(wizard),
            order='date_order, id',
        )
        selected_states = self._selected_pr_states(wizard)
        requisitions = self._get_requisitions_by_name(orders, selected_states)
        if selected_states:
            matching_pr_names = set(requisitions)
            orders = orders.filtered(
                lambda order: (
                    order.pr_number or order.requisition_order or ''
                ) in matching_pr_names
            )

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Purchase Orders')
        title_format = workbook.add_format({
            'bold': True, 'font_size': 14, 'align': 'center',
        })
        criteria_format = workbook.add_format({'italic': True})
        header_format = workbook.add_format({
            'bold': True, 'bg_color': '#D9EAF7', 'border': 1,
            'text_wrap': True, 'align': 'center', 'valign': 'vcenter',
        })
        date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
        price_format = workbook.add_format({'num_format': '#,##0.00'})
        integer_format = workbook.add_format({'num_format': '#,##0'})
        decimal_format = workbook.add_format({'num_format': '#,##0.########'})
        notes_format = workbook.add_format({'text_wrap': True, 'valign': 'top'})
        widths = [8, 18, 14, 18, 36, 20, 14, 14, 40, 58, 14, 12, 16, 12, 14, 28, 12]
        for col, width in enumerate(widths):
            sheet.set_column(col, col, width)

        sheet.merge_range(
            0, 0, 0, len(self.HEADERS) - 1,
            'รายงานใบสั่งซื้อสินค้า', title_format,
        )
        po_range = self._date_range_label(wizard.po_date_from, wizard.po_date_to)
        sheet.merge_range(
            1, 0, 1, len(self.HEADERS) - 1,
            'วันที่เปิด PO: %s' % po_range,
            criteria_format,
        )
        sheet.write_row(3, 0, self.HEADERS, header_format)
        sheet.set_row(3, 32)
        sheet.freeze_panes(4, 0)

        tz = pytz.timezone(
            self.env.context.get('tz') or self.env.user.tz or 'UTC'
        )
        lines_by_order = {}
        if orders:
            all_lines = self.env['purchase.order.line'].search_fetch(
                [('order_id', 'in', orders.ids), ('display_type', '=', False)],
                ['order_id', 'sequence', 'name', 'price_unit', 'product_qty',
                 'price_subtotal', 'qty_received', 'date_planned'],
                order='order_id, sequence, id',
            )
            for line in all_lines:
                lines_by_order.setdefault(line.order_id.id, []).append(line)
        # Warm caches in one query each instead of per line.
        orders.mapped('partner_id.partner_code')
        location_names = {
            location.id: location.display_name
            for location in orders.destination_location_id
        }

        write_string = sheet.write_string
        write_number = sheet.write_number
        row = 4
        item_number = 0
        for order in orders:
            order_lines = lines_by_order.get(order.id)
            if not order_lines:
                continue
            pr_name = order.pr_number or order.requisition_order or ''
            requisition = requisitions.get(pr_name)
            order_name = order.name or ''
            order_date = order.date_order
            partner = order.partner_id
            partner_code = partner.partner_code or ''
            partner_name = partner.name or ''
            approval_date = requisition.approval_date if requisition else False
            notes = html2plaintext(order.notes or '')
            destination = location_names.get(order.destination_location_id.id, '')
            for line in order_lines:
                item_number += 1
                write_number(row, 0, item_number)
                write_string(row, 1, order_name)
                self._write_date(sheet, row, 2, order_date, date_format, tz)
                write_string(row, 3, partner_code)
                write_string(row, 4, partner_name)
                write_string(row, 5, pr_name)
                self._write_date(sheet, row, 6, line.date_planned, date_format, tz)
                self._write_date(sheet, row, 7, approval_date, date_format, tz)
                write_string(row, 8, notes, notes_format)
                write_string(row, 9, line.name or '')
                write_number(row, 10, line.price_unit or 0.0, price_format)
                qty = line.product_qty or 0.0
                write_number(
                    row, 11, qty,
                    integer_format if float(qty).is_integer() else decimal_format,
                )
                write_number(row, 12, line.price_subtotal or 0.0, price_format)
                received = line.qty_received or 0.0
                write_number(
                    row, 13, received,
                    integer_format if float(received).is_integer() else decimal_format,
                )
                sheet.write_blank(row, 14, None)
                write_string(row, 15, destination)
                sheet.write_blank(row, 16, None)
                row += 1

        sheet.autofilter(3, 0, max(3, row - 1), len(self.HEADERS) - 1)
        workbook.close()
        return output.getvalue()
