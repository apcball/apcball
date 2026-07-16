"""Per-location configuration tests.

Validates the new contract: one `pos.lite.config` per (company, stock.location),
driven by `stock.location`. Sessions inherit the location and the single-open
invariant is enforced per location.
"""

from odoo.tests import common, tagged
from odoo.exceptions import UserError, ValidationError


@tagged('-at_install', 'post_install')
class TestLocationConfig(common.TransactionCase):
    """`pos.lite.config` is bound to a stock.location."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search([
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.pricelist = cls.env['product.pricelist'].create({
            'name': 'Loc PL',
            'company_id': cls.company.id,
        })
        cls.journal = cls.env['account.journal'].create({
            'name': 'Loc Cash',
            'type': 'cash',
            'code': 'LCSH',
            'company_id': cls.company.id,
        })
        # Two distinct internal locations under the warehouse stock location.
        cls.loc_a = cls.env['stock.location'].create({
            'name': 'Loc A',
            'location_id': cls.warehouse.lot_stock_id.id,
            'usage': 'internal',
            'company_id': cls.company.id,
        })
        cls.loc_b = cls.env['stock.location'].create({
            'name': 'Loc B',
            'location_id': cls.warehouse.lot_stock_id.id,
            'usage': 'internal',
            'company_id': cls.company.id,
        })
        # Advance sequences to avoid collisions with existing MOG_DEV data.
        cls.env.cr.execute(
            "UPDATE ir_sequence SET number_next = 100000 "
            "WHERE code IN ('pos.lite.session', 'pos.lite.order') "
            "AND number_next < 100000"
        )
        cls.env.invalidate_all()

    def _config_vals(self, location):
        return {
            'name': 'Cfg %s' % location.name,
            'company_id': self.company.id,
            'warehouse_id': self.warehouse.id,
            'location_id': location.id,
            'pricelist_id': self.pricelist.id,
            'journal_id': self.journal.id,
        }

    # ── Constraints ──────────────────────────────────────────────

    def test_config_requires_location(self):
        """A config without a location is rejected."""
        vals = self._config_vals(self.loc_a)
        del vals['location_id']
        with self.assertRaises(ValidationError):
            self.env['pos.lite.config'].create(vals)

    def test_two_configs_same_location_rejected(self):
        """Two configs on the same (company, location) collide."""
        self.env['pos.lite.config'].create(self._config_vals(self.loc_a))
        with self.assertRaises(ValidationError):
            self.env['pos.lite.config'].create(self._config_vals(self.loc_a))

    def test_two_configs_different_locations_ok(self):
        """Distinct locations each get their own config."""
        cfg_a = self.env['pos.lite.config'].create(self._config_vals(self.loc_a))
        cfg_b = self.env['pos.lite.config'].create(self._config_vals(self.loc_b))
        self.assertNotEqual(cfg_a.id, cfg_b.id)
        self.assertEqual(cfg_a.location_id, self.loc_a)
        self.assertEqual(cfg_b.location_id, self.loc_b)

    # ── Lookup helper ────────────────────────────────────────────

    def test_get_config_for_location(self):
        """get_config_for_location resolves the bound config."""
        cfg = self.env['pos.lite.config'].create(self._config_vals(self.loc_a))
        resolved = self.env['pos.lite.config'].get_config_for_location(self.loc_a.id)
        self.assertEqual(resolved, cfg)
        # An unbound location resolves to an empty recordset.
        empty = self.env['pos.lite.config'].get_config_for_location(self.loc_b.id)
        self.assertFalse(empty)
        # No location → empty recordset, no crash.
        self.assertFalse(self.env['pos.lite.config'].get_config_for_location(False))

    # ── Session inheritance ──────────────────────────────────────

    def test_session_inherits_location(self):
        """A session exposes the location of its config."""
        cfg = self.env['pos.lite.config'].create(self._config_vals(self.loc_a))
        session = self.env['pos.lite.session'].create({
            'config_id': cfg.id,
            'company_id': self.company.id,
        })
        self.assertEqual(session.location_id, self.loc_a)

    def test_two_sessions_same_location_blocked(self):
        """Two open sessions on the same location are not allowed."""
        cfg = self.env['pos.lite.config'].create(self._config_vals(self.loc_a))
        self.env['pos.lite.session'].create({
            'config_id': cfg.id,
            'company_id': self.company.id,
        })
        with self.assertRaises(UserError):
            self.env['pos.lite.session'].create({
                'config_id': cfg.id,
                'company_id': self.company.id,
            })

    def test_two_sessions_different_locations_allowed(self):
        """Two open sessions on different locations run in parallel."""
        cfg_a = self.env['pos.lite.config'].create(self._config_vals(self.loc_a))
        cfg_b = self.env['pos.lite.config'].create(self._config_vals(self.loc_b))
        self.env['pos.lite.session'].create({
            'config_id': cfg_a.id,
            'company_id': self.company.id,
        })
        # Must not raise — different location.
        sess_b = self.env['pos.lite.session'].create({
            'config_id': cfg_b.id,
            'company_id': self.company.id,
        })
        self.assertEqual(sess_b.location_id, self.loc_b)
