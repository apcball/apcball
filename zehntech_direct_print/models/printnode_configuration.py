# -*- coding: utf-8 -*-
from odoo import fields, models, api, _
from odoo.exceptions import ValidationError
from printnodeapi.gateway import Gateway

class PrintNodeConfiguration(models.Model):  # not TransientModel
    _name = "printnode.configuration"
    _description = "PrintNode Configuration Wizard"
    _sql_constraints = [
        ('only_one_row', 'CHECK (id <= 1)', 'Only one PrintNode Configuration is allowed.')
    ]

    api_key_print_node = fields.Char(
        string="API Key", required=True, help="Enter your PrintNode API Key here."
    )
    available_printers_id = fields.Many2one(
        "printer.details",
        string="Available Printers",
        help="Check your available printers and choose one for the report.",
    )
    printers_ids = fields.Many2many(
        "printer.details",
        string="Printers Details",
        help="Multiple Printers can connect and print.",
    )
    multiple_printers = fields.Boolean(
        string="Multiple Printers",
        help="You can select more than one printer only after enabling this option.",
    )

    @api.model
    def create(self, vals):        
        # Validate API Key before saving
        api_key = vals.get("api_key_print_node")
        if api_key and not self._is_valid_apikey(api_key):
            raise ValidationError(_("Invalid PrintNode API Key."))

        # Ensure proper format for many2many field
        if "printers_ids" in vals and isinstance(vals["printers_ids"], list):
            for item in vals["printers_ids"]:
                if not isinstance(item, (list, tuple)):
                    raise ValidationError(_("Invalid data format for Printers Details."))

        # If multiple printers is True, clear available_printers_id
        if vals.get("multiple_printers"):
            vals["available_printers_id"] = False
        elif vals.get("available_printers_id"):
            vals["printers_ids"] = [(5, 0, 0)]

        existing = self.search([], limit=1)
        if existing:
            existing.write(vals)
            return existing
        return super().create(vals)

    def write(self, vals):
        # Validate API Key if being updated
        api_key = vals.get("api_key_print_node")
        if api_key and not self._is_valid_apikey(api_key):
            raise ValidationError(_("Invalid PrintNode API Key."))

        if "printers_ids" in vals and isinstance(vals["printers_ids"], list):
            for item in vals["printers_ids"]:
                if not isinstance(item, (list, tuple)):
                    raise ValidationError(_("Invalid data format for Printers Details."))

        # If multiple printers is True, clear available_printers_id
        if vals.get("multiple_printers"):
            vals["available_printers_id"] = False
        elif "available_printers_id" in vals and vals["available_printers_id"]:
            vals["printers_ids"] = [(5, 0, 0)]

        res = super().write(vals)
        
        for record in self:
            company = self.env.company
            company.api_key_print_node = record.api_key_print_node
            company.available_printers_id = record.available_printers_id.id
            company.printers_ids = record.printers_ids
            company.multiple_printers = record.multiple_printers

        return res

    def _is_valid_apikey(self, apikey):
        try:
            gateway = Gateway(url="https://api.printnode.com", apikey=apikey)
            computers = gateway.computers()
            return bool(computers)
        except Exception:
            return False

    @api.onchange("multiple_printers")
    def _onchange_multiple_printers(self):
        if self.multiple_printers:
            self.available_printers_id = False
        else:
            self.printers_ids = [(5, 0, 0)]

    @api.onchange("available_printers_id")
    def _onchange_available_printer(self):
        if self.available_printers_id:
            self.multiple_printers = False
            self.printers_ids = [(5, 0, 0)]

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        config = self.search([], limit=1)
        if config:
            if "printers_ids" in fields_list:
                res["printers_ids"] = [(6, 0, config.printers_ids.ids)]
            if "available_printers_id" in fields_list and config.available_printers_id:
                res["available_printers_id"] = config.available_printers_id.id
            for field in fields_list:
                if field not in ["printers_ids", "available_printers_id"]:
                    res[field] = config[field]
        return res

    def action_validate_api_key(self):
        self = self.with_context(skip_printer_validation=True, skip_printer_check=True)
        self.ensure_one()
        if not self.api_key_print_node:
            raise ValidationError(_("Please provide a PrintNode API Key."))
        try:
            gateway = Gateway(
                url="https://api.printnode.com", apikey=self.api_key_print_node
            )
            computers = gateway.computers()
            if not computers:
                raise ValidationError(_("API Key is valid, but no computers found."))
        except Exception as e:
            raise ValidationError(_("Invalid PrintNode API Key."))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Success"),
                "message": _("API Key is valid and computers are found."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_check_printers(self):
        self = self.with_context(skip_printer_validation=True, skip_printer_check=True)
        self.ensure_one()
        if not self.api_key_print_node:
            raise ValidationError(_("Please provide a valid API Key first."))

        try:
            gateway = Gateway(
                url="https://api.printnode.com", apikey=self.api_key_print_node
            )
            computers = gateway.computers()
            if not computers:
                raise ValidationError(_("No connected computers found."))

            printers = gateway.printers(computer=computers[0].id)
            created_printers = []
            for printer in printers:
                existing = self.env["printer.details"].search(
                    [("id_of_printer", "=", printer.id)], limit=1
                )
                if not existing:
                    new_printer = self.env["printer.details"].create({
                        "id_of_printer": printer.id,
                        "printers_name": printer.name,
                        "printer_description": printer.description,
                        "state": printer.state,
                    })
                    created_printers.append(new_printer)
            if not created_printers and not printers:
                raise ValidationError(_("No printers found."))

        except Exception as e:
            raise ValidationError(_("Failed to fetch printers: %s") % str(e))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Printers Loaded"),
                "message": _("Printers were successfully fetched."),
                "type": "success",
                "sticky": False,
            },
        }

    def action_apply_settings(self):
        self.ensure_one()
        if self.multiple_printers:
            if not self.printers_ids:
                raise ValidationError(_("Please select at least one printer."))
        else:
            if not self.available_printers_id:
                raise ValidationError(_("Please select a printer."))
        
        company = self.env.company
        company.api_key_print_node = self.api_key_print_node
        company.available_printers_id = self.available_printers_id.id
        company.printers_ids = self.printers_ids
        company.multiple_printers = self.multiple_printers

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Settings Applied"),
                "message": _("Configuration has been saved to your company."),
                "type": "success",
                "sticky": False,
            },
        }
