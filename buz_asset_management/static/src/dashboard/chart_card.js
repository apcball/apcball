/** @odoo-module **/

import { loadJS } from "@web/core/assets";
import { Component, onMounted, onPatched, onWillStart, onWillUnmount, useRef } from "@odoo/owl";

/** Thin Chart.js wrapper: rebuilds the chart whenever props.config changes.
 *  Optional props.centerValue / props.centerLabel are drawn inside doughnuts. */
export class ChartCard extends Component {
    static template = "buz_asset_management.ChartCard";
    static props = {
        config: { type: [Object, { value: null }], optional: true },
        empty: { type: Boolean, optional: true },
        centerValue: { type: String, optional: true },
        centerLabel: { type: String, optional: true },
    };

    setup() {
        this.canvas = useRef("canvas");
        this.chart = null;
        this.lastConfig = null;
        onWillStart(() => loadJS("/web/static/lib/Chart/Chart.js"));
        onMounted(() => this.renderChart());
        onPatched(() => this.renderChart());
        onWillUnmount(() => this.destroy());
    }

    destroy() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
        }
    }

    get centerPlugin() {
        const props = this.props;
        return {
            id: "bamCenterText",
            afterDraw(chart) {
                if (!props.centerValue || !chart.chartArea) {
                    return;
                }
                const { ctx, chartArea } = chart;
                const x = (chartArea.left + chartArea.right) / 2;
                const y = (chartArea.top + chartArea.bottom) / 2;
                ctx.save();
                ctx.textAlign = "center";
                ctx.textBaseline = "middle";
                ctx.fillStyle = "#1d2d44";
                ctx.font = "bold 22px sans-serif";
                ctx.fillText(props.centerValue, x, y - 8);
                ctx.fillStyle = "#6a7a90";
                ctx.font = "12px sans-serif";
                ctx.fillText(props.centerLabel || "", x, y + 14);
                ctx.restore();
            },
        };
    }

    renderChart() {
        const config = this.props.config;
        if (config === this.lastConfig && this.chart) {
            return;
        }
        this.lastConfig = config;
        this.destroy();
        if (!config || this.props.empty || !this.canvas.el) {
            return;
        }
        this.chart = new window.Chart(this.canvas.el, { ...config, plugins: [this.centerPlugin] });
    }
}
