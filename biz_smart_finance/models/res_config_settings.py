# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # key แยกของโมดูลเอง (ผู้ใช้เลือก) — ไม่ reuse ai_pm_flow.* ของ biz_smart_project
    bsf_openrouter_api_key = fields.Char(
        string="OpenRouter API Key",
        config_parameter="biz_smart_finance.openrouter_api_key",
    )
    bsf_ai_model = fields.Char(
        string="AI Model",
        default="anthropic/claude-opus-5",
        config_parameter="biz_smart_finance.ai_model",
        help="OpenRouter model slug เช่น anthropic/claude-opus-5",
    )
    # ระบบภายนอก (Inventory / Ratios) — endpoint กลางของกลุ่ม แยกบริษัทด้วย
    # ext_company_code ใน biz.smart.finance.config
    bsf_ext_endpoint = fields.Char(
        string="External Source Endpoint",
        config_parameter="biz_smart_finance.ext_endpoint",
        help="URL สำหรับดึงตัวเลข inventory/งบการเงินจากระบบภายนอก "
             "(GET ?company=..&as_of=YYYY-MM-DD)",
    )
    bsf_ext_api_key = fields.Char(
        string="External Source API Key",
        config_parameter="biz_smart_finance.ext_api_key",
    )
    # สกุลนำเสนอของ CFO Cockpit — เว้นว่าง = ใช้สกุลของบริษัทอ้างอิง
    bsf_presentation_currency_id = fields.Many2one(
        "res.currency", string="สกุลเงินนำเสนอ (CFO Cockpit)",
        config_parameter="biz_smart_finance.presentation_currency_id",
        help="บังคับให้ทั้งจอแสดงเป็นสกุลนี้ (แปลงด้วยอัตราปิด ณ วันที่เลือก) "
             "เว้นว่างไว้จะใช้สกุลเงินของบริษัทที่เลือกในตัวกรอง",
    )
