import logging
import re

from odoo import models

_logger = logging.getLogger(__name__)


class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    def _safe_next_by_code(self, sequence_code, model_name, prefix=None):
        """Get next sequence value, auto-recover if out of sync with existing records.

        Uses a Postgres advisory lock keyed on the sequence id so concurrent
        callers serialize instead of racing on number_next.

        Args:
            sequence_code: ir.sequence code (e.g. 'pos.lite.order')
            model_name: model _name for searching existing records
            prefix: optional prefix to strip when parsing the max number

        Returns:
            Next unique sequence value.
        """
        name = self.next_by_code(sequence_code) or '/'
        if name == '/':
            return name

        target_model = self.env[model_name]
        if not target_model.search_count([('name', '=', name)]):
            return name

        # Sequence out of sync — recover under an advisory lock so concurrent
        # creates don't both pick the same recovered number_next.
        sequence = self.search([('code', '=', sequence_code)], limit=1)
        if not sequence:
            return name

        self.env.cr.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (sequence_code,))
        last = target_model.search([], order='name desc', limit=1)
        if last and last.name:
            # Extract trailing digits so formats like 'POS-2026-0001' recover too.
            digits = re.findall(r'\d+', last.name)
            if digits:
                try:
                    num = int(digits[-1])
                    sequence.number_next = num + 1
                    name = self.next_by_code(sequence_code) or '/'
                except ValueError:
                    _logger.warning("Sequence %s recovery failed for %s", sequence_code, last.name)
        return name
