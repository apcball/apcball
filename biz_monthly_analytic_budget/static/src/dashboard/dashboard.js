/** @odoo-module */
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";
import { KpiCards } from "./components/kpi_cards";
import { WaterfallChart } from "./components/waterfall_chart";
import { StackedBarChart } from "./components/stacked_bar";
import { AnalyticTable } from "./components/analytic_table";
import { TrendChart } from "./components/trend_chart";
import { AlertPanel } from "./components/alert_panel";

export class BudgetDashboard extends Component {
    static template = "biz_monthly_analytic_budget.BudgetDashboard";
    static components = {
        KpiCards,
        WaterfallChart,
        StackedBarChart,
        AnalyticTable,
        TrendChart,
        AlertPanel
    };

    setup() {
        this.rpc = useService("rpc");
        this.orm = useService("orm");
        this.action = useService("action");
        
        this.state = useState({
            data: {
                kpi: {},
                waterfall: [],
                stacked_bar: [],
                analytic_breakdown: [],
                trend: [],
                alerts: []
            },
            filters: {
                plan_id: '',
                company_id: '',
                department_id: '',
                project_id: '',
                category: ''
            },
            filterOptions: {
                plans: [],
                companies: [],
                departments: [],
                projects: []
            },
            loading: true
        });

        onWillStart(async () => {
            try {
                await loadJS("/web/static/lib/Chart/Chart.js");
            } catch (e) {
                console.warn("Chart.js might already be loaded in the environment.");
            }
            await this.loadFilterOptions();
            this.selectDefaultPlan();
            await this.loadData();
        });
    }

    getCurrentMonthPlan(plans) {
        const today = new Date();
        const currentMonth = today.getMonth() + 1;
        const currentYear = today.getFullYear();
        return (plans || []).find((plan) => {
            const planMonth = parseInt(plan.month, 10);
            const planYear = parseInt(plan.year, 10);
            return planMonth === currentMonth && planYear === currentYear;
        }) || null;
    }

    selectDefaultPlan() {
        const plans = this.state.filterOptions.plans || [];
        if (!plans.length) {
            this.state.filters.plan_id = '';
            return;
        }

        const planIds = plans.map((plan) => String(plan.id));
        const currentSelected = this.state.filters.plan_id && planIds.includes(this.state.filters.plan_id)
            ? this.state.filters.plan_id
            : '';
        const currentMonthPlan = this.getCurrentMonthPlan(plans);

        if (currentMonthPlan) {
            this.state.filters.plan_id = String(currentMonthPlan.id);
            return;
        }

        this.state.filters.plan_id = currentSelected || String(plans[0].id);
    }

    async loadFilterOptions() {
        try {
            const [plans, companies, departments, projects] = await Promise.all([
                this.rpc('/budget/dashboard/plans', {}),
                this.orm.searchRead('res.company', [], ['id', 'name']),
                this.orm.searchRead('hr.department', [], ['id', 'name']),
                this.orm.searchRead('project.project', [], ['id', 'name'])
            ]);
            this.state.filterOptions.plans = plans || [];
            this.state.filterOptions.companies = companies;
            this.state.filterOptions.departments = departments;
            this.state.filterOptions.projects = projects;
        } catch (e) {
            console.error("Failed to load filter options", e);
        }
    }

    async loadData() {
        this.state.loading = true;
        try {
            const result = await this.rpc('/budget/dashboard/data', {
                filters: this.state.filters
            });
            this.state.data = result;
        } catch (e) {
            console.error("Dashboard Load Error:", e);
        } finally {
            this.state.loading = false;
        }
    }

    async onFilterChange(ev) {
        const field = ev.target.name;
        this.state.filters[field] = ev.target.value;
        // When company changes, reload plan list
        if (field === 'company_id') {
            await this.reloadPlans();
        }
        await this.loadData();
    }

    async reloadPlans() {
        try {
            const companyId = this.state.filters.company_id || null;
            const plans = await this.rpc('/budget/dashboard/plans', { company_id: companyId ? parseInt(companyId) : null });
            this.state.filterOptions.plans = plans || [];
            this.selectDefaultPlan();
        } catch (e) {
            console.error("Failed to reload plans", e);
        }
    }
}

registry.category("actions").add("monthly_budget_dashboard", BudgetDashboard);
