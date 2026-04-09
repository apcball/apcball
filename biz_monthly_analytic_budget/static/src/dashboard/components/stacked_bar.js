/** @odoo-module */
import { Component, useEffect, useRef } from "@odoo/owl";

export class StackedBarChart extends Component {
    static template = "biz_monthly_analytic_budget.StackedBarChart";
    static props = {
        data: { type: Array, optional: true },
    };

    setup() {
        this.canvasRef = useRef("canvas");
        this.chartInstance = null;

        useEffect(() => {
            this.renderChart();
        }, () => [this.props.data]);
    }

    renderChart() {
        if (!this.props.data || !this.canvasRef.el) return;

        if (this.chartInstance) {
            this.chartInstance.destroy();
        }

        const items = this.props.data;
        if (items.length === 0) return;

        this.chartInstance = new window.Chart(this.canvasRef.el, {
            type: 'bar',
            data: {
                labels: items.map(i => i.label),
                datasets: [
                    {
                        label: 'Reserved',
                        data: items.map(i => i.reserved),
                        backgroundColor: '#F59E0B',
                        maxBarThickness: 50,
                        borderRadius: 4
                    },
                    {
                        label: 'Used',
                        data: items.map(i => i.used),
                        backgroundColor: '#EF4444',
                        maxBarThickness: 50,
                        borderRadius: 4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: {
                        stacked: true,
                        grid: { display: false }
                    },
                    y: {
                        stacked: true,
                        grid: {
                            color: '#f1f5f9',
                            drawBorder: false
                        }
                    }
                },
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { usePointStyle: true, padding: 20 }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(15, 23, 42, 0.9)',
                        padding: 12,
                        cornerRadius: 8
                    }
                }
            }
        });
    }
}
