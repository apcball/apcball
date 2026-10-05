/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const TILE_META = {
    api_errors: { icon: "fa-exclamation", color: "#ef4444", bg: "#fdecec" },
    retry_failed: { icon: "fa-refresh", color: "#f59e0b", bg: "#fef3e2" },
    stock_failed: { icon: "fa-cube", color: "#3b82f6", bg: "#e8f0fe" },
    unmapped: { icon: "fa-link", color: "#8b5cf6", bg: "#f1ebfe" },
    stale_push: { icon: "fa-ban", color: "#14b8a6", bg: "#e3f6f4" },
    fulfillment: { icon: "fa-bell", color: "#f59e0b", bg: "#fef3e2" },
};
const STATUS_META = {
    READY_TO_SHIP: { label: "Ready to Ship", color: "#3b82f6" },
    PROCESSED: { label: "Processed", color: "#8b5cf6" },
    SHIPPED: { label: "Shipped", color: "#22a06b" },
    COMPLETED: { label: "Completed", color: "#14b8a6" },
    UNPAID: { label: "Unpaid", color: "#f59e0b" },
    CANCELLED: { label: "Cancelled", color: "#ef4444" },
    IN_CANCEL: { label: "In Cancel", color: "#f97316" },
};
const FALLBACK_COLORS = ["#64748b", "#a855f7", "#06b6d4", "#84cc16"];
const DONUT_R = 54;
const DONUT_C = 2 * Math.PI * DONUT_R;

function prettify(status) {
    return status
        .toLowerCase()
        .split("_")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ");
}

function scale(series, w, h, pad = 2) {
    const max = Math.max(...series, 1);
    const step = series.length > 1 ? w / (series.length - 1) : w;
    return series.map((v, i) => [i * step, h - pad - (v / max) * (h - 2 * pad)]);
}

export class ShopeeDashboard extends Component {
    static template = "shopee_connector.Dashboard";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.logo = "/shopee_connector/static/description/icon.png";
        this.state = useState({
            loading: true,
            days: 7,
            shopId: null,
            data: null,
        });
        onWillStart(() => this.load());
    }

    async load() {
        this.state.loading = true;
        try {
            const shopIds = this.state.shopId ? [this.state.shopId] : [];
            this.state.data = await this.orm.call("shopee.dashboard", "get_dashboard_data", [], {
                shop_ids: shopIds,
                days: this.state.days,
            });
        } finally {
            this.state.loading = false;
        }
    }

    onShopChange(ev) {
        this.state.shopId = ev.target.value ? parseInt(ev.target.value, 10) : null;
        this.load();
    }

    onPeriodChange(ev) {
        this.state.days = parseInt(ev.target.value, 10);
        this.load();
    }

    // ---- tiles ----
    get tiles() {
        return Object.entries(this.state.data.tiles).map(([key, tile]) => {
            const meta = TILE_META[key];
            const pts = tile.series && tile.series.length > 1 ? scale(tile.series, 100, 36) : [];
            const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
            return {
                key,
                ...tile,
                meta,
                line,
                area: pts.length ? `${line} L100,36 L0,36 Z` : "",
                deltaText: this.deltaText(tile.delta),
                deltaClass: this.deltaClass(tile.delta, false),
            };
        });
    }

    deltaText(delta) {
        if (!delta) {
            return "";
        }
        if (delta.pct === null) {
            return "new";
        }
        return `${delta.dir === "up" ? "↑" : delta.dir === "down" ? "↓" : "–"} ${delta.pct}%`;
    }

    deltaClass(delta, upIsGood) {
        if (!delta || delta.dir === "flat") {
            return "o_shopee_delta_flat";
        }
        return (delta.dir === "up") === upIsGood ? "o_shopee_delta_good" : "o_shopee_delta_bad";
    }

    // ---- orders ----
    get orderStatuses() {
        let fb = 0;
        return this.state.data.orders.by_status.map((row) => {
            const meta = STATUS_META[row.status] || {
                label: prettify(row.status),
                color: FALLBACK_COLORS[fb++ % FALLBACK_COLORS.length],
            };
            return { ...row, label: meta.label, color: meta.color };
        });
    }

    get orderDonut() {
        return this.donut(
            this.orderStatuses.map((s) => ({ value: s.count, color: s.color })),
        );
    }

    donut(items) {
        const total = items.reduce((a, i) => a + i.value, 0);
        let offset = 0;
        return items
            .filter((i) => i.value > 0 && total > 0)
            .map((i) => {
                const len = (i.value / total) * DONUT_C;
                const seg = {
                    color: i.color,
                    dash: `${len.toFixed(2)} ${(DONUT_C - len).toFixed(2)}`,
                    offset: (-offset).toFixed(2),
                };
                offset += len;
                return seg;
            });
    }

    get orderDeltaText() {
        return this.deltaText(this.state.data.orders.delta);
    }

    get orderDeltaClass() {
        return this.deltaClass(this.state.data.orders.delta, true);
    }

    get dateLabels() {
        const dates = this.state.data.dates;
        const fmt = (iso) => {
            const d = new Date(iso + "T00:00:00");
            return d.toLocaleDateString("en-US", { month: "short", day: "2-digit" });
        };
        return dates.map((d, i) => ({ x: i, text: fmt(d) }));
    }

    get orderTrend() {
        const series = this.state.data.orders.trend;
        const W = 420, H = 150;
        const max = Math.max(...series, 1);
        const nice = Math.max(Math.ceil(max / 4 / 10) * 10, 1) * 4;
        const step = series.length > 1 ? W / (series.length - 1) : W;
        const pts = series.map((v, i) => [i * step, H - (v / nice) * H]);
        const line = pts.map((p, i) => `${i ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(" ");
        return {
            W, H, line, area: `${line} L${W},${H} L0,${H} Z`, pts,
            grid: [0, 1, 2, 3, 4].map((i) => ({ y: H - (i / 4) * H, label: Math.round((nice * i) / 4) })),
            labels: this.dateLabels.map((l) => ({ ...l, x: l.x * step })),
        };
    }

    // ---- sync health ----
    get syncDonut() {
        const s = this.state.data.sync;
        return this.donut([
            { value: s.ok, color: "#22a06b" },
            { value: s.failed, color: "#ef4444" },
        ]);
    }

    get syncBars() {
        const { ok_series: ok, failed_series: fail } = this.state.data.sync;
        const W = 420, H = 140, n = ok.length;
        const max = Math.max(...ok.map((v, i) => v + fail[i]), 1);
        const slot = W / n, bw = slot * 0.5;
        return {
            W, H,
            bars: ok.map((v, i) => {
                const okH = (v / max) * H, failH = (fail[i] / max) * H;
                const x = i * slot + (slot - bw) / 2;
                return { x, bw, okH, okY: H - okH, failH, failY: H - okH - failH };
            }),
            labels: this.dateLabels.map((l) => ({ ...l, x: l.x * slot + slot / 2 })),
        };
    }

    // ---- misc ----
    statusLabel(status) {
        return { active: "Active", expired: "Token expired", no_token: "Not connected" }[status] || status;
    }

    async _open(xmlid, domain) {
        const act = await this.action.loadAction(xmlid);
        await this.action.doAction({ ...act, domain, context: {} });
    }

    openTile(tile) {
        return this._open(tile.action, tile.domain);
    }

    openOrders() {
        const o = this.state.data.orders;
        return this._open(o.action, o.domain);
    }

    openSync() {
        const s = this.state.data.sync;
        return this._open(s.action, s.domain);
    }

    openCrons() {
        return this.action.doAction("base.ir_cron_act");
    }
}

registry.category("actions").add("shopee_connector.dashboard", ShopeeDashboard);
