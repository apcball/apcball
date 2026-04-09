from odoo import models, fields, api, _, exceptions
from datetime import datetime, time
import json

class FifoResetWizard(models.TransientModel):
    _name = 'fifo.reset.wizard'
    _description = 'FIFO Reset Wizard'

    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company, required=True)
    reset_date = fields.Date(string='Reset ณ วันที่', default=fields.Date.today, required=True,
                             help='ระบุวันที่ตัดยอด: ระบบจะล้างข้อมูล stock/valuation จนถึงวันที่นี้')
    warehouse_ids = fields.Many2many(
        'stock.warehouse', string='Warehouses',
        help='เลือก warehouse ที่ต้องการ reset — ระบบจะประมวลผลทีละ warehouse เพื่อลดโหลด ('
             'หากไม่เลือก จะ reset ทุก warehouse ของ company)',
    )
    
    # KPI Computed
    open_picking_count = fields.Integer(compute='_compute_kpi')
    reserved_qty_count = fields.Integer(compute='_compute_kpi')
    total_products = fields.Integer(compute='_compute_kpi')
    total_stock_value = fields.Float(compute='_compute_kpi', digits='Account')
    warehouse_count = fields.Integer(compute='_compute_kpi', string='Warehouse Count')
    
    confirm_checkbox = fields.Boolean(string="I understand this will permanently reset inventory")
    dry_run = fields.Boolean(string="Simulation mode (no data will be changed)", default=True)
    confirm_text = fields.Char(string="Type RESET to confirm")
    
    # Result Data
    result_data = fields.Text(string="Result Component Data")
    kpi_data = fields.Text(string="KPI JSON Data", compute='_compute_kpi')
    
    @api.onchange('company_id')
    def _onchange_company_id(self):
        """Reset warehouse selection when company changes."""
        self.warehouse_ids = False
        return {'domain': {'warehouse_ids': [('company_id', '=', self.company_id.id)]}}
    
    @api.depends('company_id', 'reset_date', 'warehouse_ids')
    def _compute_kpi(self):
        for rec in self:
            # Bug #5 fix: สร้าง cutoff datetime จาก reset_date
            reset_dt = False
            if rec.reset_date:
                reset_dt = datetime.combine(rec.reset_date, time.max)

            # Resolve warehouses
            if rec.warehouse_ids:
                warehouses = rec.warehouse_ids
            else:
                warehouses = self.env['stock.warehouse'].search([
                    ('company_id', '=', rec.company_id.id)
                ])
            rec.warehouse_count = len(warehouses)

            # Get internal locations for selected warehouses
            locations = self.env['stock.location'].search([
                ('warehouse_id', 'in', warehouses.ids),
                ('usage', '=', 'internal'),
                ('company_id', '=', rec.company_id.id),
            ])

            # Open pickings — filter by locations
            picking_domain = [
                ('company_id', '=', rec.company_id.id),
                ('state', 'not in', ['done', 'cancel']),
                '|',
                ('location_id', 'in', locations.ids),
                ('location_dest_id', 'in', locations.ids),
            ]
            if reset_dt:
                picking_domain += [('scheduled_date', '<=', reset_dt)]
            rec.open_picking_count = self.env['stock.picking'].search_count(picking_domain)
            
            # Reserved moves — filter by locations
            move_domain = [
                ('company_id', '=', rec.company_id.id),
                ('state', 'in', ['assigned', 'partially_available']),
                '|',
                ('location_id', 'in', locations.ids),
                ('location_dest_id', 'in', locations.ids),
            ]
            if reset_dt:
                move_domain += [('date', '<=', reset_dt)]
            moves = self.env['stock.move'].search(move_domain)
            rec.reserved_qty_count = len(moves)
            
            # Total stock value — ALL SVLs (module ล้างทั้งหมด ไม่ filter date)
            svls = self.env['stock.valuation.layer'].search([('company_id', '=', rec.company_id.id)])
            rec.total_stock_value = sum(svls.mapped('value'))
            
            # Total products with stock — filter by locations
            quants = self.env['stock.quant'].search([
                ('company_id', '=', rec.company_id.id),
                ('location_id', 'in', locations.ids),
            ]).filtered(lambda q: q.quantity != 0)
            rec.total_products = len(quants.mapped('product_id'))
            
            rec.kpi_data = json.dumps({
                'open_pickings': rec.open_picking_count,
                'reserved_qty': rec.reserved_qty_count,
                'total_products': rec.total_products,
                'total_stock_value': rec.total_stock_value,
                'currency_symbol': rec.company_id.currency_id.symbol or '$',
                'warehouse_count': rec.warehouse_count,
                'warehouse_names': ', '.join(warehouses.mapped('name')),
            })

    def run_simulation(self):
        self.ensure_one()
        return self._execute(dry_run=True)

    def execute_reset(self):
        self.ensure_one()
        if self.dry_run:
            raise exceptions.UserError(_('Please uncheck "Simulation mode" before executing.'))
        return self._execute(dry_run=False)

    def _execute(self, dry_run=False):
        service = self.env['fifo.reset.service']
        wh_ids = self.warehouse_ids.ids if self.warehouse_ids else False
        res = service.run(
            dry_run=dry_run,
            company_id=self.company_id.id,
            reset_date=self.reset_date,
            warehouse_ids=wh_ids,
        )
        
        self.result_data = json.dumps(res)
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'fifo.reset.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }
