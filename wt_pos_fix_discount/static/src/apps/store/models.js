/** @odoo-module */

import { Order, Orderline } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/store/pos_store";

patch(Orderline.prototype, {
	setup(_defaultObj, options) {
		super.setup(...arguments);
		this.fix_discount = 0;
		if(options.json && options.json.fix_discount){
			this.set_fix_discount(options.json.fix_discount || 0)
		}
	},
	init_from_JSON(json) {
		super.init_from_JSON(...arguments);
		if(json.fix_discount){
			this.set_fix_discount(json.fix_discount);
		}
	},
	export_as_JSON() {
		return {
			...super.export_as_JSON(),
			fix_discount : this.fix_discount || 0,
		}
	},
	set_fix_discount(discount) {
		discount = Math.min((this.get_unit_price() * this.get_quantity()), discount)
		const discount_per = (discount * 100)/(this.get_unit_price() * this.get_quantity()) || 0
		this.set_discount(discount_per)
		this.fix_discount = discount;
	},
	set_discount(discount) {
        super.set_discount(...arguments);
        this.fix_discount = 0
    },
    get_discount_str(){
    	if(this.fix_discount){
    		return this.env.utils.formatCurrency(this.fix_discount, this.currency);
    	}
    	return super.get_discount_str(...arguments);
    },
    getDisplayData() {
        return {
            ...super.getDisplayData(),
            fix_discount: this.fix_discount,
        };
    },
});