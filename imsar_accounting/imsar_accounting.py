from openerp import models, fields, api, _


class account_account_type(models.Model):
    _inherit = 'account.account.type'

    active = fields.Boolean(string='Active', default=True)