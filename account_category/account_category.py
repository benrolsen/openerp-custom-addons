import logging
_logger = logging.getLogger(__name__)

from openerp.osv import fields, osv


class account_category(osv.Model):
    _name = 'account.category'
    _description = 'Transaction Category'

    def _account_count(self, cr, uid, ids, name, arg, context):
        result = {}
        for cat in self.browse(cr, uid, ids):
            result[cat.id] = len(cat.account_ids)
        return result

    def _analytic_count(self, cr, uid, ids, name, arg, context):
        result = {}
        for cat in self.browse(cr, uid, ids):
            result[cat.id] = len(cat.analytic_ids)
        return result

    def onchange_type(self, cr, uid, ids, type):
        if not type:
            return {}
        return {'value':{'account_ids': []}}

    _columns = {
        'name': fields.char('Category Name', size=128, required=True),
        'type': fields.selection([('income','Income'),('expense','Expense')], "Account Type", required=True),
        'account_ids': fields.many2many('account.account', 'account_category_rel', 'category_id', 'account_id', 'Real Accounts'),
        'analytic_ids': fields.many2many('account.analytic.account', 'analytic_category_rel', 'category_id', 'analytic_id', 'Analytic Accounts'),
        'product_category_ids': fields.many2many('product.category', 'product_account_category_rel', 'account_cat_id', 'product_cat_id', 'Product Categories'),
        'account_count': fields.function(_account_count, string="Number of Accounts", type='integer'),
        'analytic_count': fields.function(_analytic_count, string="Number of Analytics", type='integer'),
    }

class product_category_account_category(osv.Model):
    _inherit = "product.category"
    _columns = {
        'allowed_categories': fields.many2many('account.category', 'product_account_category_rel', 'product_cat_id', 'account_cat_id', 'Accounting Categories', ),
    }

class account_account_category(osv.Model):
    _inherit = "account.account"

    _columns = {
        'category_ids':  fields.many2many('account.category', 'account_category_rel', 'account_id', 'category_id', 'Account Categories'),
    }

class analytic_category(osv.Model):
    _inherit = "account.analytic.account"

    _columns = {
        'category_ids':  fields.many2many('account.category', 'analytic_category_rel', 'analytic_id', 'category_id', 'Account Categories'),
    }

class account_invoice_line(osv.Model):
    _inherit = "account.invoice.line"

    _columns = {
        'category_id':  fields.many2one('account.category', 'Category', required=True,),
    }

    def onchange_category_id(self, cr, uid, ids, category_id):
        if not category_id:
            return {}
        return {'value':{'account_id': '', 'account_analytic_id': ''}}

    def product_id_change(self, cr, uid, ids, product, uom_id, qty=0, name='', type='out_invoice', partner_id=False, fposition_id=False, price_unit=False, currency_id=False, context=None, company_id=None):
        res = super(account_invoice_line, self).product_id_change(cr, uid, ids, product, uom_id, qty, name, type, partner_id, fposition_id, price_unit, currency_id, context, company_id)
        if 'account_id' in res['value']:
            del res['value']['account_id']
        return res


class sale_order_line(osv.Model):
    _inherit = "sale.order.line"

    _columns = {
        'category_id': fields.many2one('account.category', 'Category', required=True,),
        'account_id': fields.many2one('account.account', 'Income Account', required=True, readonly=True,
                        states={'draft': [('readonly', False)],}, help="The income account."),
        'account_analytic_id': fields.many2one('account.analytic.account', 'Analytic', ),
    }
    def onchange_category_id(self, cr, uid, ids, category_id):
        if not category_id:
            return {}
        return {'value':{'account_id': '', 'analytic_id': ''}}

    def _prepare_order_line_invoice_line(self, cr, uid, line, account_id=False, context=None):
        res = super(sale_order_line, self)._prepare_order_line_invoice_line(cr, uid, line, account_id, context)
        res['account_id'] = line.account_id.id
        res['category_id'] = line.category_id.id
        res['account_analytic_id'] = line.account_analytic_id.id
        return res

class purchase_order(osv.Model):
    _inherit = "purchase.order"

    def _prepare_inv_line(self, cr, uid, account_id, order_line, context=None):
        res = super(purchase_order, self)._prepare_inv_line(cr, uid, account_id, order_line, context)
        res['account_id'] = order_line.account_id.id
        res['category_id'] = order_line.category_id.id
        res['account_analytic_id'] = order_line.account_analytic_id.id
        return res


class purchase_order_line(osv.Model):
    _inherit = "purchase.order.line"

    _columns = {
        'category_id': fields.many2one('account.category', 'Category', required=True,),
        'account_id': fields.many2one('account.account', 'Expense Account', required=True,),
    }

    def onchange_category_id(self, cr, uid, ids, category_id):
        if not category_id:
            return {}
        return {'value':{'account_id': '', 'account_analytic_id': ''}}
