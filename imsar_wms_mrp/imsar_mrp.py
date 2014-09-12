from openerp import models, fields, api, _
from openerp.exceptions import Warning


class product_template(models.Model):
    _inherit = 'mrp.production'

    account_routing_id = fields.Many2one('account.routing', 'Category', required=True, readonly=False,
                                 states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True,)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True,)

    @api.onchange('account_routing_id')
    def onchange_routing_id(self):
        self.routing_line_id = ''
        self.routing_subrouting_id = ''

    @api.onchange('routing_subrouting_id')
    def onchange_routing_subrouting_id(self):
        if not self.account_routing_id or not self.routing_line_id or not self.routing_subrouting_id:
            self.account_id = ''
        else:
            self.account_id = self.routing_subrouting_id.account_id.id


class product_template(models.Model):
    _inherit = 'product.template'

    _defaults = {
        'type' : 'product',
    }
