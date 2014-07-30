import logging
_logger = logging.getLogger(__name__)

from openerp.osv import fields, osv


class IMSAR_Analytic(osv.Model):
    _inherit = "account.analytic.account"
    _order = "parent_left"
    _parent_order = "code"
    _parent_store = True

    def _remaining_not_invoiced(self, cr, uid, ids, name, arg, context=None):
        lines_obj = self.pool.get('account.analytic.line')
        res = {}
        for account in self.browse(cr, uid, ids, context=context):
            res[account.id] = account.total_cost_allowance - account.invoiced_total
        return res

    def _remaining_total(self, cr, uid, ids, name, arg, context=None):
        lines_obj = self.pool.get('account.analytic.line')
        res = {}
        for account in self.browse(cr, uid, ids, context=context):
            res[account.id] = account.total_cost_allowance - (account.invoiced_total + account.toinvoice_total)
        return res

    _columns = {
        'parent_left': fields.integer('Parent Left', select=1),
        'parent_right': fields.integer('Parent Right', select=1),
        'fix_price_invoices' : fields.boolean('Fixed Price Sales'),
        'total_cost_tracking' : fields.boolean('Track Total Cost Allowance'),
        'total_cost_allowance': fields.float('Total Cost Allowance'),
        'remaining_not_invoiced' : fields.function(_remaining_not_invoiced, string='Allowance Not Invoiced',
                                                   type="float", help="Allowance - Invoiced Amount"),
        'remaining_total' : fields.function(_remaining_total, string='Allowance Remaining',
                                            type="float", help="Allowance - (Invoiced + To Invoice)"),
    }

    _defaults = {
        'total_cost_tracking' : True,
    }

    # Don't really love the full hierarchy display as the display name
    def _get_one_full_name(self, elmt, level=6):
        return elmt.name