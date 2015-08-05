import time
from collections import defaultdict
from datetime import datetime
from openerp import models, fields, api, _
from openerp.exceptions import Warning
from openerp.tools import DEFAULT_SERVER_DATETIME_FORMAT


class mrp_production(models.Model):
    _inherit = 'mrp.production'
    _order = 'name desc'

    bom_id = fields.Many2one('mrp.bom', 'Bill of Material', readonly=False)
    # This can't be routing_id because MRP uses that field for work center routing
    mat_routing_id = fields.Many2one('account.routing', 'Category', required=True,
                                 states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    mat_routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True,
                                    states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    mat_routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True,
                                    states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    mat_task_shortname = fields.Char("Material Task", compute="_computed_fields")
    labor_routing_id = fields.Many2one('account.routing', 'Category', required=True,
                                 states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    labor_routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True,
                                        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    labor_routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True,
                                        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    labor_task_shortname = fields.Char("Labor Task", compute="_computed_fields")
    active_on_date = fields.Boolean('Active On Date', compute='_computed_fields', search='_search_active_date')
    component_bom = fields.One2many('mrp.bom.line', related='bom_id.bom_line_ids')
    component_quants = fields.One2many('stock.quant', 'reserved_mfg_order_id', "Assigned Components",
                                       states={'done': [('readonly', True)], 'cancel': [('readonly', True)]},)
    component_quants_used = fields.One2many('stock.quant', 'used_mfg_order_id', "Used Components",
                                       states={'done': [('readonly', True)], 'cancel': [('readonly', True)]},)
    production_quants = fields.One2many('stock.quant', 'wip_mfg_order_id', "Products to Produce",
                                       states={'done': [('readonly', True)], 'cancel': [('readonly', True)]},)
    produced_quants = fields.One2many('stock.quant', 'mfg_order_id', "Products Produced", readonly=True)
    production_serials = fields.One2many('stock.production.lot', compute="_computed_fields")
    missing_lines = fields.One2many('mrp.production.missing.line', 'production_id', string="Components Missing",)
    missing_lines_display = fields.One2many('mrp.production.missing.line', related='missing_lines', readonly=True)

    @api.one
    @api.depends('component_quants', 'production_quants', 'produced_quants')
    def _computed_fields(self):
        self.active_on_date = (self.state not in ['done', 'cancel'])
        serials = set()
        for quant in self.production_quants + self.produced_quants:
            serials.add(quant.lot_id)
        self.production_serials = [serial.id for serial in serials]
        self.mat_task_shortname = "{}/{}".format(self.mat_routing_id.name, self.mat_routing_subrouting_id.name)
        self.labor_task_shortname = "{}/{}".format(self.labor_routing_id.name, self.labor_routing_subrouting_id.name)

    @api.onchange('component_quants','component_bom','product_qty')
    def _missing_lines(self):
        assigned = defaultdict(float)
        missing = []
        self.missing_lines = missing
        for quant in self.component_quants:
            assigned[quant.product_id.id] += quant.qty
        for line in self.component_bom:
            if line.product_id.id in assigned:
                missing_qty = (line.product_qty * self.product_qty) - assigned[line.product_id.id]
            else:
                missing_qty = (line.product_qty * self.product_qty)
            if missing_qty > 0:
                missing.append((0,0,{'product_id':line.product_id.id, 'product_qty': missing_qty}))
        self.missing_lines = missing

    def _search_active_date(self, operator, value):
        try:
            # keep this line, as it helps check that the value is valid
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

    @api.multi
    def action_quant_return(self):
        ret_wizard = self.env['mrp.production.quant.return'].create({'production_id':self.id})
        ret_wizard.set_lines()
        view = {
            'name': _('Quant Return Wizard'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mrp.production.quant.return',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_id': ret_wizard.id,
        }
        return view

    @api.multi
    def action_produce(self):
        # consume components
        self._automove_consumed_components()
        self.component_quants_used = self.component_quants
        self.component_quants = [(5,)]
        #calculate costs and add to produced components
        self._calcuate_costs()
        # produce products
        self._automove_produced_products()
        self.produced_quants = self.production_quants
        self.production_quants = [(5,)]
        # for quant in self.production_quants:
        #     quant._computed_fields()
        # finish MO
        self.signal_workflow('button_produce')
        self.signal_workflow('button_produce_done')
        self.message_post(body=_("%s produced") % self._description)

    @api.multi
    def action_confirm(self):
        for production in self:
            taskcode = production._get_mfg_wip_taskcode()
            for num in xrange(int(production.product_qty)):
                # auto-create serial number
                vals = {
                    'production_id': production.id,
                    'product_id': production.product_id.id,
                    'base_cost': 0.0,
                }
                lot_id = self.env['stock.production.lot'].create(vals)

                # create quants for production
                vals = {
                    'product_id': production.product_id.id,
                    'routing_id': taskcode.routing_id.id,
                    'routing_line_id': taskcode.routing_line_id.id,
                    'routing_subrouting_id': taskcode.id,
                    'location_id': taskcode.location_id.id,
                    'qty': 1,
                    'lot_id': lot_id.id,
                    'in_date': datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                    'create_date': datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                    # 'mfg_order_id': production.id,
                    'wip_mfg_order_id': production.id,
                }
                self.env['stock.quant'].sudo().create(vals)
            production.write({'state': 'confirmed'})

    @api.multi
    def action_assign(self):
        from openerp import workflow
        autoassign_ids = []
        for line in self.missing_lines:
            product = line.product_id
            for location in self.env.user.company_id.prod_ready_locations:
                domain = [('qty', '>', 0.0),('available','=',True)]
                found_quants = self.env['stock.quant'].quants_get(location, product, line.product_qty, domain=domain)
                for quant, qty in found_quants:
                    if quant:
                        autoassign_ids.append(quant.id)
        if autoassign_ids:
            self.write({'component_quants': [(4,quant_id) for quant_id in autoassign_ids]})
        if len(self.missing_lines) == 0:
            workflow.trg_validate(self._uid, 'mrp.production', self.id, 'moves_ready', self._cr)

    @api.multi
    def action_ready(self):
        self.write({'state': 'ready'})
        return True

    @api.multi
    def action_cancel(self):
        self.env['stock.quant'].send_to_scrap(self.production_quants.ids)
        self.write({'component_quants': [(5,None)]})
        super(mrp_production, self).action_cancel()

    @api.multi
    def write(self, vals):
        orig_comp_ids = self.component_quants.ids
        res = super(mrp_production, self).write(vals)
        new_comp_ids = self.component_quants.ids
        added_ids = set(new_comp_ids) - set(orig_comp_ids)
        removed_ids = set(orig_comp_ids) - set(new_comp_ids)
        if added_ids:
            self._automove_components_to_wip(added_ids)
        if removed_ids:
            self._autoremove_components_from_wip(removed_ids)
        return res

    @api.model
    def create(self, vals):
        mo = super(mrp_production, self).create(vals)
        self._automove_components_to_wip(mo.component_quants.ids)
        return mo

    @api.multi
    def _calcuate_costs(self):
        total_mat_costs = 0
        total_labor_costs = 0
        total_overhead_costs = 0
        for quant in self.component_quants_used:
            total_mat_costs += quant.total_material_cost
            total_labor_costs += quant.total_labor_cost
            total_overhead_costs += quant.total_overhead_cost
        unit_mat_value = total_mat_costs / len(self.production_quants)
        unit_labor_value = total_labor_costs / len(self.production_quants)
        unit_overhead_value = total_overhead_costs / len(self.production_quants)
        for quant in self.production_quants:
            quant.add_material_cost(unit_mat_value)
            quant.add_labor_cost(unit_labor_value)
            quant.add_labor_oh_cost(unit_overhead_value)

    @api.multi
    def _automove_components_to_wip(self, component_ids):
        taskcode = self._get_mfg_wip_taskcode()
        if taskcode.location_id.usage == 'internal':
            picking_type_id = self.env.ref('stock.picking_type_internal').id
        else:
            picking_type_id = self.env.ref('stock.picking_type_out').id
        move_lines = []
        for comp_id in component_ids:
            comp = self.env['stock.quant'].browse(comp_id)
            # only move things that aren't already at destination location
            if comp.location_id == taskcode.location_id:
                continue
            vals = {
                'name': 'MFG assignment move: ' + self.name,
                'origin': self.name,
                'product_id': comp.product_id.id,
                'product_uom': comp.product_id.uom_id.id,
                'product_uom_qty': comp.qty,
                'location_id': comp.location_id.id,
                'picking_type_id': picking_type_id,
                'target_routing_id': taskcode.routing_id.id,
                'target_routing_line_id': taskcode.routing_line_id.id,
                'target_routing_subrouting_id': taskcode.id,
                'location_dest_id': taskcode.location_id.id,
                'reserved_quant_ids': [(6,0,comp.ids)],
            }
            move_lines.append((0,0,vals))
        if not move_lines:
            return True
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type_id,
            'move_lines': move_lines,
        })
        picking.action_confirm()
        picking.action_done()

    @api.multi
    def _autoremove_components_from_wip(self, component_ids):
        taskcode = self._get_mfg_wip_taskcode()
        if taskcode.location_id.usage == 'internal':
            picking_type_id = self.env.ref('stock.picking_type_internal').id
        else:
            picking_type_id = self.env.ref('stock.picking_type_in').id
        move_lines = []
        for comp_id in component_ids:
            comp = self.env['stock.quant'].browse(comp_id)
            # only move things that aren't in MFG taskcode
            if comp.location_id != taskcode.location_id:
                continue
            vals = {
                'name': 'MFG removal move: ' + self.name,
                'origin': self.name,
                'product_id': comp.product_id.id,
                'product_uom': comp.product_id.uom_id.id,
                'product_uom_qty': comp.qty,
                'location_id': comp.location_id.id,
                'picking_type_id': picking_type_id,
                'target_routing_id': comp.prev_routing_id.id,
                'target_routing_line_id': comp.prev_routing_line_id.id,
                'target_routing_subrouting_id': comp.prev_routing_subrouting_id.id,
                'location_dest_id': comp.prev_location_id.id,
                'reserved_quant_ids': [(6,0,comp.ids)],
            }
            move_lines.append((0,0,vals))
        if not move_lines:
            return True
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type_id,
            'move_lines': move_lines,
        })
        picking.action_confirm()
        picking.action_done()

    @api.multi
    def _automove_consumed_components(self):
        taskcode = self.env.user.company_id.mfg_task_code
        picking_type_id = self.env.ref('stock.picking_type_out').id
        move_lines = []
        for comp in self.component_quants:
            # only move things that aren't in MFG consume taskcode
            if comp.location_id == taskcode.location_id:
                continue
            vals = {
                'name': 'MFG consume move: ' + self.name,
                'origin': self.name,
                'product_id': comp.product_id.id,
                'product_uom': comp.product_id.uom_id.id,
                'product_uom_qty': comp.qty,
                'location_id': comp.location_id.id,
                'picking_type_id': picking_type_id,
                'target_routing_id': taskcode.routing_id.id,
                'target_routing_line_id': taskcode.routing_line_id.id,
                'target_routing_subrouting_id': taskcode.id,
                'location_dest_id': taskcode.location_id.id,
                'reserved_quant_ids': [(6,0,comp.ids)],
            }
            move_lines.append((0,0,vals))
        if not move_lines:
            return True
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type_id,
            'move_lines': move_lines,
        })
        picking.action_confirm()
        picking.action_done()

    @api.multi
    def _automove_produced_products(self):
        taskcode = self.mat_routing_subrouting_id
        if taskcode.location_id.usage == 'internal':
            picking_type_id = self.env.ref('stock.picking_type_internal').id
        else:
            picking_type_id = self.env.ref('stock.picking_type_out').id
        move_lines = []
        for comp in self.production_quants:
            vals = {
                'name': 'MFG production move: ' + self.name,
                'origin': self.name,
                'product_id': comp.product_id.id,
                'product_uom': comp.product_id.uom_id.id,
                'product_uom_qty': comp.qty,
                'location_id': comp.location_id.id,
                'picking_type_id': picking_type_id,
                'target_routing_id': taskcode.routing_id.id,
                'target_routing_line_id': taskcode.routing_line_id.id,
                'target_routing_subrouting_id': taskcode.id,
                'location_dest_id': taskcode.location_id.id,
                'reserved_quant_ids': [(6,0,comp.ids)],
            }
            move_lines.append((0,0,vals))
        if not move_lines:
            return True
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type_id,
            'move_lines': move_lines,
        })
        picking.action_confirm()
        picking.action_done()

    @api.multi
    def _get_mfg_wip_taskcode(self):
        if self.mat_routing_subrouting_id.location_id.usage == 'internal':
            return self.env.user.company_id.wip_task_code
        else:
            return self.mat_routing_subrouting_id


class mrp_production_missing_line(models.Model):
    _name = "mrp.production.missing.line"
    _description = "Components still required for production"

    production_id = fields.Many2one('mrp.production', 'Production')
    product_id = fields.Many2one('product.product', 'Product')
    product_qty = fields.Float('Quantity')


class mrp_production_quant_return(models.TransientModel):
    _name = "mrp.production.quant.return"
    _description = "Items returned from a production assignment"

    production_id = fields.Many2one('mrp.production', 'Production')
    mod_id = fields.Many2one('mrp.production.mod', 'Production Mod')
    lines = fields.One2many('mrp.production.quant.return.line', 'parent_id', string="Remaining Quantities")

    @api.multi
    def set_lines(self):
        lines = []
        prod = self.production_id
        req_product_qty = {}
        for line in prod.component_bom:
            req_product_qty[line.product_id.id] = (line.product_qty * prod.product_qty)
        for quant in prod.component_quants:
            remaining_qty = max(0, quant.qty - req_product_qty[quant.product_id.id])
            if remaining_qty > 0:
                req_product_qty[quant.product_id.id] = 0
                lines.append((0,0,{
                    'quant_id': quant.id,
                    'product_qty': remaining_qty,
                }))
            else:
                req_product_qty[quant.product_id.id] -= quant.qty
        self.lines = lines

    @api.multi
    def set_mod_lines(self):
        # assume that everything got used
        lines = []
        prod = self.mod_id
        for quant in prod.component_quants:
            lines.append((0,0,{
                'quant_id': quant.id,
                'product_qty': 0,
            }))
        self.lines = lines

    @api.multi
    def submit(self):
        returned_quant_ids = []
        for line in self.lines:
            if line.product_qty >= line.quant_id.qty:
                returned_quant_ids.append(line.quant_id.id)
            elif line.product_qty > 0 and line.quant_id.qty > line.product_qty:
                ret_quant = self.env['stock.quant']._quant_split(line.quant_id, (line.quant_id.qty - line.product_qty))
                returned_quant_ids.append(ret_quant.id)
            elif line.product_qty == 0:
                pass
            else:
                raise Warning("Error processing production components")
        if self.production_id:
            mo = self.production_id
        elif self.mod_id:
            mo = self.mod_id
        remaining_ids = set(mo.component_quants.ids) - set(returned_quant_ids)
        mo.write({'component_quants': [(6,0,list(remaining_ids))]})
        mo._autoremove_components_from_wip(returned_quant_ids)
        mo.action_produce()


class mrp_production_quant_return_line(models.TransientModel):
    _name = "mrp.production.quant.return.line"
    _description = "Items returned from a production assignment"

    parent_id = fields.Many2one('mrp.production.quant.return')
    quant_id = fields.Many2one('stock.quant', "Returned Components")
    product_id = fields.Many2one('product.product', related='quant_id.product_id')
    lot_id = fields.Many2one('stock.production.lot', related='quant_id.lot_id')
    product_qty = fields.Float('Quantity')


class mrp_production_mod(models.Model):
    _name = 'mrp.production.mod'
    _description = "Production modification order"
    _order = "id desc"
    _inherit = ['mail.thread', 'ir.needaction_mixin']

    name = fields.Char('Reference', required=True, readonly=True, states={'draft': [('readonly', False)]}, copy=False, default=lambda self: self._next_seq())
    order_type = fields.Selection([('Repair','Repair'), ('Upgrade','Upgrade')], "Type", required=True, readonly=True,
                                  states={'draft': [('readonly', False)]})
    date_planned = fields.Datetime('Scheduled Date', required=True, select=1, readonly=True, states={'draft': [('readonly', False)]}, copy=False,
                                   default=lambda self: time.strftime('%Y-%m-%d %H:%M:%S'))
    date_start = fields.Datetime('Start Date', select=True, readonly=True, copy=False)
    date_finished = fields.Datetime('End Date', select=True, readonly=True, copy=False)
    state = fields.Selection( [('draft', 'New'), ('cancel', 'Cancelled'), ('confirmed', 'Awaiting Raw Materials'),
                            ('ready', 'Ready to Produce'), ('in_production', 'Production Started'), ('done', 'Done')],
                            string='Status', readonly=True, copy=False, default='draft', track_visibility='onchange')
    mat_routing_id = fields.Many2one('account.routing', 'Category', required=True,
                                 states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    mat_routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True,
                                    states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    mat_routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True,
                                    states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    mat_task_shortname = fields.Char("Material Task", compute="_computed_fields")
    labor_routing_id = fields.Many2one('account.routing', 'Category', required=True,
                                 states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    labor_routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True,
                                        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    labor_routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True,
                                        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]})
    labor_task_shortname = fields.Char("Labor Task", compute="_computed_fields")
    # active_on_date = fields.Boolean('Active On Date', compute='_computed_fields', search='_search_active_date')
    source_quants = fields.One2many('stock.quant', 'source_mod_order_id', "Source Items", readonl=True,
                                       states={'draft': [('readonly', False)]},)
    component_quants = fields.One2many('stock.quant', 'reserved_mod_order_id', "Assigned Components",
                                       states={'done': [('readonly', True)], 'cancel': [('readonly', True)]},)
    component_quants_used = fields.One2many('stock.quant', 'used_mod_order_id', "Used Components",
                                       states={'done': [('readonly', True)], 'cancel': [('readonly', True)]},)
    result_products = fields.One2many('mrp.production.mod.line', 'mod_id', "Upgrade Into")
    production_quants = fields.One2many('stock.quant', 'wip_mod_order_id', "Products to Produce",
                                       states={'done': [('readonly', True)], 'cancel': [('readonly', True)]},)
    produced_quants = fields.One2many('stock.quant', 'mod_order_id', "Products Produced", readonly=True)
    production_serials = fields.One2many('stock.production.lot', string="Serials", compute="_computed_fields", search='_search_serials')

    def _next_seq(self):
        return self.env['ir.sequence'].next_by_code('mrp.production')

    @api.one
    @api.depends('state', 'production_quants', 'produced_quants')
    def _computed_fields(self):
        # self.active_on_date = (self.state not in ['done', 'cancel'])
        serials = set()
        for quant in self.production_quants + self.produced_quants:
            serials.add(quant.lot_id)
        self.production_serials = [serial.id for serial in serials]
        self.mat_task_shortname = "{}/{}".format(self.mat_routing_id.name, self.mat_routing_subrouting_id.name)
        self.labor_task_shortname = "{}/{}".format(self.labor_routing_id.name, self.labor_routing_subrouting_id.name)

    # def _search_active_date(self, operator, value):
    #     try:
    #         # keep this line, as it helps check that the value is valid
    #         ts_date = datetime.strptime(value, '%Y-%m-%d')
    #         cr = self._cr
    #         cr.execute("""select id from mrp_production_mod where tsrange(date_start::date, date_finished::date, '[]') @> '{}'::timestamp
    #                         and not state = ANY(array['draft','confirmed','ready','in_production','cancel']);""".format(value))
    #         lines = [row[0] for row in cr.fetchall()]
    #         cr.execute("""select id from mrp_production_mod where date_start::date <= '{}'::timestamp
    #                         and state = ANY(array['confirmed','ready','in_production']) ;""".format(value))
    #         lines += [row[0] for row in cr.fetchall()]
    #         return [('id','in',lines)]
    #     except TypeError:
    #         return [('id','in',[])]

    def _search_serials(self, operator, value):
        ids = []
        search_serials = set(self.env['stock.production.lot'].search([('name','ilike',value)]).ids)
        for mo in self.search([('name','!=',None)]):
            mo_serials = set(serial.id for serial in mo.production_serials)
            if search_serials.intersection(mo_serials):
                ids.append(mo.id)
        return [('id','in',ids)]

    @api.multi
    def write(self, vals):
        orig_comp_ids = self.component_quants.ids + self.source_quants.ids
        if self.order_type == 'Repair' and 'source_quants' in vals:
            vals['production_quants'] = vals['source_quants']
        res = super(mrp_production_mod, self).write(vals)
        new_comp_ids = self.component_quants.ids + self.source_quants.ids
        added_ids = set(new_comp_ids) - set(orig_comp_ids)
        removed_ids = set(orig_comp_ids) - set(new_comp_ids)
        if added_ids:
            self._automove_components_to_wip(added_ids)
        if removed_ids:
            self._autoremove_components_from_wip(removed_ids)
        return res

    @api.model
    def create(self, vals):
        mo = super(mrp_production_mod, self).create(vals)
        mo._automove_components_to_wip(mo.component_quants.ids + mo.source_quants.ids)
        return mo

    @api.multi
    def button_cancel(self):
        if self.order_type == 'Upgrade':
            self.env['stock.quant'].send_to_scrap(self.production_quants.ids, origin=self.name)
        self.write({'component_quants': [(5,None)], 'source_quants': [(5,None)], 'state': 'cancel'})
        return True

    @api.multi
    def button_confirm(self):
        taskcode = self._get_mfg_wip_taskcode()
        if self.order_type == 'Upgrade':
            if not self.result_products:
                raise Warning("Please select resulting products for the upgrade")
            for line in self.result_products:
                # create quants for upgrade
                vals = {
                    'product_id': line.product_id.id,
                    'routing_id': taskcode.routing_id.id,
                    'routing_line_id': taskcode.routing_line_id.id,
                    'routing_subrouting_id': taskcode.id,
                    'location_id': taskcode.location_id.id,
                    'qty': 1,
                    'lot_id': line.lot_id.id,
                    'in_date': datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                    'create_date': datetime.now().strftime(DEFAULT_SERVER_DATETIME_FORMAT),
                    'propagated_from_id': line.source_quant.id,
                    'wip_mod_order_id': self.id,
                }
                self.env['stock.quant'].sudo().create(vals)
        elif self.order_type == 'Repair':
            self.production_quants = self.source_quants
        else:
            raise Warning("Unknown order type")
        self.write({'state':'ready', 'date_start': datetime.today()})

    @api.multi
    def action_quant_return(self):
        ret_wizard = self.env['mrp.production.quant.return'].create({'mod_id':self.id})
        ret_wizard.set_mod_lines()
        view = {
            'name': _('Quant Return Wizard'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mrp.production.quant.return',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_id': ret_wizard.id,
        }
        return view

    @api.multi
    def action_produce(self):
        # consume components
        self._automove_consumed_components()
        self.component_quants_used = self.component_quants
        self.component_quants = [(5,)]
        #calculate costs and add to produced components
        self._calcuate_costs()
        # produce products
        self._automove_produced_products()
        self.produced_quants = self.production_quants
        self.production_quants = [(5,)]
        # finish MO
        self.write({'state':'done', 'date_finished': datetime.today()})

    @api.multi
    def _calcuate_costs(self):
        total_mat_costs = 0
        total_labor_costs = 0
        total_overhead_costs = 0
        for quant in self.component_quants_used:
            total_mat_costs += quant.total_material_cost
            total_labor_costs += quant.total_labor_cost
            total_overhead_costs += quant.total_overhead_cost
        unit_mat_value = total_mat_costs / len(self.production_quants)
        unit_labor_value = total_labor_costs / len(self.production_quants)
        unit_overhead_value = total_overhead_costs / len(self.production_quants)
        if self.order_type == 'Repair':
            repair = True
        elif self.order_type == 'Upgrade':
            # need to carry over source quants to new upgraded quants
            for quant in self.production_quants:
                quant.add_all_costs(quant.propagated_from_id)
            repair = False
        else:
            raise Warning("Unknown mod type")
        for quant in self.production_quants:
            quant.add_material_cost(unit_mat_value, repair=repair)
            quant.add_labor_cost(unit_labor_value, repair=repair)
            quant.add_labor_oh_cost(unit_overhead_value, repair=repair)

    @api.multi
    def _automove_components_to_wip(self, component_ids):
        taskcode = self._get_mfg_wip_taskcode()
        if taskcode.location_id.usage == 'internal':
            picking_type_id = self.env.ref('stock.picking_type_internal').id
        else:
            picking_type_id = self.env.ref('stock.picking_type_out').id
        move_lines = []
        for comp_id in component_ids:
            comp = self.env['stock.quant'].browse(comp_id)
            # only move things that aren't already at destination location
            if comp.location_id == taskcode.location_id:
                continue
            vals = {
                'name': 'MFG mod assignment move: ' + self.name,
                'origin': self.name,
                'product_id': comp.product_id.id,
                'product_uom': comp.product_id.uom_id.id,
                'product_uom_qty': comp.qty,
                'location_id': comp.location_id.id,
                'picking_type_id': picking_type_id,
                'target_routing_id': taskcode.routing_id.id,
                'target_routing_line_id': taskcode.routing_line_id.id,
                'target_routing_subrouting_id': taskcode.id,
                'location_dest_id': taskcode.location_id.id,
                'reserved_quant_ids': [(6,0,comp.ids)],
            }
            move_lines.append((0,0,vals))
        if not move_lines:
            return True
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type_id,
            'move_lines': move_lines,
        })
        picking.action_confirm()
        picking.action_done()

    @api.multi
    def _autoremove_components_from_wip(self, component_ids):
        taskcode = self._get_mfg_wip_taskcode()
        if taskcode.location_id.usage == 'internal':
            picking_type_id = self.env.ref('stock.picking_type_internal').id
        else:
            picking_type_id = self.env.ref('stock.picking_type_in').id
        move_lines = []
        for comp_id in component_ids:
            comp = self.env['stock.quant'].browse(comp_id)
            # only move things that aren't in MFG taskcode
            if comp.location_id != taskcode.location_id:
                continue
            vals = {
                'name': 'MFG mod removal move: ' + self.name,
                'origin': self.name,
                'product_id': comp.product_id.id,
                'product_uom': comp.product_id.uom_id.id,
                'product_uom_qty': comp.qty,
                'location_id': comp.location_id.id,
                'picking_type_id': picking_type_id,
                'target_routing_id': comp.prev_routing_id.id,
                'target_routing_line_id': comp.prev_routing_line_id.id,
                'target_routing_subrouting_id': comp.prev_routing_subrouting_id.id,
                'location_dest_id': comp.prev_location_id.id,
                'reserved_quant_ids': [(6,0,comp.ids)],
            }
            move_lines.append((0,0,vals))
        if not move_lines:
            return True
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type_id,
            'move_lines': move_lines,
        })
        picking.action_confirm()
        picking.action_done()

    @api.multi
    def _automove_consumed_components(self):
        taskcode = self.env.user.company_id.mfg_task_code
        picking_type_id = self.env.ref('stock.picking_type_out').id
        move_lines = []
        if self.order_type == 'Upgrade':
            quants = self.component_quants + self.source_quants
        else:
            quants = self.component_quants
        for comp in quants:
            # only move things that aren't in MFG consume taskcode
            if comp.location_id == taskcode.location_id:
                continue
            vals = {
                'name': 'MFG consume move: ' + self.name,
                'origin': self.name,
                'product_id': comp.product_id.id,
                'product_uom': comp.product_id.uom_id.id,
                'product_uom_qty': comp.qty,
                'location_id': comp.location_id.id,
                'picking_type_id': picking_type_id,
                'target_routing_id': taskcode.routing_id.id,
                'target_routing_line_id': taskcode.routing_line_id.id,
                'target_routing_subrouting_id': taskcode.id,
                'location_dest_id': taskcode.location_id.id,
                'reserved_quant_ids': [(6,0,comp.ids)],
            }
            move_lines.append((0,0,vals))
        if not move_lines:
            return True
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type_id,
            'move_lines': move_lines,
        })
        picking.action_confirm()
        picking.action_done()

    @api.multi
    def _automove_produced_products(self):
        taskcode = self.mat_routing_subrouting_id
        if taskcode.location_id.usage == 'internal':
            picking_type_id = self.env.ref('stock.picking_type_internal').id
        else:
            picking_type_id = self.env.ref('stock.picking_type_out').id
        move_lines = []
        for comp in self.production_quants:
            vals = {
                'name': 'MFG production move: ' + self.name,
                'origin': self.name,
                'product_id': comp.product_id.id,
                'product_uom': comp.product_id.uom_id.id,
                'product_uom_qty': comp.qty,
                'location_id': comp.location_id.id,
                'picking_type_id': picking_type_id,
                'target_routing_id': taskcode.routing_id.id,
                'target_routing_line_id': taskcode.routing_line_id.id,
                'target_routing_subrouting_id': taskcode.id,
                'location_dest_id': taskcode.location_id.id,
                'reserved_quant_ids': [(6,0,comp.ids)],
            }
            move_lines.append((0,0,vals))
        if not move_lines:
            return True
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type_id,
            'move_lines': move_lines,
        })
        picking.action_confirm()
        picking.action_done()

    @api.multi
    def _get_mfg_wip_taskcode(self):
        if self.mat_routing_subrouting_id.location_id.usage == 'internal':
            return self.env.user.company_id.wip_task_code
        else:
            return self.mat_routing_subrouting_id

    @api.onchange('source_quants')
    def onchange_source_quants(self):
        if self.order_type == 'Upgrade':
            vals = []
            for quant in self.source_quants:
                vals.append((0,0,{
                    'mod_id': self.id,
                    'source_quant': quant.id,
                    'lot_id': quant.lot_id.id,
                }))
            self.result_products = vals

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


class mrp_production_mod_line(models.Model):
    _name = "mrp.production.mod.line"
    _description = "Line items for upgrade into other products"

    mod_id = fields.Many2one('mrp.production.mod', "Modification Order")
    source_quant = fields.Many2one('stock.quant', "Source")
    product_id = fields.Many2one('product.product', "Product")
    # product_name = fields.Char("Product", related='product_id.product_tmpl_id.name')
    lot_id = fields.Many2one('stock.production.lot', "Serial")


class mrp_bom(models.Model):
    _inherit = 'mrp.bom'

    @api.v7
    def onchange_product_tmpl_id(self, cr, uid, ids, product_tmpl_id, product_qty=0, context=None):
        """ Changes UoM and name if product_id changes.
        @param product_id: Changed product_id
        @return:  Dictionary of changed values
        """
        res = {}
        if product_tmpl_id:
            prod = self.pool.get('product.template').browse(cr, uid, product_tmpl_id, context=context)
            res['value'] = {
                'product_uom': prod.uom_id.id,
            }
        return res


