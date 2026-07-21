/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { loadJS } from "@web/core/assets";
import { Component, onWillStart, onMounted, onWillUnmount, useState, useRef } from "@odoo/owl";

export class BuzReservationDashboard extends Component {
    static template = "buz_stock_reservation.Dashboard";
    static props = {
        action: { type: Object, optional: true },
        actionId: { type: Number, optional: true },
        className: { type: String, optional: true },
        updateActionState: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.trendCanvas = useRef("trendChart");
        this.statusCanvas = useRef("statusChart");
        this.charts = [];
        this.state = useState({
            period: "week",
            loading: true,
            data: null,
        });

        onWillStart(async () => {
            await loadJS("/web/static/lib/Chart/Chart.js");
            await this.loadData();
        });
        onMounted(() => this.renderCharts());
        onWillUnmount(() => this.destroyCharts());
    }

    async loadData() {
        this.state.loading = true;
        this.state.data = await this.orm.call(
            "buz.reservation.dashboard",
            "get_dashboard_data",
            [this.state.period]
        );
        this.state.loading = false;
    }

    async onPeriodChange(ev) {
        this.state.period = ev.target.value;
        await this.loadData();
        this.renderCharts();
    }

    async refresh() {
        await this.loadData();
        this.renderCharts();
    }

    destroyCharts() {
        this.charts.forEach((c) => c.destroy());
        this.charts = [];
    }

    renderCharts() {
        this.destroyCharts();
        const data = this.state.data;
        if (!data) {
            return;
        }
        if (this.trendCanvas.el) {
            this.charts.push(
                new Chart(this.trendCanvas.el, {
                    type: "line",
                    data: {
                        labels: data.trend.labels,
                        datasets: [
                            {
                                label: "Reservations",
                                data: data.trend.values,
                                borderColor: "#7367f0",
                                backgroundColor: "rgba(115, 103, 240, 0.12)",
                                fill: true,
                                tension: 0.35,
                                pointRadius: 3,
                            },
                        ],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: { legend: { display: false } },
                        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
                    },
                })
            );
        }
        if (this.statusCanvas.el) {
            const dist = data.status_distribution;
            this.charts.push(
                new Chart(this.statusCanvas.el, {
                    type: "doughnut",
                    data: {
                        labels: dist.map((d) => d.label),
                        datasets: [
                            {
                                data: dist.map((d) => d.value),
                                backgroundColor: dist.map((d) => d.color),
                                borderWidth: 2,
                            },
                        ],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        cutout: "62%",
                        plugins: { legend: { position: "right" } },
                    },
                })
            );
        }
    }

    openReservation(id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "buz.stock.reservation",
            res_id: id,
            views: [[false, "form"]],
        });
    }

    openAction(xmlid) {
        this.action.doAction(xmlid);
    }

    newReservation() {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "buz.stock.reservation",
            views: [[false, "form"]],
            target: "current",
        });
    }

    formatQty(value) {
        return Number(value || 0).toLocaleString();
    }

    formatDate(value) {
        return value ? value.substring(0, 16) : "";
    }
}

registry.category("actions").add("buz_reservation_dashboard", BuzReservationDashboard);
