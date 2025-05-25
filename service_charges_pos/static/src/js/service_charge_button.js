/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { useService } from "@web/core/utils/hooks";
import { NumberPopup } from "@point_of_sale/app/utils/input_popups/number_popup";
import { ErrorPopup } from "@point_of_sale/app/errors/popups/error_popup";
import { Component } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/store/pos_hook";
import { parseFloat } from "@web/views/fields/parsers";

export class ServiceChargeButton extends Component {
    static template = "service_charges_pos.ServiceChargeButton";

    setup() {
        this.pos = usePos();
        this.popup = useService("popup");
    }

    async click() {
        var self = this;
        const { confirmed, payload } = await this.popup.add(NumberPopup, {
            title: _t("Service Charge"),
            startingValue: this.pos.config.service_charge,
            isInputSelected: true,
        });
        if (confirmed) {
            const val = Math.max(0, Math.min(100, parseFloat(payload)));
            if (val > 0) {
                await self.apply_service_charge(val);
            }
        }
    }

    async apply_service_charge(val) {
        const order = this.pos.get_order();
        const lines = order.get_orderlines();
        const product = this.pos.db.get_product_by_id(this.pos.config.service_product_id[0]);
        if (product === undefined) {
            await this.popup.add(ErrorPopup, {
                title: _t("No service product found"),
                body: _t(
                    "The service product seems misconfigured. Make sure it is flagged as 'Can be Sold' and 'Available in Point of Sale'."
                ),
            });
            return;
        }
        // Remove existing service charges
        lines
            .filter((line) => line.get_product() === product)
            .forEach((line) => order._unlinkOrderline(line));
        // Add service charge
        if (this.pos.config.service_charge_type == 'amount') {
            var sc_price = val
        } else {
            var sc_price = order.get_total_with_tax() * val / 100
        }
        order.add_product(product, {
            price: sc_price,
            tax_ids: []
        });
    }

}

ProductScreen.addControlButton({
    component: ServiceChargeButton,
    condition: function () {
        const { is_service_charges, service_product_id } = this.pos.config;
        return is_service_charges && service_product_id;
    },
});
