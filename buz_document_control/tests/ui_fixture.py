"""Manual browser-test fixture; run with `odoo shell` ONLY on a fresh MOG_TEST_DOCUMENT_UI database.

Not imported by the Odoo test suite. Credentials are randomly generated for each run.
Never run this file against MOG_DEV or a production database.
"""
import base64
import json
import secrets
from io import BytesIO

from odoo import fields
from odoo.tools.pdf import PdfFileWriter


def seed(env):
    if not env.cr.dbname.startswith("MOG_TEST_DOCUMENT_UI_"):
        raise RuntimeError("UI fixtures require a dedicated MOG_TEST_DOCUMENT_UI_ database")
    users = {}
    for role, group in [("reader", "group_document_user"), ("confidential", "group_document_confidential_user"),
                        ("manager", "group_document_manager")]:
        password = secrets.token_urlsafe(24)
        login = "bdc_ui_" + role
        values = {"name": "Document " + role.title(), "login": login, "password": password,
                  "groups_id": [fields.Command.set([env.ref("base.group_user").id, env.ref("buz_document_control." + group).id])]}
        user = env["res.users"].search([("login", "=", login)])
        if user:
            user.write(values)
        else:
            user = env["res.users"].create(values)
        users[role] = {"id": user.id, "login": login, "password": password}
    manager = env["res.users"].browse(users["manager"]["id"])
    department = env["hr.department"].create({"name": "Information Technology"})
    group = env["res.groups"].create({"name": "IT Department — UI test"})
    env["hr.employee"].create({"name": "Document Reader", "user_id": users["reader"]["id"], "department_id": department.id})
    output = BytesIO()
    pdf = PdfFileWriter()
    for _index in range(3):
        pdf.addBlankPage(595, 842)
    pdf.write(output)
    original = base64.b64encode(output.getvalue())
    docs = {}
    examples = [
        ("QP-ITD-01", "ระเบียบปฏิบัติงานสารสนเทศ", "QP", "general", 12),
        ("WI-ITD-02", "คู่มือการใช้งานระบบเอกสาร", "WI", "general", 90),
        ("FM-HR-01", "แบบฟอร์มคำขอฝึกอบรม", "FM", "general", 45),
        ("QM-QA-01", "คู่มือระบบบริหารคุณภาพ", "QM", "general", -3),
        ("SD-ITD-01", "มาตรฐานการจัดเก็บข้อมูล", "SD", "general", 60),
        ("QP-RESTRICTED-01", "IT Infrastructure — Restricted", "QP", "restricted", 60),
        ("QP-CONFIDENTIAL-01", "Company Strategy — Confidential", "QP", "confidential", 60),
        ("FM-FIN-02", "แบบฟอร์มขออนุมัติค่าใช้จ่าย", "FM", "general", 60),
        ("WI-ITD-03", "การจัดการบัญชีผู้ใช้งาน", "WI", "general", 60),
    ]
    for number, name, type_code, security, days in examples:
        doc = env["buz.document"].with_user(manager).create({
            "document_no": number, "name": name, "department_id": department.id,
            "document_type_id": env["buz.document.type"].search([("code", "=", type_code)], limit=1).id,
            "security_level": security, "description": "เอกสารควบคุมสำหรับการปฏิบัติงานภายในบริษัท",
            "allowed_group_ids": [fields.Command.set(group.ids)] if security == "restricted" else [],
        })
        revision = env["buz.document.revision"].with_user(manager).create({
            "document_id": doc.id, "revision": "04", "effective_date": "2026-09-01",
            "review_date": fields.Date.add(fields.Date.today(), days=days),
            "original_file": original, "original_filename": number + "_Rev04.pdf",
            "change_description": "ปรับปรุงขั้นตอนปฏิบัติงานและทบทวนผู้รับผิดชอบ",
        })
        revision.action_publish()
        docs[number] = {"id": doc.id, "revision_id": revision.id}
    main = env["buz.document"].browse(docs["QP-ITD-01"]["id"])
    old = env["buz.document.revision"].with_user(manager).create({
        "document_id": main.id, "revision": "03", "change_description": "Previous approved procedure", "state": "obsolete",
        "original_file": original, "original_filename": "QP-ITD-01_Rev03.pdf",
    })
    docs["obsolete"] = {"revision_id": old.id}
    env["buz.document.revision"].with_user(manager).create({"document_id": main.id, "revision": "05", "state": "review", "change_description": "Pending approval"})
    env["buz.document"].with_user(manager).create({"document_no": "QP-DRAFT-01", "name": "New procedure draft"})
    failed = env["buz.document.revision"].browse(docs["SD-ITD-01"]["revision_id"])
    failed.with_user(manager).write({"preview_status": "failed", "preview_file": False})
    env["ir.config_parameter"].sudo().set_param("buz_document_control.enable_download_log", True)
    env.cr.commit()
    return {"db": env.cr.dbname, "users": users, "documents": docs,
            "action_id": env.ref("buz_document_control.action_document_center").id,
            "menu_id": env.ref("buz_document_control.menu_document_center").id,
            "pdf": original.decode()}


if "env" in globals():
    print("BDC_UI_FIXTURE=" + json.dumps(seed(env)))
