from odoo import models, fields, api, tools


class MarketplaceFeeAllocationReport(models.Model):
    _name = 'marketplace.fee.allocation.report'
    _description = 'Marketplace Fee Allocation Report'
    _auto = False
    _rec_name = 'settlement_name'

    # Settlement information
    settlement_id = fields.Many2one('marketplace.settlement', string='Settlement', readonly=True)
    settlement_name = fields.Char('Settlement Reference', readonly=True)
    settlement_date = fields.Date('Settlement Date', readonly=True)
    trade_channel = fields.Selection([
        ('shopee', 'Shopee'), 
        ('lazada', 'Lazada'), 
        ('nocnoc', 'Noc Noc'), 
        ('tiktok', 'Tiktok'), 
        ('spx', 'SPX'),
        ('other', 'Other')
    ], string='Trade Channel', readonly=True)
    marketplace_partner_id = fields.Many2one('res.partner', string='Marketplace Partner', readonly=True)

    # Invoice information
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True)
    invoice_number = fields.Char('Invoice Number', readonly=True)
    invoice_date = fields.Date('Invoice Date', readonly=True)
    customer_id = fields.Many2one('res.partner', string='Customer', readonly=True)
    invoice_amount_untaxed = fields.Monetary('Invoice Amount (Pre-tax)', readonly=True, currency_field='company_currency_id')
    invoice_amount_total = fields.Monetary('Invoice Total', readonly=True, currency_field='company_currency_id')

    # Allocation information
    allocation_method = fields.Selection([
        ('proportional', 'Proportional by Pre-tax Amount'),
        ('exact', 'Exact Values from Marketplace CSV')
    ], string='Allocation Method', readonly=True)
    allocation_base_amount = fields.Monetary('Allocation Base Amount', readonly=True, currency_field='company_currency_id')
    allocation_percentage = fields.Float('Allocation %', readonly=True, digits=(12, 6))

    # Allocated amounts
    base_fee_alloc = fields.Monetary('Base Fee Allocated', readonly=True, currency_field='company_currency_id')
    vat_input_alloc = fields.Monetary('VAT Input Allocated', readonly=True, currency_field='company_currency_id')
    wht_alloc = fields.Monetary('WHT Allocated', readonly=True, currency_field='company_currency_id')
    total_deductions_alloc = fields.Monetary('Total Deductions Allocated', readonly=True, currency_field='company_currency_id')
    net_payout_alloc = fields.Monetary('Net Payout Allocated', readonly=True, currency_field='company_currency_id')

    # Profitability analysis
    gross_profit = fields.Monetary('Gross Profit', readonly=True, currency_field='company_currency_id',
                                   help='Revenue minus allocated marketplace fees')
    profit_margin = fields.Float('Profit Margin %', readonly=True, digits=(12, 2),
                                 help='Gross profit as percentage of revenue')
    
    # Time dimensions
    year = fields.Integer('Year', readonly=True)
    month = fields.Integer('Month', readonly=True)
    quarter = fields.Integer('Quarter', readonly=True)
    
    # Currency
    company_currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    def init(self):
        """Create database view for reporting"""
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    row_number() OVER () AS id,
                    
                    -- Settlement information
                    fa.settlement_id,
                    s.name AS settlement_name,
                    s.date AS settlement_date,
                    s.trade_channel,
                    s.marketplace_partner_id,
                    
                    -- Invoice information
                    fa.invoice_id,
                    fa.invoice_number,
                    fa.invoice_date,
                    fa.invoice_partner_id AS customer_id,
                    fa.invoice_amount_untaxed,
                    fa.invoice_amount_total,
                    
                    -- Allocation information
                    fa.allocation_method,
                    fa.allocation_base_amount,
                    fa.allocation_percentage,
                    
                    -- Allocated amounts
                    fa.base_fee_alloc,
                    fa.vat_input_alloc,
                    fa.wht_alloc,
                    fa.total_deductions_alloc,
                    fa.net_payout_alloc,
                    
                    -- Profitability analysis
                    (fa.allocation_base_amount - fa.total_deductions_alloc) AS gross_profit,
                    CASE 
                        WHEN fa.allocation_base_amount > 0 THEN
                            ((fa.allocation_base_amount - fa.total_deductions_alloc) / fa.allocation_base_amount) * 100
                        ELSE 0
                    END AS profit_margin,
                    
                    -- Time dimensions
                    EXTRACT(year FROM fa.invoice_date) AS year,
                    EXTRACT(month FROM fa.invoice_date) AS month,
                    EXTRACT(quarter FROM fa.invoice_date) AS quarter,
                    
                    -- Currency and company
                    fa.company_currency_id,
                    fa.company_id
                    
                FROM marketplace_fee_allocation fa
                JOIN marketplace_settlement s ON fa.settlement_id = s.id
                WHERE fa.invoice_id IS NOT NULL
            )
        """ % self._table)
