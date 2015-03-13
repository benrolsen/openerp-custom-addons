from datetime import datetime, date
from openerp import models, fields, api, _


class account_routing_subrouting(models.Model):
    _inherit = "account.routing.subrouting"

    location_id = fields.Many2one('stock.location','Location')
    material_type = fields.Boolean('Material Type', compute='_check_mat_type')

    @api.one
    def _check_mat_type(self):
        mat_types = self.env.user.company_id.material_account_type_ids
        if self.routing_line_id.account_type_id.id in mat_types.ids:
            self.material_type = True
        else:
            self.material_type = False


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

    mfr1_name = fields.Char('MFR 1 Name')
    mfr1_partnum = fields.Char('MFR 1 Part #')
    mfr2_name = fields.Char('MFR 2 Name')
    mfr2_partnum = fields.Char('MFR 2 Part #')
    mfr3_name = fields.Char('MFR 3 Name')
    mfr3_partnum = fields.Char('MFR 3 Part #')

    can_buy = fields.Boolean(compute='_computed_fields', readonly=True)

    @api.one
    @api.depends('route_ids')
    def _computed_fields(self):
        buy_route_id = self.env['ir.model.data'].xmlid_to_res_id('purchase.route_warehouse0_buy')
        self.can_buy = (buy_route_id in self.route_ids.ids)

    _defaults = {
        'type': 'product',
        'track_all': True,
    }

    @api.v7
    def do_change_standard_price(self, cr, uid, ids, new_price, context=None):
        return True


class stock_location(models.Model):
    _inherit = "stock.location"

    account_subroutes = fields.One2many('account.routing.subrouting', 'location_id', 'Task Codes')