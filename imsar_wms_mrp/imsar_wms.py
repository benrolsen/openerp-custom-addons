from openerp import models, fields, api, _


class stock_quant(models.Model):
    _inherit = 'stock.quant'

    labor_cost = fields.Float('Labor Cost')

    # @api.v7
    # def _get_inventory_value(self, cr, uid, quant, context=None):
    #     return (quant.cost * quant.qty) + quant.labor_cost


class product_category(models.Model):
    _inherit = 'product.category'

    @api.model
    def _get_fifo(self):
        return self.env['ir.model.data'].xmlid_to_res_id('stock.removal_fifo')

    _defaults = {
        'removal_strategy_id': _get_fifo,
    }


class product_template(models.Model):
    _inherit = 'product.template'

    _defaults = {
        'type': 'product',
        'track_all': True,
    }
