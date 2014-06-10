import logging
_logger = logging.getLogger(__name__)

from osv import fields, osv


class txn_category(osv.Model):
    _name = 'account.txn.category'
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

    _columns = {
        'name': fields.char('Category Name', size=128, required=True),
        'account_ids': fields.many2many('account.account', 'account_category_rel', 'category_id', 'account_id', 'Real Accounts'),
        'analytic_ids': fields.many2many('account.analytic.account', 'analytic_category_rel', 'category_id', 'analytic_id', 'Analytic Accounts'),
        'account_count': fields.function(_account_count, string="Number of Accounts", type='integer'),
        'analytic_count': fields.function(_analytic_count, string="Number of Analytics", type='integer'),
    }

class account_category(osv.Model):
    _inherit = "account.account"

    _columns = {
        'txn_category_ids':  fields.many2many('account.txn.category', 'account_category_rel', 'account_id', 'category_id', 'Txn Categories'),
    }

class analytic_category(osv.Model):
    _inherit = "account.analytic.account"

    _columns = {
        'txn_category_ids':  fields.many2many('account.txn.category', 'analytic_category_rel', 'analytic_id', 'category_id', 'Txn Categories'),
    }

class account_invoice_line(osv.Model):
    _inherit = "account.invoice.line"

    def onchange_category_id(self, cr, uid, ids, category_id):
        if not category_id:
            return {}
        account_obj = self.pool.get('account.account')
        account_ids = account_obj.search(cr, uid, [('txn_category_ids','=',category_id)])
        account_list = account_obj.browse(cr, uid, account_ids)
        first_account_id = account_list[0] or None
        return {'value':{'account_id': first_account_id.id}}

