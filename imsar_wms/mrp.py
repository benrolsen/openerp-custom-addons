from datetime import datetime
from openerp import models, fields, api, _
from openerp.exceptions import Warning
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT


class mrp_production(models.Model):
    _inherit = 'mrp.production'
    _order = 'name desc'

    # This can't be routing_id because MRP uses that field for work center routing
    mat_routing_id = fields.Many2one('account.routing', 'Category', required=True,
                                 states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    mat_routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True,)
    mat_routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True,)
    mat_task_shortname = fields.Char("Material Task", compute="_computed_fields")
    labor_routing_id = fields.Many2one('account.routing', 'Category', required=True,
                                 states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    labor_routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True,)
    labor_routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True,)
    labor_task_shortname = fields.Char("Labor Task", compute="_computed_fields")
    to_consume_lines = fields.One2many('stock.move', 'raw_material_production_id', 'Products to Consume',
                            domain=[('state', 'not in', ('done', 'cancel'))], states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    consumed_lines = fields.One2many('stock.move', 'raw_material_production_id', 'Products Consumed',
                                       domain=[('state', 'in', ('done', 'cancel'))], readonly=True,)
    to_produce_lines = fields.One2many('stock.move', 'production_id', 'Products to Produce',
                            domain=[('state', 'not in', ('done', 'cancel'))], states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    produced_lines = fields.One2many('stock.move', 'production_id', 'Produced Products',
                                        domain=[('state', 'in', ('done', 'cancel'))], readonly=True)
    active_on_date = fields.Boolean('Active On Date', compute='_computed_fields', search='_search_active_date')
    production_quants = fields.One2many('stock.quant', compute="_computed_fields")
    production_serials = fields.One2many('stock.production.lot', compute="_computed_fields")

    @api.one
    @api.depends('to_produce_lines','produced_lines')
    def _computed_fields(self):
        self.active_on_date = (self.state not in ['done', 'cancel'])
        # gather up serials from to_produce_lines and produced_lines lines
        quants = []
        for prod_move in self.to_produce_lines + self.produced_lines:
            quants += [prod_move.quant_ids + prod_move.reserved_quant_ids]
        self.production_quants = [quant.id for quant in quants]
        serials = set()
        for quant in quants:
            serials.add(quant.lot_id)
        self.production_serials = [serial.id for serial in serials]
        self.mat_task_shortname = "{}/{}".format(self.mat_routing_id.name, self.mat_routing_subrouting_id.name)
        self.labor_task_shortname = "{}/{}".format(self.labor_routing_id.name, self.labor_routing_subrouting_id.name)

    def _search_active_date(self, operator, value):
        try:
            ts_date = datetime.strptime(value, '%Y-%m-%d')
            cr = self._cr
            cr.execute("""select id from mrp_production where tsrange(date_start::date, date_finished::date, '[]') @> '{}'::timestamp
                            and not state = ANY(array['draft','confirmed','ready','in_production','cancel']);""".format(value))
            lines = [row[0] for row in cr.fetchall()]
            cr.execute("""select id from mrp_production where date_start::date <= '{}'::timestamp
                            and state = ANY(array['confirmed','ready','in_production']) ;""".format(value))
            lines += [row[0] for row in cr.fetchall()]
            return [('id','in',lines)]
        except TypeError:
            return [('id','in',[])]

    @api.onchange('mat_routing_id')
    def onchange_mat_routing_id(self):
        self.mat_routing_line_id = ''
        mat_types = self.env.user.company_id.material_account_type_ids
        for routing_line in self.mat_routing_id.routing_lines:
            if routing_line.account_type_id.id in mat_types.ids:
                self.mat_routing_line_id = routing_line.id
                break

    @api.onchange('mat_routing_line_id')
    def onchange_mat_routing_line_id(self):
        self.mat_routing_subrouting_id = ''

    @api.onchange('mat_routing_subrouting_id')
    def onchange_mat_routing_subrouting_id(self):
        self.location_dest_id = self.mat_routing_subrouting_id.location_id.id

    @api.onchange('labor_routing_id')
    def onchange_labor_routing_id(self):
        self.labor_routing_line_id = ''
        routing_line = self.env['hr.timekeeping.line']._get_timekeeping_routing_line(self.labor_routing_id.id)
        self.labor_routing_line_id = routing_line.id

    @api.onchange('labor_routing_line_id')
    def onchange_labor_routing_line_id(self):
        self.labor_routing_subrouting_id = ''

    @api.model
    def _make_production_produce_line(self, production):
        # copied from and overwrites function from mrp/mrp.py

        # We need to put a unique serial on each item produced
        for num in xrange(int(production.product_qty)):
            # auto-create serial number
            vals = {
                'production_id': production.id,
                'product_id': production.product_id.id,
                'base_cost': 0.0,
            }
            lot_id = self.env['stock.production.lot'].create(vals)

            # create a quant by creating a completed move from virt production to WIP/expense account
            if production.location_dest_id.usage == 'internal':
                target_task = self.env.user.company_id.wip_task_code
            else:
                target_task = production.mat_routing_subrouting_id
            data = {
                'name': production.name,
                'date': production.date_planned,
                'product_id': production.product_id.id,
                'product_uom': production.product_uom.id,
                'product_uom_qty': 1,
                'source_routing_id': self.env.user.company_id.mfg_task_code.routing_id.id,
                'source_routing_line_id': self.env.user.company_id.mfg_task_code.routing_line_id.id,
                'source_routing_subrouting_id': self.env.user.company_id.mfg_task_code.id,
                'target_routing_id': target_task.routing_id.id,
                'target_routing_line_id': target_task.routing_line_id.id,
                'target_routing_subrouting_id': target_task.id,
                'location_id': self.env.user.company_id.mfg_task_code.location_id.id,
                'location_dest_id': target_task.location_id.id,
                'company_id': production.company_id.id,
                'mfg_order_id': production.id,
                'origin': production.name,
                'restrict_lot_id': lot_id.id,
            }
            move = self.env['stock.move'].create(data)
            move.action_confirm()
            move.action_done()

            # create move from WIP/expense to dest location, assign the new quant to that move
            data = {
                'name': production.name,
                'date': production.date_planned,
                'product_id': production.product_id.id,
                'product_uom': production.product_uom.id,
                'product_uom_qty': 1,
                'source_routing_id': target_task.routing_id.id,
                'source_routing_line_id': target_task.routing_line_id.id,
                'source_routing_subrouting_id': target_task.id,
                'target_routing_id': production.mat_routing_id.id,
                'target_routing_line_id': production.mat_routing_line_id.id,
                'target_routing_subrouting_id': production.mat_routing_subrouting_id.id,
                'location_id': target_task.location_id.id,
                'location_dest_id': production.mat_routing_subrouting_id.location_id.id,
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

        prod_locs = self.env.user.company_id.prod_ready_locations
        kitting_locs = self.env.user.company_id.kitting_mat_locations

        # Is this internal (direct mfg) or external (expense/contract)?
        if production.mat_routing_subrouting_id.location_id.usage == 'internal':
            wip_task = self.env.user.company_id.wip_task_code
            target_task = self.env.user.company_id.mfg_task_code
        else:
            wip_task = production.mat_routing_subrouting_id
            target_task = production.mat_routing_subrouting_id

        # Tower, etc can be moved directly from location to virt production
        for loc in prod_locs:
            if qty <= 0:
                continue
            prod_loc_qty = 0
            quants = self.env['stock.quant'].quants_get(loc, product, qty, domain=[('qty', '>', 0.0),('reservation_id','=',None)])
            for found_quant, found_qty in quants:
                if found_quant:
                    prod_loc_qty += found_qty
                    qty -= found_qty
            if prod_loc_qty > 0:
                source_task = self.env['account.routing.subrouting'].search([('location_id','=',loc.id)])[0] or None
                if not source_task:
                    raise Warning("Location {} doesn't have any task codes that use it".format(loc.name))
                self._make_prod_stock_move(source_task, target_task, production, product, uom_id, prod_loc_qty, loc)

        # Cage, etc need to be kitted (moved from loc to WIP) and then set up to move from WIP to virt production
        for loc in kitting_locs:
            if qty <= 0:
                continue
            kitting_loc_qty = 0
            quants = self.env['stock.quant'].quants_get(loc, product, qty, domain=[('qty', '>', 0.0),('reservation_id','=',None)])
            for found_quant, found_qty in quants:
                if found_quant:
                    kitting_loc_qty += found_qty
                    qty -= found_qty
            if kitting_loc_qty > 0:
                prod_move_id = self._make_prod_stock_move(wip_task, target_task, production, product, uom_id, kitting_loc_qty, wip_task.location_id)
                self._make_kitting_stock_move(production, product, uom_id, kitting_loc_qty, loc, prod_move_id)

        # if remaining qty > 0, need to request more from default locations
        if qty > 0:
            loc = product.categ_id.default_location
            prod_move_id = self._make_prod_stock_move(wip_task, target_task, production, product, uom_id, qty, wip_task.location_id)
            self._make_kitting_stock_move(production, product, uom_id, qty, loc, prod_move_id)
        return False

    @api.model
    def _make_prod_stock_move(self, source_task, target_task, production, product, uom_id, qty, location):
        data = {
            'name': production.name,
            'date': production.date_planned,
            'product_id': product.id,
            'product_uom_qty': qty,
            'product_uom': uom_id,
            'source_routing_id': source_task.routing_id.id,
            'source_routing_line_id': source_task.routing_line_id.id,
            'source_routing_subrouting_id': source_task.id,
            'target_routing_id': target_task.routing_id.id,
            'target_routing_line_id': target_task.routing_line_id.id,
            'target_routing_subrouting_id': target_task.id,
            'location_id': location.id,
            'location_dest_id':  target_task.location_id.id,
            'company_id': production.company_id.id,
            'raw_material_production_id': production.id,
            'price_unit': 0.0,
            'origin': production.name,
            'group_id': production.move_prod_id.group_id.id,
        }
        move_id = self.env['stock.move'].create(data)
        move_id.action_confirm()
        return move_id

    @api.model
    def _make_kitting_stock_move(self, production, product, uom_id, qty, location, prod_move_id):
        source_task = self.env['account.routing.subrouting'].search([('location_id','=',location.id)])[0] or None
        if not source_task:
            raise Warning("Location {} doesn't have any task codes that use it".format(location.name))
        target_task = prod_move_id.source_routing_subrouting_id
        data = {
            'name': production.name,
            'date': production.date_planned,
            'product_id': product.id,
            'product_uom_qty': qty,
            'product_uom': uom_id,
            'source_routing_id': source_task.routing_id.id,
            'source_routing_line_id': source_task.routing_line_id.id,
            'source_routing_subrouting_id': source_task.id,
            'target_routing_id': target_task.routing_id.id,
            'target_routing_line_id': target_task.routing_line_id.id,
            'target_routing_subrouting_id': target_task.id,
            'location_id': location.id,
            'location_dest_id':  target_task.location_id.id,
            'company_id': production.company_id.id,
            'kitting_production_id': production.id,
            'price_unit': 0.0,
            'origin': production.name,
            'group_id': production.move_prod_id.group_id.id,
            'move_dest_id': prod_move_id.id,
            'picking_type_id': self.env.ref('stock.picking_type_internal').id,
        }
        kitting_move_id = self.env['stock.move'].create(data)
        kitting_move_id.action_confirm()
        return kitting_move_id

    @api.multi
    def action_produce(self):
        # all consume moves need to be at least assigned a quant
        for move in self.to_consume_lines:
            if move.state in ('draft', 'waiting', 'confirmed'):
                raise Warning("Please ensure all Products to Consume lines are assigned or finished.")
        # complete all moves in to_consume_lines
        todo_moves = [move for move in self.to_consume_lines]
        while todo_moves:
            consume_move = todo_moves.pop()
            if consume_move.location_dest_id.usage not in ['customer','production']:
                raise Warning("All MFG stock movements must be to external locations, such as production or customer.")
            if consume_move.state in ('done', 'cancel'):
                continue
            # extra_ids = consume_move.action_consume(consume_move.reserved_quant_ids[0].qty, consume_move.location_id.id, restrict_lot_id=consume_move.reserved_quant_ids[0].lot_id.id)
            extra_ids = consume_move.action_consume(consume_move.product_uom_qty, consume_move.location_id.id)
            if extra_ids:
                todo_moves += self.env['stock.move'].browse(extra_ids)
        # gather and distribute costs
        material_costs = 0.0
        labor_costs = 0.0
        overhead_costs = 0.0
        for consume_move in self.consumed_lines:
            # automatically add costs for raw materials
            if consume_move.product_id.categ_id.id in self.env.user.company_id.rm_product_categories.ids:
                for quant in consume_move.quant_ids:
                    material_costs += quant.total_material_cost
                    labor_costs += quant.total_labor_cost
                    overhead_costs += quant.total_overhead_cost
            # mark other internal source moves for accounting review
            elif consume_move.location_id.usage == 'internal' and consume_move.target_routing_subrouting_id != consume_move.source_routing_subrouting_id:
                consume_move.write({'accounting_review_flag': True})
        material_unit_cost = material_costs / len(self.production_quants)
        labor_unit_cost = labor_costs / len(self.production_quants)
        overhead_unit_cost = overhead_costs / len(self.production_quants)
        for quant in self.production_quants:
            quant.add_material_cost(material_unit_cost)
            quant.add_labor_cost(labor_unit_cost)
            quant.add_labor_oh_cost(overhead_unit_cost)
        # finish the produce lines
        for produce_move in self.to_produce_lines:
            produce_move.action_done()
        self.action_production_end()
        self.message_post(body=_("%s produced") % self._description)

    @api.multi
    def action_confirm(self):
        super(mrp_production, self).action_confirm()
        # raise Warning('stop in action_confirm')

    @api.multi
    def action_cancel(self):
        for consume_move in self.to_consume_lines:
            for move in consume_move.move_orig_ids:
                if move.state not in ('cancel','done'):
                    move.action_cancel()
        for move in self.to_produce_lines:
            for quant in move.reserved_quant_ids:
                # TODO move mat/labor/oh costs on quant to somewhere else
                quant.unlink()
        super(mrp_production, self).action_cancel()


# class mrp_product_modify(models.TransientModel):
#     _name = "mrp.product.modify"
#     _description = "Modify or upgrade produced products"
#
#     lot_ids = fields.Many2many('stock.production.lot','product_modify_lot_ids','modify_id','lot_id','Serial to Modify/Upgrade')
#     consume_lines = fields.One2many('mrp.product.modify.line', 'modify_id', 'Products To Use')
#
#
# class mrp_product_modify_line(models.TransientModel):
#     _name="mrp.product.modify.line"
#     _description = "Product Modify Consume lines"
#
#     product_id = fields.Many2one('product.product', 'Product')
#     product_qty = fields.Float('Quantity')
#     lot_id = fields.Many2one('stock.production.lot', 'Serial')
#     modify_id = fields.Many2one('mrp.product.modify')




