from openerp import models, fields, api, _

class crossovered_budget_lines(models.Model):
    _inherit = 'crossovered.budget.lines'

    date_from = fields.Date(related='crossovered_budget_id.date_from', string='Start Date', readonly=True)
    date_to =fields.Date(related='crossovered_budget_id.date_to', string='End Date', readonly=True)
    remaining_amount = fields.Float(string="Remaining", compute='_compute', store=False, readonly=True)
    loaded_amount = fields.Float(string="Loaded", compute='_compute', store=False, readonly=True)

    @api.one
    def _compute(self):
        # Since we mostly track expenses, we're reversing the sign on debits/credits
        # This means revenue budgets will need to be computed as negatives, but that's the CFO's preference
        self.remaining_amount = self.planned_amount - (-1.0 * self.practical_amount)
        self.loaded_amount = self.practical_amount + (self.practical_amount * self.general_budget_id.overhead_rate)

    @api.multi
    def _get_all_analytics(self):
        analytics = self.analytic_account_id.get_all_children()
        analytic_lines = self.env['account.analytic.line'].search([
            ('account_id','in',analytics.ids),
            ('general_account_id','in',self.general_budget_id.account_ids.ids),
            ('date','>=',self.date_from),
            ('date','<=',self.date_to),
        ])
        return analytic_lines

    @api.multi
    def get_analytic_lines(self):
        item_ids=[]
        if self.analytic_account_id:
            item_ids = self._get_all_analytics().ids

        return {
            'name': _('Analytic Account Lines'),
            'view_type': 'form',
            "view_mode": 'tree,form',
            'res_model': 'account.analytic.line',
            'type': 'ir.actions.act_window',
            'domain': [('id','=',item_ids)],
        }

    @api.multi
    def _prac_amt(self):
        result = 0.0
        if self.analytic_account_id:
            analytic_lines = self._get_all_analytics()
            result += sum(a.amount for a in analytic_lines)
        return {self.id: result}
