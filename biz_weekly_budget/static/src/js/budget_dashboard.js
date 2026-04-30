/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";
import { Component, onWillStart, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";

export class WeeklyBudgetDashboard extends Component {
    setup() {
        this.rpc = useService("rpc");
        this.state = useState({
            summary: {},
            weeks: [],
            plans: [],
            pieData: { labels: [], values: [] },
            departments: [],
            years: [],
            months: [
                {id: 'all', name: 'All Months'},
                {id: 1, name: 'January'},
                {id: 2, name: 'February'},
                {id: 3, name: 'March'},
                {id: 4, name: 'April'},
                {id: 5, name: 'May'},
                {id: 6, name: 'June'},
                {id: 7, name: 'July'},
                {id: 8, name: 'August'},
                {id: 9, name: 'September'},
                {id: 10, name: 'October'},
                {id: 11, name: 'November'},
                {id: 12, name: 'December'}
            ],
            selectedPlanId: "all",
            selectedYear: "all",
            selectedMonth: "all",
            loaded: false,
        });
        this.chartRef = useRef("chart");
        this.lineChartRef = useRef("lineChart");
        this.pieChartRef = useRef("pieChart");
        this.chart = null;
        this.lineChart = null;
        this.pieChart = null;

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            await this.loadPlans();
            await this.loadYears();
            await this.loadData();
            this.state.loaded = true;
        });

        onMounted(() => {
            // Always attempt all renders — Chart.js handles empty arrays gracefully.
            this.renderChart();
            this.renderLineChart();
            this.renderPieChart();
        });

        onWillUnmount(() => {
            if (this.chart) {
                this.chart.destroy();
                this.chart = null;
            }
            if (this.lineChart) {
                this.lineChart.destroy();
                this.lineChart = null;
            }
            if (this.pieChart) {
                this.pieChart.destroy();
                this.pieChart = null;
            }
        });
    }

    async loadPlans() {
        try {
            const plans = await this.rpc("/web/dataset/call_kw/monthly.budget.plan/search_read", {
                model: "monthly.budget.plan",
                method: "search_read",
                args: [[['state', '=', 'confirmed']], ['id', 'name']],
                kwargs: {},
            });
            this.state.plans = plans || [];
        } catch (error) {
            console.error("Failed to load budget plans", error);
        }
    }

    async loadYears() {
        try {
            const years = await this.rpc("/web/dataset/call_kw/weekly.budget.report/get_available_years", {
                model: "weekly.budget.report",
                method: "get_available_years",
                args: [],
                kwargs: {},
            });
            this.state.years = years || [];
        } catch (error) {
            console.error("Failed to load available years", error);
        }
    }

    async loadData() {
        try {
            const data = await this.rpc("/budget/api/dashboard_data", {
                selectedPlanId: this.state.selectedPlanId,
                selectedYear: this.state.selectedYear,
                selectedMonth: this.state.selectedMonth
            });
            this.state.summary = data.summary || {};
            this.state.weeks = data.weeks || [];
            this.state.departments = data.departments || [];
            this.state.pieData = data.pie_data || { labels: [], values: [] };
        } catch (error) {
            console.error("Failed to load dashboard data", error);
        }
    }

    async onPlanChange(ev) {
        this.state.selectedPlanId = ev.target.value;
        await this.loadData();
        this.renderChart();
        this.renderLineChart();
        this.renderPieChart();
    }

    async onYearChange(ev) {
        this.state.selectedYear = ev.target.value;
        await this.loadData();
        this.renderChart();
        this.renderLineChart();
        this.renderPieChart();
    }

    async onMonthChange(ev) {
        this.state.selectedMonth = ev.target.value;
        await this.loadData();
        this.renderChart();
        this.renderLineChart();
        this.renderPieChart();
    }

    renderChart() {
        if (!this.chartRef.el) return;

        const ChartJS = window.Chart;
        if (!ChartJS) {
            console.error("Chart.js library is not available.");
            return;
        }

        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }

        if (!this.state.departments.length) return;

        const labels = this.state.departments.map(d => d.name);
        const limitData = this.state.departments.map(d => d.limit);
        const usedData = this.state.departments.map(d => d.used);
        const reservedData = this.state.departments.map(d => d.reserved);
        const forecastData = this.state.departments.map(d => d.forecast);

        const ctx = this.chartRef.el.getContext('2d');
        this.chart = new ChartJS(ctx, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Limit',
                        data: limitData,
                        backgroundColor: 'rgba(54, 162, 235, 0.7)',
                    },
                    {
                        label: 'Used',
                        data: usedData,
                        backgroundColor: 'rgba(255, 99, 132, 0.7)',
                    },
                    {
                        label: 'Reserved',
                        data: reservedData,
                        backgroundColor: 'rgba(255, 159, 64, 0.7)',
                    },
                    {
                        label: 'Forecast',
                        data: forecastData,
                        backgroundColor: 'rgba(153, 102, 255, 0.7)',
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: function (value) {
                                return value.toLocaleString();
                            }
                        }
                    },
                    x: {
                        grid: {
                            display: false
                        }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            usePointStyle: true,
                            padding: 20
                        }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        callbacks: {
                            label: function (context) {
                                let label = context.dataset.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                if (context.parsed.y !== null) {
                                    label += new Intl.NumberFormat('en-US', { style: 'currency', currency: 'THB' }).format(context.parsed.y);
                                }
                                return label;
                            }
                        }
                    }
                }
            }
        });
    }

    renderLineChart() {
        if (!this.lineChartRef.el) return;
        const ChartJS = window.Chart;
        if (!ChartJS) return;
        if (this.lineChart) {
            this.lineChart.destroy();
            this.lineChart = null;
        }
        if (!this.state.weeks.length) return;

        const labels      = this.state.weeks.map(w => w.name);
        const budgetData   = this.state.weeks.map(w => w.budget   || 0);
        const reservedData = this.state.weeks.map(w => w.reserved || 0);
        const usedData     = this.state.weeks.map(w => w.actual   || 0);

        const ctx = this.lineChartRef.el.getContext('2d');
        this.lineChart = new ChartJS(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Budget Limit',
                        data: budgetData,
                        borderColor: 'rgba(54, 162, 235, 0.9)',
                        backgroundColor: 'rgba(54, 162, 235, 0.08)',
                        borderWidth: 2,
                        borderDash: [6, 3],
                        tension: 0.3,
                        fill: false,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                    },
                    {
                        label: 'Reserved (ยอดจอง)',
                        data: reservedData,
                        borderColor: 'rgba(255, 159, 64, 0.9)',
                        backgroundColor: 'rgba(255, 159, 64, 0.08)',
                        borderWidth: 2,
                        tension: 0.3,
                        fill: false,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                    },
                    {
                        label: 'Actual Used (ยอดใช้จริง)',
                        data: usedData,
                        borderColor: 'rgba(255, 99, 132, 0.9)',
                        backgroundColor: 'rgba(255, 99, 132, 0.08)',
                        borderWidth: 2,
                        tension: 0.3,
                        fill: false,
                        pointRadius: 4,
                        pointHoverRadius: 6,
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: {
                    mode: 'index',
                    intersect: false,
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            callback: (value) => {
                                if (value >= 1000000) return (value / 1000000).toFixed(1) + 'M';
                                if (value >= 1000)    return (value / 1000).toFixed(0) + 'K';
                                return value.toLocaleString();
                            }
                        },
                        grid: { color: 'rgba(0,0,0,0.05)' }
                    },
                    x: {
                        grid: { display: false }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            usePointStyle: true,
                            padding: 18,
                            font: { size: 12 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const val = context.parsed.y;
                                const fmt = new Intl.NumberFormat('th-TH', {
                                    style: 'currency', currency: 'THB',
                                    minimumFractionDigits: 0,
                                    maximumFractionDigits: 0,
                                }).format(val);
                                return ` ${context.dataset.label}: ${fmt}`;
                            }
                        }
                    }
                }
            }
        });
    }

    renderPieChart() {
        if (!this.pieChartRef.el) return;

        const ChartJS = window.Chart;
        if (!ChartJS) return;

        if (this.pieChart) {
            this.pieChart.destroy();
            this.pieChart = null;
        }

        const { labels, values } = this.state.pieData;
        if (!labels || !labels.length) return;

        const ctx = this.pieChartRef.el.getContext('2d');
        this.pieChart = new ChartJS(ctx, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: [
                        'rgba(255, 99, 132, 0.85)',
                        'rgba(255, 159, 64, 0.85)',
                        'rgba(54, 162, 235, 0.85)',
                    ],
                    borderColor: [
                        'rgb(255, 99, 132)',
                        'rgb(255, 159, 64)',
                        'rgb(54, 162, 235)',
                    ],
                    borderWidth: 2,
                    hoverOffset: 8,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: '65%',
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            usePointStyle: true,
                            padding: 16,
                            font: { size: 13 }
                        }
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const val = context.parsed;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const pct = total ? ((val / total) * 100).toFixed(1) : 0;
                                const fmt = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'THB' }).format(val);
                                return ` ${context.label}: ${fmt} (${pct}%)`;
                            }
                        }
                    }
                }
            }
        });
    }

    formatCurrency(value) {
        return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'THB' }).format(value || 0);
    }
}

WeeklyBudgetDashboard.template = "biz_weekly_budget.WeeklyBudgetDashboard";

registry.category("actions").add("weekly_budget_dashboard", WeeklyBudgetDashboard);
