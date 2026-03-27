/** @odoo-module */
import { Component } from "@odoo/owl";

export class ProgressBar extends Component {
    static template = "biz_monthly_analytic_budget.ProgressBar";
    static props = {
        value: { type: Number, optional: true },
    };

    get color() {
        const val = this.props.value || 0;
        if (val < 0.5) return 'success';
        if (val < 0.8) return 'warning';
        return 'danger';
    }

    get percentage() {
        const val = this.props.value || 0;
        return Math.round(val * 100);
    }

    get barWidth() {
        const val = this.props.value || 0;
        return Math.min(val * 100, 100);
    }
}

export class AnalyticTable extends Component {
    static template = "biz_monthly_analytic_budget.AnalyticTable";
    static components = { ProgressBar };
    static props = {
        data: { type: Array, optional: true },
    };

    formatCurrency(value) {
        if (!value) return "0.00";
        return new Intl.NumberFormat('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2
        }).format(value);
    }
}
