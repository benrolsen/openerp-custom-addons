import logging
_logger = logging.getLogger(__name__)

from openerp.osv import fields, osv


class account_routing(osv.Model):
    _name = 'account.routing'
    _description = 'Account Routing'

    _columns = {
        'name': fields.char('Accounting Category', size=128, required=True),
        'routing_lines': fields.one2many('account.routing.line', 'routing_id', 'Account Type Routes'),
    }

class account_routing_line(osv.Model):
    _name = 'account.routing.line'
    _description = 'Account Routing Line'

    _columns = {
        'routing_id':  fields.many2one('account.routing', 'Account Routing', required=True,),
        'account_type_id': fields.many2one('account.account.type', 'Account Type', required=True,),
        'account_id':  fields.many2one('account.account', 'Default Account',),
        'subrouting_ids': fields.one2many('account.routing.subrouting', 'routing_line_id', 'Analytic Routes'),
    }

class account_routing_subrouting(osv.Model):
    _name = 'account.routing.subrouting'
    _description = 'Account Subrouting'

    _columns = {
        'routing_line_id':  fields.many2one('account.routing.line', 'Account Routing Line', required=True,),
        'account_analytic_id': fields.many2one('account.analytic.account', 'Analytic Account', required=True,),
        'account_id': fields.many2one('account.account', 'Real Account', required=True,),
    }

class account_account_type_routing(osv.Model):
    _inherit = "account.account.type"

    _columns = {
        'allow_routing': fields.boolean('Allow routing', help="Allows you to set special account routing rules via this account type"),
    }

    _defaults = {
        'allow_routing': False,
    }

# class account_invoice_line(osv.Model):
#     _inherit = "account.invoice.line"
#
#     _columns = {
#         'category_id':  fields.many2one('account.category', 'Category', required=True,),
#     }
#
#     def onchange_category_id(self, cr, uid, ids, category_id):
#         if not category_id:
#             return {}
#         return {'value':{'account_id': '', 'account_analytic_id': ''}}
#
#     def product_id_change(self, cr, uid, ids, product, uom_id, qty=0, name='', type='out_invoice', partner_id=False, fposition_id=False, price_unit=False, currency_id=False, context=None, company_id=None):
#         res = super(account_invoice_line, self).product_id_change(cr, uid, ids, product, uom_id, qty, name, type, partner_id, fposition_id, price_unit, currency_id, context, company_id)
#         if 'account_id' in res['value']:
#             del res['value']['account_id']
#         return res

#
# class sale_order_line(osv.Model):
#     _inherit = "sale.order.line"
#
#     _columns = {
#         'category_id': fields.many2one('account.category', 'Category', required=True,),
#         'account_analytic_id': fields.many2one('account.analytic.account', 'Analytic', ),
#     }
#     def onchange_category_id(self, cr, uid, ids, category_id):
#         if not category_id:
#             return {}
#         return {'value':{'': '', 'analytic_id': ''}}
#
#     def _prepare_order_line_invoice_line(self, cr, uid, line, account_id=False, context=None):
#         res = super(sale_order_line, self)._prepare_order_line_invoice_line(cr, uid, line, account_id, context)
#         res['account_id'] = line.account_id.id
#         res['category_id'] = line.category_id.id
#         res['account_analytic_id'] = line.account_analytic_id.id
#         return res
#
# class purchase_order(osv.Model):
#     _inherit = "purchase.order"
#
#     def _prepare_inv_line(self, cr, uid, account_id, order_line, context=None):
#         res = super(purchase_order, self)._prepare_inv_line(cr, uid, account_id, order_line, context)
#         res['account_id'] = order_line.account_id.id
#         res['category_id'] = order_line.category_id.id
#         res['account_analytic_id'] = order_line.account_analytic_id.id
#         return res
#
#
# class purchase_order_line(osv.Model):
#     _inherit = "purchase.order.line"
#
#     _columns = {
#         'category_id': fields.many2one('account.category', 'Category', required=True,),
#     }
#
#     def onchange_category_id(self, cr, uid, ids, category_id):
#         if not category_id:
#             return {}
#         return {'value':{'': '', 'account_analytic_id': ''}}
