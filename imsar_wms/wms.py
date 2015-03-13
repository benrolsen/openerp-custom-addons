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
    def quants_reserve(self, cr, uid, quants, move, link=False, context=None):
        quants = quant_obj.quants_get_prefered_domain(cr, uid, ops.location_id, move.product_id, qty, domain=domain, prefered_domain_list=[], restrict_lot_id=move.restrict_lot_id.id, restrict_partner_id=move.restrict_partner_id.id, context=context)

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


class stock_picking(models.Model):
    _inherit = "stock.picking"
    _description = "Picking List"
    _order = "priority desc, date desc, id desc"

    @api.multi
    def action_invoice_create(self, journal_id=False, group=False, type='out_invoice'):
        # overrides same method from account_anglo_saxon/stock.py
        # Note that this function side-steps tax fiscal position, at least until we find
        # a need for it.
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
    def _prepare_values_extra_move(self, cr, uid, op, product, remaining_qty, context=None):
        res = super(stock_picking, self)._prepare_values_extra_move(cr, uid, op, product, remaining_qty, context)
        res['source_routing_id'] = op.linked_move_operation_ids.move_id.source_routing_id.id
        res['source_routing_line_id'] = op.linked_move_operation_ids.move_id.source_routing_line_id.id
        res['source_routing_subrouting_id'] = op.linked_move_operation_ids.move_id.source_routing_subrouting_id.id
        res['target_routing_id'] = op.linked_move_operation_ids.move_id.target_routing_id.id
        res['target_routing_line_id'] = op.linked_move_operation_ids.move_id.target_routing_line_id.id
        res['target_routing_subrouting_id'] = op.linked_move_operation_ids.move_id.target_routing_subrouting_id.id
        return res


class stock_move_operation_link(models.Model):
    _inherit = "stock.move.operation.link"

    @api.v7
    def get_specific_domain(self, cr, uid, record, context=None):
        # only called for linked moves
        domain = super(stock_move_operation_link, self).get_specific_domain(cr, uid, record, context)
        move = record.move_id
        domain.append(('routing_id', '=', move.source_routing_id.id))
        domain.append(('routing_line_id', '=', move.source_routing_line_id.id))
        domain.append(('routing_subrouting_id', '=', move.routing_subrouting_id.id))
        print(domain)
        return domain


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
        # print('_anglo_saxon_sale_move_lines')
        return []

    @api.v7
    def _anglo_saxon_purchase_move_lines(self, cr, uid, i_line, res, context=None):
        # print('_anglo_saxon_purchase_move_lines')
        return []


class account_invoice(models.Model):
    _inherit = "account.invoice"

    # @api.v7
    # def _prepare_refund(self, cr, uid, invoice, date=None, period_id=None, description=None, journal_id=None, context=None):
    #     # account_anglo_saxon does something for refunds here, may want to revisit this
    #     pass

    # @api.multi
    # def finalize_invoice_move_lines(self, move_lines):
    #     # print(move_lines)
    #     for temp_line in move_lines:
    #         line = temp_line[2]
    #         print("DR {}, CR {}, GA {}, AA {}".format(line['debit'],line['credit'],line['account_id'],line['analytic_account_id']))
    #     return move_lines


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


class account_routing_purchase_preferences(models.TransientModel):
    # This is a temporary model that lets purchase.order.line entries "remember"
    # the last used routing info, so that new lines auto-fill with it
    _name = "account.routing.purchase.preferences"
    _description = "Account routing preference for purchase order lines"

    user_id = fields.Many2one('res.users', 'User', )
    routing_id = fields.Many2one('account.routing', 'Category',)
    routing_line_id = fields.Many2one('account.routing.line', 'Type',)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Identifier',)


