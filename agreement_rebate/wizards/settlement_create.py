# Copyright 2020 Tecnativa - Carlos Dauden
# Copyright 2020 Tecnativa - Sergio Teruel
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from collections import defaultdict

from odoo import Command, api, fields, models
from odoo.exceptions import UserError
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval


class AgreementSettlementCreateWiz(models.TransientModel):
    _name = "agreement.settlement.create.wiz"
    _description = "Agreement settlement create wizard"

    date = fields.Date(default=fields.Date.today)
    date_from = fields.Date(string="From")
    date_to = fields.Date(string="To", required=True)
    domain = fields.Selection("_domain_selection", default="sale")
    journal_ids = fields.Many2many(
        comodel_name="account.journal",
        string="Journals",
    )
    agreement_type_ids = fields.Many2many(
        comodel_name="agreement.type",
        string="Agreement types",
    )
    agreement_ids = fields.Many2many(
        comodel_name="agreement",
        string="Agreements",
    )
    discard_settled_agreement = fields.Boolean(
        string="Discard settled agreements",
        default="True",
        help="If checked, the agreements with settlements in selected period "
        "will be discard",
    )

    @api.model
    def _domain_selection(self):
        return self.env["agreement"]._domain_selection()

    def _prepare_agreement_domain(self):
        domain = [
            ("rebate_type", "!=", False),
            ("agreement_type_id.is_rebate", "=", True),
            ("rebate_approval_state", "=", "approved"),
        ]
        settlement_domain = []
        if self.date_from:
            domain.extend(
                ["|", ("end_date", "=", False), ("end_date", ">=", self.date_from)]
            )
            settlement_domain.extend([("date_to", ">=", self.date_from)])
        if self.date_to:
            domain.extend([("start_date", "<=", self.date_to)])
            settlement_domain.extend([("date_to", "<=", self.date_to)])
        if self.agreement_ids:
            domain.extend([("id", "in", self.agreement_ids.ids)])
            settlement_domain.extend(
                [("line_ids.agreement_id", "in", self.agreement_ids.ids)]
            )
        elif self.agreement_type_ids:
            domain.extend([("agreement_type_id", "in", self.agreement_type_ids.ids)])
            settlement_domain.extend(
                [
                    (
                        "line_ids.agreement_id.agreement_type_id",
                        "in",
                        self.agreement_type_ids.ids,
                    )
                ]
            )
        else:
            domain.extend([("agreement_type_id.domain", "=", self.domain)])
        # For sale settlements, duplicate prevention is handled at invoice/credit
        # note line level, so the agreement-level discard is not applied. The
        # purchase flow keeps its original behavior.
        if self.domain != "sale" and self.discard_settled_agreement:
            settlements = self._get_existing_settlement(settlement_domain)
            if settlements:
                domain.extend(
                    [("id", "not in", settlements.mapped("line_ids.agreement_id").ids)]
                )
        return domain

    def _get_existing_settlement(self, domain):
        return self.env["agreement.rebate.settlement"].search(domain)

    def _get_target_model(self):
        return self.env["account.invoice.report"]

    def _prepare_target_domain(self):
        domain = [
            ("state", "not in", ["draft", "cancel"]),
        ]
        if self.journal_ids:
            domain.extend([("journal_id", "in", self.journal_ids.ids)])
        else:
            domain.extend([("journal_id.type", "=", self.domain)])
        # Sale period is driven by the delivery order completion date. The period
        # filter is applied to the qualifying invoice lines instead.
        if self.domain != "sale":
            if self.date_from:
                domain.extend(
                    [
                        (
                            "invoice_date",
                            ">=",
                            fields.Date.to_string(self.date_from),
                        )
                    ]
                )
            if self.date_to:
                domain.extend(
                    [
                        (
                            "invoice_date",
                            "<=",
                            fields.Date.to_string(self.date_to),
                        )
                    ]
                )
        return domain

    def _get_settled_invoice_line_ids(self):
        # Invoice and credit note lines already used by any settlement (active or
        # archived) are never eligible again, regardless of the selected period.
        lines = self.env["agreement.rebate.settlement.line"].with_context(
            active_test=False
        ).search([])
        return lines.mapped("source_invoice_line_ids").ids

    def _check_sales_ready(self):
        """Check that the standard Sales + Inventory relationships are available."""
        checks = [
            ("account.move.line", "sale_line_ids", "Sales"),
            ("sale.order.line", "move_ids", "Sale Stock"),
            ("stock.move", "picking_id", "Inventory"),
            ("stock.picking", "picking_type_code", "Inventory"),
            ("stock.picking", "state", "Inventory"),
            ("stock.picking", "date_done", "Inventory"),
        ]
        missing = []
        for model, field, module in checks:
            if model not in self.env:
                missing.append("%s (%s module)" % (model, module))
            elif field not in self.env[model]._fields:
                missing.append("%s.%s (%s module)" % (model, field, module))
        if missing:
            raise UserError(
                "Sales rebate settlement requires the following fields, which "
                "need the Sales and Inventory (Sale Stock) modules to be "
                "installed first: %s" % ", ".join(missing)
            )

    def _get_invoice_line_last_do_date(self, invoice_line):
        """Return the completion date of the last delivery order of an invoice
        line, or False when the line cannot be settled yet.

        Only non-cancelled outgoing delivery pickings are considered, and every
        one of them must be `done`.
        """
        moves = invoice_line.sale_line_ids.move_ids.filtered(
            lambda move: move.picking_id
            and move.picking_id.picking_type_code == "outgoing"
            and move.state != "cancel"
            and move.picking_id.state != "cancel"
        )
        pickings = moves.picking_id
        if not pickings:
            return False
        if any(picking.state != "done" for picking in pickings):
            return False
        dates = [picking.date_done.date() for picking in pickings if picking.date_done]
        if not dates:
            return False
        return max(dates)

    def _get_qualifying_invoice_lines(self, agreement, settled_ids=None):
        """Return the posted customer invoice lines eligible for a sale settlement."""
        if settled_ids is None:
            settled_ids = self._get_settled_invoice_line_ids()
        domain = [
            ("move_id.move_type", "=", "out_invoice"),
            ("parent_state", "=", "posted"),
            ("display_type", "=", "product"),
            ("sale_line_ids", "!=", False),
        ]
        if self.journal_ids:
            domain.append(("move_id.journal_id", "in", self.journal_ids.ids))
        else:
            domain.append(("move_id.journal_id.type", "=", self.domain))
        if agreement.company_id:
            domain.append(("company_id", "=", agreement.company_id.id))
        domain += self._partner_domain(agreement)
        if settled_ids:
            domain.append(("id", "not in", settled_ids))
        lines = self.env["account.move.line"].search(domain)
        qualifying = self.env["account.move.line"]
        for line in lines:
            last_date = self._get_invoice_line_last_do_date(line)
            if not last_date:
                continue
            if self.date_from and last_date < self.date_from:
                continue
            if self.date_to and last_date > self.date_to:
                continue
            if agreement.start_date and last_date < agreement.start_date:
                continue
            if agreement.end_date and last_date > agreement.end_date:
                continue
            qualifying |= line
        return qualifying

    def _get_linked_refund_lines(self, invoice_lines):
        """Posted customer credit note lines directly linked to invoice lines."""
        if not invoice_lines:
            return self.env["account.move.line"]
        return self.env["account.move.line"].search(
            [
                ("move_id.move_type", "=", "out_refund"),
                ("parent_state", "=", "posted"),
                ("origin_line_id", "in", invoice_lines.ids),
            ]
        )

    def _check_returns(self, invoice_lines):
        """Block the settlement when a done return has no linked posted credit note."""
        for line in invoice_lines:
            moves = line.sale_line_ids.move_ids.filtered(
                lambda move: move.picking_id
                and move.picking_id.picking_type_code == "outgoing"
                and move.state != "cancel"
                and move.picking_id.state != "cancel"
            )
            if not moves:
                continue
            returns = self.env["stock.move"].search(
                [
                    ("origin_returned_move_id", "in", moves.ids),
                    ("state", "=", "done"),
                ]
            )
            if not returns:
                continue
            if self._get_linked_refund_lines(line):
                continue
            deliveries = ", ".join(moves.mapped("picking_id").mapped("name"))
            return_pickings = ", ".join(returns.mapped("picking_id").mapped("name"))
            raise UserError(
                "Invoice %s has done returns on Delivery Order(s) %s (return %s) "
                "without a directly linked posted Credit Note. Please create or "
                "verify the Credit Note before creating the settlement."
                % (line.move_id.name, deliveries, return_pickings)
            )

    def _validate_sections(self, agreement):
        """Validate that a `section_total` tier configuration is unambiguous."""
        sections = agreement.rebate_section_ids
        if len(sections) <= 1:
            return
        open_ended = sections.filtered(lambda section: not section.amount_to)
        if len(open_ended) > 1:
            raise UserError(
                "Agreement %s has more than one open-ended rebate section."
                % agreement.display_name
            )
        ordered = sections.sorted(key=lambda section: (section.amount_from, section.amount_to))
        for idx, section in enumerate(ordered[:-1]):
            next_section = ordered[idx + 1]
            effective_to = section.amount_to or float("inf")
            if next_section.amount_from < effective_to:
                raise UserError(
                    "Rebate sections overlap for agreement %s."
                    % agreement.display_name
                )

    def _get_matching_section(self, agreement, amount, strict=False):
        sections = agreement.rebate_section_ids.filtered(
            lambda section: section.amount_from <= amount
            and (not section.amount_to or amount <= section.amount_to)
        )
        if strict:
            self._validate_sections(agreement)
            if len(sections) > 1:
                raise UserError(
                    "More than one rebate section matches the net amount %s for "
                    "agreement %s." % (amount, agreement.display_name)
                )
            if not sections:
                raise UserError(
                    "No rebate section matches the net amount %s for agreement %s. "
                    "Check the rebate sections for a gap or a missing tier."
                    % (amount, agreement.display_name)
                )
            return sections[:1]
        if len(sections) > 1:
            raise UserError(
                "Rebate sections overlap for agreement %s." % agreement.display_name
            )
        return sections[:1]

    def _target_line_domain(self, agreement_domain, agreement, line=False):
        domain = agreement_domain.copy()
        # For sale settlements the period and the agreement date range are applied
        # on the delivery order completion date, not on the invoice date.
        if self.domain != "sale":
            if agreement.start_date:
                domain.append(
                    (
                        "invoice_date",
                        ">=",
                        fields.Date.to_string(agreement.start_date),
                    )
                )
            if agreement.end_date:
                domain.append(
                    (
                        "invoice_date",
                        "<=",
                        fields.Date.to_string(agreement.end_date),
                    )
                )
        if line:
            domain += safe_eval(line.rebate_domain)
        elif agreement.rebate_line_ids:
            domain = expression.AND(
                [
                    domain,
                    expression.OR(
                        [safe_eval(x.rebate_domain) for x in agreement.rebate_line_ids]
                    ),
                ]
            )
        return domain

    def get_agregate_fields(self):
        return [
            "price_subtotal",
        ]

    def _get_amount_field(self):
        return "price_subtotal"

    def _prepare_settlement_line(
        self,
        domain,
        group,
        agreement,
        line=False,
        section=False,
        strict_sections=False,
        source_invoice_lines=False,
    ):
        amount = group[self._get_amount_field()] or 0.0
        if self.domain == "purchase":
            amount = -amount
        amount += agreement.additional_consumption
        amount_section = 0.0
        vals = {
            "agreement_id": agreement.id,
            "partner_id": group["partner_id"][0]
            if "partner_id" in group
            else agreement.partner_id.id,
        }
        if agreement.rebate_type == "line":
            rebate = amount * line.rebate_discount / 100
            vals.update({"rebate_line_id": line.id, "percent": line.rebate_discount})
        elif agreement.rebate_type == "section_prorated":
            if amount >= section.amount_to:
                amount_section = section.amount_to
            elif amount >= section.amount_from:
                amount_section = amount - section.amount_from
            rebate = amount_section * section.rebate_discount / 100
            vals.update(
                {
                    "rebate_section_id": section.id,
                    "amount_from": section.amount_from,
                    "amount_to": section.amount_to,
                    "percent": section.rebate_discount,
                }
            )
        elif agreement.rebate_type == "global":
            rebate = amount * agreement.rebate_discount / 100
            vals.update({"percent": agreement.rebate_discount})
        elif agreement.rebate_type == "section_total":
            if not section:
                section = self._get_matching_section(
                    agreement, amount, strict=strict_sections
                )
            rebate = amount * section.rebate_discount / 100 if section else 0.0
            vals.update(
                {
                    "percent": section.rebate_discount if section else 0.0,
                    "amount_from": section.amount_from if section else 0.0,
                    "amount_to": section.amount_to if section else 0.0,
                }
            )
        vals.update(
            {
                "target_domain": domain,
                "amount_invoiced": agreement.company_id.currency_id.round(
                    amount_section or amount
                ),
                "amount_rebate": agreement.company_id.currency_id.round(rebate),
            }
        )
        if source_invoice_lines:
            vals["source_invoice_line_ids"] = [Command.set(source_invoice_lines.ids)]
        return vals

    def _get_rebate_discount(self, agreement, amount):
        if agreement.rebate_type == "global":
            return agreement.rebate_discount
        if agreement.rebate_type == "section_total":
            section = self._get_matching_section(agreement, amount)
            return section.rebate_discount if section else 0.0

    def _partner_domain(self, agreement):
        return [
            ("partner_id", "child_of", agreement.partner_id.ids),
        ]

    def get_settlement_key(self, agreement):
        return agreement

    def action_create_settlement(self):
        self.ensure_one()
        Agreement = self.env["agreement"]
        target_model = self._get_target_model()
        if self.domain == "sale":
            self._check_sales_ready()
        orig_domain = self._prepare_target_domain()
        settled_invoice_line_ids = self._get_settled_invoice_line_ids()
        if settled_invoice_line_ids:
            orig_domain.append(("id", "not in", settled_invoice_line_ids))
        settlement_dic = defaultdict(lambda: {"lines": []})
        agreements = Agreement.search(self._prepare_agreement_domain())
        for agreement in agreements:
            key = self.get_settlement_key(agreement)
            if key not in settlement_dic:
                settlement_dic[key].update(
                    {
                        "amount_rebate": 0.0,
                        "amount_invoiced": 0.0,
                        "partner_id": agreement.partner_id.id,
                        "used_invoice_line_ids": [],
                    }
                )
            agreement_domain = orig_domain + self._partner_domain(agreement)
            evidence = self.env["account.move.line"]
            if self.domain == "sale":
                qualifying_lines = self._get_qualifying_invoice_lines(
                    agreement, settled_invoice_line_ids
                )
                if not qualifying_lines:
                    continue
                self._check_returns(qualifying_lines)
                refund_lines = self._get_linked_refund_lines(qualifying_lines)
                evidence = qualifying_lines + refund_lines
                agreement_domain.append(("id", "in", evidence.ids))
                settlement_dic[key]["used_invoice_line_ids"].extend(evidence.ids)
            if agreement.rebate_type == "line":
                if not agreement.rebate_line_ids:
                    continue
                for line in agreement.rebate_line_ids:
                    domain = self._target_line_domain(
                        agreement_domain, agreement, line=line
                    )
                    groups = target_model.read_group(
                        domain,
                        self.get_agregate_fields(),
                        self._settlement_line_break_fields(),
                        lazy=False,
                    )
                    if (
                        not groups
                        or not groups[0]["__count"]
                        and not agreement.additional_consumption
                    ):
                        continue
                    for group in groups:
                        vals = self._prepare_settlement_line(
                            domain,
                            group,
                            agreement,
                            line=line,
                            source_invoice_lines=evidence,
                        )
                        settlement_dic[key]["amount_rebate"] += vals["amount_rebate"]
                        settlement_dic[key]["amount_invoiced"] += vals[
                            "amount_invoiced"
                        ]
                        settlement_dic[key]["lines"].append((0, 0, vals))
            elif agreement.rebate_type == "section_prorated":
                domain = self._target_line_domain(agreement_domain, agreement)
                groups = target_model.read_group(
                    domain,
                    self.get_agregate_fields(),
                    self._settlement_line_break_fields(),
                    lazy=False,
                )
                if (
                    not groups
                    or not groups[0]["__count"]
                    and not agreement.additional_consumption
                ):
                    continue
                amount = groups and groups[0][self._get_amount_field()] or 0.0
                for section in agreement.rebate_section_ids:
                    if amount < section.amount_to and amount < section.amount_from:
                        break
                    for group in groups:
                        vals = self._prepare_settlement_line(
                            domain,
                            group,
                            agreement,
                            section=section,
                            source_invoice_lines=evidence,
                        )
                        settlement_dic[key]["amount_rebate"] += vals["amount_rebate"]
                        settlement_dic[key]["lines"].append((0, 0, vals))
                settlement_dic[key]["amount_invoiced"] += amount
            else:
                domain = self._target_line_domain(agreement_domain, agreement)
                groups = target_model.read_group(
                    domain,
                    self.get_agregate_fields(),
                    self._settlement_line_break_fields(),
                    lazy=False,
                )
                if (
                    not groups
                    or not groups[0]["__count"]
                    and not agreement.additional_consumption
                ):
                    continue
                if self.domain == "sale" and agreement.rebate_type == "section_total":
                    total = sum(g[self._get_amount_field()] or 0.0 for g in groups)
                    section = self._get_matching_section(agreement, total, strict=True)
                    for group in groups:
                        vals = self._prepare_settlement_line(
                            domain,
                            group,
                            agreement,
                            section=section,
                            strict_sections=True,
                            source_invoice_lines=evidence,
                        )
                        settlement_dic[key]["amount_rebate"] += vals["amount_rebate"]
                        settlement_dic[key]["lines"].append((0, 0, vals))
                    settlement_dic[key]["amount_invoiced"] += total
                else:
                    for group in groups:
                        vals = self._prepare_settlement_line(
                            domain,
                            group,
                            agreement,
                            source_invoice_lines=evidence,
                        )
                        settlement_dic[key]["lines"].append((0, 0, vals))
                        settlement_dic[key]["amount_rebate"] += vals["amount_rebate"]
                        settlement_dic[key]["amount_invoiced"] += vals["amount_invoiced"]
        settlements = self._create_settlement(settlement_dic)
        return settlements.action_show_settlement()

    def _settlement_line_break_fields(self):
        return ["partner_id"]

    def _filter_settlement_lines(self, settlement_lines):
        return [
            line
            for line in filter(
                lambda sl: sl[2]["amount_rebate"] != 0.0, settlement_lines
            )
        ]

    def _prepare_settlement(self, settlement_lines):
        lines = self._filter_settlement_lines(settlement_lines["lines"])
        if not lines:
            return {}
        used_ids = settlement_lines.get("used_invoice_line_ids", [])
        if used_ids:
            duplicates = set(used_ids) & set(self._get_settled_invoice_line_ids())
            if duplicates:
                raise UserError(
                    "One or more invoice/credit note lines are already included in "
                    "another settlement. Please adjust the period and try again."
                )
        return {
            "date": self.date,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "line_ids": lines,
            "partner_id": settlement_lines["partner_id"],
            "amount_rebate": settlement_lines["amount_rebate"],
            "amount_invoiced": settlement_lines["amount_invoiced"],
        }

    def _create_settlement(self, settlements):
        vals_list = []
        for settlement_lines in settlements.values():
            vals = self._prepare_settlement(settlement_lines)
            if vals:
                vals_list.append(vals)
        return self.env["agreement.rebate.settlement"].create(vals_list)
