from datetime import datetime
from openerp import models, fields, api, _
from openerp.exceptions import Warning
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT


class mrp_production(models.Model):
    _inherit = 'mrp.production'
    _order = 'name desc'

    # This can't be routing_id because MRP uses that field for work center routing
    account_routing_id = fields.Many2one('account.routing', 'Category', required=True, readonly=False,
                                 states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True,)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True,)

    @api.onchange('account_routing_id')
    def onchange_routing_id(self):
        self.routing_line_id = ''
        mat_types = self.env.user.company_id.material_account_type_ids
        for routing_line in self.account_routing_id.routing_lines:
            if routing_line.account_type_id.id in mat_types.ids:
                self.routing_line_id = routing_line.id
                break

    @api.onchange('routing_line_id')
    def onchange_routing_line_id(self):
        self.routing_subrouting_id = ''

    @api.onchange('routing_subrouting_id')
    def onchange_routing_subrouting_id(self):
        self.location_dest_id = self.routing_subrouting_id.location_id.id

    @api.model
    def _default_location(self):
        return self.env.user.company_id.mfg_location

    @api.model
    def _make_production_produce_line(self, production):
        # copied from and overwrites function from mrp/mrp.py

        # We need to put a unique serial on each item produced
        for num in xrange(int(production.product_qty)):
            # auto-create serial number
            vals = {
                'product_id': production.product_id.id,
                'base_cost': 0.0,
            }
            lot_id = self.env['stock.production.lot'].create(vals)

            # create a quant by creating a completed move from virt production to WIP
            data = {
                'name': production.name,
                'date': production.date_planned,
                'product_id': production.product_id.id,
                'product_uom': production.product_uom.id,
                'product_uom_qty': 1,
                'source_routing_id': self.env.user.company_id.mfg_task_code.routing_id.id,
                'source_routing_line_id': self.env.user.company_id.mfg_task_code.routing_line_id.id,
                'source_routing_subrouting_id': self.env.user.company_id.mfg_task_code.id,
                'target_routing_id': self.env.user.company_id.wip_task_code.routing_id.id,
                'target_routing_line_id': self.env.user.company_id.wip_task_code.routing_line_id.id,
                'target_routing_subrouting_id': self.env.user.company_id.wip_task_code.id,
                'location_id': self.env.user.company_id.mfg_task_code.location_id.id,
                'location_dest_id': self.env.user.company_id.wip_task_code.location_id.id,
                # 'move_dest_id': production.move_prod_id.id,
                'company_id': production.company_id.id,
                # 'production_id': production.id,
                'origin': production.name,
                'restrict_lot_id': lot_id.id,
            }
            move = self.env['stock.move'].create(data)
            move.action_confirm()
            move.action_done()

            # create move from WIP to dest location, assign the new quant to that move
            data = {
                'name': production.name,
                'date': production.date_planned,
                'product_id': production.product_id.id,
                'product_uom': production.product_uom.id,
                'product_uom_qty': 1,
                'source_routing_id': self.env.user.company_id.wip_task_code.routing_id.id,
                'source_routing_line_id': self.env.user.company_id.wip_task_code.routing_line_id.id,
                'source_routing_subrouting_id': self.env.user.company_id.wip_task_code.id,
                'target_routing_id': production.account_routing_id.id,
                'target_routing_line_id': production.routing_line_id.id,
                'target_routing_subrouting_id': production.routing_subrouting_id.id,
                'location_id': self.env.user.company_id.wip_task_code.location_id.id,
                'location_dest_id': production.routing_subrouting_id.location_id.id,
                'move_dest_id': production.move_prod_id.id,
                'company_id': production.company_id.id,
                'production_id': production.id,
                'origin': production.name,
                'restrict_lot_id': lot_id.id,
            }
            finish_move = self.env['stock.move'].create(data)
            finish_move.action_confirm()
            quant = self.env['stock.quant'].search([('lot_id','=',lot_id.id)])[0]
            self.env['stock.quant'].quants_reserve([(quant, 1)], finish_move)
        return True

    @api.model
    def _make_consume_line_from_data(self, production, product, uom_id, qty, uos_id, uos_qty):
        # copied from and overwrites function from mrp/mrp.py
        # with the exception that I've removed the bom routing logic for now
        if product.type not in ('product', 'consu'):
            return False

        # TODO check production location for raw materials first, and only make stock.move for needed items/qty
        prod_locs = self.env.user.company_id.prod_ready_locations
        rm_locs = self.env.user.company_id.raw_mat_locations

        quants = []
        # Tower, etc can be moved directly from location to virt production
        for loc in prod_locs:
            prod_loc_qty = 0
            quants += self.env['stock.quant'].quants_get(loc, product, qty, domain=[('qty', '>', 0.0),('reservation_id','=',None)])
            for found_quant, found_qty in quants:
                if found_quant:
                    prod_loc_qty += found_qty
                    qty -= found_qty
            source_task = self.env['account.routing.subrouting'].search([('location_id','=',loc.id)])[0] or None
            if not source_task:
                source_task = self.env.user.company_id.mfg_task_code
            target_task = self.env.user.company_id.mfg_task_code
            if prod_loc_qty > 0:
                data = {
                    'name': production.name,
                    'date': production.date_planned,
                    'product_id': product.id,
                    'product_uom_qty': prod_loc_qty,
                    'product_uom': uom_id,
                    'source_routing_id': source_task.routing_id.id,
                    'source_routing_line_id': source_task.routing_line_id.id,
                    'source_routing_subrouting_id': source_task.id,
                    'target_routing_id': target_task.routing_id.id,
                    'target_routing_line_id': target_task.routing_line_id.id,
                    'target_routing_subrouting_id': target_task.id,
                    'location_id': loc.id,
                    'location_dest_id':  target_task.location_id.id,
                    'company_id': production.company_id.id,
                    'raw_material_production_id': production.id,
                    'price_unit': 0.0,
                    'origin': production.name,
                    'group_id': production.move_prod_id.group_id.id,
                    # moving to virt prod to be consumed isn't internal picking, is it a different type of picking?
                    # 'picking_type_id': self.env.ref('stock.picking_type_internal').id,
                }
                move_id = self.env['stock.move'].create(data)
                move_id.action_confirm()

        # Cage, etc need to be kitted (moved from loc to WIP) and then set up to move from WIP to virt production
        quants = []
        for loc in rm_locs:
            kitting_loc_qty = 0
            quants += self.env['stock.quant'].quants_get(loc, product, qty, domain=[('qty', '>', 0.0),('reservation_id','=',None)])
            for found_quant, found_qty in quants:
                if found_quant:
                    kitting_loc_qty += found_qty
                    qty -= found_qty
            if kitting_loc_qty > 0:
                # WIP -> Virt Prod
                source_task = self.env.user.company_id.wip_task_code
                target_task = self.env.user.company_id.mfg_task_code
                data = {
                    'name': production.name,
                    'date': production.date_planned,
                    'product_id': product.id,
                    'product_uom_qty': kitting_loc_qty,
                    'product_uom': uom_id,
                    'source_routing_id': source_task.routing_id.id,
                    'source_routing_line_id': source_task.routing_line_id.id,
                    'source_routing_subrouting_id': source_task.id,
                    'target_routing_id': target_task.routing_id.id,
                    'target_routing_line_id': target_task.routing_line_id.id,
                    'target_routing_subrouting_id': target_task.id,
                    'location_id': source_task.location_id.id,
                    'location_dest_id':  target_task.location_id.id,
                    'company_id': production.company_id.id,
                    'raw_material_production_id': production.id,
                    'price_unit': 0.0,
                    'origin': production.name,
                    'group_id': production.move_prod_id.group_id.id,
                    # 'picking_type_id': self.env.ref('stock.picking_type_internal').id,
                }
                prod_move_id = self.env['stock.move'].create(data)
                prod_move_id.action_confirm()

                # Kitting Source -> WIP, chained to move above
                source_task = self.env['account.routing.subrouting'].search([('location_id','=',loc.id)])[0] or None
                if not source_task:
                    source_task = self.env.user.company_id.wip_task_code
                target_task = self.env.user.company_id.wip_task_code
                data = {
                    'name': production.name,
                    'date': production.date_planned,
                    'product_id': product.id,
                    'product_uom_qty': kitting_loc_qty,
                    'product_uom': uom_id,
                    'source_routing_id': source_task.routing_id.id,
                    'source_routing_line_id': source_task.routing_line_id.id,
                    'source_routing_subrouting_id': source_task.id,
                    'target_routing_id': target_task.routing_id.id,
                    'target_routing_line_id': target_task.routing_line_id.id,
                    'target_routing_subrouting_id': target_task.id,
                    'location_id': loc.id,
                    'location_dest_id':  target_task.location_id.id,
                    'company_id': production.company_id.id,
                    # 'raw_material_production_id': production.id,
                    'price_unit': 0.0,
                    'origin': production.name,
                    'group_id': production.move_prod_id.group_id.id,
                    'move_dest_id': prod_move_id.id,
                    'picking_type_id': self.env.ref('stock.picking_type_internal').id,
                }
                kittin_move_id = self.env['stock.move'].create(data)
                kittin_move_id.action_confirm()
        return False

    # TODO inherit _costs_generate and get correct costs, write them to the quant and lot/serial
    @api.model
    def _costs_generate(self, production):
        print('calculating costs')
        material_costs = 0.0
        for consume_move in production.move_lines2:
            for quant in consume_move.quant_ids:
                material_costs += (quant.material_cost * consume_move.product_uom_qty)
        print("total mat costs ", material_costs)
        num_produced = len(production.move_created_ids2)
        mat_unit_cost = material_costs / num_produced
        print("unit mat costs ", mat_unit_cost)
        for produce_move in production.move_created_ids2:
            print(produce_move)
            for quant in produce_move.quant_ids:
                print(quant)
        return mat_unit_cost
        # raise Warning('stop in _costs_generate')

    @api.model
    def action_produce(self, production_id, production_qty, production_mode, wiz=False):
        super(mrp_production, self).action_produce(production_id, production_qty, production_mode, wiz)
        print(wiz)
        raise Warning('stop in action_produce')


    @api.multi
    def action_confirm(self):
        super(mrp_production, self).action_confirm()
        # raise Warning('stop in action_confirm')


class mrp_product_produce(models.TransientModel):
    _inherit = "mrp.product.produce"

    lot_ids = fields.Many2many('stock.production.lot','product_produce_lot_ids','produce_id','lot_id','Serials', default=lambda self: self._default_lots())

    @api.onchange('lot_ids')
    def onchange_lot_ids(self):
        self.product_qty = len(self.lot_ids)

    @api.model
    def _default_lots(self):
        production_id = self._context.get('active_id')
        production = self.env['mrp.production'].browse(production_id)
        return [(4,move.restrict_lot_id.id) for move in production.move_created_ids]

    @api.multi
    def do_produce(self):
        production_id = self._context.get('active_id')
        production = self.env['mrp.production'].browse(production_id)
        lot_id_map = dict()
        for move in production.move_created_ids:
            lot_id_map[move.restrict_lot_id.id] = move
        self.product_qty = 1
        for lot in self.lot_ids:
            self.lot_id = lot
            production.action_produce(production.id, 1, 'consume', self)
            produce_move = lot_id_map[lot.id]
            produce_move.action_consume(1, location_id=produce_move.location_id.id, restrict_lot_id=lot.id)
            produce_move.write({'production_id': production_id})
        if len(production.move_created_ids) == 0:
            production.action_production_end()
        return True


# class stock_move(models.Model):
#     _inherit = 'stock.move'
#
#     for_mfg_order = fields.Many2one('mrp.production', 'For Mfg Order', copy=True)
#
#     @api.multi
#     def action_done(self):
#         super(stock_move, self).action_done()
#         for move in self:
#             if move.raw_material_production_id:
#                 for quant in move.quant_ids:
#                     quant.write({'assigned_to_mfg_order': move.raw_material_production_id.id})
#         return True
#

