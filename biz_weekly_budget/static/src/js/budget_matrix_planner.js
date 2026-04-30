/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class BudgetMatrixPlanner extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        this.state = useState({
            weeks: [],
            rows: [],
            selectedPlanId: null,
            plans: [],
            loading: true,
        });

        onWillStart(async () => {
            await this.loadPlans();
            if (this.state.plans.length > 0) {
                this.state.selectedPlanId = this.state.plans[0].id;
                await this.loadMatrixData();
            }
            this.state.loading = false;
        });
    }

    async loadPlans() {
        try {
            const plans = await this.rpc("/web/dataset/call_kw/monthly.budget.plan/search_read", {
                model: "monthly.budget.plan",
                method: "search_read",
                args: [[['state', 'in', ['draft', 'confirmed']]], ['id', 'name']],
                kwargs: {},
            });
            this.state.plans = plans || [];
        } catch (error) {
            console.error("Failed to load budget plans", error);
        }
    }

    async loadMatrixData() {
        this.state.loading = true;
        try {
            const data = await this.rpc("/budget/api/matrix", {
                plan_id: parseInt(this.state.selectedPlanId)
            });
            if (data.error) {
                this.notification.add(data.error, { type: "danger" });
            } else {
                this.state.weeks = data.weeks || [];
                this.state.rows = data.rows || [];
            }
        } catch (error) {
            console.error("Failed to load matrix data", error);
            this.notification.add("Failed to load data", { type: "danger" });
        }
        this.state.loading = false;
    }

    async onPlanChange(ev) {
        this.state.selectedPlanId = ev.target.value;
        await this.loadMatrixData();
    }

    async updateCellLimit(lineId, ev) {
        const newLimit = parseFloat(ev.target.value);
        if (isNaN(newLimit)) return;
        await this._updateCell(lineId, { amount_limit: newLimit });
    }

    async updateCellForecast(lineId, ev) {
        const newForecast = parseFloat(ev.target.value);
        if (isNaN(newForecast)) return;
        await this._updateCell(lineId, { forecast_amount: newForecast });
    }

    async _updateCell(lineId, vals) {
        try {
            const res = await this.rpc("/budget/api/update_cell", {
                line_id: lineId,
                amount_limit: vals.amount_limit,
                forecast_amount: vals.forecast_amount
            });
            if (res.status === 'success') {
                this.notification.add("Saved", { type: "success" });
                for (const row of this.state.rows) {
                    for (const week in row.cells) {
                        if (row.cells[week].line_id === lineId) {
                            if (vals.amount_limit !== undefined) row.cells[week].limit = vals.amount_limit;
                            if (vals.forecast_amount !== undefined) row.cells[week].forecast = vals.forecast_amount;
                            row.cells[week].available = row.cells[week].limit - row.cells[week].used - row.cells[week].reserved - row.cells[week].forecast;
                        }
                    }
                }
            } else {
                this.notification.add(res.error || "Save Failed", { type: "danger" });
            }
        } catch (error) {
            console.error(error);
            this.notification.add("Failed to update cell", { type: "danger" });
        }
    }

    formatCurrency(val) {
        if (!val) return '0.00';
        return Number(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
}

BudgetMatrixPlanner.template = "biz_weekly_budget.BudgetMatrixPlanner";
registry.category("actions").add("weekly_budget_matrix", BudgetMatrixPlanner);
