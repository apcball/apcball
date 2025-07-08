# -*- coding: utf-8 -*-
###############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2023-TODAY Cybrosys Technologies(<https://www.cybrosys.com>)
#    Author: Vishnu KP S (odoo@cybrosys.com)
#
#    This program is under the terms of the Odoo Proprietary License v1.0 (OPL-1)
#    It is forbidden to publish, distribute, sublicense, or sell copies of the
#    Software or modified copies of the Software.
#
#    THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#    FITNESS FOR A PARTICULAR PURPOSE AND NON INFRINGEMENT. IN NO EVENT SHALL
#    THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,DAMAGES OR OTHER
#    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,ARISING
#    FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#    DEALINGS IN THE SOFTWARE.
#
###############################################################################
from datetime import datetime
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import pytz


class MobileService(models.Model):
    """Creates the model mobile.service"""
    _name = 'mobile.service'
    _rec_name = 'name'
    _description = "Mobile Service"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Service Number', copy=False, default="New",
                       help="Number of The Service.")
    person_name = fields.Many2one('res.partner',
                                  string="Customer Name", required=True,
                                  help="Name of the customer.")
    contact_no = fields.Char(related='person_name.mobile',
                             string="Contact Number",
                             help="Contact number of the customer.")
    email_id = fields.Char(related='person_name.email', string="Email",
                           help="Email ID of the customer.")
    street = fields.Char(related='person_name.street', string="Address",
                         help="Street of the customer.")
    street2 = fields.Char(related='person_name.street2', string="Address",
                          help="Street2 of the customer.")
    city = fields.Char(related='person_name.city', string="Address",
                       help="City of the customer.")
    state_id = fields.Many2one(related='person_name.state_id', string="Address",
                               help="State of the customer.")
    zip = fields.Char(related='person_name.zip', string="Address",
                      help="Zip number of the customer address.")
    country_id = fields.Many2one(related='person_name.country_id',
                                 string="Address",
                                 help="Country of the customer.")
    brand_name = fields.Many2one('mobile.brand',
                                 string="Mobile Brand",
                                 help="Brand name of the mobile.")
    is_in_warranty = fields.Boolean(
        'In Warranty', default=False,
        help="Specify if the product is in warranty.")
    warranty_number = fields.Char(string="Warranty No ",
                                  help="Warranty details.")
    re_repair = fields.Boolean('Re-repair', default=False,
                               help="Re-repairing.")
    imei_no = fields.Char(string="IMEI Number",
                          help="IMEI Number of the device.")
    model_name = fields.Many2one('brand.model', string="Model",
                                 domain="[('mobile_brand_name','=',brand_name)]"
                                 , help="Model name of the device.")
    image_medium = fields.Binary(related='model_name.image_medium', store=True,
                                 attachment=True, help="Image of the device.")
    date_request = fields.Date(string="Requested Date",
                               default=fields.Date.context_today,
                               help="Device submitted date.")
    return_date = fields.Date(string="Return Date", required=True,
                              help="Device returned date.")
    technician_name = fields.Many2one('res.users',
                                      string="Technician Name",
                                      default=lambda self: self.env.user,
                                      help="Work assigned technician name.",
                                      required=True)
    service_state = fields.Selection(
        [('draft', 'Draft'), ('assigned', 'Assigned'),
         ('completed', 'Completed'), ('returned', 'Returned'),
         ('not_solved', 'Not solved')],
        string='Service Status', default='draft', track_visibility='always',
        help='Service status of the work.')
    complaints_tree = fields.One2many('mobile.complaint.tree',
                                      'complaint_id',
                                      string='Complaints Tree',
                                      help='Mobile complaint details.')
    product_order_line = fields.One2many('product.order.line',
                                         'product_order_id',
                                         string='Parts Order Lines',
                                         help='Product parts order details.')
    internal_notes = fields.Text(string="Internal Notes")
    invoice_count = fields.Integer(compute='_compute_invoice_count',
                                   string='# Invoice', copy=False,
                                   help="Count of invoice.")
    invoice_ids = fields.Many2many("account.move", string='Invoices',
                                   compute="_get_invoiced", readonly=True,
                                   copy=False, help="Invoices line")
    first_payment_inv = fields.Many2one('account.move', copy=False,
                                        help="First payment of the invoice.")
    first_invoice_created = fields.Boolean(string="First Invoice Created",
                                           invisible=True, copy=False,
                                           help="Date of the first invoice.")
    journal_type = fields.Many2one('account.journal',
                                   'Journal', invisible=True,
                                   default=lambda self: self.env[
                                       'account.journal'].search(
                                       [('code', '=', 'SERV')]),
                                   help='Type of the journal.')
    company_id = fields.Many2one('res.company', 'Company',
                                 default=lambda self: self.env.company,
                                 help='Default company id.')

    @api.model
    def _default_picking_transfer(self):
        """To get the default picking transfers."""
        type_obj = self.env['stock.picking.type']
        company_id = self.env.context.get(
            'company_id') or self.env.user.company_id.id
        types = type_obj.search([('code', '=', 'outgoing'),
                                 ('warehouse_id.company_id', '=', company_id)],
                                limit=1)
        if not types:
            types = type_obj.search([('code', '=', 'outgoing'),
                                     ('warehouse_id', '=', False)])
        return types[:4]

    stock_picking_id = fields.Many2one('stock.picking',
                                       string="Picking Id",
                                       help='Stock picking ID information.')
    picking_transfer_id = fields.Many2one('stock.picking.type',
                                          string='Deliver To',
                                          required=True,
                                          default=_default_picking_transfer,
                                          help="This will determine picking "
                                               "type of outgoing shipment.")
    picking_count = fields.Integer(string="Picking Count",
                                   help='Number of outgoing shipment')

    @api.onchange('return_date')
    def check_date(self):
        """Check the return date and request date"""
        if self.return_date:
            return_date_string = datetime.strptime(str(self.return_date),
                                                   "%Y-%m-%d")
            request_date_string = datetime.strptime(str(self.date_request),
                                                    "%Y-%m-%d")
            if return_date_string < request_date_string:
                raise UserError(
                    "Return date should be greater than requested date")

    def approve(self):
        """Assigning the Service Request to the corresponding user"""
        self.service_state = 'assigned'

    def complete(self):
        """Mark the service request as completed"""
        self.service_state = 'completed'

    def return_to(self):
        """The service request is returned to the client"""
        self.service_state = 'returned'

    def not_solved(self):
        """Mark the service request as not solved"""
        self.service_state = 'not_solved'

    def action_send_mail(self):
        """This function opens a window to compose an email, with the edi sale
        template message loaded by default"""
        self.ensure_one()
        try:
            template_id = self.env.ref(
                'mobile_service_shop.email_template_mobile_service')
        except ValueError:
            template_id = False
        try:
            compose_form_id = self.env.ref(
                'mail.email_compose_message_wizard_form')
        except ValueError:
            compose_form_id = False
        ctx = {
            'default_model': 'mobile.service',
            'default_res_ids': self.ids,
            'default_use_template': bool(template_id),
            'default_template_id': template_id.id,
            'default_composition_mode': 'comment'}
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form_id.id, 'form')],
            'view_id': compose_form_id.id,
            'target': 'new',
            'context': ctx}

    def return_advance(self):
        """This method returns the current invoice related to the work"""
        inv_obj = self.env['account.move'].search(
            [('invoice_origin', '=', self.name)])
        inv_ids = []
        for each in inv_obj:
            inv_ids.append(each.id)
        view_id = self.env.ref('account.view_move_form').id
        if inv_ids:
            if len(inv_ids) <= 1:
                value = {
                    'view_mode': 'form',
                    'res_model': 'account.move',
                    'view_id': view_id,
                    'type': 'ir.actions.act_window',
                    'name': 'Invoice',
                    'res_id': inv_ids[0]}
            else:
                value = {
                    'domain': str([('id', 'in', inv_ids)]),
                    'view_mode': 'tree,form',
                    'res_model': 'account.move',
                    'view_id': False,
                    'type': 'ir.actions.act_window',
                    'name': 'Invoice',
                    'res_id': inv_ids[0]}
            return value
        else:
            raise UserError("No invoice created")

    def _compute_invoice_count(self):
        """Calculating the number of invoices"""
        self.invoice_count = self.env['account.move'].search_count(
            [('invoice_origin', '=', self.name)])

    @api.model
    def create(self, vals):
        """Creating sequence"""
        if 'company_id' in vals:
            company_id = vals['company_id']
        else:
            company_id = self.env.company.id
        
        # Ensure we have a unique reference per company
        company = self.env['res.company'].browse(company_id)
        sequence = self.env['ir.sequence'].sudo().search([
            ('code', '=', 'mobile.service'),
            '|', ('company_id', '=', company_id), ('company_id', '=', False)
        ], limit=1)
        
        if sequence:
            vals['name'] = sequence.with_context(ir_sequence_date=fields.Date.context_today(self)).next_by_id() or _('New')
        else:
            vals['name'] = self.env['ir.sequence'].sudo().next_by_code('mobile.service') or _('New')
        
        vals['service_state'] = 'draft'
        return super(MobileService, self).create(vals)

    def unlink(self):
        """Supering the unlink function"""
        for service in self:
            if service.service_state != 'draft':
                raise UserError(
                    _('You cannot delete an assigned service request'))
        return super(MobileService, self).unlink()

    def action_invoice_create_wizard(self):
        """Opening a wizard to create invoice"""
        return {
            'name': _('Create Invoice'),
            'view_mode': 'form',
            'res_model': 'mobile.invoice',
            'type': 'ir.actions.act_window',
            'target': 'new'}

    def action_post_stock(self):
        """Open wizard to create stock transfer"""
        if not self.product_order_line:
            raise UserError(_('No product lines found to post stock moves for.'))
            
        # Check if any product has quantity to post
        products_to_move = False
        for order in self.product_order_line:
            if order.product_uom_qty > order.qty_stock_move:
                products_to_move = True
                break
                
        if not products_to_move:
            raise UserError(_('All product quantities have already been posted as stock moves.'))
        
        # Make sure there are products to move before opening the wizard
        products_to_move = []
        for order in self.product_order_line:
            if (order.product_id and 
                order.product_uom_qty > order.qty_stock_move and 
                order.product_id.type in ['product', 'consu']):
                
                # Get valid UOM
                uom_id = order.product_id.uom_id.id
                if not uom_id:
                    continue
                    
                # Create line vals
                line_vals = {
                    'product_id': order.product_id.id,
                    'product_uom_id': uom_id,
                    'ordered_qty': order.product_uom_qty,
                    'already_moved_qty': order.qty_stock_move,
                    'remaining_qty': order.product_uom_qty - order.qty_stock_move,
                    'qty_to_transfer': order.product_uom_qty - order.qty_stock_move,
                    'order_line_id': order.id,
                }
                products_to_move.append((0, 0, line_vals))
        
        # Prepare context with products that need to be moved
        context = {
            'default_mobile_service_id': self.id,
            'active_id': self.id,
            'active_model': 'mobile.service',
            'default_origin': self.name,
            'force_create_lines': True,  # Flag to force creation of lines
            'default_product_line_ids': products_to_move,  # Pre-populate product lines
        }
        
        # Return wizard action
        return {
            'name': _('Create Stock Transfer'),
            'type': 'ir.actions.act_window',
            'res_model': 'post.stock.move.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': context
        }

    def action_view_invoice(self):
        """It will show the invoice for the customer"""
        self.ensure_one()
        ctx = dict(create=False)
        action = {
            'name': _("Invoices"),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'target': 'current',
            'context': ctx}
        invoice_ids = self.env['account.move'].search(
            [('invoice_origin', '=', self.name)])
        inv_ids = []
        for each_ids in invoice_ids:
            inv_ids.append(each_ids.id)
        if len(invoice_ids) == 1:
            invoice = inv_ids and inv_ids[0]
            action['res_id'] = invoice
            action['view_mode'] = 'form'
            action['views'] = [
                (self.env.ref('account.view_move_form').id, 'form')]
        else:
            action['view_mode'] = 'tree,form'
            action['domain'] = [('id', 'in', inv_ids)]
        return action

    def get_ticket(self):
        """This will return a ticket associated with the given service"""
        self.ensure_one()
        user = self.env['res.users'].browse(self.env.uid)
        if user.tz:
            tz = pytz.timezone(user.tz)
            time = pytz.utc.localize(datetime.now()).astimezone(tz)
            date_today = time.strftime("%Y-%m-%d %H:%M %p")
        else:
            date_today = datetime.strftime(datetime.now(),
                                           "%Y-%m-%d %I:%M:%S %p")
        complaint_text = ""
        description_text = ""
        complaint_id = self.env['mobile.complaint.tree'].search(
            [('complaint_id', '=', self.id)])
        if complaint_id:
            for obj in complaint_id:
                complaint = obj.complaint_type_tree
                description = obj.description_tree
                complaint_text = complaint.complaint_type + ", " + complaint_text
                if description.description:
                    description_text = description.description + ", " + description_text
        else:
            for obj in complaint_id:
                complaint = obj.complaint_type_tree
                complaint_text = complaint.complaint_type + ", " + complaint_text
        data = {
            'ids': self.ids,
            'model': self._name,
            'date_today': date_today,
            'date_request': self.date_request,
            'date_return': self.return_date,
            'sev_id': self.name,
            'warranty': self.is_in_warranty,
            'customer_name': self.person_name.name,
            'imei_no': self.imei_no,
            'technician': self.technician_name.name,
            'complaint_types': complaint_text,
            'complaint_description': description_text,
            'mobile_brand': self.brand_name.brand_name,
            'model_name': self.model_name.mobile_brand_models}
        return self.env.ref('mobile_service_shop.mobile_service_ticket').report_action(self, data=data)

    def _get_invoiced(self):
        """Get the invoices"""
        for record in self:
            invoices = self.env['account.move'].search([('invoice_origin', '=', record.name)])
            record.invoice_ids = [(6, 0, invoices.ids)] if invoices else [(6, 0, [])]
        
    def action_view_picking(self):
        """ดูใบส่งสินค้าที่เกี่ยวข้องกับงานบริการ"""
        self.ensure_one()
        action = {
            'name': _("Stock Transfers"),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'target': 'current',
            'context': {}}
        
        # ลำดับที่ 1: ใช้ picking ที่เชื่อมโยงโดยตรงถ้ามี
        if self.stock_picking_id and self.stock_picking_id.exists():
            action['res_id'] = self.stock_picking_id.id
            action['view_mode'] = 'form'
            
            # ใช้ try-except เพื่อป้องกันกรณีที่ไม่มี view_id
            try:
                form_view = self.env.ref('stock.view_picking_form')
                action['views'] = [(form_view.id, 'form')]
            except:
                action['view_mode'] = 'form'
                
            return action
        
        # ลำดับที่ 2: ค้นหา picking ที่เกี่ยวข้องกับชื่องานบริการ
        domain = [
            '|', '|',
            ('origin', '=like', f"{self.name}/%"),       # รูปแบบใหม่ที่มี timestamp
            ('origin', '=like', f"{self.name}-%"),       # รูปแบบเดิมที่มีเครื่องหมาย -
            ('origin', '=', self.name)                   # รูปแบบดั้งเดิม
        ]
        
        picking_ids = self.env['stock.picking'].search(domain)
        pick_ids = picking_ids.ids
            
        if len(pick_ids) == 1:
            action['res_id'] = pick_ids[0]
            action['view_mode'] = 'form'
            
            # ใช้ try-except เพื่อป้องกันกรณีที่ไม่มี view_id
            try:
                form_view = self.env.ref('stock.view_picking_form')
                action['views'] = [(form_view.id, 'form')]
            except:
                action['view_mode'] = 'form'
        else:
            action['view_mode'] = 'tree,form'
            action['domain'] = [('id', 'in', pick_ids)]
            
        return action

    @api.model
    def _clear_duplicate_sequences(self):
        """จัดการลำดับและความซ้ำซ้อนของลำดับระหว่างการติดตั้ง/อัพเกรดโมดูล"""
        # วิธีนี้จะถูกเรียกจากไฟล์ sequence_data.xml
        
        # จัดการ sequence สำหรับ mobile.service
        service_sequences = self.env['ir.sequence'].sudo().search([
            ('code', '=', 'mobile.service')
        ])
        
        # ถ้ามีมากกว่า 1 sequence ให้เก็บแค่อันเดียว
        if len(service_sequences) > 1:
            # เก็บเฉพาะ sequence แรกและลบที่เหลือ
            primary_seq = service_sequences[0]
            for seq in service_sequences[1:]:
                seq.sudo().unlink()
            
            # ตั้งค่า sequence ที่เหลือให้ถูกต้อง
            primary_seq.sudo().write({
                'prefix': 'SERV/%(year)s/%(month)s/',
                'use_date_range': True,
                'padding': 4,
                'company_id': False,  # ทำให้ใช้ได้กับทุกบริษัท
            })
        elif len(service_sequences) == 1:
            # ถ้ามีแค่ sequence เดียว ให้ตั้งค่าให้ถูกต้อง
            service_sequences[0].sudo().write({
                'prefix': 'SERV/%(year)s/%(month)s/',
                'use_date_range': True,
                'padding': 4,
                'company_id': False,  # ทำให้ใช้ได้กับทุกบริษัท
            })
            
        # ถ้าไม่มี sequence เลย ระบบจะสร้างให้อัตโนมัติจากข้อมูลในไฟล์ XML
        
        # จัดการ sequence สำหรับ mobile.service.picking ด้วย (ถ้ามี)
        self._ensure_picking_sequence()
        
        return True
        
    @api.model
    def _ensure_picking_sequence(self):
        """สร้างหรืออัพเดต sequence สำหรับ mobile.service.picking"""
        # ตรวจสอบว่ามี sequence สำหรับ mobile.service.picking หรือไม่
        picking_seq = self.env['ir.sequence'].sudo().search([
            ('code', '=', 'mobile.service.picking')
        ], limit=1)
        
        if not picking_seq:
            # สร้าง sequence ใหม่ถ้าไม่มี
            self.env['ir.sequence'].sudo().create({
                'name': 'Mobile Service Stock Picking',
                'code': 'mobile.service.picking',
                'prefix': 'MS/PICK/%(year)s/%(month)s/',
                'padding': 4,
                'company_id': False,  # ทำให้ใช้ได้กับทุกบริษัท
                'use_date_range': True,
            })
        else:
            # อัพเดต sequence ที่มีอยู่
            picking_seq.sudo().write({
                'prefix': 'MS/PICK/%(year)s/%(month)s/',
                'padding': 4,
                'company_id': False,
                'use_date_range': True,
            })
    
    @api.model
    def _reset_sequences(self):
        """รีเซ็ตหมายเลข sequence ในกรณีที่พบปัญหา Reference ซ้ำ
        
        วิธีนี้ใช้สำหรับตั้งค่าหมายเลขลำดับใหม่ เมื่อมีปัญหาเรื่อง reference ซ้ำในระบบ
        สามารถเรียกใช้ได้จาก Developer mode > Technical > Sequences > Run scheduler
        """
        # ค้นหาเลขลำดับล่าสุดของ stock.picking จากฐานข้อมูล
        self.env.cr.execute("""
            SELECT MAX(CAST(
                CASE WHEN name ~ '^\\d+$' 
                THEN name 
                ELSE COALESCE(NULLIF(REGEXP_REPLACE(name, '\\D', '', 'g'), ''), '0') 
                END AS INTEGER)) as max_number 
            FROM stock_picking
        """)
        result = self.env.cr.fetchone()
        max_number = result[0] or 0
        
        # ค้นหา sequence ทั้งหมดที่ใช้สำหรับ picking
        pick_sequences = self.env['ir.sequence'].sudo().search([
            ('code', 'in', ['stock.picking', 'mobile.service.picking'])
        ])
        
        # ตั้งค่า sequence ใหม่ให้สูงกว่าเลขที่มีในฐานข้อมูล
        for seq in pick_sequences:
            new_number = max_number + 10  # เพิ่มอีก 10 เพื่อให้แน่ใจว่าไม่ซ้ำ
            seq.sudo().write({
                'number_next': new_number,
            })
            
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Sequences Reset'),
                'message': _('All stock picking sequences have been reset to avoid reference conflicts.'),
                'type': 'success',
                'sticky': False,
            }
        }
    
    @api.model
    def _force_reset_picking_sequence(self):
        """บังคับรีเซ็ต sequence ของ stock.picking เพื่อป้องกันการซ้ำ"""
        # ค้นหาหมายเลขลำดับสูงสุดจาก stock.picking ที่มีอยู่
        self.env.cr.execute("""
            SELECT MAX(CAST(
                CASE 
                    WHEN name ~ '^[A-Z]+/[0-9]+/[0-9]+/[0-9]+$' THEN 
                        SPLIT_PART(name, '/', 4)
                    WHEN name ~ '^[A-Z]+/[0-9]+$' THEN 
                        SPLIT_PART(name, '/', 2)
                    WHEN name ~ '^[0-9]+$' THEN 
                        name
                    ELSE 
                        COALESCE(NULLIF(REGEXP_REPLACE(name, '[^0-9]', '', 'g'), ''), '0')
                END AS INTEGER
            )) as max_seq_number 
            FROM stock_picking 
            WHERE company_id = %s OR company_id IS NULL
        """, (self.company_id.id,))
        
        result = self.env.cr.fetchone()
        max_number = (result[0] or 0) + 1
        
        # อัพเดตทุก sequence ที่เกี่ยวข้องกับ stock.picking
        picking_sequences = self.env['ir.sequence'].sudo().search([
            '|', 
            ('code', '=', 'stock.picking'),
            ('model', '=', 'stock.picking')
        ])
        
        # รีเซ็ต sequence ให้สูงกว่าเลขที่มีอยู่
        for seq in picking_sequences:
            if seq.company_id == self.company_id or not seq.company_id:
                seq.sudo().write({'number_next': max_number + 10})
                
        return max_number
