from datetime import date

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestSopCore(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.other_company = cls.env["res.company"].create({"name": "S&OP Other Company"})
        cls.viewer_group = cls.env.ref("mogen_sop_core.group_sop_viewer")
        cls.demand_group = cls.env.ref("mogen_sop_core.group_sop_demand_planner")
        cls.manager_group = cls.env.ref("mogen_sop_core.group_sop_manager")
        cls.admin_group = cls.env.ref("mogen_sop_core.group_sop_admin")
        cls.viewer = cls._make_user("sop_viewer", cls.viewer_group, cls.company)
        cls.demand_planner = cls._make_user(
            "sop_demand_planner",
            cls.demand_group,
            cls.company,
        )
        cls.manager = cls._make_user("sop_manager", cls.manager_group, cls.company)
        cls.sop_admin = cls._make_user(
            "sop_admin",
            cls.admin_group,
            cls.company,
            companies=cls.company | cls.other_company,
        )

    @classmethod
    def _make_user(cls, login, group, company, companies=None):
        companies = companies or company
        return cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": login.replace("_", " ").title(),
                "login": login,
                "company_id": company.id,
                "company_ids": [Command.set(companies.ids)],
                "groups_id": [Command.set([group.id])],
            }
        )

    def _model(self, model_name):
        self.assertIn(model_name, self.env.registry.models)
        return self.env[model_name]

    def _create_plan(self, **values):
        defaults = {
            "name": "FY Planning Cycle",
            "company_id": self.company.id,
            "date_start": date(2026, 1, 1),
            "date_end": date(2026, 12, 31),
        }
        defaults.update(values)
        return self._model("mogen.sop.plan").create(defaults)

    def _move_to_approved(self, plan):
        plan.action_prepare_data()
        plan.action_review()
        plan.action_consensus()
        plan.with_user(self.manager).action_approve()

    def test_models_and_sequence_codes_are_available(self):
        for model_name in (
            "mogen.sop.plan",
            "mogen.sop.plan.version",
            "mogen.sop.scenario",
            "mogen.sop.recommendation",
            "mogen.sop.alert",
        ):
            self._model(model_name)

        first = self._create_plan()
        second = self._create_plan(name="Second Cycle")
        self.assertRegex(first.code, r"^SOP/")
        self.assertNotEqual(first.code, second.code)

    def test_plan_validates_date_range_and_company_code_uniqueness(self):
        with self.assertRaises(ValidationError):
            self._create_plan(
                name="Invalid Dates",
                date_start=date(2026, 5, 1),
                date_end=date(2026, 4, 30),
            )

        self._create_plan(code="SOP/UNIQUE")
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self._create_plan(name="Duplicate", code="SOP/UNIQUE")

        other_company_plan = self._create_plan(
            name="Other Company",
            code="SOP/UNIQUE",
            company_id=self.other_company.id,
        )
        self.assertEqual(other_company_plan.company_id, self.other_company)

    def test_plan_workflow_follows_the_intended_path(self):
        plan = self._create_plan()
        self.assertEqual(plan.state, "draft")
        plan.action_prepare_data()
        self.assertEqual(plan.state, "data_prepared")
        plan.action_review()
        self.assertEqual(plan.state, "review")
        plan.action_consensus()
        self.assertEqual(plan.state, "consensus")

        with self.assertRaises(AccessError):
            plan.with_user(self.viewer).action_approve()
        plan.with_user(self.manager).action_approve()
        self.assertEqual(plan.state, "approved")
        self.assertEqual(plan.approved_by_id, self.manager)
        self.assertTrue(plan.approved_date)

        plan.with_user(self.manager).action_lock()
        self.assertEqual(plan.state, "locked")
        with self.assertRaises(UserError):
            plan.with_user(self.manager).action_cancel()

    def test_plan_state_cannot_bypass_workflow_actions(self):
        Plan = self._model("mogen.sop.plan").with_user(self.demand_planner)
        with self.assertRaises(UserError):
            Plan.create(
                {
                    "name": "Bypassed Create",
                    "company_id": self.company.id,
                    "date_start": date(2026, 1, 1),
                    "date_end": date(2026, 12, 31),
                    "state": "approved",
                }
            )

        plan = self._create_plan()
        with self.assertRaises(UserError):
            plan.with_user(self.demand_planner).write({"state": "approved"})
        with self.assertRaises(UserError):
            plan.with_user(self.manager).write({"state": "locked"})
        self.assertEqual(plan.state, "draft")

    def test_planner_cannot_spoof_plan_workflow_context(self):
        plan = self._create_plan()
        with self.assertRaises(UserError):
            plan.with_user(self.demand_planner).with_context(
                _sop_allow_state_transition=True
            ).write({"state": "approved"})
        self.assertEqual(plan.state, "draft")

    def test_invalid_workflow_transition_is_rejected(self):
        plan = self._create_plan()
        with self.assertRaises(UserError):
            plan.action_review()
        with self.assertRaises(UserError):
            plan.with_user(self.manager).action_approve()
        with self.assertRaises(UserError):
            plan.with_user(self.manager).action_lock()

    def test_cancel_reset_and_locked_admin_reset(self):
        plan = self._create_plan()
        plan.action_prepare_data()
        plan.action_cancel()
        self.assertEqual(plan.state, "cancelled")
        plan.with_user(self.manager).action_reset_draft()
        self.assertEqual(plan.state, "draft")

        self._move_to_approved(plan)
        plan.with_user(self.manager).action_lock()
        with self.assertRaises(AccessError):
            plan.with_user(self.manager).action_reset_draft()
        plan.with_user(self.sop_admin).action_reset_draft()
        self.assertEqual(plan.state, "draft")

    def test_approved_plan_can_be_cancelled_before_it_is_locked(self):
        plan = self._create_plan()
        self._move_to_approved(plan)
        plan.with_user(self.manager).action_cancel()
        self.assertEqual(plan.state, "cancelled")

    def test_new_version_is_sequential_and_only_one_is_current(self):
        plan = self._create_plan()
        first = plan.action_create_version()
        self.assertEqual(first.version_number, 1)
        self.assertEqual(first.state, "current")
        self.assertTrue(first.is_current)
        self.assertEqual(plan.active_version_id, first)

        second = plan.action_create_version()
        self.assertEqual(second.version_number, 2)
        self.assertEqual(second.state, "current")
        self.assertTrue(second.is_current)
        self.assertEqual(first.state, "archived")
        self.assertFalse(first.is_current)
        self.assertEqual(plan.active_version_id, second)
        self.assertEqual(
            self._model("mogen.sop.plan.version").search_count(
                [("plan_id", "=", plan.id), ("is_current", "=", True)]
            ),
            1,
        )

    def test_current_version_constraint_and_plan_consistency(self):
        plan = self._create_plan()
        plan.action_create_version()
        Version = self._model("mogen.sop.plan.version")
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                Version.create(
                    {
                        "plan_id": plan.id,
                        "version_number": 99,
                        "state": "current",
                        "is_current": True,
                    }
                )

        other_plan = self._create_plan(name="Other Plan")
        other_version = other_plan.action_create_version()
        with self.assertRaises(ValidationError):
            plan.active_version_id = other_version

    def test_direct_current_version_updates_the_active_plan_version(self):
        plan = self._create_plan()
        version = self._model("mogen.sop.plan.version").create(
            {
                "plan_id": plan.id,
                "version_number": 1,
                "state": "current",
                "is_current": True,
            }
        )
        self.assertEqual(plan.active_version_id, version)

    def test_locked_plan_cannot_be_modified_or_deleted_by_non_admin(self):
        plan = self._create_plan()
        self._move_to_approved(plan)
        plan.with_user(self.manager).action_lock()
        with self.assertRaises(AccessError):
            plan.with_user(self.manager).write({"note": "<p>Changed</p>"})
        with self.assertRaises(AccessError):
            plan.with_user(self.manager).unlink()

        plan.with_user(self.sop_admin).write({"note": "<p>Admin correction</p>"})
        self.assertIn("Admin correction", plan.note)

    def test_locked_plan_protects_versions_recommendations_and_alerts(self):
        plan = self._create_plan()
        version = plan.action_create_version()
        recommendation = self._model("mogen.sop.recommendation").create(
            {
                "name": "Locked recommendation",
                "plan_id": plan.id,
                "recommendation_type": "warning",
            }
        )
        alert = self._model("mogen.sop.alert").create(
            {
                "name": "Locked alert",
                "plan_id": plan.id,
                "message": "Locked child integrity.",
            }
        )
        self._move_to_approved(plan)
        plan.with_user(self.manager).action_lock()

        child_operations = (
            lambda: self._model("mogen.sop.plan.version")
            .with_user(self.manager)
            .create({"plan_id": plan.id}),
            lambda: version.with_user(self.manager).write({"note": "No"}),
            lambda: version.with_user(self.manager).unlink(),
            lambda: recommendation.with_user(self.manager).write({"reason": "No"}),
            lambda: recommendation.with_user(self.manager).unlink(),
            lambda: alert.with_user(self.manager).write({"message": "No"}),
            lambda: alert.with_user(self.manager).unlink(),
            lambda: self._model("mogen.sop.recommendation")
            .with_user(self.manager)
            .create(
                {
                    "name": "No new recommendation",
                    "plan_id": plan.id,
                    "recommendation_type": "warning",
                }
            ),
            lambda: self._model("mogen.sop.alert").with_user(self.manager).create(
                {
                    "name": "No new alert",
                    "plan_id": plan.id,
                    "message": "No",
                }
            ),
        )
        for operation in child_operations:
            with self.assertRaises(AccessError):
                operation()

        recommendation.with_user(self.sop_admin).write({"reason": "Admin"})
        alert.with_user(self.sop_admin).write({"message": "Admin"})
        version.with_user(self.sop_admin).write({"note": "Admin"})

    def test_recommendation_approval_requires_manager(self):
        plan = self._create_plan()
        recommendation = self._model("mogen.sop.recommendation").create(
            {
                "name": "Expedite a constrained component",
                "plan_id": plan.id,
                "recommendation_type": "purchase",
                "quantity": 10.0,
                "reason": "Required for consensus plan",
            }
        )
        with self.assertRaises(AccessError):
            recommendation.with_user(self.viewer).action_approve()
        recommendation.with_user(self.manager).action_approve()
        self.assertEqual(recommendation.state, "approved")
        self.assertEqual(recommendation.approved_by_id, self.manager)
        self.assertTrue(recommendation.approved_date)

        rejected = recommendation.copy({"name": "Reject this recommendation"})
        rejected.with_user(self.manager).action_reject()
        self.assertEqual(rejected.state, "rejected")

    def test_recommendation_state_cannot_bypass_actions(self):
        Recommendation = self._model("mogen.sop.recommendation")
        plan = self._create_plan()
        with self.assertRaises(UserError):
            Recommendation.with_user(self.manager).create(
                {
                    "name": "Bypassed recommendation",
                    "plan_id": plan.id,
                    "recommendation_type": "warning",
                    "state": "approved",
                }
            )

        recommendation = Recommendation.create(
            {
                "name": "Protected recommendation",
                "plan_id": plan.id,
                "recommendation_type": "warning",
            }
        )
        with self.assertRaises(UserError):
            recommendation.with_user(self.manager).write({"state": "approved"})
        recommendation.with_user(self.manager).action_approve()
        self.assertEqual(recommendation.state, "approved")
        self.assertEqual(recommendation.approved_by_id, self.manager)
        self.assertTrue(recommendation.approved_date)

    def test_planner_cannot_spoof_recommendation_workflow_context(self):
        plan = self._create_plan()
        recommendation = self._model("mogen.sop.recommendation").create(
            {
                "name": "Protected from spoofed context",
                "plan_id": plan.id,
                "recommendation_type": "warning",
            }
        )
        with self.assertRaises(UserError):
            recommendation.with_user(self.demand_planner).with_context(
                _sop_allow_recommendation_transition=True
            ).write({"state": "approved"})
        self.assertEqual(recommendation.state, "draft")

    def test_alert_lifecycle(self):
        plan = self._create_plan()
        alert = self._model("mogen.sop.alert").create(
            {
                "name": "Capacity warning",
                "plan_id": plan.id,
                "alert_type": "capacity",
                "severity": "warning",
                "message": "Capacity requires review.",
            }
        )
        alert.with_user(self.manager).action_acknowledge()
        self.assertEqual(alert.state, "acknowledged")
        alert.with_user(self.manager).action_resolve()
        self.assertEqual(alert.state, "resolved")
        self.assertTrue(alert.resolved_date)

    def test_viewer_only_sees_approved_or_locked_plans_in_their_company(self):
        draft = self._create_plan(name="Draft Cycle")
        approved = self._create_plan(name="Approved Cycle")
        self._move_to_approved(approved)
        other = self._create_plan(
            name="Other Company Approved",
            company_id=self.other_company.id,
        )
        other.action_prepare_data()
        other.action_review()
        other.action_consensus()
        other.with_user(self.sop_admin).action_approve()

        visible = self._model("mogen.sop.plan").with_user(self.viewer).search([])
        self.assertNotIn(draft, visible)
        self.assertIn(approved, visible)
        self.assertNotIn(other, visible)
        with self.assertRaises(AccessError):
            approved.with_user(self.viewer).write({"note": "<p>No</p>"})

    def test_viewer_only_sees_children_of_approved_or_locked_plans(self):
        draft = self._create_plan(name="Draft Parent")
        approved = self._create_plan(name="Approved Parent")
        draft_version = draft.action_create_version()
        approved_version = approved.action_create_version()
        draft_recommendation = self._model("mogen.sop.recommendation").create(
            {
                "name": "Draft recommendation",
                "plan_id": draft.id,
                "recommendation_type": "warning",
            }
        )
        approved_recommendation = self._model("mogen.sop.recommendation").create(
            {
                "name": "Approved recommendation",
                "plan_id": approved.id,
                "recommendation_type": "warning",
            }
        )
        draft_alert = self._model("mogen.sop.alert").create(
            {
                "name": "Draft alert",
                "plan_id": draft.id,
                "message": "Draft",
            }
        )
        approved_alert = self._model("mogen.sop.alert").create(
            {
                "name": "Approved alert",
                "plan_id": approved.id,
                "message": "Approved",
            }
        )
        self._move_to_approved(approved)

        expectations = (
            ("mogen.sop.plan.version", draft_version, approved_version),
            (
                "mogen.sop.recommendation",
                draft_recommendation,
                approved_recommendation,
            ),
            ("mogen.sop.alert", draft_alert, approved_alert),
        )
        for model_name, draft_child, approved_child in expectations:
            viewer_records = self._model(model_name).with_user(self.viewer).search([])
            self.assertNotIn(draft_child, viewer_records)
            self.assertIn(approved_child, viewer_records)
            planner_records = (
                self._model(model_name).with_user(self.demand_planner).search([])
            )
            self.assertIn(draft_child, planner_records)

    def test_plan_stat_actions_use_expected_models_and_domains(self):
        plan = self._create_plan()
        expectations = {
            "action_view_recommendations": "mogen.sop.recommendation",
            "action_view_alerts": "mogen.sop.alert",
            "action_view_versions": "mogen.sop.plan.version",
        }
        for method_name, model_name in expectations.items():
            action = getattr(plan, method_name)()
            self.assertEqual(action["res_model"], model_name)
            self.assertEqual(action["domain"], [("plan_id", "=", plan.id)])

        unavailable = {
            "action_view_demand_lines": "mogen_sop_demand",
            "action_view_supply_lines": "mogen_sop_supply",
            "action_view_inventory_health": "mogen_sop_inventory",
        }
        for method_name, addon_name in unavailable.items():
            with self.assertRaisesRegex(UserError, addon_name):
                getattr(plan, method_name)()

    def test_cancel_button_is_available_for_approved_plans(self):
        view = self.env.ref("mogen_sop_core.view_sop_plan_form")
        self.assertIn(
            'name="action_cancel" type="object" string="Cancel" '
            'invisible="state in (\'locked\', \'cancelled\')"',
            view.arch_db,
        )
