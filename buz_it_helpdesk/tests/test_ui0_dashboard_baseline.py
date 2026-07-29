from pathlib import Path
from unittest import TestCase


class TestUI0DashboardBaseline(TestCase):
    def test_asset_is_absent_from_manifest_menu_and_dashboard_contract(self):
        root = Path(__file__).resolve().parents[1]
        combined = "\n".join([
            (root / "__manifest__.py").read_text(encoding="utf-8"),
            (root / "views/helpdesk_menus.xml").read_text(encoding="utf-8"),
            (root / "static/src/js/it_management_dashboard.js").read_text(encoding="utf-8"),
            (root / "static/src/xml/it_management_dashboard.xml").read_text(encoding="utf-8"),
        )
        self.assertNotIn("buz.it.asset", combined)
        self.assertNotIn("menu_it_assets", combined)
        self.assertNotIn("renewals_due", combined)
