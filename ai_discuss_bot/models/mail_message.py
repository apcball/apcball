# -*- coding: utf-8 -*-
from collections import defaultdict
import json
import logging
import re

try:
    import requests
except ImportError:
    requests = None

from html import unescape

from markupsafe import escape, Markup

from odoo import api, models, _
from odoo.exceptions import UserError
from odoo.tools import float_round

_logger = logging.getLogger(__name__)


THAI_HINT_RE = re.compile(r'[฀-๿]')
HTML_TAG_RE = re.compile(r'<[^>]+>')


class MailMessage(models.Model):
    _inherit = 'mail.message'

    @api.model_create_multi
    def create(self, vals_list):
        messages = super().create(vals_list)
        if self.env.context.get('skip_ai_discuss_bot'):
            return messages
        for message in messages:
            message._ai_discuss_bot_handle_message()
        return messages

    def _ai_discuss_bot_handle_message(self):
        self.ensure_one()
        _logger.debug("AI BOT: handle_message called — model=%s res_id=%s type=%s author=%s",
                      self.model, self.res_id, self.message_type,
                      self.author_id.name if self.author_id else 'none')

        if self.model != 'discuss.channel' or not self.res_id:
            _logger.debug("AI BOT: skip — not a discuss.channel message")
            return
        if self.message_type not in ('comment', 'email'):
            _logger.debug("AI BOT: skip — message_type=%s", self.message_type)
            return
        if self.env.context.get('skip_ai_discuss_bot'):
            _logger.debug("AI BOT: skip — context skip flag set")
            return

        channel = self.env['discuss.channel'].sudo().browse(self.res_id)
        if not channel.exists():
            _logger.debug("AI BOT: skip — channel %s does not exist", self.res_id)
            return
        if not channel.is_ai_bot_channel:
            _logger.debug("AI BOT: skip — channel '%s' (id=%s) is NOT an AI bot channel",
                          channel.name, channel.id)
            return

        bot_partner = channel.ai_bot_partner_id
        if bot_partner and self.author_id and self.author_id.id == bot_partner.id:
            _logger.debug("AI BOT: skip — message is from the bot itself")
            return

        query = self._ai_discuss_bot_extract_query(channel)
        _logger.debug("AI BOT: extracted query = %r", query)
        if not query:
            _logger.debug("AI BOT: skip — empty query")
            return

        _logger.info("AI BOT: generating response for query=%r in channel='%s'", query, channel.name)
        try:
            response = self._ai_discuss_bot_generate_response(query)
        except Exception as e:
            _logger.error("AI BOT: generate_response raised: %s", e, exc_info=True)
            return

        if not response:
            _logger.warning("AI BOT: got empty response, not posting")
            return

        _logger.info("AI BOT: posting response to channel '%s'", channel.name)
        try:
            channel.sudo().with_context(skip_ai_discuss_bot=True).message_post(
                body=Markup(response),
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                author_id=bot_partner.id if bot_partner else False,
            )
        except Exception as e:
            _logger.error("AI BOT: message_post failed: %s", e, exc_info=True)

    def _ai_discuss_bot_extract_query(self, channel):
        self.ensure_one()
        body = self.body or ''
        text = HTML_TAG_RE.sub(' ', body)
        text = unescape(text)
        text = re.sub(r'\s+', ' ', text).strip()
        if not text:
            return ''
        bot_name = channel.ai_bot_partner_id.name if channel.ai_bot_partner_id else 'AI Bot'
        text = re.sub(rf'@?{re.escape(bot_name)}', ' ', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _ai_discuss_bot_generate_response(self, query):
        # Try AI first if active config exists
        config = self.env['ai.discuss.config'].get_active_config()
        if config:
            try:
                response = self._ai_discuss_bot_call_openai(query, config)
                if response:
                    config.increment_stats(success=True)
                    return response
                else:
                    config.increment_stats(success=False)
                    _logger.warning("AI returned empty response, falling back to keyword matching")
            except Exception as e:
                config.increment_stats(success=False)
                _logger.error("AI API call failed: %s, falling back to keyword matching", e)

        # Fallback to keyword matching
        return self._ai_discuss_bot_generate_response_keyword(query)

    def _ai_discuss_bot_call_openai(self, query, config):
        """Call AI API to generate a response."""
        self.ensure_one()

        # Prepare messages
        messages = [
            {"role": "system", "content": config.system_prompt},
            {"role": "user", "content": query},
        ]

        # Prepare payload
        payload = {
            "model": config.model_name,
            "messages": messages,
            "max_tokens": config.max_tokens,
            "temperature": config.temperature,
        }

        # Build URL
        url = config.base_url.rstrip('/') + '/chat/completions'

        # Make request with retry
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {config.api_key}',
        }

        for attempt in range(config.retry_count):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=config.timeout,
                )
                response.raise_for_status()

                data = response.json()

                # Extract response content
                if 'choices' in data and len(data['choices']) > 0:
                    content = data['choices'][0].get('message', {}).get('content', '')
                    if content:
                        # Convert markdown to HTML if needed
                        html_content = self._ai_discuss_bot_markdown_to_html(content)
                        return html_content

                _logger.warning("AI API returned unexpected response format")
                return None

            except requests.exceptions.Timeout:
                _logger.warning("AI API timeout on attempt %d/%d", attempt + 1, config.retry_count)
                if attempt == config.retry_count - 1:
                    raise
            except requests.exceptions.RequestException as e:
                _logger.error("AI API request failed: %s", e)
                raise
            except json.JSONDecodeError as e:
                _logger.error("AI API response JSON decode failed: %s", e)
                raise

        return None

    def _ai_discuss_bot_markdown_to_html(self, text):
        """Simple markdown to HTML conversion."""
        if not text:
            return ''

        lines = text.split('\n')
        html_lines = []

        in_list = False
        for line in lines:
            line = line.strip()

            # Empty line
            if not line:
                if in_list:
                    html_lines.append(Markup('</ul>'))
                    in_list = False
                continue

            # List item
            if line.startswith(('-', '*', '+')):
                if not in_list:
                    html_lines.append(Markup('<ul>'))
                    in_list = True
                item_text = line[1:].strip()
                html_lines.append(Markup('<li>%s</li>') % item_text)
                continue

            # End list if we were in one
            if in_list:
                html_lines.append(Markup('</ul>'))
                in_list = False

            # Escape text first, then apply bold markdown safely
            safe_line = escape(line)
            safe_line = Markup(re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', str(safe_line)))

            # Regular paragraph
            html_lines.append(Markup('<p>%s</p>') % safe_line)

        if in_list:
            html_lines.append(Markup('</ul>'))

        return Markup('').join(html_lines)

    def _ai_discuss_bot_generate_response_keyword(self, query):
        """Fallback keyword matching response."""
        intent = self._ai_discuss_bot_detect_intent(query)
        language = 'th' if THAI_HINT_RE.search(query or '') else 'en'
        if intent == 'stock':
            stock_lines = self._ai_discuss_bot_search_stock(query)
            title = '📦 Stock Results:' if language == 'en' else '📦 ผลการค้นหาสต็อก:'
            if stock_lines:
                return self._ai_discuss_bot_wrap_response(title, stock_lines)
            no_result = 'No matching products found.' if language == 'en' else 'ไม่พบสินค้าที่ตรงกับคำค้น'
            return self._ai_discuss_bot_wrap_response(title, [no_result])
        if intent == 'document':
            doc_lines = self._ai_discuss_bot_search_documents(query)
            title = '📄 Document Results:' if language == 'en' else '📄 ผลการค้นหาเอกสาร:'
            if doc_lines:
                return self._ai_discuss_bot_wrap_response(title, doc_lines)
            no_result = 'No matching documents found.' if language == 'en' else 'ไม่พบเอกสารที่ตรงกับคำค้น'
            return self._ai_discuss_bot_wrap_response(title, [no_result])
        title = 'AI Bot'
        guidance = 'Try asking for stock or document numbers.' if language == 'en' else 'ลองถามเกี่ยวกับสต็อกหรือเลขที่เอกสาร'
        return self._ai_discuss_bot_wrap_response(title, [guidance])

    def _ai_discuss_bot_detect_intent(self, query):
        q = (query or '').lower()
        document_keywords = [
            'so', 'po', 'inv', 'invoice', 'dn', 'delivery', 'document', 'number', 'เลขที่', 'เอกสาร',
            'หาเลขที่', 'ค้นหา', 'บิล', 'ใบสั่งขาย', 'ใบสั่งซื้อ', 'ใบแจ้งหนี้', 'ใบส่งของ',
        ]
        stock_keywords = [
            'stock', 'quantity', 'qty', 'inventory', 'on hand', 'available',
            'กี่', 'ชิ้น', 'คงเหลือ', 'สต็อก', 'จำนวน', 'เหลือ',
        ]
        if any(keyword in q for keyword in document_keywords):
            return 'document'
        if any(keyword in q for keyword in stock_keywords):
            return 'stock'
        return 'general'

    def _ai_discuss_bot_search_stock(self, query):
        Product = self.env['product.product'].sudo()
        cleaned = self._ai_discuss_bot_clean_query(query, intent='stock')
        search_terms = self._ai_discuss_bot_tokenize(cleaned)
        candidates = Product.browse()
        for term in search_terms:
            if len(term) < 2:
                continue
            candidates |= Product.search([
                '|', ('name', 'ilike', term), ('default_code', 'ilike', term),
            ], limit=20)
        if not candidates and cleaned:
            candidates = Product.search([
                '|', ('name', 'ilike', cleaned), ('default_code', 'ilike', cleaned),
            ], limit=20)
        if not candidates:
            return []

        Quant = self.env['stock.quant'].sudo()
        quants = Quant.search([
            ('product_id', 'in', candidates.ids),
            ('quantity', '!=', 0),
        ])
        grouped = defaultdict(lambda: defaultdict(float))
        for quant in quants:
            warehouse_name = self._ai_discuss_bot_get_warehouse_name(quant.location_id)
            grouped[quant.product_id.id][warehouse_name] += quant.quantity

        lines = []
        for product in candidates.sorted(lambda p: (p.default_code or '', p.display_name or '')):
            warehouses = grouped.get(product.id, {})
            if not warehouses:
                continue
            for warehouse_name, qty in sorted(warehouses.items()):
                qty_display = float_round(qty, precision_rounding=product.uom_id.rounding if product.uom_id else 0.01)
                uom = product.uom_name or ''
                suffix = f' {uom}' if uom else ''
                lines.append(
                    f"• {escape(product.display_name)} ({escape(warehouse_name)}): {qty_display}{suffix}"
                )
        return lines

    def _ai_discuss_bot_get_warehouse_name(self, location):
        if not location:
            return _('Unknown Warehouse')
        if location._fields.get('warehouse_id') and location.warehouse_id:
            return location.warehouse_id.display_name
        if location.location_id:
            return self._ai_discuss_bot_get_warehouse_name(location.location_id)
        return location.display_name or _('Unknown Warehouse')

    def _ai_discuss_bot_search_documents(self, query):
        cleaned = self._ai_discuss_bot_clean_query(query, intent='document')
        search_terms = self._ai_discuss_bot_tokenize(cleaned)
        config = [
            ('sale.order', 'SO', 'date_order', 'state', ['name', 'partner_id.name', 'client_order_ref']),
            ('purchase.order', 'PO', 'date_order', 'state', ['name', 'partner_id.name', 'partner_ref']),
            ('account.move', 'INV', 'invoice_date', 'state', ['name', 'partner_id.name', 'payment_reference', 'ref']),
            ('stock.picking', 'DN', 'scheduled_date', 'state', ['name', 'partner_id.name', 'origin']),
        ]
        lines = []
        for model_name, doc_label, date_field, state_field, fields_to_match in config:
            if model_name not in self.env.registry.models:
                continue
            Model = self.env[model_name].sudo()
            records = Model.browse()
            if search_terms:
                for term in search_terms:
                    if len(term) < 2:
                        continue
                    records |= Model.search(self._ai_discuss_bot_build_or_domain(fields_to_match, term), limit=10)
            if not records and cleaned:
                records = Model.search(self._ai_discuss_bot_build_or_domain(fields_to_match, cleaned), limit=10)
            for record in records.sorted(lambda r: (getattr(r, date_field, False) or False, r.display_name or '')):
                partner = getattr(record, 'partner_id', False)
                record_date = getattr(record, date_field, False)
                state_value = getattr(record, state_field, '')
                state_field_obj = record._fields.get(state_field)
                if state_field_obj and getattr(state_field_obj, 'selection', None):
                    state_value = dict(state_field_obj.selection).get(state_value, state_value)
                date_text = str(record_date) if record_date else ''
                lines.append(
                    f"• {escape(doc_label)} {escape(record.name or record.display_name or '')} - {escape(partner.display_name if partner else '')} - {escape(date_text)} - {escape(state_value)}"
                )
        return lines

    def _ai_discuss_bot_build_or_domain(self, fields_to_match, term):
        domain = []
        for idx, field in enumerate(fields_to_match):
            if idx:
                domain.insert(0, '|')
            domain.append((field, 'ilike', term))
        return domain

    def _ai_discuss_bot_wrap_response(self, title, lines):
        items = Markup('').join(Markup('<li>%s</li>') % line for line in lines)
        return Markup('<p><strong>%s</strong></p><ul>%s</ul>') % (title, items)

    def _ai_discuss_bot_clean_query(self, query, intent):
        q = (query or '').lower()
        if intent == 'stock':
            stopwords = [
                'stock', 'quantity', 'qty', 'inventory', 'on', 'hand', 'available', 'check', 'please', 'how', 'many',
                'สินค้า', 'มีกี่ชิ้น', 'กี่ชิ้น', 'คงเหลือ', 'สต็อก', 'จำนวน', 'เหลือ', 'เช็ค', 'ตรวจ',
            ]
        else:
            stopwords = [
                'find', 'search', 'document', 'number', 'invoice', 'bill', 'order', 'เลขที่', 'เอกสาร', 'หาเลขที่',
                'ค้นหา', 'เลข', 'so', 'po', 'inv', 'dn',
            ]
        for word in stopwords:
            if ' ' in word or any(ord(ch) > 127 for ch in word):
                q = q.replace(word, ' ')
            else:
                q = re.sub(rf'\b{re.escape(word)}\b', ' ', q)
        q = re.sub(r'[^\w฀-๿\-/\. ]+', ' ', q)
        q = re.sub(r'\s+', ' ', q).strip()
        return q

    def _ai_discuss_bot_tokenize(self, query):
        if not query:
            return []
        tokens = []
        for token in re.split(r'\s+', query):
            token = token.strip().strip(".,()[]{}:;\"'")
            if token:
                tokens.append(token)
        if len(query) >= 3 and query not in tokens:
            tokens.insert(0, query)
        return tokens[:6]
