from openerp import models, fields, api, _


class stock_quant(models.Model):
    _inherit = 'stock.quant'

    labor_cost = fields.Float('Labor Cost')


    @api.v7
    def _get_inventory_value(self, cr, uid, quant, context=None):
        return (quant.cost * quant.qty) + quant.labor_cost
