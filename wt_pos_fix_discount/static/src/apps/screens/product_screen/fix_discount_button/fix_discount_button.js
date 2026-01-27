/** @odoo-module **/

import { _t } from "@web/core/l10n/translation";
import { ProductScreen } from "@point_of_sale/app/screens/product_screen/product_screen";
import { useService } from "@web/core/utils/hooks";
import { NumberPopup } from "@point_of_sale/app/utils/input_popups/number_popup";
import { Component } from "@odoo/owl";
import { usePos } from "@point_of_sale/app/store/pos_hook";

export class SetFixDiscountButton extends Component {
    static template = "wt_pos_fix_discount.SetFixDiscountButton";

    setup() {
        this.pos = usePos();
        this.popup = useService("popup");
    }
    async click() {
        const selectedOrderline = this.pos.get_order().get_selected_orderline();
        if (!selectedOrderline) {
            return;
        }
        const { confirmed, payload } = await this.popup.add(NumberPopup, {
            title: _t("Discount Fixed"),
            startingValue: 0,
            isInputSelected: true,
        });
        if (confirmed) {
            const price_unit = selectedOrderline.get_unit_price()
            const val = parseFloat(payload)
            selectedOrderline.set_fix_discount(val)
        }
    }
}
ProductScreen.addControlButton({
    component: SetFixDiscountButton,
});