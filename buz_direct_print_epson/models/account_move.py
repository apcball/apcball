# -*- coding: utf-8 -*-
import base64
import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_print_epson(self):
        """
        Action to print selected invoices to Epson printer via Local Print Agent
        """
        config = self.env["buz.epson.config"].search([("active", "=", True)], limit=1)
        if not config:
            raise UserError(_("Please configure Epson Print Agent first."))
        
        base_url = self.env["ir.config_parameter"].sudo().get_param("web.base.url")
        success_count = 0
        error_count = 0
        
        for record in self:
            try:
                # Generate PDF for the invoice
                pdf_content, pdf_type = self.env.ref('account.account_invoices')._render_qweb_pdf([record.id])
                
                # Create attachment for the PDF
                attachment = self.env["ir.attachment"].create({
                    "name": f"{record.name or 'Invoice'}.pdf",
                    "type": "binary",
                    "datas": base64.b64encode(pdf_content),
                    "res_model": record._name,
                    "res_id": record.id,
                    "mimetype": "application/pdf",
                })
                
                # Construct the PDF URL
                pdf_url = f"{base_url}/web/content/{attachment.id}?download=true"
                
                # Prepare payload for the print agent
                payload = {
                    "printer": config.default_printer,
                    "file_url": pdf_url,
                    "type": "pdf"
                }
                
                # Send request to the print agent
                response = requests.post(config.agent_url, json=payload, timeout=10)
                response.raise_for_status()
                
                success_count += 1
                
            except Exception as e:
                error_count += 1
                self.env['bus.bus']._sendone(
                    self.env.user.partner_id, 
                    'simple_notification', 
                    {
                        'title': _('Print Error'),
                        'message': _('Failed to print %s: %s') % (record.name, str(e)),
                        'type': 'danger',
                    }
                )
        
        # Show summary notification
        if success_count > 0:
            self.env['bus.bus']._sendone(
                self.env.user.partner_id, 
                'simple_notification', 
                {
                    'title': _('Print Status'),
                    'message': _('Successfully sent %d documents to printer.') % success_count,
                    'type': 'success',
                }
            )
        
        if error_count > 0:
            self.env['bus.bus']._sendone(
                self.env.user.partner_id, 
                'simple_notification', 
                {
                    'title': _('Print Status'),
                    'message': _('Failed to print %d documents.') % error_count,
                    'type': 'warning',
                }
            )
        
        return True