from openerp import models, fields, api, _


class account_account_type(models.Model):
    _inherit = 'account.account.type'

    active = fields.Boolean(string='Active', default=True)


class account_budget_post(models.Model):
    _inherit = 'account.budget.post'

    overhead_rate = fields.Float(string='Overhead Rate', default=0.0)