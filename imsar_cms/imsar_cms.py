from openerp import models, fields, api, _


class res_partner(models.Model):
    _inherit = "res.partner"

    manager_id = fields.Many2one('res.partner', 'Manager')

