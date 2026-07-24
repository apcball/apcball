/** @odoo-module **/
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class SopCopilot extends Component {
    static template = "mogen_sop_ai.Copilot";
    setup() {
        this.orm = useService("orm"); this.action = useService("action");
        this.state = useState({question: "", conversationId: false, messages: [], loading: false, error: false});
        onWillStart(() => this.load());
    }
    get context() { return this.props.action?.context || {}; }
    async load() { if (this.state.conversationId) { const data = await this.orm.call("mogen.sop.ai.copilot.service", "get_conversation", [this.state.conversationId]); this.state.messages = data.messages; } }
    async ask() { if (!this.state.question.trim() || this.state.loading) return; this.state.loading = true; this.state.error = false; try { const result = await this.orm.call("mogen.sop.ai.copilot.service", "ask", [this.state.question, this.state.conversationId, this.context.sop_plan_id || false, this.context.scenario_id || false, this.context.dashboard_filters || {}]); this.state.conversationId = result.conversation_id; this.state.question = ""; await this.load(); } catch (error) { this.state.error = error.message || "Unable to queue Copilot analysis."; } finally { this.state.loading = false; } }
    async clear() { if (!this.state.conversationId) return; await this.orm.call("mogen.sop.ai.conversation", "action_clear", [[this.state.conversationId]]); this.state.conversationId = false; this.state.messages = []; }
    openSource(source) { this.action.doAction({type: "ir.actions.act_window", res_model: source.model, res_id: source.id, views: [[false, "form"]], target: "current"}); }
}
registry.category("actions").add("mogen_sop_ai.copilot", SopCopilot);
