from odoo import models, api
import logging

_logger = logging.getLogger(__name__)


class SaleAdvancePaymentInvInherit(models.TransientModel):
    _inherit = 'sale.advance.payment.inv'

    def _prepare_invoice_values(self, order, so_lines):
        """
        Override เพื่อเพิ่มค่า advance_payment_method ลงใน invoice
        """
        # เรียก method เดิม
        invoice_vals = super()._prepare_invoice_values(order, so_lines)
        
        # เพิ่มค่า advance_payment_method ลงใน invoice
        invoice_vals['advance_payment_method'] = self.advance_payment_method
        
        _logger.info(f"Creating invoice with advance_payment_method: {self.advance_payment_method}")
        
        return invoice_vals
