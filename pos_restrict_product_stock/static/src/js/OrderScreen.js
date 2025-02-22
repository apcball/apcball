/** @odoo-module */

import { Order } from "@point_of_sale/app/store/models";
import { patch } from "@web/core/utils/patch";
import RestrictStockPopup from "@pos_restrict_product_stock/js/RestrictStockPopup"

patch(Order.prototype, {
    async pay() {
             var type = this.pos.config.stock_type
             const pay = true
             const body = []
             const pro_id = false
            for (const line of this.orderlines) {
             if (line.pos.config.is_restrict_product && ((type == 'qty_on_hand') && (line.product.qty_available <= 0)) | ((type == 'virtual_qty') && (line.product.virtual_available <= 0)) |
                                     ((line.product.qty_available <= 0) && (line.product.virtual_available <= 0))) {
                                     // If the product restriction is activated in the settings and quantity is out stock, it show the restrict popup.
                                body.push(line.product.display_name)
                 }
             }
             if (body.length > 0) { // Check if body has items
                     const confirmed = await this.pos.popup.add(RestrictStockPopup, {
                         body: body,
                         pro_id: pro_id
                     });
                     if (confirmed == true) {
                         return super.pay(); // Proceed with payment
                     } else {
                          return ;
                     }
                 } else {
                     return super.pay(); // No restrictions, proceed with payment
                 }
             }

    })