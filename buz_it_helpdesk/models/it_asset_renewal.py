from datetime import datetime, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class ItAssetNotificationConfig(models.Model):
    _name = "buz.it.asset.notification.config"
    _description = "IT Asset Notification Configuration"
    _check_company_auto = True

    name = fields.Char(required=True, default="Default Asset Notifications")
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company, index=True
    )
    timezone = fields.Selection(
        selection=lambda self: [(tz, tz) for tz in pytz.all_timezones],
        required=True,
        default=lambda self: self.env.user.tz or "UTC",
    )
    recipient_ids = fields.Many2many("res.users", string="Recipients")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ("company_uniq", "unique(company_id)", "Only one active notification configuration is allowed per company."),
    ]


class ItAssetRenewal(models.Model):
    _name = "buz.it.asset.renewal"
    _description = "IT Asset License Renewal"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _check_company_auto = True
    _order = "start_date desc, id desc"

    asset_id = fields.Many2one("buz.it.asset", required=True, ondelete="restrict", check_company=True, tracking=True)
    company_id = fields.Many2one("res.company", related="asset_id.company_id", store=True, index=True)
    previous_renewal_id = fields.Many2one("buz.it.asset.renewal", readonly=True, ondelete="restrict")
    name = fields.Char(required=True, copy=False, default="New", tracking=True)
    status = fields.Selection([
        ("not_required", "Not Required"),
        ("pending_review", "Pending Review"),
        ("in_progress", "Renewal In Progress"),
        ("renewed", "Renewed"),
        ("expired", "Expired"),
        ("cancelled", "Cancelled"),
    ], required=True, default="pending_review", tracking=True)
    owner_id = fields.Many2one("res.users", default=lambda self: self.env.user, tracking=True)
    vendor_id = fields.Many2one("res.partner", tracking=True)
    cost = fields.Monetary(currency_field="currency_id", tracking=True)
    currency_id = fields.Many2one("res.currency", related="company_id.currency_id", store=True, readonly=True)
    start_date = fields.Date(required=True, default=fields.Date.context_today, tracking=True)
    success_date = fields.Date(readonly=True, tracking=True)
    new_expiry_date = fields.Date(tracking=True)
    document_no = fields.Char(string="Document No.", tracking=True)
    evidence_attachment_ids = fields.Many2many("ir.attachment", string="Evidence")
    notes = fields.Text()
    notification_ids = fields.One2many("buz.it.asset.notification.log", "renewal_id", readonly=True)

    @api.constrains("asset_id")
    def _check_asset_type(self):
        for renewal in self:
            if renewal.asset_id.asset_type != "software_license":
                raise ValidationError("Renewal is only available for Software License assets.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            asset = self.env["buz.it.asset"].browse(vals.get("asset_id")).exists()
            if asset and asset.asset_type != "software_license":
                raise ValidationError("Renewal is only available for Software License assets.")
            if vals.get("name", "New") == "New":
                vals["name"] = "%s Renewal" % (asset.display_name if asset else "License")
        records = super().create(vals_list)
        records._ensure_notification_schedule()
        return records

    def _company_today(self):
        self.ensure_one()
        config = self.env["buz.it.asset.notification.config"].search([
            ("company_id", "=", self.company_id.id), ("active", "=", True)
        ], limit=1)
        timezone = pytz.timezone((config.timezone if config else False) or self.env.user.tz or "UTC")
        return datetime.now(timezone).date()

    def _notification_specs(self):
        self.ensure_one()
        if not self.new_expiry_date:
            return []
        return [(days, self.new_expiry_date - timedelta(days=days)) for days in (90, 60, 30)] + [(0, self.new_expiry_date)]

    def _ensure_notification_schedule(self):
        Log = self.env["buz.it.asset.notification.log"].sudo()
        for renewal in self:
            if renewal.status in ("renewed", "cancelled", "not_required"):
                continue
            expiry = renewal.new_expiry_date or renewal.asset_id.license_expiry_date
            if not expiry:
                continue
            schedule = renewal._notification_specs() if renewal.new_expiry_date else [(d, expiry - timedelta(days=d)) for d in (90, 60, 30, 0)]
            for days, scheduled_date in schedule:
                kind = "expired" if days == 0 else "%s_days" % days
                key = "%s:%s" % (renewal.id, kind)
                if not Log.search_count([("dedupe_key", "=", key)]):
                    Log.create({
                        "renewal_id": renewal.id,
                        "notification_type": kind,
                        "scheduled_date": scheduled_date,
                        "dedupe_key": key,
                    })

    def _history(self, event_type, old_value=False, new_value=False):
        self.ensure_one()
        self.asset_id._create_history(
            event_type, old_value=old_value, new_value=new_value, renewal_id=self.id
        )

    def _transition(self, status):
        allowed = {
            "pending_review": {"in_progress", "cancelled", "expired"},
            "in_progress": {"renewed", "cancelled", "expired"},
            "expired": {"in_progress", "cancelled"},
            "renewed": set(),
            "cancelled": set(),
            "not_required": {"pending_review"},
        }
        for renewal in self:
            if status not in allowed.get(renewal.status, set()):
                raise UserError("Invalid renewal transition from %s to %s." % (renewal.status, status))

    def write(self, vals):
        if "status" in vals and not self.env.context.get("renewal_transition"):
            raise UserError("Use a Renewal action to change its status.")
        return super().write(vals)

    def action_start(self):
        self._transition("in_progress")
        for renewal in self:
            old = renewal.status
            renewal.with_context(renewal_transition=True).write({"status": "in_progress"})
            renewal._history("renewal_start", old, "in_progress")
        return True

    def action_mark_renewed(self):
        self.ensure_one()
        self._transition("renewed")
        if not self.new_expiry_date:
            raise ValidationError("A new expiry date is required before renewal can be completed.")
        if not self.evidence_attachment_ids:
            raise ValidationError("At least one renewal evidence attachment is required.")
        if self.new_expiry_date <= self.asset_id.license_expiry_date:
            raise ValidationError("The new expiry date must be after the current Asset expiry date.")
        old_expiry = self.asset_id.license_expiry_date
        next_renewal = self.env["buz.it.asset.renewal"].sudo().create({
            "asset_id": self.asset_id.id,
            "previous_renewal_id": self.id,
            "start_date": self.new_expiry_date,
            "status": "pending_review",
            "owner_id": self.owner_id.id,
        })
        self.env.cr.execute(
            "UPDATE buz_it_asset_notification_log SET state = 'cancelled' "
            "WHERE renewal_id = %s AND state IN ('pending', 'failed')", (self.id,)
        )
        self.asset_id.with_context(skip_asset_history=True).write({"license_expiry_date": self.new_expiry_date})
        self.with_context(renewal_transition=True).write({"status": "renewed", "success_date": fields.Date.context_today(self)})
        self._history("renewal_renewed", old_expiry, self.new_expiry_date)
        next_renewal._ensure_notification_schedule()
        self.message_post(body="License renewal completed. A new notification cycle was started.")
        return next_renewal

    def action_mark_expired(self):
        self._transition("expired")
        for renewal in self:
            old = renewal.status
            renewal.with_context(renewal_transition=True).write({"status": "expired"})
            renewal._history("renewal_expired", old, "expired")
        return True

    def action_cancel(self):
        self._transition("cancelled")
        for renewal in self:
            old = renewal.status
            renewal.with_context(renewal_transition=True).write({"status": "cancelled"})
            renewal._history("renewal_cancelled", old, "cancelled")
            renewal.notification_ids.filtered(lambda log: log.state in ("pending", "failed")).write({"state": "cancelled"})
        return True

    def unlink(self):
        raise UserError("Renewal records are retained for audit and cannot be deleted.")

    @api.model
    def _cron_process_notifications(self):
        logs = self.env["buz.it.asset.notification.log"].sudo().search([
            ("scheduled_date", "<=", fields.Date.today()),
            ("state", "in", ("pending", "failed")),
            ("renewal_id.status", "not in", ("cancelled", "not_required")),
        ], order="scheduled_date, id")
        for log in logs:
            log._send()
        return True


class ItAssetNotificationLog(models.Model):
    _name = "buz.it.asset.notification.log"
    _description = "IT Asset Notification Log"
    _order = "scheduled_date desc, id desc"
    _check_company_auto = True

    renewal_id = fields.Many2one("buz.it.asset.renewal", required=True, ondelete="restrict", check_company=True)
    company_id = fields.Many2one("res.company", related="renewal_id.company_id", store=True, index=True)
    notification_type = fields.Selection([
        ("90_days", "90 Days"), ("60_days", "60 Days"), ("30_days", "30 Days"), ("expired", "Expired"),
    ], required=True, readonly=True)
    scheduled_date = fields.Date(required=True, readonly=True)
    sent_at = fields.Datetime(readonly=True)
    state = fields.Selection([
        ("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed"), ("cancelled", "Cancelled"),
    ], default="pending", required=True, readonly=True)
    dedupe_key = fields.Char(required=True, readonly=True, index=True)
    retry_count = fields.Integer(readonly=True)
    error_detail = fields.Text(readonly=True)
    mail_id = fields.Many2one("mail.mail", readonly=True, ondelete="set null")

    _sql_constraints = [("dedupe_key_uniq", "unique(dedupe_key)", "Notification dedupe key must be unique.")]

    def _recipient_users(self):
        self.ensure_one()
        config = self.env["buz.it.asset.notification.config"].sudo().search([
            ("company_id", "=", self.company_id.id), ("active", "=", True)
        ], limit=1)
        users = config.recipient_ids if config and config.recipient_ids else self.env["res.users"].sudo().search([
            ("groups_id", "in", self.env.ref("buz_it_helpdesk.group_it_asset_manager").id),
            ("company_ids", "in", self.company_id.id), ("active", "=", True),
        ])
        return users.filtered(lambda user: user.email)

    def _safe_subject_body(self):
        self.ensure_one()
        asset = self.renewal_id.asset_id
        label = {"90_days": "90 days", "60_days": "60 days", "30_days": "30 days", "expired": "expired"}[self.notification_type]
        subject = "IT Asset license renewal: %s (%s)" % (asset.license_product, label)
        body = "License renewal review is required for %s (%s). Expiry date: %s. Renewal: %s." % (
            asset.license_product, asset.license_version, asset.license_expiry_date, self.renewal_id.display_name
        )
        return subject, body

    def _send(self):
        self = self.sudo()
        self.ensure_one()
        if self.state in ("sent", "cancelled"):
            return True
        if self.scheduled_date > self.renewal_id._company_today():
            return True
        users = self._recipient_users()
        if not users:
            self.write({"state": "failed", "retry_count": self.retry_count + 1, "error_detail": "No configured recipient with an email address."})
            return False
        if self.notification_type == "expired" and self.renewal_id.status in ("pending_review", "in_progress"):
            self.renewal_id.action_mark_expired()
        subject, body = self._safe_subject_body()
        try:
            mail = self.env["mail.mail"].sudo().create({
                "subject": subject,
                "body_html": "<p>%s</p>" % body,
                "email_to": ",".join(users.mapped("email")),
                "email_from": self.company_id.email or self.env.user.email or False,
                "auto_delete": False,
            })
            mail.send(raise_exception=True)
            self.write({"state": "sent", "sent_at": fields.Datetime.now(), "mail_id": mail.id, "error_detail": False})
            for user in users:
                self.renewal_id.sudo().activity_schedule(
                    "mail.mail_activity_data_todo", user_id=user.id,
                    date_deadline=fields.Date.context_today(self),
                    summary="Review IT Asset license renewal",
                    note=body,
                )
            self.renewal_id.sudo().message_post(body="Renewal notification sent: %s." % self.notification_type)
            return True
        except Exception as error:
            self.write({"state": "failed", "retry_count": self.retry_count + 1, "error_detail": str(error)[:2000]})
            managers = self.env["res.users"].sudo().search([
                ("groups_id", "in", self.env.ref("buz_it_helpdesk.group_it_asset_manager").id),
                ("company_ids", "in", self.company_id.id), ("active", "=", True),
            ])
            for manager in managers:
                self.renewal_id.sudo().activity_schedule(
                    "mail.mail_activity_data_todo", user_id=manager.id,
                    date_deadline=fields.Date.context_today(self),
                    summary="IT Asset notification failed",
                    note="Notification %s failed and will be retried. Error: %s" % (self.dedupe_key, str(error)[:500]),
                )
            return False
