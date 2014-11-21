from openerp import models, fields, api, _

class IMSAR_Analytic(models.Model):
    _inherit = "account.analytic.account"
    _order = "parent_left,name"
    _parent_order = "code"
    _parent_store = True

    parent_left = fields.Integer('Parent Left', select=1)
    parent_right = fields.Integer('Parent Right', select=1)
    fix_price_invoices = fields.Boolean('Fixed Price Sales')
    total_cost_tracking = fields.Boolean('Track Total Cost Allowance')
    total_cost_allowance =  fields.Float('Total Cost Allowance')

    _defaults = {
        'total_cost_tracking' : True,
    }

    # Don't really love the full hierarchy display as the display name
    def _get_one_full_name(self, elmt, level=6):
        return elmt.name

    def _recursive_children(self, analytic, result=[]):
        result += [analytic.id]
        if analytic.child_complete_ids:
            for child in analytic.child_complete_ids:
                self._recursive_children(child, result)
        return result

    @api.multi
    def get_all_children(self):
        result_list = self._recursive_children(self, [])
        result = self.browse(result_list)
        return result


