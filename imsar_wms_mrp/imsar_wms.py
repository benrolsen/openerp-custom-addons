from openerp import models, fields, api, _


class stock_move(models.Model):
    _inherit = 'stock.move'

    dest_employee = fields.Many2one('hr.employee', 'Deliver to')
    # for now, these are informational, therefore not required
    routing_id = fields.Many2one('account.routing', 'Category', )
    routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', )
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', )


class stock_quant(models.Model):
    _inherit = 'stock.quant'

    labor_cost = fields.Float('Labor Cost')
    purchase_order_id = fields.Many2one('purchase.order', 'Purchase Order', copy=True, readonly=True)
    mfg_order_id = fields.Many2one('mrp.production', 'Manufacturing Order', copy=True, readonly=True)

    # @api.v7
    # def _get_inventory_value(self, cr, uid, quant, context=None):
    #     return (quant.cost * quant.qty) + quant.labor_cost

    @api.v7
    def _quant_create(self, cr, uid, qty, move, lot_id=False, owner_id=False, src_package_id=False, dest_package_id=False,
                      force_location_from=False, force_location_to=False, context=None):
        quant = super(stock_quant, self)._quant_create(cr, uid, qty, move, lot_id, owner_id, src_package_id, dest_package_id,
                      force_location_from, force_location_to, context)
        if move.purchase_line_id:
            quant.sudo().write({'purchase_order_id': move.purchase_line_id.order_id.id})
        if move.production_id:
            quant.sudo().write({'mfg_order_id': move.production_id.id})


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


class stock_warehouse_orderpoint(models.Model):
    _inherit = 'stock.warehouse.orderpoint'

    routing_id = fields.Many2one('account.routing', 'Category', required=True,)
    routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True,)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True,)


class procurement_order(models.Model):
    _inherit = 'procurement.order'

    @api.model
    def _get_po_line_values_from_proc(self, procurement, partner, company, schedule_date):
        vals = super(procurement_order, self)._get_po_line_values_from_proc(procurement, partner, company, schedule_date)
        vals.update({
            'routing_id': procurement.orderpoint_id.routing_id.id,
            'routing_line_id': procurement.orderpoint_id.routing_line_id.id,
            'routing_subrouting_id': procurement.orderpoint_id.routing_subrouting_id.id,
        })
        return vals


class purchase_order(models.Model):
    _inherit = 'purchase.order'

    @api.v7
    def _prepare_order_line_move(self, cr, uid, order, order_line, picking_id, group_id, context=None):
        res = super(purchase_order,self)._prepare_order_line_move(cr, uid, order, order_line, picking_id, group_id, context)
        for vals in res:
            vals['dest_employee'] = order_line.dest_employee.id
            vals['routing_id'] = order_line.routing_id.id
            vals['routing_line_id'] = order_line.routing_line_id.id
            vals['routing_subrouting_id'] = order_line.routing_subrouting_id.id
        return res


class purchase_order_line(models.Model):
    _inherit = 'purchase.order.line'

    shipping_method = fields.Char('Shipping Method')
    dest_employee = fields.Many2one('hr.employee', 'Deliver to')

