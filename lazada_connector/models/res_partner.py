import re

from odoo import api, fields, models

_MASKED = re.compile(r"\*{2,}")
_STATE_PREFIX = re.compile(r"^\s*(จังหวัด|จ\.|changwat)\s*", re.IGNORECASE)
_SUBDISTRICT_TAIL = re.compile(r"(?:^|\s)((?:ตำบล|แขวง)\S+)$")


class ResPartner(models.Model):
    _inherit = "res.partner"
    lazada_buyer_id = fields.Char(string="Lazada Buyer ID", copy=False)
    lazada_config_id = fields.Many2one(
        "lazada.config", string="Lazada Seller Config", copy=False,
        ondelete="set null"
    )

    _sql_constraints = [
        (
            "lazada_buyer_seller_unique",
            "unique(lazada_config_id, lazada_buyer_id)",
            "A Lazada buyer can only have one partner per seller.",
        ),
    ]

    @staticmethod
    def _lazada_clean(value):
        """Return a usable string, or False for empty / masked Lazada data."""
        value = str(value or "").strip()
        # Lazada masks hidden data fully ("*****") or partly ("66******78").
        if not value or _MASKED.search(value):
            return False
        return value

    @api.model
    def _lazada_find_state(self, state_name, country):
        State = self.env["res.country.state"]
        if not state_name or not country:
            return State
        name = _STATE_PREFIX.sub("", state_name).strip()
        domain = [("country_id", "=", country.id)]
        for lang in ("en_US", "th_TH"):
            LangState = State.with_context(lang=lang)
            state = LangState.search(
                domain + [("name", "=ilike", name)], limit=1
            ) or LangState.search(
                domain + ["|", ("name", "ilike", name), ("code", "=ilike", name)],
                limit=1,
            )
            if state:
                return State.browse(state.id)
        return State

    @staticmethod
    def _lazada_split_street(full_address, tail_parts):
        """Split a one-line address into (street, subdistrict).

        Buyers often repeat "ตำบล… อำเภอ… จังหวัด… 55000" in the detailed
        address. Odoo shows city/province/zip on their own lines, so drop
        those trailing parts and return the ตำบล/แขวง part separately.
        """
        if not full_address:
            return False, False
        street = full_address.strip()
        parts = [p.strip() for p in tail_parts if p and p.strip()]
        changed = True
        while changed:
            changed = False
            for part in parts:
                # whole words only: "น่าน" must not eat "อำเภอเมืองน่าน"
                if street.endswith(" " + part):
                    street = street[: -len(part)].rstrip(" ,")
                    changed = True
        subdistrict = False
        match = _SUBDISTRICT_TAIL.search(street)
        if match and match.start(1) > 0:
            subdistrict = match.group(1)
            street = street[: match.start(1)].rstrip(" ,")
            while street.endswith(" " + subdistrict):
                street = street[: -len(subdistrict)].rstrip(" ,")
        return street or full_address.strip(), subdistrict

    @staticmethod
    def _lazada_thai_phone(value):
        """Lazada may send Thai numbers as 66XXXXXXXXX; show them as 0XXXXXXXXX."""
        if not value:
            return value
        digits = re.sub(r"\D", "", str(value))
        if digits.startswith("66") and len(digits) == 11:
            return "0" + digits[2:]
        return value

    @api.model
    def _lazada_country(self, address, config=None):
        Country = self.env["res.country"]
        value = self._lazada_clean(address.get("country"))
        if value:
            country = Country.search([("code", "=ilike", value)], limit=1) or \
                Country.with_context(lang="en_US").search([("name", "=ilike", value)], limit=1)
            if country:
                return Country.browse(country.id)
        region = config.region if config else False
        if region and region != "cb":
            return Country.search([("code", "=ilike", region)], limit=1)
        return Country

    @api.model
    def _lazada_address_values(self, address, config=None):
        """Partner values from a Lazada address (real data only).

        Lazada: address1 = detailed address, address3 = province,
        address4 = district (อำเภอ/เขต), address5 = sub-district
        (ตำบล/แขวง), post_code. Masked or missing fields are left out:
        never fill a buyer with somebody else's data (e.g. the company).
        """
        address = address or {}
        clean = self._lazada_clean
        country = self._lazada_country(address, config)
        state_name = clean(address.get("address3"))
        state = self._lazada_find_state(state_name, country)
        district = (clean(address.get("address4")) or clean(address.get("addressDistrict"))
                    or clean(address.get("addressDsitrict")))
        city = district or clean(address.get("city"))
        subdistrict = clean(address.get("address5"))
        zipcode = clean(address.get("post_code") or address.get("postcode"))
        street, tail_subdistrict = self._lazada_split_street(
            clean(address.get("address1")),
            [zipcode, state_name, state_name and _STATE_PREFIX.sub("", state_name),
             city, district, subdistrict, clean(address.get("city"))],
        )
        values = {
            "name": " ".join(filter(None, [
                clean(address.get("first_name")), clean(address.get("last_name")),
            ])) or False,
            "phone": self._lazada_thai_phone(
                clean(address.get("phone")) or clean(address.get("phone2"))
            ),
            "street": street,
            "street2": subdistrict or tail_subdistrict or False,
            "city": city,
            "zip": zipcode,
            "country_id": country.id or False,
            "state_id": state.id or False,
        }
        return {k: v for k, v in values.items() if v}

    @api.model
    def _lazada_buyer_values(self, order, config=None):
        return self._lazada_address_values(order.get("address_shipping"), config)

    @api.model
    def _lazada_buyer_key(self, order):
        """Stable buyer key: Lazada buyer id, else e-mail or name (as stored
        by earlier versions), else one contact per order rather than merging
        buyers whose names are masked."""
        clean = self._lazada_clean
        name = " ".join(filter(None, [
            clean(order.get("customer_first_name")), clean(order.get("customer_last_name")),
        ]))
        return str(
            order.get("buyer_id") or clean(order.get("customer_email")) or name
            or f"order-{order.get('order_id') or ''}"
        )

    @api.model
    def find_or_create_lazada_buyer(self, config, order):
        # Lazada may mask buyer data, so buyers can lack the address, phone
        # and email that buz_partner_required_fields demands. Skip that check
        # for buyers created here; staff complete them when needed.
        Partner = self.with_context(skip_partner_required_fields=True)
        buyer_id = self._lazada_buyer_key(order)
        partner = Partner.search([
            ("lazada_config_id", "=", config.id),
            ("lazada_buyer_id", "=", buyer_id),
        ], limit=1)
        values = self._lazada_buyer_values(order, config)
        if partner:
            # A buyer with tax invoice data keeps it; the recipient goes to a
            # delivery contact (see _lazada_update_from_order).
            if values and not partner.vat:
                partner.write(values)
            return partner
        clean = self._lazada_clean
        values.setdefault(
            "name",
            " ".join(filter(None, [
                clean(order.get("customer_first_name")), clean(order.get("customer_last_name")),
            ])) or f"Lazada Buyer {order.get('order_number') or order.get('order_id') or ''}".strip(),
        )
        values.update({
            "lazada_buyer_id": buyer_id,
            "lazada_config_id": config.id,
            "company_id": config.company_id.id,
            "customer_rank": 1,
        })
        return Partner.create(values)

    def _lazada_update_from_order(self, order, config=None):
        """Apply the real (unmasked) recipient of a Lazada order.

        Returns the contact to use as the order's delivery address. A buyer
        that carries tax invoice data (VAT) keeps it; the recipient then
        goes to a delivery contact under the buyer instead.
        """
        self.ensure_one()
        values = self._lazada_buyer_values(order, config or self.lazada_config_id)
        if not values:
            return self
        if self.vat:
            return self._lazada_delivery_contact(values)
        self.with_context(skip_partner_required_fields=True).write(values)
        return self

    def _lazada_delivery_contact(self, values):
        """Find or create the delivery contact holding ``values``."""
        self.ensure_one()
        Partner = self.with_context(skip_partner_required_fields=True)
        name = values.get("name") or self.name
        contact = Partner.search([
            ("parent_id", "=", self.id),
            ("type", "=", "delivery"),
            ("name", "=", name),
            ("street", "=", values.get("street") or False),
        ], limit=1)
        if contact:
            contact.write(values)
            return contact
        return Partner.create(dict(
            values, name=name, parent_id=self.id, type="delivery",
        ))

    def _lazada_apply_tax_invoice(self, order, config=None):
        """Put the order's tax invoice identity (TH: tax_code, branch_number,
        address_billing) on the buyer. Odoo invoices use the commercial
        partner's VAT, so it lives here and not on a child contact."""
        self.ensure_one()
        vat = re.sub(r"[\s-]", "", self._lazada_clean(order.get("tax_code")) or "")
        if not vat:
            return False
        values = self._lazada_address_values(order.get("address_billing"), config)
        values["vat"] = vat
        branch = self._lazada_clean(order.get("branch_number"))
        if branch:
            values["company_type"] = "company"
            branch_field = self._fields.get("branch")
            if branch_field and branch_field.type == "char":
                values["branch"] = branch.zfill(5) if branch.isdigit() else branch
        self.with_context(skip_partner_required_fields=True).write(values)
        return True
