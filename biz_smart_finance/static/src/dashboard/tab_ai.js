/** @odoo-module **/

import { onWillStart, useRef, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { BsfTab } from "./bsf_widgets";

/**
 * แท็บ AI Copilot — แชทถาม-ตอบข้อมูลการเงิน + สร้างรายงาน CFO +
 * ให้ AI เสนอความเสี่ยง (manager) ทุกคำขอส่งแค่ filters — server ดึงข้อมูลเอง
 */
export class BsfTabAi extends BsfTab {
    static template = "biz_smart_finance.TabAi";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.ui = useState({
            conversations: [],
            activeId: false,
            activeName: "",
            messages: [],
            sending: false,
            suggestions: [],
            reports: [],
            reportView: null,
            generatingReport: false,
            suggesting: false,
        });
        // ช่องพิมพ์ไม่ผูกกับ state — t-model ยิง re-render ทั้งแท็บ (รายการ
        // สนทนา, ข้อความ, ชิปคำถาม, เนื้อรายงาน) **ทุกครั้งที่กดแป้น**
        this.inputRef = useRef("chatInput");
        this.draft = "";
        onWillStart(() => this.refreshLists());
    }

    get configured() {
        return !!(this.props.data.ai && this.props.data.ai.configured);
    }

    get isManager() {
        return !!(this.props.data.ai && this.props.data.ai.is_manager);
    }

    get filters() {
        const f = this.props.data.filters;
        return {
            company_id: f.company_id,
            year: f.year,
            month: f.month,
            scenario: f.scenario,
        };
    }

    async refreshLists() {
        try {
            // สองลิสต์ไม่พึ่งกัน — ยิงขนานแทนการรอทีละใบ (เดิมสอง round-trip
            // ต่อเนื่องกันก่อนแท็บจะวาดครั้งแรก)
            const [conversations, reports] = await Promise.all([
                this.orm.call(
                    "biz.smart.finance.conversation", "list_conversations", []),
                this.orm.call("biz.smart.finance.report", "list_reports", []),
            ]);
            this.ui.conversations = conversations;
            this.ui.reports = reports;
        } catch {
            // list ล้มเหลว (เช่นสิทธิ์) — ปล่อยว่าง แชทยังพยายามใช้ได้
        }
    }

    notifyError(error) {
        this.notification.add(
            (error.data && error.data.message) || String(error),
            { type: "danger" });
    }

    // ---------------- chat ----------------
    onInput(ev) {
        this.draft = ev.target.value;
    }

    /** ล้างช่องพิมพ์ทั้งค่าใน DOM และร่างที่จำไว้ (ไม่ผ่าน state จึงต้องทำเอง) */
    clearDraft() {
        this.draft = "";
        if (this.inputRef.el) {
            this.inputRef.el.value = "";
        }
    }

    async send() {
        const text = (this.draft || "").trim();
        if (!text || this.ui.sending) {
            return;
        }
        this.clearDraft();
        this.ui.sending = true;
        this.ui.reportView = null;
        this.ui.messages.push({ role: "user", content: text });
        try {
            let result;
            if (this.ui.activeId) {
                result = await this.orm.call(
                    "biz.smart.finance.conversation", "chat_send",
                    [[this.ui.activeId], text, this.filters]);
            } else {
                result = await this.orm.call(
                    "biz.smart.finance.conversation", "create_and_send",
                    [text, this.filters]);
            }
            this.ui.activeId = result.conversation_id;
            this.ui.activeName = result.name;
            this.ui.messages.push({ role: "assistant", content: result.answer });
            this.ui.suggestions = result.suggestions || [];
            await this.refreshLists();
        } catch (error) {
            this.ui.messages.pop();
            this.notifyError(error);
        } finally {
            this.ui.sending = false;
        }
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    askSuggestion(text) {
        this.draft = text;
        this.send();
    }

    async openConversation(conv) {
        try {
            this.ui.messages = await this.orm.call(
                "biz.smart.finance.conversation", "get_messages", [[conv.id]]);
            this.ui.activeId = conv.id;
            this.ui.activeName = conv.name;
            this.ui.reportView = null;
            this.ui.suggestions = [];
        } catch (error) {
            this.notifyError(error);
        }
    }

    newConversation() {
        this.ui.activeId = false;
        this.ui.activeName = "";
        this.ui.messages = [];
        this.ui.suggestions = [];
        this.ui.reportView = null;
    }

    // ---------------- report ----------------
    async generateReport() {
        if (this.ui.generatingReport) {
            return;
        }
        this.ui.generatingReport = true;
        try {
            const result = await this.orm.call(
                "biz.smart.finance.report", "generate", [this.filters]);
            if (result.state === "error") {
                this.notification.add(result.error || "สร้างรายงานไม่สำเร็จ",
                    { type: "danger" });
            } else {
                this.ui.reportView = result;
            }
            await this.refreshLists();
        } catch (error) {
            this.notifyError(error);
        } finally {
            this.ui.generatingReport = false;
        }
    }

    async openReport(report) {
        try {
            this.ui.reportView = await this.orm.call(
                "biz.smart.finance.report", "get_content", [[report.id]]);
        } catch (error) {
            this.notifyError(error);
        }
    }

    /** mini markdown: หัวข้อ #/## กับ bullet -,*,• เท่านั้น (ตัด ** ทิ้ง)
     *  จำผลไว้ต่อเนื้อรายงานหนึ่งฉบับ — เป็น getter ที่ split + regex ทุกบรรทัด
     *  จึงถูกรันใหม่ทั้งฉบับทุกครั้งที่แท็บ re-render (รวมถึงตอนพิมพ์แชท) */
    get reportLines() {
        const content = (this.ui.reportView && this.ui.reportView.content) || "";
        return this.memoChart("reportLines", [content], () =>
            this._parseReport(content));
    }

    _parseReport(content) {
        const lines = [];
        for (const raw of content.split("\n")) {
            const line = raw.replace(/\*\*/g, "").trim();
            if (!line) {
                continue;
            }
            if (line.startsWith("## ")) {
                lines.push({ kind: "h2", text: line.slice(3) });
            } else if (line.startsWith("# ")) {
                lines.push({ kind: "h1", text: line.slice(2) });
            } else if (line.startsWith("### ")) {
                lines.push({ kind: "h2", text: line.slice(4) });
            } else if (/^[-*•]\s+/.test(line)) {
                lines.push({ kind: "li", text: line.replace(/^[-*•]\s+/, "") });
            } else {
                lines.push({ kind: "p", text: line });
            }
        }
        return lines;
    }

    // ---------------- risk suggestions ----------------
    async suggestRisks() {
        if (this.ui.suggesting) {
            return;
        }
        this.ui.suggesting = true;
        try {
            const result = await this.orm.call(
                "biz.smart.finance.ai", "suggest_risks", [this.filters]);
            this.notification.add(
                `AI สร้างความเสี่ยง (ร่าง) ${result.created} รายการ` +
                (result.skipped ? ` ข้ามซ้ำ ${result.skipped}` : ""),
                { type: "success" });
        } catch (error) {
            this.notifyError(error);
        } finally {
            this.ui.suggesting = false;
        }
    }

    openRiskRegister() {
        this.openList("Risk Register", "biz.smart.finance.risk", []);
    }
}
