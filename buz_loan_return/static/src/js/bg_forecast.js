/** @odoo-module **/

import { Component, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { standardWidgetProps } from "@web/views/widgets/standard_widget_props";
import { StockForecasted } from "@stock/stock_forecasted/stock_forecasted";
import { ForecastedButtons } from "@stock/stock_forecasted/forecasted_buttons";

class BGForecastedButtons extends ForecastedButtons {
    async _onClickUpdateQuantity() {
        const action = await this.orm.call(this.resModel, "action_update_quantity_on_hand", [[this.productId]]);
        if (action.res_model === "stock.quant") {
            action.views = [[false, "tree"]];
        }
        return this.actionService.doAction({
            ...action, target: "new", context: { ...action.context, ...this.context },
        }, { onClose: this._onClose.bind(this) });
    }
}

export class BGForecasted extends StockForecasted {
    // โหลดใน dialog เดิม เพื่อไม่ให้การสลับคลังแทนที่ฟอร์ม BG ที่ยังไม่ได้บันทึก
    async reloadReport() {
        await this._getReportValues();
        this.render(true);
    }

    async _getReportValues() {
        const request = this.reportRequest = (this.reportRequest || 0) + 1;
        const context = { ...this.context };
        const [warehouses, report] = await Promise.all([
            this.orm.searchRead("stock.warehouse", [], ["id", "name", "code"], { context }),
            this.orm.call("stock.forecasted_product_product", "get_report_values", [], {
                context, docids: [this.productId],
            }),
        ]);
        // ไม่ให้ผลลัพธ์ของคลังที่กดก่อนหน้าทับคลังล่าสุด เมื่อเครือข่ายตอบกลับช้า
        if (request === this.reportRequest) {
            this.warehouses.splice(0, this.warehouses.length, ...warehouses);
            this.docs = { ...report.docs, ...report.precision };
        }
    }

    async openView(resModel, view, resId) {
        return this.action.doAction({
            type: "ir.actions.act_window",
            res_model: resModel,
            views: [[false, view]],
            res_id: resId,
            target: "new",
            context: this.context,
        });
    }
}
BGForecasted.components = { ...StockForecasted.components, ForecastedButtons: BGForecastedButtons };
registry.category("actions").add("buz_loan_return_forecast", BGForecasted);

export class BGForecastWidget extends Component {
    static template = "buz_loan_return.BGForecastWidget";
    static props = { ...standardWidgetProps };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ loading: false });
    }

    async openForecast() {
        if (this.state.loading) {
            return;
        }
        const line = this.props.record.data;
        const wizard = this.props.record.model.root.data;
        if (!line.product_id || line.product_type !== "product" || wizard.document_kind !== "loan") {
            return;
        }
        this.state.loading = true;
        try {
            // อ่านค่าจากแถวที่ยังไม่บันทึก ไม่ save wizard และไม่สร้าง stock move
            const action = await this.orm.call("buz.loan.return.create.wizard", "action_bg_forecast", [], {
                product_id: line.product_id[0],
                location_id: wizard.location_id?.[0] || false,
                operation_type_id: wizard.operation_type_id?.[0] || false,
                company_id: wizard.company_id?.[0] || false,
            });
            await this.action.doAction({ ...action, tag: "buz_loan_return_forecast", target: "new" });
        } finally {
            this.state.loading = false;
        }
    }
}
registry.category("view_widgets").add("buz_bg_forecast", { component: BGForecastWidget });
