import re

from odoo import api, fields, models

_MASKED = re.compile(r"\*{2,}")
_STATE_PREFIX = re.compile(r"^\s*(จังหวัด|จ\.|changwat)\s*", re.IGNORECASE)
_SUBDISTRICT_TAIL = re.compile(r"(?:^|\s)((?:ตำบล|แขวง)\S+)$")
# Contact fields that may have been filled from the company address by
# 17.0.2.5.0 when Shopee masked the buyer data (cleaned up in 17.0.2.7.0).
_COMPANY_COPY_FIELDS = ("street", "street2", "city", "zip", "state_id", "phone")


class ResPartner(models.Model):
    _inherit = "res.partner"
    shopee_buyer_id = fields.Char(string="Shopee Buyer ID", copy=False)
    shopee_config_id = fields.Many2one(
        "shopee.config", string="Shopee Shop Config", copy=False, ondelete="set null"
    )

    _sql_constraints = [
        (
            "shopee_buyer_shop_unique",
            "unique(shopee_config_id, shopee_buyer_id)",
            "A Shopee buyer can only have one partner per shop.",
        ),
    ]

    @staticmethod
    def _shopee_clean(value):
        """Return a usable string, or False for empty / masked Shopee data."""
        value = str(value or "").strip()
        # Shopee masks hidden data fully ("*****") or partly ("******78").
        if not value or _MASKED.search(value):
            return False
        return value

    @api.model
    def _shopee_find_state(self, state_name, country):
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
    def _shopee_split_street(full_address, tail_parts):
        """Split Shopee's one-line address into (street, subdistrict).

        Shopee appends "ตำบล… อำเภอ… จังหวัด… 55000" to the address the
        buyer typed. Odoo shows city/province/zip on their own lines, so drop
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
            # Shopee sometimes repeats the subdistrict ("ตำบลX ตำบลX")
            while street.endswith(" " + subdistrict):
                street = street[: -len(subdistrict)].rstrip(" ,")
        return street or full_address.strip(), subdistrict

    @staticmethod
    def _shopee_thai_phone(value):
        """Shopee sends Thai numbers as 66XXXXXXXXX; show them as 0XXXXXXXXX."""
        if not value:
            return value
        digits = re.sub(r"\D", "", str(value))
        if digits.startswith("66") and len(digits) == 11:
            return "0" + digits[2:]
        return value

    @api.model
    def _shopee_buyer_values(self, order):
        """Partner values taken from the Shopee order (real data only).

        Masked or missing fields are left out: never fill a buyer with
        somebody else's data (e.g. the company address).
        """
        address = order.get("recipient_address") or {}
        clean = self._shopee_clean
        # The recipient region is masked with the rest of the address, but
        # the order-level "region" (e.g. "TH") is always sent.
        region = clean(address.get("region")) or clean(order.get("region"))
        country = (
            self.env["res.country"].search([("code", "=ilike", region)], limit=1)
            if region else self.env["res.country"]
        )
        state_name = clean(address.get("state"))
        state = self._shopee_find_state(state_name, country)
        city = clean(address.get("city"))
        zipcode = clean(address.get("zipcode"))
        district = clean(address.get("district"))
        town = clean(address.get("town"))
        street, subdistrict = self._shopee_split_street(
            clean(address.get("full_address")),
            [zipcode, state_name, state_name and _STATE_PREFIX.sub("", state_name),
             city, district, town],
        )
        street2 = " ".join(filter(None, [district, town])) or subdistrict
        values = {
            "name": clean(address.get("name")),
            "phone": self._shopee_thai_phone(clean(address.get("phone"))),
            "street": street,
            "street2": street2 or False,
            "city": city,
            "zip": zipcode,
            "country_id": country.id or False,
            "state_id": state.id or False,
        }
        return {k: v for k, v in values.items() if v}

    @api.model
    def find_or_create_shopee_buyer(self, config, order):
        buyer_id = str(order.get("buyer_user_id") or order.get("buyer_username") or "")
        # Shopee often masks the recipient, so buyers can lack the address,
        # phone and email that buz_partner_required_fields demands. Skip that
        # check for buyers created here; staff complete them when needed.
        Partner = self.with_context(skip_partner_required_fields=True)
        partner = Partner.search([
            ("shopee_config_id", "=", config.id),
            ("shopee_buyer_id", "=", buyer_id),
        ], limit=1) if buyer_id else Partner.browse()

        values = self._shopee_buyer_values(order)
        if partner:
            if values:
                partner.write(values)
            return partner

        values.setdefault(
            "name",
            self._shopee_clean(order.get("buyer_username"))
            or f"Shopee Buyer {order.get('order_sn') or buyer_id}".strip(),
        )
        values.update({
            "shopee_buyer_id": buyer_id or False,
            "shopee_config_id": config.id,
            "company_id": config.company_id.id,
            "customer_rank": 1,
        })
        return Partner.create(values)

    def _shopee_update_from_order(self, order):
        """Apply the real (unmasked) recipient of a Shopee order.

        Returns the contact to use as the order's delivery address. A buyer
        that carries tax invoice data (VAT) keeps it; the recipient then
        goes to a delivery contact under the buyer instead.
        """
        self.ensure_one()
        values = self._shopee_buyer_values(order)
        if not values:
            return self
        if self.vat:
            return self._shopee_delivery_contact(values)
        self.with_context(skip_partner_required_fields=True).write(values)
        return self

    def _shopee_delivery_contact(self, values):
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

    def _shopee_apply_tax_invoice(self, tax):
        """Put the Seller Center tax invoice identity on the buyer.

        ``tax`` keys: type (Personal/Company), name, branch_type, branch_code,
        street, subdistrict, district, state, zipcode, vat, phone, email.
        Odoo invoices use the commercial partner's VAT, so it lives here and
        not on a child contact.
        """
        self.ensure_one()
        clean = self._shopee_clean
        country = self.env.ref("base.th", raise_if_not_found=False) or self.env["res.country"]
        state = self._shopee_find_state(clean(tax.get("state")), country)
        values = {
            "name": clean(tax.get("name")),
            "vat": re.sub(r"[\s-]", "", clean(tax.get("vat")) or "") or False,
            "street": clean(tax.get("street")),
            "street2": clean(tax.get("subdistrict")),
            "city": clean(tax.get("district")),
            "zip": clean(tax.get("zipcode")),
            "state_id": state.id or False,
            "country_id": country.id or False,
            "phone": self._shopee_thai_phone(clean(tax.get("phone"))),
            "email": clean(tax.get("email")),
        }
        values = {k: v for k, v in values.items() if v}
        if str(tax.get("type") or "").strip().lower() == "company":
            values["company_type"] = "company"
            branch_field = self._fields.get("branch")
            if branch_field and branch_field.type == "char":
                head_office = "ใหญ่" in str(tax.get("branch_type") or "")
                values["branch"] = "00000" if head_office else (
                    clean(tax.get("branch_code")) or False
                )
        if values:
            self.with_context(skip_partner_required_fields=True).write(values)
        return self

    @api.model
    def _shopee_normalise_phones(self):
        """Convert stored Shopee buyer phones to the Thai 0XXXXXXXXX form."""
        partners = self.with_context(
            active_test=False, skip_partner_required_fields=True
        ).search([
            "|", ("shopee_config_id", "!=", False),
            ("parent_id.shopee_config_id", "!=", False),
            ("phone", "!=", False),
        ])
        for partner in partners:
            phone = self._shopee_thai_phone(partner.phone)
            if phone != partner.phone:
                partner.phone = phone

    @api.model
    def _shopee_clear_company_copies(self, extra_emails=()):
        """Remove company address/phone/email copied onto Shopee buyers.

        ``extra_emails``: other fallback emails that were used (the removed
        "Buyer Fallback Email" setting).
        """
        cleared = 0
        buyers = self.with_context(
            active_test=False, skip_partner_required_fields=True
        ).search([("shopee_config_id", "!=", False)])
        for partner in buyers:
            company = partner.shopee_config_id.company_id
            company_partner = company.partner_id
            values = {}
            for field_name in _COMPANY_COPY_FIELDS:
                if partner[field_name] and partner[field_name] == company_partner[field_name]:
                    values[field_name] = False
            company_emails = {
                (email or "").strip().lower()
                for email in (company.email, company_partner.email, *extra_emails)
                if email
            }
            if (partner.email or "").strip().lower() in company_emails:
                values["email"] = False
            if values:
                partner.write(values)
                cleared += 1
        return cleared
