from openerp import models, fields, api, _
from openerp.exceptions import Warning


class mrp_production(models.Model):
    _inherit = 'mrp.production'

    account_routing_id = fields.Many2one('account.routing', 'Category', required=True, readonly=False,
                                 states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True,)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True,)

    @api.onchange('account_routing_id')
    def onchange_routing_id(self):
        self.routing_line_id = ''
        self.routing_subrouting_id = ''

