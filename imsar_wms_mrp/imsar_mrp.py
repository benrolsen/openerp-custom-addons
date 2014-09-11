from openerp import models, fields, api, _
from openerp.exceptions import Warning


class product_template(models.Model):
    _inherit = 'mrp.production'

    account_routing_id = fields.Many2one('account.routing', 'Category', required=True, readonly=False,
                                 states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True,)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True,)
    account_id = fields.Many2one('account.account', 'General Account', required=True, ondelete='restrict', select=True,)

    @api.onchange('account_routing_id')
    def onchange_routing_id(self):
        self.account_type_id = ''
        self.analytic_account_id = ''

    @api.onchange('analytic_account_id')
    def onchange_account_type_id(self):
        if not self.account_routing_id or not self.account_type_id or not self.analytic_account_id:
            self.account_id = ''
        else:
            domain = [('routing_id','=',self.account_routing_id.id),('account_type_id','=',self.account_type_id.id)]
            routing_line_id = self.env['account.routing.line'].search(domain)
            analytic = self.env['account.analytic.account'].browse(self.analytic_account_id.id)
            self.account_id = analytic._search_for_subroute_account(routing_line_id=routing_line_id.id)


class product_template(models.Model):
    _inherit = 'product.template'

    _defaults = {
        'type' : 'product',
    }
