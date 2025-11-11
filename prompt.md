🧩 สร้าง module (Current Stock by Date + Export Excel)

Module name: buz_stock_current_report
Odoo Version: 17.0

🎯 ฟังก์ชันหลัก

แสดง สินค้าคงเหลือ (On Hand)

กรองตาม Location / Product / Category

มีตัวเลือก “Stock Date” เพื่อดูคงเหลือย้อนหลัง

ปุ่ม Export Excel บนหน้า Tree View

ใช้ข้อมูลจริงจาก stock.quant และประวัติ stock_move_line

filter “Show Zero Qty = False” (ซ่อนสินค้าที่คงเหลือเป็น 0)

📁 โครงสร้างโมดูล
buz_stock_current_report/
│
├── __manifest__.py
├── __init__.py
│
├── models/
│   ├── __init__.py
│   └── stock_current_report.py
│
├── wizard/
│   ├── __init__.py
│   └── stock_current_export_wizard.py
│
├── views/
│   ├── stock_current_report_views.xml
│   └── stock_current_export_wizard_views.xml
│
└── report/
    ├── __init__.py
    └── stock_current_report_xlsx.py

📄 __manifest__.py
{
    'name': 'Current Stock Report by Date',
    'version': '17.0.1.0.0',
    'summary': 'View and Export Current Stock by Location and Date',
    'category': 'Inventory/Reports',
    'depends': ['stock', 'report_xlsx'],
    'data': [
        'views/stock_current_report_views.xml',
        'views/stock_current_export_wizard_views.xml',
    ],
    'installable': True,
    'application': False,
}

🧠 models/stock_current_report.py
from odoo import models, fields, tools, api

class StockCurrentReport(models.Model):
    _name = 'stock.current.report'
    _description = 'Current Stock Report (by Date)'
    _auto = False
    _order = 'location_id, product_id'

    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    location_id = fields.Many2one('stock.location', string='Location', readonly=True)
    category_id = fields.Many2one('product.category', string='Category', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='UoM', readonly=True)
    quantity = fields.Float('On Hand Qty', readonly=True, digits='Product Unit of Measure')

    stock_date = fields.Date(string="Stock Date", default=fields.Date.context_today)

    def init(self):
        # view basic real-time stock
        tools.drop_view_if_exists(self._cr, self._table)
        self._cr.execute(f"""
            CREATE OR REPLACE VIEW {self._table} AS (
                SELECT
                    sq.id AS id,
                    sq.product_id,
                    sq.location_id,
                    sq.quantity AS quantity,
                    sq.uom_id,
                    pt.categ_id AS category_id
                FROM stock_quant sq
                JOIN product_product pp ON pp.id = sq.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                JOIN stock_location sl ON sl.id = sq.location_id
                WHERE sl.usage = 'internal'
            )
        """)

    @api.model
    def compute_stock_at_date(self, date):
        """Return quantities at a specific date (historical)"""
        query = f"""
            SELECT
                sml.product_id,
                sml.location_id,
                sum(
                    CASE
                        WHEN sml.location_dest_id IN (
                            SELECT id FROM stock_location WHERE usage = 'internal'
                        )
                        THEN sml.qty_done
                        ELSE 0
                    END
                    -
                    CASE
                        WHEN sml.location_id IN (
                            SELECT id FROM stock_location WHERE usage = 'internal'
                        )
                        THEN sml.qty_done
                        ELSE 0
                    END
                ) AS quantity
            FROM stock_move_line sml
            JOIN stock_move sm ON sm.id = sml.move_id
            WHERE sm.date <= %s
            AND sm.state = 'done'
            GROUP BY sml.product_id, sml.location_id
        """
        self._cr.execute(query, (date,))
        return self._cr.dictfetchall()

🧮 wizard/stock_current_export_wizard.py
from odoo import models, fields, api

class StockCurrentExportWizard(models.TransientModel):
    _name = 'stock.current.export.wizard'
    _description = 'Export Current Stock to Excel'

    stock_date = fields.Date(string="Stock Date", required=True, default=fields.Date.context_today)

    def action_export_excel(self):
        return self.env.ref(
            'buz_stock_current_report.action_report_stock_current_xlsx'
        ).report_action(self, data={'stock_date': self.stock_date})

📊 report/stock_current_report_xlsx.py
from odoo import models
from datetime import datetime

class StockCurrentReportXlsx(models.AbstractModel):
    _name = 'report.buz_stock_current_report.stock_current_report_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Current Stock Report Excel (By Date)'

    def generate_xlsx_report(self, workbook, data, wizard):
        sheet = workbook.add_worksheet('Current Stock')
        bold = workbook.add_format({'bold': True})

        headers = ['Location', 'Product', 'Category', 'Qty', 'UoM']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, bold)

        stock_date = data.get('stock_date')
        sheet.write(1, 0, f"Stock as of: {stock_date}", bold)

        # get stock by date
        stock_lines = self.env['stock.current.report'].compute_stock_at_date(stock_date)

        row = 3
        for rec in stock_lines:
            product = self.env['product.product'].browse(rec['product_id'])
            location = self.env['stock.location'].browse(rec['location_id'])
            sheet.write(row, 0, location.display_name)
            sheet.write(row, 1, product.display_name)
            sheet.write(row, 2, product.categ_id.display_name)
            sheet.write(row, 3, rec['quantity'])
            sheet.write(row, 4, product.uom_id.display_name)
            row += 1

🪄 views/stock_current_report_views.xml
<odoo>
  <record id="view_stock_current_report_tree" model="ir.ui.view">
    <field name="name">stock.current.report.tree</field>
    <field name="model">stock.current.report</field>
    <field name="arch" type="xml">
      <tree string="Current Stock">
        <field name="location_id"/>
        <field name="product_id"/>
        <field name="category_id"/>
        <field name="quantity" sum="Total"/>
        <field name="uom_id"/>
      </tree>
    </field>
  </record>

  <record id="view_stock_current_report_search" model="ir.ui.view">
    <field name="name">stock.current.report.search</field>
    <field name="model">stock.current.report</field>
    <field name="arch" type="xml">
      <search string="Filters">
        <field name="location_id"/>
        <field name="product_id"/>
        <field name="category_id"/>
        <group expand="1" string="Group By">
          <filter name="group_location" string="Location" context="{'group_by':'location_id'}"/>
          <filter name="group_category" string="Category" context="{'group_by':'category_id'}"/>
        </group>
      </search>
    </field>
  </record>

  <record id="action_stock_current_report" model="ir.actions.act_window">
    <field name="name">Current Stock Report</field>
    <field name="res_model">stock.current.report</field>
    <field name="view_mode">tree</field>
    <field name="help" type="html">
      <p>ดูสินค้าคงเหลือตาม Location แบบ Real-time หรือย้อนหลังตามวันที่เลือก</p>
    </field>
  </record>

  <act_window
      id="action_stock_current_export_wizard"
      name="Export to Excel"
      res_model="stock.current.export.wizard"
      view_mode="form"
      target="new"
      binding_model="stock.current.report"
      binding_view_types="list"/>

  <menuitem id="menu_stock_current_report_root"
            name="Current Stock Report"
            parent="stock.menu_stock_reporting"
            action="action_stock_current_report"/>
</odoo>

🧾 views/stock_current_export_wizard_views.xml
<odoo>
  <record id="view_stock_current_export_wizard_form" model="ir.ui.view">
    <field name="name">stock.current.export.wizard.form</field>
    <field name="model">stock.current.export.wizard</field>
    <field name="arch" type="xml">
      <form string="Export Current Stock">
        <group>
          <field name="stock_date"/>
        </group>
        <footer>
          <button name="action_export_excel" string="Export Excel" type="object" class="btn-primary"/>
          <button string="Cancel" class="btn-secondary" special="cancel"/>
        </footer>
      </form>
    </field>
  </record>
</odoo>

