# Part of buz addons for Mogen Co. See LICENSE file.
from odoo.tests.common import TransactionCase


class ReverseManufacturingCommon(TransactionCase):
    """Shared fixtures.

    Note: MOG_DEV has orphaned columns on stock.warehouse and
    product.product creates can fail there — locations are therefore
    reused from the standard warehouse, only products/categories are
    created (needed for valuation isolation). Run against the isolated
    docker-compose.test.yml Postgres first.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        cls.company = cls.env.company
        cls.stock_location = cls.env.ref('stock.stock_location_stock')
        account_vals = cls._get_valuation_account_vals()
        cls.category_fifo = cls.env['product.category'].create(dict({
            'name': 'RMO Test FIFO',
            'property_cost_method': 'fifo',
            'property_valuation': 'real_time',
        }, **account_vals))
        cls.category_avco = cls.env['product.category'].create(dict({
            'name': 'RMO Test AVCO',
            'property_cost_method': 'average',
            'property_valuation': 'real_time',
        }, **account_vals))
        cls.finished = cls._create_product('RMO TV', cls.category_fifo, 1000.0, 12.0)
        cls.comp_panel = cls._create_product('RMO Panel', cls.category_fifo, 500.0, 6.0)
        cls.comp_pcb = cls._create_product('RMO PCB', cls.category_fifo, 300.0, 1.0)
        cls.comp_plastic = cls._create_product('RMO Plastic', cls.category_fifo, 100.0, 4.0)

        cls.loc_reuse = cls.env['stock.location'].create({
            'name': 'RMO Reusable',
            'usage': 'internal',
            'location_id': cls.stock_location.id,
        })
        cls.loc_repair = cls.env['stock.location'].create({
            'name': 'RMO Repair',
            'usage': 'internal',
            'location_id': cls.stock_location.id,
        })

        cls.workcenter = cls.env['mrp.workcenter'].create({
            'name': 'RMO Bench',
            'costs_hour': 120.0,
        })
        # buz_mrp_workcenter_cost_breakdown turns costs_hour into a stored
        # compute (dl + idl + oh): feed the breakdown fields when present
        # so the hourly rate is really 120.
        if 'dl_per_hour' in cls.workcenter._fields:
            cls.workcenter.dl_per_hour = 120.0

        cls.bom_reverse = cls.env['mrp.bom'].create({
            'product_tmpl_id': cls.finished.product_tmpl_id.id,
            'product_qty': 1.0,
            'type': 'reverse',
            'consumption': 'flexible',
            'allocation_method': 'bom_cost',
            'bom_line_ids': [
                (0, 0, {
                    'product_id': cls.comp_panel.id,
                    'product_qty': 1.0,
                    'recovery_percent': 100.0,
                    'dest_location_id': cls.loc_reuse.id,
                }),
                (0, 0, {
                    'product_id': cls.comp_pcb.id,
                    'product_qty': 1.0,
                    'recovery_percent': 100.0,
                    'dest_location_id': cls.loc_repair.id,
                }),
                (0, 0, {
                    'product_id': cls.comp_plastic.id,
                    'product_qty': 2.0,
                    'recovery_percent': 50.0,
                }),
            ],
            'operation_ids': [
                (0, 0, {
                    'name': 'Disassemble',
                    'workcenter_id': cls.workcenter.id,
                    'time_cycle_manual': 30.0,
                }),
            ],
        })

    @classmethod
    def _get_valuation_account_vals(cls):
        """Create dedicated stock valuation accounts and journal so the
        tests are self-contained regardless of the DB's chart of
        accounts configuration."""
        Account = cls.env['account.account']
        input_acc = Account.create({
            'name': 'RMO Stock Input',
            'code': 'RMO.IN',
            'account_type': 'asset_current',
            'reconcile': True,
        })
        output_acc = Account.create({
            'name': 'RMO Stock Output',
            'code': 'RMO.OUT',
            'account_type': 'asset_current',
            'reconcile': True,
        })
        valuation_acc = Account.create({
            'name': 'RMO Stock Valuation',
            'code': 'RMO.VAL',
            'account_type': 'asset_current',
        })
        journal = cls.env['account.journal'].create({
            'name': 'RMO Stock Journal',
            'code': 'RMOSJ',
            'type': 'general',
        })
        return {
            'property_stock_account_input_categ_id': input_acc.id,
            'property_stock_account_output_categ_id': output_acc.id,
            'property_stock_valuation_account_id': valuation_acc.id,
            'property_stock_journal': journal.id,
        }

    @classmethod
    def _create_product(cls, name, category, price, weight):
        return cls.env['product.product'].create({
            'name': name,
            'detailed_type': 'product',
            'categ_id': category.id,
            'standard_price': price,
            'weight': weight,
        })

    @classmethod
    def _receive_input(cls, qty=1.0, price=None):
        """Put input product in stock at a known cost via an incoming move."""
        move = cls.env['stock.move'].create({
            'name': 'RMO test in',
            'product_id': cls.finished.id,
            'product_uom': cls.finished.uom_id.id,
            'product_uom_qty': qty,
            'price_unit': price if price is not None else cls.finished.standard_price,
            'location_id': cls.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': cls.stock_location.id,
            'company_id': cls.company.id,
        })
        move._action_confirm()
        move.quantity = qty
        move.picked = True
        move._action_done()
        return move

    @classmethod
    def _create_rmo(cls, qty=1.0):
        rmo = cls.env['mrp.production'].create({
            'is_reverse': True,
            'product_id': cls.finished.id,
            'product_uom_id': cls.finished.uom_id.id,
            'product_qty': qty,
            'bom_id': cls.bom_reverse.id,
        })
        if not rmo.recovery_line_ids:
            rmo.recovery_line_ids = [
                (0, 0, vals) for vals in rmo._prepare_recovery_line_vals()
            ]
        return rmo
