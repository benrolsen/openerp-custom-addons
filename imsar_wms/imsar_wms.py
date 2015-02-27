from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp
from openerp.exceptions import Warning


class stock_move(models.Model):
    _inherit = 'stock.move'

    dest_employee = fields.Many2one('hr.employee', 'Deliver to')
    # for now, these are informational, therefore not required
    source_routing_id = fields.Many2one('account.routing', 'Source Category', )
    source_routing_line_id = fields.Many2one('account.routing.line', 'Source Type', )
    source_routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Source Identifier', )
    target_routing_id = fields.Many2one('account.routing', 'Target Category', )
    target_routing_line_id = fields.Many2one('account.routing.line', 'Target Type', )
    target_routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Target Identifier', )

    @api.v7
    def _get_invoice_line_vals(self, cr, uid, move, partner, inv_type, context=None):
        # overwrites the function from both stock_account/stock.py and account_anglo_saxon/stock.py
        # TODO address the refund case like the original function
        if move.source_routing_subrouting_id:
            # I'm not sure what would cause a manual stock move (which would have a source task)
            # to generate an invoice, but here it is in case we need it
            source_account = move.source_routing_subrouting_id.account_id.id
            source_analytic = move.source_routing_subrouting_id.account_analytic_id.id
        else:
            # currently only picks category, not product.template
            source_account = move.product_id.categ_id.property_stock_account_input_categ.id
            source_analytic = move.product_id.categ_id.analytic_input_categ.id
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


class stock_quant(models.Model):
    _inherit = 'stock.quant'

    cost = fields.Float('Unit Cost', compute='_total_cost', store=True)
    material_cost = fields.Float('Material Cost')
    labor_cost = fields.Float('Labor Cost')
    overhead_cost = fields.Float('Overhead Cost')
    purchase_order_id = fields.Many2one('purchase.order', 'Purchase Order', copy=True, readonly=True)
    mfg_order_id = fields.Many2one('mrp.production', 'Manufacturing Order', copy=True, readonly=True)

    @api.one
    @api.depends('material_cost', 'labor_cost', 'overhead_cost')
    def _total_cost(self):
        self.cost = self.material_cost + self.labor_cost + self.overhead_cost

    @api.cr_uid_ids_context
    def _price_update(self, cr, uid, quant_ids, newprice, context=None):
        pass

    @api.v7
    def _account_entry_move(self, cr, uid, quants, move, context=None):
        # copied and modified from stock_account/stock_account.py, stock.quant function _account_entry_move
        if move.product_id.valuation != 'real_time':
            return False
        for q in quants:
            if q.owner_id:
                return False
            if q.qty <= 0:
                return False

        # Use task codes if they exist, or product category inputs if not
        # TODO address the refund case like the original function
        if move.source_routing_subrouting_id:
            source_account = move.source_routing_subrouting_id.account_id.id
            source_analytic = move.source_routing_subrouting_id.account_analytic_id.id
        else:
            # currently only picks category, not product.template
            source_account = move.product_id.product_tmpl_id.categ_id.property_stock_account_input_categ.id
            source_analytic = move.product_id.product_tmpl_id.categ_id.analytic_input_categ.id
        target_account = move.target_routing_subrouting_id.account_id.id
        target_analytic = move.target_routing_subrouting_id.account_analytic_id.id
        journal_id = move.product_id.product_tmpl_id.categ_id.property_stock_journal.id
        self._create_account_move_line(cr, uid, quants, move, source_account, target_account, journal_id, context=context)

    # @api.v7
    # def _prepare_account_move_line(self, cr, uid, move, qty, cost, credit_account_id, debit_account_id, context=None):
    #     lines = super(stock_quant, self)._prepare_account_move_line(cr, uid, move, qty, cost, credit_account_id, debit_account_id, context)
    #     print(lines)
    #     # add analytic accounts here?
    #     return lines

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

    analytic_input_categ = fields.Many2one('account.analytic.account', 'Stock Input Analytic')
    analytic_output_categ = fields.Many2one('account.analytic.account', 'Stock Output Analytic')

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
    analytic_input_categ = fields.Many2one('account.analytic.account', 'Stock Input Analytic')
    analytic_output_categ = fields.Many2one('account.analytic.account', 'Stock Output Analytic')

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


class purchase_order(models.Model):
    _inherit = 'purchase.order'

    @api.model
    def view_init(self, fields_list):
        # this makes sure that the current user has an account.routing.purchase.preferences line
        pref = self.env['account.routing.purchase.preferences'].search([('user_id','=',self._uid)])
        if not pref:
            pref = self.env['account.routing.purchase.preferences'].create({'user_id':self._uid})

    # @api.v7
    # def _choose_account_from_po_line(self, cr, uid, po_line, context=None):
    #     # this is copied from purchase/purchase.py and account_anglo_saxon/purchase.py,
    #     # because of the else case when there's no product. It needs to change from the
    #     # system default expense account to the task code expense account
    #     fiscal_obj = self.pool.get('account.fiscal.position')
    #     if po_line.product_id and not po_line.product_id.type == 'service':
    #         acc_id = po_line.product_id.property_stock_account_input and po_line.product_id.property_stock_account_input.id
    #         if not acc_id:
    #             acc_id = po_line.product_id.categ_id.property_stock_account_input_categ and po_line.product_id.categ_id.property_stock_account_input_categ.id
    #         if not acc_id:
    #             raise Warning(_('Error!'), _('Define a Stock Input Account for this product: "%s" (id:%d).') % (po_line.product_id.name, po_line.product_id.id,))
    #     else:
    #         acc_id = po_line.routing_subrouting_id.account_id.id
    #     fpos = po_line.order_id.fiscal_position or False
    #     return fiscal_obj.map_account(cr, uid, fpos, acc_id)

    @api.model
    def _prepare_inv_line(self, account_id, order_line):
        """
        This function does not call super and invalidates the work done by _choose_account_from_po_line
        from purchase/purchase.py and account_anglo_saxon/purchase.py, in order to choose the
        correct account and analytic.
        If there's a non-service product, put the debit (expense) into
        the stock input account/analytic, and let the stock.move make a balancing credit in both and
        put the debit in the actual asset/expense account according to task code.
        If there's no product, or it's a service product, there will be no stock.move, so the invoice
        should pick the asset/expense account/analytic directly.
        Also note that this function side-steps tax fiscal position, at least until we find
        a need for it.
        """
        analytic_id = False
        if order_line.product_id and not order_line.product_id.type == 'service':
            # for now we're only using product category, but these exist on product template as well
            if order_line.product_id.categ_id.property_stock_account_input_categ:
                account_id = order_line.product_id.categ_id.property_stock_account_input_categ.id
            if order_line.product_id.categ_id.analytic_input_categ:
                analytic_id = order_line.product_id.categ_id.analytic_input_categ.id
            if not account_id or not analytic_id:
                raise Warning(_('Error!'), _('Define a Stock Input Account and Analytic for this product: "%s" (id:%d).') % (order_line.product_id.name, order_line.product_id.id,))
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

    @api.v7
    def _prepare_order_line_move(self, cr, uid, order, order_line, picking_id, group_id, context=None):
        res = super(purchase_order,self)._prepare_order_line_move(cr, uid, order, order_line, picking_id, group_id, context)
        for vals in res:
            vals['dest_employee'] = order_line.dest_employee.id
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
            if self.product_id.categ_id.property_stock_account_input_categ:
                account_id = self.product_id.categ_id.property_stock_account_input_categ.id
            if self.product_id.categ_id.analytic_input_categ:
                analytic_id = self.product_id.categ_id.analytic_input_categ.id
            if not account_id or not analytic_id:
                raise Warning(_('Error!'), _('Define a Stock Input Account and Analytic for this product: "%s" (id:%d).') % (self.product_id.name, self.product_id.id,))
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

    # @api.v7
    # def product_id_change(self, cr, uid, ids, product, uom_id, qty=0, name='', type='out_invoice', partner_id=False, fposition_id=False, price_unit=False, currency_id=False, company_id=None, context=None):
    #     fiscal_pool = self.pool.get('account.fiscal.position')
    #     res = super(account_invoice_line, self).product_id_change(cr, uid, ids, product, uom_id, qty, name, type, partner_id, fposition_id, price_unit, currency_id, company_id, context)
    #     if not product:
    #         return res
    #     if type in ('in_invoice','in_refund'):
    #         product_obj = self.pool.get('product.product').browse(cr, uid, product, context=context)
    #         oa = product_obj.property_stock_account_input and product_obj.property_stock_account_input.id
    #         if not oa:
    #             oa = product_obj.categ_id.property_stock_account_input_categ and product_obj.categ_id.property_stock_account_input_categ.id
    #         if oa and product_obj.type != 'service':
    #             fpos = fposition_id and fiscal_pool.browse(cr, uid, fposition_id, context=context) or False
    #             a = fiscal_pool.map_account(cr, uid, fpos, oa)
    #             res['value'].update({'account_id':a})
    #     return res

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