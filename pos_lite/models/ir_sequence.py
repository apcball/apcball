from odoo import models


class IrSequence(models.Model):
    _inherit = 'ir.sequence'

    def _safe_next_by_code(self, sequence_code, model_name, prefix=None):
        """Get next sequence value, auto-recover if out of sync with existing records.

        Args:
            sequence_code: ir.sequence code (e.g. 'pos.lite.order')
            model_name: model _name for searching existing records (e.g. 'pos.lite.order')
            prefix: optional prefix to strip when parsing max number (e.g. 'POS')

        Returns:
            Next unique sequence value.
        """
        name = self.next_by_code(sequence_code) or '/'
        if name == '/':
            return name

        target_model = self.env[model_name]
        if not target_model.search_count([('name', '=', name)]):
            return name

        # Sequence out of sync — find max name and recover
        last = target_model.search([], order='name desc', limit=1)
        if last and last.name and prefix:
            try:
                num = int(last.name.replace(prefix, ''))
                sequence = self.search([('code', '=', sequence_code)], limit=1)
                if sequence:
                    sequence.number_next = num + 1
                name = self.next_by_code(sequence_code) or '/'
            except ValueError:
                pass

        return name
