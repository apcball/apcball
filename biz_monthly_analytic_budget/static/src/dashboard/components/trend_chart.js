/** @odoo-module */
import { Component, useEffect, useRef } from "@odoo/owl";

export class TrendChart extends Component {
    static template = "biz_monthly_analytic_budget.TrendChart";
    static props = {
        data: { type: Array, optional: true }
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
        
        const labels = this.props.data.map(d => d.month);
        const budgets = this.props.data.map(d => d.budget);
        const used = this.props.data.map(d => d.used);
        
        let ctx = this.canvasRef.el.getContext("2d");
        let gradientBudget = ctx.createLinearGradient(0, 0, 0, 400);
        gradientBudget.addColorStop(0, 'rgba(59, 130, 246, 0.8)');
        gradientBudget.addColorStop(1, 'rgba(59, 130, 246, 0.2)');

        this.chartInstance = new window.Chart(this.canvasRef.el, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Total Budget',
                        data: budgets,
                        backgroundColor: gradientBudget,
                        maxBarThickness: 50,
                        borderRadius: 6
                    },
                    {
                        label: 'Actual Used',
                        data: used,
                        type: 'line',
                        borderColor: '#EF4444',
                        borderWidth: 3,
                        tension: 0.4, // smooth curves
                        pointBackgroundColor: '#ffffff',
                        pointBorderColor: '#EF4444',
                        pointBorderWidth: 2,
                        pointRadius: 4,
                        fill: false
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: { usePointStyle: true, padding: 20 }
                    },
                    tooltip: {
                        mode: 'index',
                        intersect: false,
                        backgroundColor: 'rgba(15, 23, 42, 0.9)',
                        padding: 12,
                        cornerRadius: 8
                    }
                },
                scales: {
                    x: {
                        grid: { display: false }
                    },
                    y: {
                        grid: {
                            color: '#f1f5f9',
                            drawBorder: false
                        }
                    }
                }
            }
        });
    }
}
