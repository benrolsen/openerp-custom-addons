from datetime import date, datetime
from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp
from openerp.exceptions import Warning
from openerp import SUPERUSER_ID


class stock_move(models.Model):
    _inherit = 'stock.move'

    quant_ids = fields.Many2many('stock.quant', 'stock_quant_move_rel', 'move_id', 'quant_id', 'Moved Quants', copy=False,
                                 states={'done': [('readonly', True)], 'cancel': [('readonly', True)]},)
    reserved_quant_ids = fields.One2many('stock.quant', 'reservation_id', 'Reserved quants',
                                 states={'done': [('readonly', True)], 'cancel': [('readonly', True)]},)
    dest_employee = fields.Many2one('hr.employee', 'Deliver to', copy=True)
    target_routing_id = fields.Many2one('account.routing', 'Target Category', required=True, copy=True,
                                        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]},)
    target_routing_line_id = fields.Many2one('account.routing.line', 'Target Type', required=True, copy=True,
                                        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]},)
    target_routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Target Identifier', required=True, copy=True,
                                        states={'done': [('readonly', True)], 'cancel': [('readonly', True)]},)
    target_task_name = fields.Char('Target Task', compute='_compute_names')
    picking_is_incoming_type = fields.Boolean(related='picking_id.is_incoming_type')
    accounting_review_flag = fields.Boolean('Needs manual accounting review', default=False)
    mfg_order_id = fields.Many2one('mrp.production', 'Created by MFG Order', select=True, copy=False)
    kitting_production_id = fields.Many2one('mrp.production', 'Kitted to Production Order', select=True)

    @api.one
    def _compute_names(self):
        self.target_task_name = "{}/{}".format(self.target_routing_id.name, self.target_routing_subrouting_id.name)

    @api.v7
    def _get_invoice_line_vals(self, cr, uid, move, partner, inv_type, context=None):
        # overwrites the function from both stock_account/stock.py and account_anglo_saxon/stock.py
        # TODO address the refund case like the original function
        uos_id = move.product_uom.id
        quantity = move.product_uom_qty
        if move.product_uos:
            uos_id = move.product_uos.id
            quantity = move.product_uos_qty
        return {
            'name': move.name,
            'account_id': move.target_routing_subrouting_id.account_id.id,
            'account_analytic_id': move.target_routing_subrouting_id.account_analytic_id.id,
            'product_id': move.product_id.id,
            'uos_id': uos_id,
            'quantity': quantity,
            'price_unit': self._get_price_unit_invoice(cr, uid, move, inv_type),
            'discount': 0.0,
            'routing_id': move.target_routing_id.id,
            'routing_line_id': move.target_routing_line_id.id,
            'routing_subrouting_id': move.target_routing_subrouting_id.id,
            'move_id': move.id,
        }

    @api.onchange('target_routing_id')
    def onchange_target_route(self):
        self.target_routing_line_id = ''
        mat_types = self.env.user.company_id.material_account_type_ids
        for routing_line in self.target_routing_id.routing_lines:
            if routing_line.account_type_id.id in mat_types.ids:
                self.target_routing_line_id = routing_line.id
                break

    @api.onchange('target_routing_line_id')
    def onchange_target_routing_line(self):
        if self.target_routing_subrouting_id and self.target_routing_subrouting_id.routing_line_id != self.target_routing_line_id:
            self.target_routing_subrouting_id = ''

    @api.onchange('target_routing_subrouting_id')
    def onchange_target_subroute(self):
        self.location_dest_id = self.target_routing_subrouting_id.location_id.id

    @api.multi
    def write(self, vals):
        super(stock_move, self).write(vals)
        for move in self:
            if move.raw_material_production_id and move.location_dest_id.usage not in ['customer','production']:
                raise Warning("All MFG stock movements must be to external locations, such as production or customer.")

    @api.v7
    def check_tracking(self, cr, uid, move, lot_id, context=None):
        # rather than required lot restrictions, we're going to force quants to be manually assigned ahead of time
        assigned_qty = sum([quant.qty for quant in move.reserved_quant_ids])
        if not move.picking_is_incoming_type and assigned_qty < move.product_uom_qty:
            raise Warning("Assigned quants do not meet required quantity!")

    @api.multi
    def action_assign(self):
        for move in self:
            assigned_qty = sum([quant.qty for quant in move.reserved_quant_ids])
            if assigned_qty >= move.product_uom_qty:
                move.force_assign()


class stock_quant(models.Model):
    _inherit = 'stock.quant'

    # for IMSAR, task code essentially replaces location
    routing_id = fields.Many2one('account.routing', 'Category', )
    routing_line_id = fields.Many2one('account.routing.line', 'Type', )
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Identifier', )
    task_name = fields.Char('Task', compute='_computed_fields')
    material_cost = fields.Float('Material Unit Cost')
    labor_cost = fields.Float('Labor Unit Cost')
    overhead_cost = fields.Float('Overhead Unit Cost')
    cost = fields.Float('Full Unit Cost', compute='_compute_costs', inverse='_set_cost', store=True)
    repair_material_cost = fields.Float('Repair Material Cost')
    repair_labor_cost = fields.Float('Repair Labor Cost')
    repair_overhead_cost = fields.Float('Repair Overhead Cost')
    total_material_cost = fields.Float('Total Material Cost', compute='_compute_costs')
    total_labor_cost = fields.Float('Total Labor Cost', compute='_compute_costs')
    total_overhead_cost = fields.Float('Total OH Cost', compute='_compute_costs')
    inventory_value = fields.Float('Inventory Value', compute='_compute_costs', store=True)
    purchase_order_id = fields.Many2one('purchase.order', 'Created by Purchase Order', copy=True, readonly=True)
    reserved_mfg_order_id = fields.Many2one('mrp.production', 'Assigned to Manufacturing Order', readonly=True)
    used_mfg_order_id = fields.Many2one('mrp.production', 'Used by Manufacturing Order', readonly=True)
    wip_mfg_order_id = fields.Many2one('mrp.production', 'Manufacturing Order WIP', readonly=True)
    mfg_order_id = fields.Many2one('mrp.production', 'Created by Manufacturing Order', copy=True, readonly=True)
    source_mod_order_id = fields.Many2one('mrp.production.mod', 'Assigned to Modification Order', readonly=True)
    reserved_mod_order_id = fields.Many2one('mrp.production.mod', 'Assigned to Modification Order', readonly=True)
    used_mod_order_id = fields.Many2one('mrp.production.mod', 'Used by Modification Order', readonly=True)
    wip_mod_order_id = fields.Many2one('mrp.production.mod', 'Modification Order WIP', readonly=True)
    mod_order_id = fields.Many2one('mrp.production.mod', 'Created by Modification Order', copy=True, readonly=True)
    # available = fields.Boolean('Available', compute='_computed_fields', store=True)
    available = fields.Boolean('Available', compute='_computed_fields', store=False)
    prev_routing_id = fields.Many2one('account.routing', 'Previous Category', copy=True)
    prev_routing_line_id = fields.Many2one('account.routing.line', 'Previous Type', copy=True)
    prev_routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Previous Identifier', copy=True)
    prev_location_id = fields.Many2one('stock.location', 'Previous Location', copy=True)

    @api.one
    @api.depends('material_cost', 'labor_cost', 'overhead_cost', 'qty')
    def _compute_costs(self):
        self.cost = self.material_cost + self.overhead_cost + self.labor_cost
        self.inventory_value = self.cost * self.qty
        self.total_material_cost = self.material_cost * self.qty
        self.total_labor_cost = self.labor_cost * self.qty
        self.total_overhead_cost = self.overhead_cost * self.qty

    @api.one
    @api.depends('routing_id', 'routing_line_id', 'routing_subrouting_id','reservation_id','reserved_mfg_order_id','reserved_mod_order_id','source_mod_order_id','location_id')
    def _computed_fields(self):
        self.task_name = "{}/{}/{}".format(self.routing_id.name, self.routing_line_id.name, self.routing_subrouting_id.name)
        if (self.reservation_id or self.reserved_mfg_order_id or self.wip_mfg_order_id or
            self.reserved_mod_order_id or self.wip_mod_order_id or self.source_mod_order_id) or self.location_id.usage == 'production':
            self.available = False
        else:
            self.available = True

    @api.one
    def _set_cost(self):
        self.material_cost = self.cost

    @api.v7
    def _get_inventory_value(self, cr, uid, quant, context=None):
        return (quant.material_cost * quant.qty) + (quant.overhead_cost * quant.qty) + (quant.labor_cost * quant.qty)

    @api.model
    def _account_entry_move(self, quants, move):
        # don't do automatic accounting in Odoo, create a historical record instead
        for quant in quants:
            vals = {
                'quant_id': quant.id,
                'move_id': move.id,
                'source_routing_id': quant.prev_routing_id.id or None,
                'source_routing_line_id': quant.prev_routing_line_id.id or None,
                'source_routing_subrouting_id': quant.prev_routing_subrouting_id.id or None,
                'source_loc': quant.prev_location_id.id or move.location_id.id,
                'target_routing_id': move.target_routing_id.id,
                'target_routing_line_id': move.target_routing_line_id.id,
                'target_routing_subrouting_id': move.target_routing_subrouting_id.id,
                'dest_loc': move.location_dest_id.id,
            }
            self.env['stock.quant.move.record'].create(vals)

    @api.model
    def _make_debit_move_line(self, move, amount, debit_account, debit_analytic=None, quantity=None):
        partner_id = move.picking_id.partner_id.commercial_partner_id.id or False
        debit_line_vals = {
                    'name': move.name,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_id.uom_id.id,
                    'date': move.date,
                    'partner_id': partner_id,
                    'debit': amount > 0 and amount or 0,
                    'credit': amount < 0 and -amount or 0,
                    'account_id': debit_account,
                    'analytic_account_id': debit_analytic,
        }
        if quantity:
            debit_line_vals.update({'quantity': quantity,})
        return (0, 0, debit_line_vals)

    @api.model
    def _make_credit_move_line(self, move, amount, credit_account, credit_analytic=None, quantity=None):
        partner_id = move.picking_id.partner_id.commercial_partner_id.id or False
        credit_line_vals = {
                    'name': move.name,
                    'product_id': move.product_id.id,
                    'product_uom_id': move.product_id.uom_id.id,
                    'date': move.date,
                    'partner_id': partner_id,
                    'debit': amount < 0 and -amount or 0,
                    'credit': amount > 0 and amount or 0,
                    'account_id': credit_account,
                    'analytic_account_id': credit_analytic,
        }
        if quantity:
            credit_line_vals.update({'quantity': quantity,})
        return (0, 0, credit_line_vals)

    @api.v7
    def _quant_create(self, cr, uid, qty, move, lot_id=False, owner_id=False, src_package_id=False, dest_package_id=False,
                      force_location_from=False, force_location_to=False, context=None):
        # Note that this function is only used by stock.move
        quant = super(stock_quant, self)._quant_create(cr, uid, qty, move, lot_id, owner_id, src_package_id, dest_package_id,
                      force_location_from, force_location_to, context)
        vals = dict()
        if move.purchase_line_id:
            vals.update({'purchase_order_id': move.purchase_line_id.order_id.id})
        if move.mfg_order_id:
            vals.update({'mfg_order_id': move.mfg_order_id.id})
        vals.update({'material_cost': move.price_unit})
        vals.update({'routing_id': move.target_routing_id.id})
        vals.update({'routing_line_id': move.target_routing_line_id.id})
        vals.update({'routing_subrouting_id': move.target_routing_subrouting_id.id})
        quant.sudo().write(vals)
        return quant

    @api.v7
    def move_quants_write(self, cr, uid, quants, move, location_dest_id, dest_package_id, context=None):
        for quant in quants:
            quant.write({
                'prev_routing_id': quant.routing_id.id,
                'prev_routing_line_id': quant.routing_line_id.id,
                'prev_routing_subrouting_id': quant.routing_subrouting_id.id,
                'prev_location_id': quant.location_id.id,
            })
        super(stock_quant, self).move_quants_write(cr, uid, quants, move, location_dest_id, dest_package_id, context)
        vals = {'routing_id': move.target_routing_id.id,
                'routing_line_id': move.target_routing_line_id.id,
                'routing_subrouting_id': move.target_routing_subrouting_id.id}
        self.write(cr, SUPERUSER_ID, [q.id for q in quants], vals, context=context)

    @api.model
    def send_to_scrap(self, quant_ids, origin=None):
        taskcode = self.env.user.company_id.attrition
        picking_type_id = self.env.ref('stock.picking_type_out').id
        move_lines = []
        for quant_id in quant_ids:
            quant = self.env['stock.quant'].browse(quant_id)
            # only move things that aren't already at destination location
            if quant.location_id == taskcode.location_id:
                continue
            vals = {
                'name': 'Sent to attrition/scrap',
                'product_id': quant.product_id.id,
                'product_uom': quant.product_id.uom_id.id,
                'product_uom_qty': quant.qty,
                'location_id': quant.location_id.id,
                'picking_type_id': picking_type_id,
                'target_routing_id': taskcode.routing_id.id,
                'target_routing_line_id': taskcode.routing_line_id.id,
                'target_routing_subrouting_id': taskcode.id,
                'location_dest_id': taskcode.location_id.id,
                'reserved_quant_ids': [(6,0,quant.ids)],
            }
            if origin:
                vals['origin'] = origin
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
    def add_material_cost(self, amount, repair=False):
        if not amount:
            return None
        unit_cost = amount / self.qty
        if repair:
            self.write({'repair_material_cost': self.repair_material_cost + unit_cost})
        else:
            self.write({'material_cost': self.material_cost + unit_cost})
            self.lot_id.write({'base_cost': self.lot_id.base_cost + unit_cost})

    @api.multi
    def add_labor_cost(self, amount, repair=False):
        if not amount:
            return None
        unit_cost = amount / self.qty
        if repair:
            self.write({'repair_labor_cost': self.repair_labor_cost + unit_cost})
        else:
            self.write({'labor_cost': self.labor_cost + unit_cost})
            self.lot_id.write({'base_cost': self.lot_id.base_cost + unit_cost})

    @api.multi
    def add_labor_oh_cost(self, amount, repair=False):
        if not amount:
            return None
        unit_cost = amount / self.qty
        if repair:
            self.write({'repair_overhead_cost': self.repair_overhead_cost + unit_cost})
        else:
            self.write({'overhead_cost': self.overhead_cost + unit_cost})
            self.lot_id.write({'base_cost': self.lot_id.base_cost + unit_cost})

    @api.multi
    def add_all_costs(self, source_quant):
        self.write({
            'material_cost': self.material_cost + source_quant.material_cost,
            'repair_material_cost': self.repair_material_cost + source_quant.repair_material_cost,
            'labor_cost': self.labor_cost + source_quant.labor_cost,
            'repair_labor_cost': self.repair_labor_cost + source_quant.repair_labor_cost,
            'overhead_cost': self.overhead_cost + source_quant.overhead_cost,
            'repair_overhead_cost': self.repair_overhead_cost + source_quant.repair_overhead_cost,
        })

    @api.multi
    def button_split_wizard(self):
        split_wizard = self.env['stock.quant.split'].create({
            'quant': self.id,
        })
        view = {
            'name': _('Quant Split Wizard'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'stock.quant.split',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_id': split_wizard.id,
        }
        return view


class stock_picking(models.Model):
    _inherit = "stock.picking"
    _description = "Picking List"
    _order = "priority desc, date desc, id desc"

    is_incoming_type = fields.Boolean('Is Incoming', compute='_check_type')
    do_recalc_lot_cost = fields.Boolean('Need to recompute lot base cost')

    @api.one
    @api.depends('picking_type_id')
    def _check_type(self):
        if self.picking_type_id == self.env.ref('stock.picking_type_in'):
            self.is_incoming_type = True
        else:
            self.is_incoming_type = False

    @api.multi
    def action_invoice_create(self, journal_id=False, group=False, type='out_invoice'):
        # overrides same method from account_anglo_saxon/stock.py
        # Note that this function side-steps tax fiscal position, at least until we find a need for it.
        res = super(stock_picking, self).action_invoice_create(journal_id, group, type)
        if type in ('in_invoice', 'in_refund'):
            for invoice in self.env['account.invoice'].browse(res):
                for line in invoice.invoice_line:
                    if line.product_id and not line.product_id.type == 'service' and \
                            line.routing_subrouting_id.location_id.usage == 'internal':
                        # use warehouse settings for interim receiving of physical products
                        account_id = self.env.user.company_id.interim_receiving.account_id.id
                        analytic_id = self.env.user.company_id.interim_receiving.account_analytic_id.id
                        if not account_id or not analytic_id:
                            raise Warning(_('Error!'), _('You must define an interim receiving task code in the Warehouse settings.'))
                    else:
                        account_id = line.routing_subrouting_id.account_id.id
                        analytic_id = line.routing_subrouting_id.account_analytic_id.id
                    line.write({'account_id': account_id, 'account_analytic_id': analytic_id})
        return res

    @api.v7
    def _create_extra_moves(self, cr, uid, picking, context=None):
        moves = super(stock_picking, self)._create_extra_moves(cr, uid, picking, context)
        # if we got more than expected on receiving, we need to adjust the unit price based on PO line
        if picking.is_incoming_type:
            for move in self.pool.get('stock.move').browse(cr, uid, moves):
                if move.move_orig_ids:
                    orig_move = self.pool.get('stock.move').browse(cr, uid, move.move_orig_ids.ids[0])
                    total_qty = orig_move.product_qty + move.product_qty
                    orig_subtotal = orig_move.product_qty * orig_move.price_unit
                    new_price_unit = orig_subtotal / total_qty
                    move.write({'price_unit': new_price_unit})
                    orig_move.write({'price_unit': new_price_unit})
                    # We can't get to the op and lot at this point, so set a flag to correct it later down the line
                    picking.write({'do_recalc_lot_cost': True})
                else:
                    # no source move means no PO line info, so value is 0
                    move.write({'price_unit': 0.0})
        return moves

    @api.v7
    def _prepare_values_extra_move(self, cr, uid, op, product, remaining_qty, context=None):
        res = super(stock_picking, self)._prepare_values_extra_move(cr, uid, op, product, remaining_qty, context)
        res['move_orig_ids'] = [(6,0, [op.linked_move_operation_ids.move_id.id])]
        res['target_routing_id'] = op.linked_move_operation_ids.move_id.target_routing_id.id
        res['target_routing_line_id'] = op.linked_move_operation_ids.move_id.target_routing_line_id.id
        res['target_routing_subrouting_id'] = op.linked_move_operation_ids.move_id.target_routing_subrouting_id.id
        res['purchase_line_id'] = op.linked_move_operation_ids.move_id.purchase_line_id.id
        res['origin'] = op.linked_move_operation_ids.move_id.origin
        return res

    @api.cr_uid_ids_context
    def do_enter_transfer_details(self, cr, uid, picking_id, context=None):
        picking = self.pool.get('stock.picking').browse(cr, uid, picking_id)
        # this button should recompute packages every time
        picking.do_prepare_partial()
        if picking.is_incoming_type:
            # automatically create lot/serials to receive into
            for line in picking.pack_operation_ids:
                move_id = line.linked_move_operation_ids[0].move_id
                vals = {
                    'product_id': line.product_id.id,
                    'base_cost': move_id.price_unit,
                }
                lot_id = self.pool.get('stock.production.lot').create(cr, uid, vals)
                line.write({'lot_id': lot_id})
        return super(stock_picking, self).do_enter_transfer_details(cr, uid, picking_id)

    @api.cr_uid_ids_context
    def do_transfer(self, cr, uid, picking_ids, context=None):
        res = super(stock_picking, self).do_transfer(cr, uid, picking_ids, context)
        for picking in self.browse(cr, uid, picking_ids, context=context):
            if picking.do_recalc_lot_cost:
                for move in picking.move_lines:
                    for op in move.linked_move_operation_ids.operation_id:
                        lot = op.lot_id
                        lot.write({'base_cost': move.price_unit})
        return res

    @api.multi
    def action_confirm(self):
        # copied from and overwrites function from stock/stock.py
        if self.picking_type_id == self.env.ref('stock.picking_type_in'):
            self.force_assign()
        elif self.picking_type_id == self.env.ref('stock.picking_type_internal'):
            # internal
            pass
        elif self.picking_type_id == self.env.ref('stock.picking_type_out'):
            # shipping/outgoing
            pass
        for line in self.move_lines:
            if line.state == 'draft':
                line.action_confirm()
        return True


class stock_picking_type(models.Model):
    _inherit = "stock.picking.type"

    @api.multi
    def name_get(self):
        res = []
        for record in self:
            res.append((record.id, record.name))
        return res


class stock_production_lot(models.Model):
    _inherit = 'stock.production.lot'

    serial_seq = fields.Char('Serial Sequence', default=lambda self: self._serial_seq(), required=True)
    name = fields.Char('Serial', compute='_computed_fields', store=True, index=True)
    base_cost = fields.Float('Base unit cost', default=0.0, digits=(1,4), required=True)
    production_id = fields.Many2one('mrp.production', "MFG Order")
    active_on_date = fields.Boolean('Active On Date', compute='_computed_fields', search='_search_active_date')

    @api.depends('serial_seq','product_id')
    def _computed_fields(self):
        self.active_on_date = True
        self.name = "{}{}".format(self.product_id.product_tmpl_id.serial_prefix, self.serial_seq)

    def _search_active_date(self, operator, value):
        try:
            # the strptime just validates the date in the try/catch
            ts_date = datetime.strptime(value, '%Y-%m-%d')
            res = []
            cr = self._cr
            cr.execute("""select id from mrp_production where tsrange(date_start::date, date_finished::date, '[]') @> '{}'::timestamp
                            and not state = ANY(array['draft','confirmed','ready','in_production','cancel']);""".format(value))
            lines = [row[0] for row in cr.fetchall()]
            cr.execute("""select id from mrp_production where date_start::date <= '{}'::timestamp
                            and state = ANY(array['confirmed','ready','in_production']) ;""".format(value))
            lines += [row[0] for row in cr.fetchall()]
            mfg_orders = self.env['mrp.production'].browse(lines)
            for mfg_order in mfg_orders:
                res += mfg_order.production_serials.ids
            cr.execute("""select id from mrp_production_mod where tsrange(date_start::date, date_finished::date, '[]') @> '{}'::timestamp
                            and not state = ANY(array['draft','confirmed','ready','in_production','cancel']);""".format(value))
            lines = [row[0] for row in cr.fetchall()]
            cr.execute("""select id from mrp_production_mod where date_start::date <= '{}'::timestamp
                            and state = ANY(array['confirmed','ready','in_production']) ;""".format(value))
            lines += [row[0] for row in cr.fetchall()]
            mod_orders = self.env['mrp.production.mod'].browse(lines)
            for mod_order in mod_orders:
                res += mod_order.production_serials.ids
            return [('id','in',res)]
        except TypeError:
            return [('id','in',[])]

    def _serial_seq(self):
        return self.env['ir.sequence'].next_by_code('stock.lot.serial')

    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'For IMSAR internal tracking, every serial/lot number must be unique!'),
    ]
    _defaults = {
        'name': '',
    }


class stock_inventory(models.Model):
    _inherit = "stock.inventory"

    @api.v7
    def _get_inventory_lines(self, cr, uid, inventory, context=None):
        # replaces the same function from stock/stock.py, does not call super()
        location_obj = self.pool.get('stock.location')
        product_obj = self.pool.get('product.product')
        location_ids = location_obj.search(cr, uid, [('id', 'child_of', [inventory.location_id.id])], context=context)
        domain = ' location_id in %s'
        args = (tuple(location_ids),)
        if inventory.partner_id:
            domain += ' and owner_id = %s'
            args += (inventory.partner_id.id,)
        if inventory.lot_id:
            domain += ' and lot_id = %s'
            args += (inventory.lot_id.id,)
        if inventory.product_id:
            domain += ' and product_id = %s'
            args += (inventory.product_id.id,)
        if inventory.package_id:
            domain += ' and package_id = %s'
            args += (inventory.package_id.id,)

        cr.execute('''
           SELECT product_id, sum(qty) as product_qty, location_id, routing_id, routing_line_id, routing_subrouting_id, lot_id as prod_lot_id, package_id, owner_id as partner_id
           FROM stock_quant WHERE''' + domain + '''
           GROUP BY product_id, location_id, routing_id, routing_line_id, routing_subrouting_id, lot_id, package_id, partner_id
        ''', args)
        vals = []
        for product_line in cr.dictfetchall():
            #replace the None the dictionary by False, because falsy values are tested later on
            for key, value in product_line.items():
                if not value:
                    product_line[key] = False
            product_line['inventory_id'] = inventory.id
            product_line['theoretical_qty'] = product_line['product_qty']
            if product_line['product_id']:
                product = product_obj.browse(cr, uid, product_line['product_id'], context=context)
                product_line['product_uom_id'] = product.uom_id.id
            vals.append(product_line)
        return vals


class stock_inventory_line(models.Model):
    _inherit = "stock.inventory.line"

    routing_id = fields.Many2one('account.routing', 'Category', required=True)
    routing_line_id = fields.Many2one('account.routing.line', 'Type', required=True)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Identifier', required=True)

    @api.v7
    def _resolve_inventory_line(self, cr, uid, inventory_line, context=None):
        raise Warning("FIX ME")
        # copied from and replaces function from stock/stock.py
        stock_move_obj = self.pool.get('stock.move')
        diff = inventory_line.theoretical_qty - inventory_line.product_qty
        if not diff:
            return
        #each theorical_lines where difference between theoretical and checked quantities is not 0 is a line for which we need to create a stock move
        vals = {
            'name': _('INV:') + (inventory_line.inventory_id.name or ''),
            'product_id': inventory_line.product_id.id,
            'product_uom': inventory_line.product_uom_id.id,
            'date': inventory_line.inventory_id.date,
            'company_id': inventory_line.inventory_id.company_id.id,
            'inventory_id': inventory_line.inventory_id.id,
            'state': 'confirmed',
            'restrict_lot_id': inventory_line.prod_lot_id.id,
            'restrict_partner_id': inventory_line.partner_id.id,
            'price_unit': inventory_line.prod_lot_id.base_cost,
         }
        inventory_location_id = inventory_line.product_id.property_stock_inventory.id
        if diff < 0:
            #found more than expected
            vals['source_routing_id'] = inventory_line.inventory_id.company_id.attrition.routing_id.id
            vals['source_routing_line_id'] = inventory_line.inventory_id.company_id.attrition.routing_line_id.id
            vals['source_routing_subrouting_id'] = inventory_line.inventory_id.company_id.attrition.id
            vals['location_id'] = inventory_line.inventory_id.company_id.attrition.location_id.id
            vals['target_routing_id'] = inventory_line.routing_id.id
            vals['target_routing_line_id'] = inventory_line.routing_line_id.id
            vals['target_routing_subrouting_id'] = inventory_line.routing_subrouting_id.id
            vals['location_dest_id'] = inventory_line.routing_subrouting_id.location_id.id
            vals['product_uom_qty'] = -diff
        else:
            #found fewer than expected
            vals['source_routing_id'] = inventory_line.routing_id.id
            vals['source_routing_line_id'] = inventory_line.routing_line_id.id
            vals['source_routing_subrouting_id'] = inventory_line.routing_subrouting_id.id
            vals['location_id'] = inventory_line.routing_subrouting_id.location_id.id
            vals['target_routing_id'] = inventory_line.inventory_id.company_id.attrition.routing_id.id
            vals['target_routing_line_id'] = inventory_line.inventory_id.company_id.attrition.routing_line_id.id
            vals['target_routing_subrouting_id'] = inventory_line.inventory_id.company_id.attrition.id
            vals['location_dest_id'] = inventory_line.inventory_id.company_id.attrition.location_id.id
            vals['product_uom_qty'] = diff
        return stock_move_obj.create(cr, uid, vals, context=context)

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        self.routing_line_id = ''
        mat_types = self.env.user.company_id.material_account_type_ids
        for routing_line in self.routing_id.routing_lines:
            if routing_line.account_type_id.id in mat_types.ids:
                self.routing_line_id = routing_line.id
                return

    @api.onchange('routing_line_id')
    def onchange_routing_line_id(self):
        self.routing_subrouting_id = ''

    @api.onchange('routing_subrouting_id')
    def onchange_routing_subrouting_id(self):
        pass


class stock_change_product_qty(models.TransientModel):
    _inherit = "stock.change.product.qty"

    routing_id = fields.Many2one('account.routing', 'Category', required=True)
    routing_line_id = fields.Many2one('account.routing.line', 'Type', required=True)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Identifier', required=True)

    @api.v7
    def change_product_qty(self, cr, uid, ids, context=None):
        # copied from and replaces function from stock/stock_change_product_qty.py
        if context is None:
            context = {}

        inventory_obj = self.pool.get('stock.inventory')
        inventory_line_obj = self.pool.get('stock.inventory.line')

        for data in self.browse(cr, uid, ids, context=context):
            if data.new_quantity < 0:
                raise Warning(_('Warning!'), _('Quantity cannot be negative.'))
            ctx = context.copy()
            ctx['location'] = data.location_id.id
            ctx['lot_id'] = data.lot_id.id
            inventory_id = inventory_obj.create(cr, uid, {
                'name': _('INV: %s') % (data.product_id.name),
                'product_id': data.product_id.id,
                'location_id': data.location_id.id,
                'lot_id': data.lot_id.id}, context=context)
            product = data.product_id.with_context(location=data.location_id.id, lot_id= data.lot_id.id)
            th_qty = product.qty_available
            line_data = {
                'inventory_id': inventory_id,
                'product_qty': data.new_quantity,
                'location_id': data.location_id.id,
                'product_id': data.product_id.id,
                'product_uom_id': data.product_id.uom_id.id,
                'theoretical_qty': th_qty,
                'prod_lot_id': data.lot_id.id,
                'routing_id': data.routing_id.id,
                'routing_line_id': data.routing_line_id.id,
                'routing_subrouting_id': data.routing_subrouting_id.id,
            }
            inventory_line_obj.create(cr , uid, line_data, context=context)
            inventory_obj.action_done(cr, uid, [inventory_id], context=context)
        return {}

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        self.routing_line_id = ''
        mat_types = self.env.user.company_id.material_account_type_ids
        for routing_line in self.routing_id.routing_lines:
            if routing_line.account_type_id.id in mat_types.ids:
                self.routing_line_id = routing_line.id
                return

    @api.onchange('routing_line_id')
    def onchange_routing_line_id(self):
        self.routing_subrouting_id = ''

    @api.onchange('routing_subrouting_id')
    def onchange_routing_subrouting_id(self):
        self.location_id = self.routing_subrouting_id.location_id.id


class purchase_request(models.Model):
    _name = "purchase.request"
    _description = "Purchase Requisition"
    _inherit = ['mail.thread']

    # model columns
    name = fields.Char('Requisition Number', copy=False)
    created_by = fields.Many2one('res.users', "Created by", required=True, default=lambda self: self.env.user)
    deliver_to = fields.Many2one('res.users', "Deliver to", required=True, copy=True)
    state = fields.Selection([('draft','Draft'),('waiting','Waiting for Approval'),('confirm','Confirmed'),('done','Delivered')],
                             string="Status", default='draft', index=True, required=True, readonly=True)
    suggested_vendor = fields.Char('Suggested Vendor')
    line_ids = fields.One2many('purchase.request.line', 'req_id', string='Req Lines')
    linked_po = fields.Many2one('purchase.order', 'PO #')


class purchase_request_line(models.Model):
    _name = "purchase.request.line"
    _description = "Purchase Requisition Line"

    # model columns
    name = fields.Char('Item Description', required=True)
    req_id = fields.Many2one('purchase.request', string='Requisition ID', required=True, ondelete='cascade')
    product_id = fields.Many2one('product.product', 'Product', domain=[('purchase_ok', '=', True)])
    product_uom_id = fields.Many2one('product.uom', 'Product Unit of Measure')
    product_qty = fields.Float('Quantity', required=True, digits_compute=dp.get_precision('Product Unit of Measure'))
    manufacturer = fields.Char('Manufacturer')
    mfg_part = fields.Char('MFG Part #')
    product_price = fields.Float('Unit Price', required=True, digits_compute= dp.get_precision('Product Price'))
    date_needed = fields.Date('Date Needed')
    state = fields.Selection([('draft','Draft'),('waiting','Waiting for Approval'),('approved','Approved')], string='Status', readonly=True)
    routing_id = fields.Many2one('account.routing', 'Category', required=True)
    routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True)
    account_analytic_id = fields.Many2one('account.analytic.account', related='routing_subrouting_id.account_analytic_id', readonly=True)
    approved_by = fields.Many2one('res.users', string='Approved by')

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        self.routing_line_id = ''

    @api.onchange('routing_line_id')
    def onchange_routing_line_id(self):
        self.routing_subrouting_id = ''


class account_invoice_line(models.Model):
    _inherit = "account.invoice.line"

    @api.onchange('product_id')
    def onchange_product_id(self):
        # replaces product_id_change in account_invoice.py, so we can use new-style onchange
        self.name = self.product_id.name
        self.price_unit = self.price_unit or self.product_id.standard_price
        self.uos_id = self.uos_id or self.product_id.uom_id.id
        if self.product_id and not self.product_id.type == 'service':
            account_id = self.env.user.company_id.interim_receiving.account_id.id
            analytic_id = self.env.user.company_id.interim_receiving.account_analytic_id.id
            if not account_id or not analytic_id:
                raise Warning(_('Error!'), _('You must define an interim receiving task code in the Warehouse settings.'))
            self.account_id = account_id
            self.account_analytic_id = analytic_id
        else:
            self.account_id = self.routing_subrouting_id.account_id
            self.account_analytic_id = self.routing_subrouting_id.account_analytic_id


    @api.onchange('routing_subrouting_id')
    def onchange_analytic_id(self):
        # overwrite this function from account_routing to deal with non-service products
        if not self.product_id or self.product_id.type == 'service':
            self.account_id = self.routing_subrouting_id.account_id
            self.account_analytic_id = self.routing_subrouting_id.account_analytic_id

    @api.v7
    def _anglo_saxon_sale_move_lines(self, cr, uid, i_line, res, context=None):
        return []

    @api.v7
    def _anglo_saxon_purchase_move_lines(self, cr, uid, i_line, res, context=None):
        return []


class account_voucher(models.Model):
    _inherit = "account.voucher"

    @api.multi
    def write(self, vals):
        res = super(account_voucher, self).write(vals)
        # make it auto-compute the total without falling into an infinite loop from compute_tax()
        keys = vals.keys()
        if not (len(keys) == 2 and 'amount' in keys and 'tax_amount' in keys):
            self.compute_tax()
        return res


class account_voucher_line(models.Model):
    _inherit = "account.voucher.line"

    routing_id = fields.Many2one('account.routing', 'Category', required=True)
    routing_line_id = fields.Many2one('account.routing.line', 'Type', required=True)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Identifier', required=True)

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        self.routing_line_id = ''

    @api.onchange('routing_line_id')
    def onchange_routing_line_id(self):
        self.routing_subrouting_id = ''

    @api.onchange('routing_subrouting_id')
    def onchange_subrouting_id(self):
        self.account_id = self.routing_subrouting_id.account_id
        self.account_analytic_id = self.routing_subrouting_id.account_analytic_id


class stock_warehouse_orderpoint(models.Model):
    _inherit = 'stock.warehouse.orderpoint'

    routing_id = fields.Many2one('account.routing', 'Category', required=True,)
    routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True,)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True,)

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        self.routing_line_id = ''

    @api.onchange('routing_line_id')
    def onchange_routing_line_id(self):
        self.routing_subrouting_id = ''


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


class account_routing_purchase_preferences(models.TransientModel):
    # This is a temporary model that lets purchase.order.line entries "remember"
    # the last used routing info, so that new lines auto-fill with it
    _name = "account.routing.purchase.preferences"
    _description = "Account routing preference for purchase order lines"

    user_id = fields.Many2one('res.users', 'User', )
    routing_id = fields.Many2one('account.routing', 'Category',)
    routing_line_id = fields.Many2one('account.routing.line', 'Type',)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Identifier',)


class quant_move_cost(models.TransientModel):
    _name = "stock.quant.move_cost"
    _description = "Wizard to move cost from quant"

    quant_id = fields.Many2one('stock.quant')
    cost_type = fields.Selection([('material','Material'),('labor','Labor'),('overhead','Overhead'),], "Cost Type")
    amount = fields.Float('Amount', default=0.0)
    account_id = fields.Many2one('account.account', 'Real Account')
    account_analytic_id = fields.Many2one('account.analytic.account', 'Analytic Account')

    @api.multi
    def confirm(self):
        if self.cost_type == 'material':
            self.quant_id.material_cost -= self.amount
        if self.cost_type == 'labor':
            self.quant_id.labor_cost -= self.amount
        if self.cost_type == 'overhead':
            self.quant_id.overhead_cost -= self.amount
        move_lines = list()
        # for positive amount, debit the target account, credit the inventory account
        debit_line = {
            'name': 'Quant cost adjustment',
            'debit': self.amount if self.amount >= 0.0 else 0.0,
            'credit': -self.amount if self.amount < 0.0 else 0.0,
            'account_id': self.account_id.id,
            'analytic_account_id': self.account_analytic_id.id,
        }
        credit_line = {
            'name': 'Quant cost adjustment',
            'debit': -self.amount if self.amount < 0.0 else 0.0,
            'credit': self.amount if self.amount >= 0.0 else 0.0,
            'account_id': self.quant_id.routing_subrouting_id.account_id.id,
            'analytic_account_id': self.quant_id.routing_subrouting_id.account_analytic_id.id,
        }
        move_lines.append((0, 0, debit_line))
        move_lines.append((0, 0, credit_line))
        move_vals = {
            'ref': 'Quant Move Cost',
            'line_id': move_lines,
            'journal_id': self.env.user.company_id.stock_journal.id,
            'date': date.today(),
            'narration': '',
            'company_id': self.env.user.company_id.id,
        }
        move = self.env['account.move'].with_context(self._context).create(move_vals)
        move.post()


class quant_split_wizard(models.TransientModel):
    _name = "stock.quant.split"
    _description = "Split a quant"

    quant = fields.Many2one('stock.quant')
    qty = fields.Float("Split Quantity")

    @api.multi
    def submit(self):
        if self.qty:
            self.env['stock.quant']._quant_split(self.quant, self.qty)


class stock_quant_move_record(models.Model):
    _name = "stock.quant.move.record"
    _description = "Historical record of quant movements for accounting"

    _order = 'date desc'

    quant_id = fields.Many2one('stock.quant', 'Moved Quant', readonly=True)
    lot_id = fields.Many2one('stock.production.lot', 'Serial', related='quant_id.lot_id')
    qty = fields.Float('Quantity', related='quant_id.qty')
    total_material_cost = fields.Float('Total Material Cost', related='quant_id.total_material_cost')
    total_labor_cost = fields.Float('Total Labor Cost', related='quant_id.total_labor_cost')
    total_overhead_cost = fields.Float('Total OH Cost', related='quant_id.total_overhead_cost')
    inventory_value = fields.Float('Total Value', related='quant_id.inventory_value')
    product_id = fields.Many2one('product.product', 'Product', related='quant_id.product_id')
    move_id = fields.Many2one('stock.move', 'Stock move', readonly=True)
    origin = fields.Char('Source', related='move_id.origin')
    date = fields.Datetime('Date', related='move_id.date', store=True)
    picking_type_id = fields.Many2one('stock.picking.type', 'Picking Type', related='move_id.picking_type_id')
    name = fields.Char('Description', related='move_id.name', readonly=True)
    source_routing_id = fields.Many2one('account.routing', 'Source Category', copy=True, readonly=True)
    source_routing_line_id = fields.Many2one('account.routing.line', 'Source Type', copy=True, readonly=True)
    source_routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Source Identifier', copy=True, readonly=True)
    source_task_name = fields.Char('Source Task', compute='_compute_names')
    source_loc = fields.Many2one('stock.location', 'Source Location', readonly=True)
    target_routing_id = fields.Many2one('account.routing', 'Target Category', required=True, copy=True, readonly=True)
    target_routing_line_id = fields.Many2one('account.routing.line', 'Target Type', required=True, copy=True, readonly=True)
    target_routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Target Identifier', required=True, copy=True, readonly=True)
    target_task_name = fields.Char('Target Task', compute='_compute_names')
    dest_loc = fields.Many2one('stock.location', 'Destination Location', readonly=True)

    @api.one
    def _compute_names(self):
        if self.source_routing_id:
            self.source_task_name = "{}/{}/{}".format(self.source_routing_id.name, self.source_routing_line_id.name, self.source_routing_subrouting_id.name)
        else:
            self.source_task_name = ""
        self.target_task_name = "{}/{}/{}".format(self.target_routing_id.name, self.target_routing_line_id.name, self.target_routing_subrouting_id.name)


class stock_quant_move_record_search(models.TransientModel):
    _name = "stock.quant.move.record.search"
    _description = "Search date range for quant move records"

    start_date = fields.Date('Start Date')
    end_date = fields.Date('End Date')

    @api.multi
    def submit(self):
        ids = []
        ids = self.env['stock.quant.move.record'].search([('date','>=',self.start_date), ('date','<=',self.end_date)]).ids
        view = {
            'name': _('Quant Move Search'),
            'view_type': 'form',
            'view_mode': 'tree',
            'res_model': 'stock.quant.move.record',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'domain': [('id','in',list(ids))],
        }
        return view


