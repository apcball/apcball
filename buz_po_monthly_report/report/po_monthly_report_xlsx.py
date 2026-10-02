import io
from datetime import datetime, time, timedelta

import pytz
import xlsxwriter

from odoo import _, fields, models
from odoo.exceptions import AccessError, UserError


class PurchaseOrderMonthlyXlsx(models.AbstractModel):
    _name = 'buz.po.monthly.report.xlsx.generator'
    _description = 'Purchase Order Monthly XLSX Report'

    HEADERS = [
        'ลำดับ', 'เลขที่เอกสาร', 'วันที่เปิดPO', 'รหัสผู้จำหน่าย',
        'ชื่อผู้จำหน่าย', 'Ref', 'กำหนดส่ง', 'วันที่ PR', 'ชื่อ', 'ราคา',
        'จำนวน', 'AMOUNT', 'รับ', 'คงเหลือ', 'สถานที่ส่ง', 'CREDIT',
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

        if wizard.pr_date_from:
            pr_domain = [
                ('requisition_date', '>=', wizard.pr_date_from),
                ('requisition_date', '<=', wizard.pr_date_to),
            ]
            try:
                requisitions = self.env['employee.purchase.requisition'].search(
                    pr_domain
                )
            except AccessError as error:
                raise UserError(_(
                    'You need access to Purchase Requisitions to filter this report by PR date.'
                )) from error

            pr_names = requisitions.mapped('name')
            if not pr_names:
                return [('id', '=', 0)]
            # PR และ PO ต้องตรงตามช่วงที่เลือกพร้อมกัน
            domain.extend([
                '|',
                ('pr_number', 'in', pr_names),
                ('requisition_order', 'in', pr_names),
            ])
        return domain

    def _get_requisitions_by_name(self, purchase_orders):
        pr_names = {
            order.pr_number or order.requisition_order
            for order in purchase_orders
            if order.pr_number or order.requisition_order
        }
        if not pr_names:
            return {}
        try:
            requisitions = self.env['employee.purchase.requisition'].search([
                ('name', 'in', list(pr_names)),
            ])
        except AccessError as error:
            raise UserError(_(
                'You need access to Purchase Requisitions to include PR dates in this report.'
            )) from error
        return {requisition.name: requisition for requisition in requisitions}

    @staticmethod
    def _credit_days(order):
        payment_term = (
            order.payment_term_id
            or order.partner_id.property_supplier_payment_term_id
        )
        if not payment_term or not payment_term.line_ids:
            return None
        return max(payment_term.line_ids.mapped('nb_days'))

    def _date_value(self, value):
        if not value:
            return False
        if isinstance(value, datetime):
            return fields.Datetime.context_timestamp(self, value).date()
        return fields.Date.to_date(value)

    def _write_date(self, sheet, row, col, value, cell_format):
        date_value = self._date_value(value)
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
        requisitions = self._get_requisitions_by_name(orders)

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
        quantity_format = workbook.add_format({'num_format': '#,##0.####'})
        widths = [8, 18, 14, 18, 36, 20, 14, 14, 58, 14, 12, 16, 12, 14, 28, 12]
        for col, width in enumerate(widths):
            sheet.set_column(col, col, width)

        sheet.merge_range(
            0, 0, 0, len(self.HEADERS) - 1,
            'รายงานใบสั่งซื้อสินค้า', title_format,
        )
        pr_range = self._date_range_label(wizard.pr_date_from, wizard.pr_date_to)
        po_range = self._date_range_label(wizard.po_date_from, wizard.po_date_to)
        sheet.merge_range(
            1, 0, 1, len(self.HEADERS) - 1,
            'วันที่ PR: %s    วันที่เปิด PO: %s' % (pr_range, po_range),
            criteria_format,
        )
        sheet.write_row(3, 0, self.HEADERS, header_format)
        sheet.set_row(3, 32)
        sheet.freeze_panes(4, 0)

        money_formats = {}
        row = 4
        for order in orders:
            pr_name = order.pr_number or order.requisition_order or ''
            requisition = requisitions.get(pr_name)
            currency = order.currency_id
            if currency.id not in money_formats:
                symbol = (currency.symbol or '').replace('"', '""')
                money_formats[currency.id] = workbook.add_format({
                    'num_format': '"%s"#,##0.00;[Red]("%s"#,##0.00)' % (
                        symbol, symbol,
                    ),
                })
            money_format = money_formats[currency.id]
            item_number = 0
            lines = order.order_line.filtered(
                lambda line: not line.display_type
            ).sorted(key=lambda item: (item.sequence, item.id))
            for line in lines:
                item_number += 1
                values = [
                    item_number,
                    order.name or '',
                    order.date_order,
                    order.partner_id.partner_code or '',
                    order.partner_id.name or '',
                    pr_name,
                    line.date_planned,
                    requisition.requisition_date if requisition else False,
                    line.name or '',
                    line.price_unit,
                    line.product_qty,
                    line.price_subtotal,
                    line.qty_received,
                    line.product_qty - line.qty_received,
                    order.destination_location_id.display_name
                    if order.destination_location_id else '',
                    self._credit_days(order),
                ]
                sheet.write_number(row, 0, values[0])
                sheet.write(row, 1, values[1])
                self._write_date(sheet, row, 2, values[2], date_format)
                sheet.write(row, 3, values[3])
                sheet.write(row, 4, values[4])
                sheet.write(row, 5, values[5])
                self._write_date(sheet, row, 6, values[6], date_format)
                self._write_date(sheet, row, 7, values[7], date_format)
                sheet.write(row, 8, values[8])
                sheet.write_number(row, 9, values[9] or 0.0, money_format)
                sheet.write_number(row, 10, values[10] or 0.0, quantity_format)
                sheet.write_number(row, 11, values[11] or 0.0, money_format)
                sheet.write_number(row, 12, values[12] or 0.0, quantity_format)
                sheet.write_number(row, 13, values[13] or 0.0, quantity_format)
                sheet.write(row, 14, values[14])
                if values[15] is None:
                    sheet.write_blank(row, 15, None)
                else:
                    sheet.write_number(row, 15, values[15])
                row += 1

        sheet.autofilter(3, 0, max(3, row - 1), len(self.HEADERS) - 1)
        workbook.close()
        return output.getvalue()
