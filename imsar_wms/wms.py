from datetime import date
from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp
from openerp.exceptions import Warning


class stock_move(models.Model):
    _inherit = 'stock.move'

    dest_employee = fields.Many2one('hr.employee', 'Deliver to', copy=True)
    # source is empty when creating a stock move from a PO
    source_routing_id = fields.Many2one('account.routing', 'Source Category', required=True, copy=True)
    source_routing_line_id = fields.Many2one('account.routing.line', 'Source Type', required=True, copy=True)
    source_routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Source Identifier', required=True, copy=True)
    target_routing_id = fields.Many2one('account.routing', 'Target Category', required=True, copy=True)
    target_routing_line_id = fields.Many2one('account.routing.line', 'Target Type', required=True, copy=True)
    target_routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Target Identifier', required=True, copy=True)
    source_task_name = fields.Char('Source Task', compute='_compute_names')
    target_task_name = fields.Char('Target Task', compute='_compute_names')
    picking_is_incoming_type = fields.Boolean(related='picking_id.is_incoming_type')

    @api.one
    def _compute_names(self):
        self.target_task_name = "{}/{}".format(self.target_routing_id.name, self.target_routing_subrouting_id.name)
        self.source_task_name = "{}/{}".format(self.source_routing_id.name, self.source_routing_subrouting_id.name)

    @api.v7
    def _get_invoice_line_vals(self, cr, uid, move, partner, inv_type, context=None):
        # overwrites the function from both stock_account/stock.py and account_anglo_saxon/stock.py
        # TODO address the refund case like the original function
        source_account = move.source_routing_subrouting_id.account_id.id
        source_analytic = move.source_routing_subrouting_id.account_analytic_id.id
        uos_id = move.product_uom.id
        quantity = move.product_uom_qty
        if move.product_uos:
            uos_id = move.product_uos.id
            quantity = move.product_uos_qty
        return {
            'name': move.name,
            'account_id': source_account,
            'account_analytic_id': source_analytic,
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

    @api.onchange('source_routing_id')
    def onchange_source_route(self):
        self.source_routing_line_id = ''
        mat_types = self.env.user.company_id.material_account_type_ids
        for routing_line in self.source_routing_id.routing_lines:
            if routing_line.account_type_id.id in mat_types.ids:
                self.source_routing_line_id = routing_line.id
                return

    @api.onchange('source_routing_line_id')
    def onchange_source_routing_line(self):
        self.source_routing_subrouting_id = ''

    @api.onchange('source_routing_subrouting_id')
    def onchange_source_subroute(self):
        self.location_id = self.source_routing_subrouting_id.location_id.id

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
        self.target_routing_subrouting_id = ''

    @api.onchange('target_routing_subrouting_id')
    def onchange_target_subroute(self):
        self.location_dest_id = self.target_routing_subrouting_id.location_id.id


class stock_quant(models.Model):
    _inherit = 'stock.quant'

    # for IMSAR, task code essentially replaces location
    routing_id = fields.Many2one('account.routing', 'Category', )
    routing_line_id = fields.Many2one('account.routing.line', 'Type', )
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Identifier', )
    cost = fields.Float('Unit Cost', related='material_cost', store=True)
    material_cost = fields.Float('Material Unit Cost')
    labor_cost = fields.Float('Labor Cost')
    overhead_cost = fields.Float('Overhead Cost')
    purchase_order_id = fields.Many2one('purchase.order', 'Purchase Order', copy=True, readonly=True)
    mfg_order_id = fields.Many2one('mrp.production', 'Manufacturing Order', copy=True, readonly=True)

    @api.v7
    def _get_inventory_value(self, cr, uid, quant, context=None):
        # labor costs are applied per quant, not per unit
        return ((quant.material_cost + quant.overhead_cost) * quant.qty) + quant.labor_cost

    @api.cr_uid_ids_context
    def _price_update(self, cr, uid, quant_ids, newprice, context=None):
        pass

    @api.model
    def _account_entry_move(self, quants, move):
        # copied and modified from stock_account/stock_account.py, stock.quant function _account_entry_move
        # Note: this does not call super
        if move.product_id.valuation != 'real_time':
            return False
        for q in quants:
            if q.owner_id:
                return False
            if q.qty <= 0:
                return False

        # TODO address the refund case like the original function
        source_account = move.source_routing_subrouting_id.account_id.id
        target_account = move.target_routing_subrouting_id.account_id.id
        journal_id = self.env.user.company_id.stock_journal.id
        self._create_account_move_line(quants, move, source_account, target_account, journal_id)

    @api.v7
    def _prepare_account_move_line(self, cr, uid, move, qty, cost, credit_account_id, debit_account_id, context=None):
        # TODO address the refund case like the original function
        source_analytic = move.source_routing_subrouting_id.account_analytic_id.id
        target_analytic = move.target_routing_subrouting_id.account_analytic_id.id
        lines = super(stock_quant, self)._prepare_account_move_line(cr, uid, move, qty, cost, credit_account_id, debit_account_id, context)
        debit_tuple, credit_tuple = lines
        debit_line_vals = debit_tuple[2]
        credit_line_vals = credit_tuple[2]
        credit_line_vals['analytic_account_id'] = source_analytic
        debit_line_vals['analytic_account_id'] = target_analytic
        return [(0, 0, debit_line_vals), (0, 0, credit_line_vals)]

    @api.v7
    def _quant_create(self, cr, uid, qty, move, lot_id=False, owner_id=False, src_package_id=False, dest_package_id=False,
                      force_location_from=False, force_location_to=False, context=None):
        # Note that this function is only used by stock.move
        quant = super(stock_quant, self)._quant_create(cr, uid, qty, move, lot_id, owner_id, src_package_id, dest_package_id,
                      force_location_from, force_location_to, context)
        vals = dict()
        if move.purchase_line_id:
            vals.update({'purchase_order_id': move.purchase_line_id.order_id.id})
        if move.production_id:
            vals.update({'mfg_order_id': move.production_id.id})
        vals.update({'material_cost': move.price_unit})
        vals.update({'routing_id': move.target_routing_id.id})
        vals.update({'routing_line_id': move.target_routing_line_id.id})
        vals.update({'routing_subrouting_id': move.target_routing_subrouting_id.id})
        quant.sudo().write(vals)

    @api.multi
    def button_move_mat_cost(self):
        vals = {
            'quant_id': self.id,
            'cost_type': 'material',
        }
        move_cost = self.env['stock.quant.move_cost'].create(vals)
        view = {
            'name': _('Move Cost'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'stock.quant.move_cost',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_id': move_cost.id,
        }
        return view

    @api.multi
    def button_move_labor_cost(self):
        print('nothing')

    @api.multi
    def button_move_oh_cost(self):
        print('nothing')


class stock_picking(models.Model):
    _inherit = "stock.picking"
    _description = "Picking List"
    _order = "priority desc, date desc, id desc"

    is_incoming_type = fields.Boolean('Is Internal', compute='_check_type')
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
                    if line.product_id and not line.product_id.type == 'service':
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
        res['source_routing_id'] = op.linked_move_operation_ids.move_id.source_routing_id.id
        res['source_routing_line_id'] = op.linked_move_operation_ids.move_id.source_routing_line_id.id
        res['source_routing_subrouting_id'] = op.linked_move_operation_ids.move_id.source_routing_subrouting_id.id
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
                vals = {
                    'name': "{}-{}".format(picking.origin,line.linked_move_operation_ids.move_id.id),
                    'product_id': line.product_id.id,
                    'base_cost': line.linked_move_operation_ids.move_id.price_unit,
                }
                lot_id = self.pool.get('stock.production.lot').search(cr, uid, [('name','=',vals['name'])])
                if not lot_id:
                    lot_id = self.pool.get('stock.production.lot').create(cr, uid, vals)
                else:
                    lot_id = lot_id[0]
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


class stock_production_lot(models.Model):
    _inherit = 'stock.production.lot'

    base_cost = fields.Float('Base unit cost', default=0.0, digits=(1,4), required=True)

    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'For IMSAR internal tracking, every serial/lot number must be unique!'),
    ]


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


class purchase_order(models.Model):
    _inherit = 'purchase.order'

    @api.model
    def view_init(self, fields_list):
        # this makes sure that the current user has an account.routing.purchase.preferences line
        pref = self.env['account.routing.purchase.preferences'].search([('user_id','=',self._uid)])
        if not pref:
            pref = self.env['account.routing.purchase.preferences'].create({'user_id':self._uid})

    @api.model
    def _prepare_inv_line(self, account_id, order_line):
        """
        This function does not call super and invalidates the work done by _choose_account_from_po_line
        from purchase/purchase.py and account_anglo_saxon/purchase.py, in order to choose the
        correct account and analytic.
        If there's a non-service product, put the debit (expense) into
        the interim receiving account/analytic, and let the stock.move make a balancing credit in both and
        put the debit in the actual asset/expense account according to task code.
        If there's no product, or it's a service product, there will be no stock.move, so the invoice
        should pick the asset/expense account/analytic directly.
        Also note that this function side-steps tax fiscal position, at least until we find
        a need for it.
        """
        if order_line.product_id and not order_line.product_id.type == 'service':
            # use warehouse settings for interim receiving of physical products
            account_id = self.env.user.company_id.interim_receiving.account_id.id
            analytic_id = self.env.user.company_id.interim_receiving.account_analytic_id.id
            if not account_id or not analytic_id:
                raise Warning(_('Error!'), _('You must define an interim receiving task code in the Warehouse settings.'))
        else:
            account_id = order_line.routing_subrouting_id.account_id.id
            analytic_id = order_line.routing_subrouting_id.account_analytic_id.id
        return {
            'name': order_line.name,
            'account_id': account_id,
            'account_analytic_id': analytic_id,
            'price_unit': order_line.price_unit or 0.0,
            'quantity': order_line.product_qty,
            'product_id': order_line.product_id.id or False,
            'uos_id': order_line.product_uom.id or False,
            'invoice_line_tax_id': [(6, 0, [x.id for x in order_line.taxes_id])],
            'purchase_line_id': order_line.id,
            'routing_id': order_line.routing_id.id,
            'routing_line_id': order_line.routing_subrouting_id.id,
            'routing_subrouting_id': order_line.routing_subrouting_id.id,
        }

    @api.model
    def _prepare_order_line_move(self, order, order_line, picking_id, group_id):
    # def _prepare_order_line_move(self, cr, uid, order, order_line, picking_id, group_id, context=None):
        res = super(purchase_order,self)._prepare_order_line_move(order, order_line, picking_id, group_id)
        for vals in res:
            vals['dest_employee'] = order_line.dest_employee.id
            vals['source_routing_id'] = self.env.user.company_id.interim_receiving.routing_id.id
            vals['source_routing_line_id'] = self.env.user.company_id.interim_receiving.routing_line_id.id
            vals['source_routing_subrouting_id'] = self.env.user.company_id.interim_receiving.id
            vals['target_routing_id'] = order_line.routing_id.id
            vals['target_routing_line_id'] = order_line.routing_line_id.id
            vals['target_routing_subrouting_id'] = order_line.routing_subrouting_id.id
        return res


class purchase_order_line(models.Model):
    _inherit = 'purchase.order.line'

    routing_id = fields.Many2one('account.routing', 'Category', required=True, default=lambda self: self._get_routing_id())
    routing_line_id = fields.Many2one('account.routing.line', 'Type', required=True, default=lambda self: self._get_routing_line_id())
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Identifier', required=True, default=lambda self: self._get_routing_subrouting_id())
    shipping_method = fields.Char('Shipping Method')
    dest_employee = fields.Many2one('hr.employee', 'Deliver to')

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        pref = self.env['account.routing.purchase.preferences'].search([('user_id','=',self._uid)])
        if self.routing_id:
            pref.write({'routing_id': self.routing_id.id})
        if self.routing_line_id not in self.routing_id.routing_lines:
            self.routing_line_id = ''

    @api.onchange('routing_line_id')
    def onchange_routing_line_id(self):
        pref = self.env['account.routing.purchase.preferences'].search([('user_id','=',self._uid)])
        if self.routing_line_id:
            pref.write({'routing_line_id': self.routing_line_id.id})
        if self.routing_subrouting_id not in self.routing_line_id.subrouting_ids:
            self.routing_subrouting_id = ''

    @api.onchange('routing_subrouting_id')
    def onchange_routing_subrouting_id(self):
        pref = self.env['account.routing.purchase.preferences'].search([('user_id','=',self._uid)])
        if self.routing_subrouting_id:
            pref.write({'routing_subrouting_id': self.routing_subrouting_id.id})

    @api.model
    def _get_routing_id(self):
        pref = self.env['account.routing.purchase.preferences'].search([('user_id','=',self._uid)])
        return pref.routing_id.id

    @api.model
    def _get_routing_line_id(self):
        pref = self.env['account.routing.purchase.preferences'].search([('user_id','=',self._uid)])
        return pref.routing_line_id.id

    @api.model
    def _get_routing_subrouting_id(self):
        pref = self.env['account.routing.purchase.preferences'].search([('user_id','=',self._uid)])
        return pref.routing_subrouting_id.id

    @api.v7
    def onchange_product_id(self, cr, uid, ids, pricelist_id, product_id, qty, uom_id,
            partner_id, date_order=False, fiscal_position_id=False, date_planned=False,
            name=False, price_unit=False, state='draft', context=None):
        res = super(purchase_order_line, self).onchange_product_id(cr, uid, ids, pricelist_id, product_id, qty, uom_id,
            partner_id, date_order, fiscal_position_id, date_planned, name, price_unit, state, context)
        product = self.pool.get('product.product').browse(cr, uid, product_id)
        price = price_unit
        if not price_unit:
            price = product.standard_price
        res['value'].update({'price_unit': price,})
        return res


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
            self.quant_id.material_cost -= self.amount
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
