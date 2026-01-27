from odoo import models

class PricelistExcelExport(models.AbstractModel):
    _name = 'report.buz_pricelist_product_manager.pricelist_xlsx'
    _description = 'Pricelist Excel Export'
    
    # Placeholder for potential future report engine integration
    # Currently handled by export wizard directly using xlsxwriter
    pass
