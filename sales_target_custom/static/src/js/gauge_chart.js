/** @odoo-module **/

import { GraphRenderer } from "@web/views/graph/graph_renderer";
import { registry } from "@web/core/registry";

export class GaugeChartRenderer extends GraphRenderer {

    async willStart() {
        await super.willStart();
    }

    _renderChart() {
        if (this.props.type !== "gauge") {
            return super._renderChart();
        }

        const canvas = this.canvasRef.el;
        const ctx = canvas.getContext("2d");

        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const data = this._processGaugeData();

        data.forEach((item, index) => {
            this._renderSingleGauge(ctx, item, index, data.length);
        });
    }

    _processGaugeData() {
        const data = [];
        const datasets = this.chart.data.datasets || [];
        const labels = this.chart.data.labels || [];

        if (datasets.length > 0 && labels.length > 0) {
            labels.forEach((label, index) => {
                const value = datasets[0].data[index] || 0;
                data.push({
                    label: label,
                    value: Math.min(Math.max(value, 0), 100),
                    color: this._getGaugeColor(value)
                });
            });
        }

        return data;
    }

    _renderSingleGauge(ctx, data, index, total) {
        const canvas = ctx.canvas;
        const gaugeWidth = Math.min(canvas.width / Math.ceil(Math.sqrt(total)), 200);
        const gaugeHeight = gaugeWidth;

        const cols = Math.ceil(Math.sqrt(total));
        const x = (index % cols) * gaugeWidth + gaugeWidth / 2;
        const y = Math.floor(index / cols) * gaugeHeight + gaugeHeight / 2;

        const radius = gaugeWidth * 0.35;
        const centerX = x;
        const centerY = y;

        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, Math.PI, 2 * Math.PI);
        ctx.lineWidth = 20;
        ctx.strokeStyle = "#e0e0e0";
        ctx.stroke();

        const endAngle = Math.PI + (data.value / 100) * Math.PI;
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, Math.PI, endAngle);
        ctx.strokeStyle = data.color;
        ctx.stroke();

        ctx.fillStyle = "#333";
        ctx.font = "bold 16px Arial";
        ctx.textAlign = "center";
        ctx.fillText(`${data.value.toFixed(1)}%`, centerX, centerY - 10);

        ctx.font = "12px Arial";
        ctx.fillText(data.label, centerX, centerY + 20);
    }

    _getGaugeColor(value) {
        if (value >= 100) return "#28a745";
        if (value >= 75) return "#ffc107";
        if (value >= 50) return "#fd7e14";
        return "#dc3545";
    }
}

registry.category("renderers").add("gauge_chart", GaugeChartRenderer);
