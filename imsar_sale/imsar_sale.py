from openerp.osv import fields, osv
from openerp import models, fields, api, _


class sale_order_line(models.Model):
    _inherit = "sale.order.line"

    routing_id = fields.Many2one('account.routing', 'Category', required=True,)
    routing_line_id = fields.Many2one('account.routing.line', 'Type', required=True,)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Identifier', required=True,)

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        self.routing_line_id = ''
        self.routing_subrouting_id = ''

    @api.onchange('routing_line_id')
    def onchange_routing_line_id(self):
        self.routing_subrouting_id = ''

    @api.v7
    def _prepare_order_line_invoice_line(self, cr, uid, line, account_id=False, context=None):
        account_id = line.routing_subrouting_id.account_id.id
        res = super(sale_order_line, self)._prepare_order_line_invoice_line(cr, uid, line, account_id, context)
        res['routing_id'] = line.routing_id.id
        res['routing_line_id'] = line.routing_line_id.id
        res['routing_subrouting_id'] = line.routing_subrouting_id.id
        res['account_analytic_id'] = line.routing_subrouting_id.account_analytic_id.id
        return res



class custom_sale_order(models.Model):
   _inherit = "sale.order"

   sales_contact = fields.Many2one('res.partner', 'Point of Contact')
