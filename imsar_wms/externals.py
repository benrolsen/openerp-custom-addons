from datetime import datetime, date
from openerp import models, fields, api, _


class account_routing_subrouting(models.Model):
    _inherit = "account.routing.subrouting"

    location_id = fields.Many2one('stock.location','Location')
    material_type = fields.Boolean('Material Type', compute='_check_mat_type')
    labor_oh_rate = fields.Float('Labor Overhead Rate', digits=(2,4))

    @api.one
    def _check_mat_type(self):
        mat_types = self.env.user.company_id.material_account_type_ids
        if self.routing_line_id.account_type_id.id in mat_types.ids:
            self.material_type = True
        else:
            self.material_type = False


class product_category(models.Model):
    _inherit = 'product.category'

    default_location = fields.Many2one('stock.location', "Default Location", required=True, domain="[('usage','=','internal')]")

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
    serial_prefix = fields.Char('Serial Prefix', required=True)
    can_buy = fields.Boolean(compute='_computed_fields', readonly=True)

    @api.one
    @api.depends('route_ids')
    def _computed_fields(self):
        buy_route_id = self.env['ir.model.data'].xmlid_to_res_id('purchase.route_warehouse0_buy')
        self.can_buy = (buy_route_id in self.route_ids.ids)

    _defaults = {
        'type': 'product',
        # 'track_all': True,
    }
    _sql_constraints = [
        ('serial_prefix_uniq', 'unique (serial_prefix)', 'All Serial Prefix codes must be unique!'),
    ]

    @api.v7
    def do_change_standard_price(self, cr, uid, ids, new_price, context=None):
        return True


class stock_location(models.Model):
    _inherit = "stock.location"

    account_subroutes = fields.One2many('account.routing.subrouting', 'location_id', 'Task Codes')


class purchase_order(models.Model):
    _inherit = 'purchase.order'

    fob = fields.Selection([('Shipping Point','Shipping Point'), ('Destination', 'Destination')], string="FOB Responsibility", required=True, default="Shipping Point")
    shipping_method = fields.Many2one('purchase.shipping.method', 'Shipping Method', default=lambda self: self._get_default_shipping(), copy=True)

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
        if order_line.product_id and not order_line.product_id.type == 'service' and \
            order_line.routing_subrouting_id.location_id and order_line.routing_subrouting_id.location_id.usage == 'internal':
            # use config settings for interim receiving of physical products
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
            'routing_line_id': order_line.routing_line_id.id,
            'routing_subrouting_id': order_line.routing_subrouting_id.id,
        }

    @api.model
    def _prepare_order_line_move(self, order, order_line, picking_id, group_id):
        res = super(purchase_order,self)._prepare_order_line_move(order, order_line, picking_id, group_id)
        for vals in res:
            vals['dest_employee'] = order_line.dest_employee.id
            vals['source_routing_id'] = self.env.user.company_id.interim_receiving.routing_id.id
            vals['source_routing_line_id'] = self.env.user.company_id.interim_receiving.routing_line_id.id
            vals['source_routing_subrouting_id'] = self.env.user.company_id.interim_receiving.id
            vals['location_id'] = self.env.user.company_id.interim_receiving.location_id.id
            vals['target_routing_id'] = order_line.routing_id.id
            vals['target_routing_line_id'] = order_line.routing_line_id.id
            vals['target_routing_subrouting_id'] = order_line.routing_subrouting_id.id
            vals['location_dest_id'] = order_line.routing_subrouting_id.location_id.id
        return res

    @api.model
    def _get_default_shipping(self):
        try:
            return self.env.ref('imsar_wms.shipping_method_prepay').id
        except ValueError:
            return None


class purchase_order_line(models.Model):
    _inherit = 'purchase.order.line'

    routing_id = fields.Many2one('account.routing', 'Category', required=True, default=lambda self: self._get_routing_id())
    routing_line_id = fields.Many2one('account.routing.line', 'Type', required=True, default=lambda self: self._get_routing_line_id())
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Identifier', required=True, default=lambda self: self._get_routing_subrouting_id())
    dest_employee = fields.Many2one('hr.employee', 'Deliver to')

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        pref = self.env['account.routing.purchase.preferences'].search([('user_id','=',self._uid)])
        if self.routing_id:
            pref.write({'routing_id': self.routing_id.id})
        if self.routing_line_id not in self.routing_id.routing_lines:
            self.routing_line_id = ''
        self.source_routing_line_id = ''
        mat_types = self.env.user.company_id.material_account_type_ids
        for routing_line in self.routing_id.routing_lines:
            if routing_line.account_type_id.id in mat_types.ids:
                self.routing_line_id = routing_line.id
                return

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


class purchase_shipping_method(models.Model):
    _name = 'purchase.shipping.method'

    name = fields.Char('Shipping Method')
    account_number = fields.Char('IMSAR account #')


class hr_timekeeping_sheet(models.Model):
    _inherit = 'hr.timekeeping.sheet'

    @api.multi
    def button_done(self):
        super(hr_timekeeping_sheet, self).button_done()
        for line in self.line_ids:
            if line.serial_ids:
                quants = [serial.quant_ids for serial in line.serial_ids]
                unit_amount = line.full_amount / len(quants)
                for quant in quants:
                    quant.add_labor_cost(unit_amount)
                    # check to see if the quant has been moved from its production destination location
                    if quant.location_id != quant.mfg_order_id.mat_routing_subrouting_id.location_id:
                        line.write_override({'accounting_review_flag': True})
                    if quant.mfg_order_id.mat_routing_subrouting_id.location_id.usage == 'internal':
                        if line.routing_subrouting_id.labor_oh_rate and line.routing_subrouting_id.labor_oh_rate > 0:
                            oh_amount = unit_amount * line.routing_subrouting_id.labor_oh_rate
                            quant.add_labor_oh_cost(oh_amount)
                        else:
                            oh_amount = 0
                        # create account move lines to wip/cogs labor ending inv if it was direct (internal)
                        self._post_direct_mfg_labor(line, quant, unit_amount, oh_amount)

    @api.multi
    def _post_direct_mfg_labor(self, line, quant, unit_amount, oh_amount):
        # debit in WIP, credit in mfg labor ending inventory
        move_lines = []
        move_lines.append((0,0,{
            'name': '{}/Direct MFG Labor Debit'.format(quant.lot_id.name),
            'date': date.today(),
            'debit': unit_amount > 0 and unit_amount or 0,
            'credit': unit_amount < 0 and -unit_amount or 0,
            'account_id': self.env.user.company_id.wip_task_code.account_id.id,
            # 'timekeeping_line_ids': [(6,0,[line.id])],
            'timekeeping_line_ids': [(4, line.id)],
        }))
        move_lines.append((0,0,{
            'name': '{}/Direct MFG Labor Credit'.format(quant.lot_id.name),
            'date': date.today(),
            'debit': unit_amount < 0 and -unit_amount or 0,
            'credit': unit_amount > 0 and unit_amount or 0,
            'account_id': self.env.user.company_id.pnl_labor_credit.id,
            # 'timekeeping_line_ids': [(6,0,[line.id])],
            'timekeeping_line_ids': [(4, line.id)],
        }))
        if oh_amount:
            move_lines.append((0,0,{
                'name': '{}/Direct MFG Labor OH Debit'.format(quant.lot_id.name),
                'date': date.today(),
                'debit': oh_amount > 0 and oh_amount or 0,
                'credit': oh_amount < 0 and -oh_amount or 0,
                'account_id': self.env.user.company_id.wip_task_code.account_id.id,
                # 'timekeeping_line_ids': [(6,0,[line.id])],
                'timekeeping_line_ids': [(4, line.id)],
            }))
            move_lines.append((0,0,{
                'name': '{}/Direct MFG Labor OH Credit'.format(quant.lot_id.name),
                'date': date.today(),
                'debit': oh_amount < 0 and -oh_amount or 0,
                'credit': oh_amount > 0 and oh_amount or 0,
                'account_id': self.env.user.company_id.pnl_mfg_oh.id,
                # 'timekeeping_line_ids': [(6,0,[line.id])],
                'timekeeping_line_ids': [(4, line.id)],
            }))
        journal_id = self.env.user.company_id.stock_journal.id
        period = self.env['account.period'].find(date.today())[0]
        entry = self.env['account.move'].create(
            {'journal_id': journal_id,
             'line_id': move_lines,
             'period_id': period.id,
             'date': date.today(),
             'ref': '{}/Direct MFG Labor'.format(quant.lot_id.name),
             },)
        entry.post()


class hr_timekeeping_line(models.Model):
    _inherit = 'hr.timekeeping.line'

    mfg_order_id = fields.Many2one('mrp.production', "MFG Order")
    serial_ids = fields.Many2many('stock.production.lot', 'tk_line_serial_rel', 'tk_line', 'serial_id', "Serial Numbers",
                                  help="Required when working on manufacturing items.")
    accounting_review_flag = fields.Boolean('Needs manual accounting review', default=False)

    @api.one
    @api.constrains('routing_subrouting_id','mfg_order_id')
    def _check_mfg_order_id(self):
        for serial in self.serial_ids:
            mfg_labor_task = serial.production_id.labor_routing_subrouting_id
            mfg_mat_task = serial.production_id.mat_routing_subrouting_id
            if mfg_mat_task.location_id.usage == 'internal' and not self.routing_subrouting_id.require_serial:
                raise Warning("Serial numbers built to direct manufacturing must have MFG Direct task codes")
            elif mfg_mat_task.location_id.usage != 'internal' and mfg_labor_task.account_analytic_id != self.routing_subrouting_id.account_analytic_id:
                raise Warning("Serial numbers build to contract/expense codes must use a matching contract/expense task code.")

    @api.onchange('mfg_order_id')
    def onchange_mfg_order_id(self):
        self.serial_ids = self.mfg_order_id.production_serials.ids

    @api.onchange('date')
    def onchange_date(self):
        super(hr_timekeeping_line, self).onchange_date()
        self.mfg_order_id = ''
        self.serial_ids = ''

    @api.multi
    def button_manual_accounting(self):
        tkline_review = self.env['hr.timekeeping.line.review'].create({
            'timekeeping_line_id': self.id,
            'ref': "Adjustments for {}/{} on {}".format(self.employee_id.name, self.sheet_id.name, self.date)
        })
        view = {
            'name': _('Timesheet Line Review'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.timekeeping.line.review',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_id': tkline_review.id,
        }
        return view


class timekeeping_line_move_review(models.TransientModel):
    _name = "hr.timekeeping.line.review"
    _description = "Wizard to manually create correcting accounting entries for timesheet lines"

    timekeeping_line_id = fields.Many2one('hr.timekeeping.line', 'Timesheet Line to review')
    sheet_id = fields.Many2one('hr.timekeeping.sheet', "Sheet", related='timekeeping_line_id.sheet_id')
    date = fields.Date(string='Date', related='timekeeping_line_id.date')
    employee_id = fields.Many2one('hr.employee', related='timekeeping_line_id.sheet_id.employee_id')
    tkline_task = fields.Char("Timesheet Line Task", related='timekeeping_line_id.task_shortname')
    description = fields.Char("Description", related='timekeeping_line_id.name')
    unit_amount = fields.Float("Time", related='timekeeping_line_id.unit_amount')
    full_amount = fields.Float("Labor Amount", related='timekeeping_line_id.full_amount')
    oh_amount = fields.Float("OH Amount", compute='_computed_fields')
    total_amount = fields.Float("Total", compute='_computed_fields')
    serial_ids = fields.Many2many('stock.production.lot', related='timekeeping_line_id.serial_ids')
    quant_ids = fields.One2many('stock.quant', string="Quants", compute="_related_quants")
    mfg_order_id = fields.Many2one('mrp.production', 'MFG Order', related='timekeeping_line_id.mfg_order_id')
    mfg_product_id = fields.Many2one('product.product', related='timekeeping_line_id.mfg_order_id.product_id')
    mfg_serial_ids = fields.One2many('stock.production.lot', related='timekeeping_line_id.mfg_order_id.production_serials')
    mat_task_shortname = fields.Char("MFG Material Task", related='timekeeping_line_id.mfg_order_id.mat_task_shortname')
    labor_task_shortname = fields.Char("MFG Labor Task", related='timekeeping_line_id.mfg_order_id.labor_task_shortname')
    ref = fields.Char("Description", required=True)
    account_move_lines = fields.Many2many('account.move.line', string="Posted GL Lines", related='timekeeping_line_id.move_line_ids')
    line_ids = fields.One2many('hr.timekeeping.line.review.line', 'review_id', "Correcting GL Lines")
    total_credits = fields.Float('Total Credits', compute='_line_stats', digits=(2,2))
    total_debits = fields.Float('Total Debits', compute='_line_stats', digits=(2,2))

    @api.one
    def _computed_fields(self):
        self.oh_amount = self.full_amount * self.timekeeping_line_id.routing_subrouting_id.labor_oh_rate
        self.total_amount = self.full_amount + self.oh_amount

    @api.one
    def _related_quants(self):
        quants = []
        if not self.serial_ids:
            serials = self.mfg_serial_ids
        else:
            serials = self.serial_ids
        for serial in serials:
            quants += serial.quant_ids.ids
        self.quant_ids = [(6,0,[q for q in quants])]

    @api.one
    @api.depends('line_ids')
    def _line_stats(self):
        total_credits = 0.0
        total_debits = 0.0
        for line in self.line_ids:
            if line.line_type == 'Credit':
                total_credits += line.amount
            if line.line_type == 'Debit':
                total_debits += line.amount
        self.total_credits = total_credits
        self.total_debits = total_debits

    @api.multi
    def submit(self):
        if self.total_credits != self.total_debits:
            raise Warning("Credits and Debits are not balanced!")
        # write journal entries
        journal_id = self.env.user.company_id.timekeeping_journal_id.id
        period = self.env['account.period'].find(date.today())[0]
        move_lines = []
        for line in self.line_ids:
            if not line.name:
                line.name = self.ref
            if line.line_type == 'Debit' and line.amount > 0.0:
                move_lines.append(self._make_debit_move_line(line.name, line.amount, line.account_id.id, line.analytic_id.id))
            if line.line_type == 'Credit' and line.amount > 0.0:
                move_lines.append(self._make_credit_move_line(line.name, line.amount, line.account_id.id, line.analytic_id.id))
        if move_lines:
            entry = self.env['account.move'].create({'journal_id': journal_id, 'line_id': move_lines, 'period_id': period.id, 'date': date.today(), 'ref': self.ref},)
            entry.post()
        # mark move as reviewed
        self.timekeeping_line_id.write_override({'accounting_review_flag': False})
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    @api.model
    def _make_debit_move_line(self, name, amount, debit_account, debit_analytic=None, quantity=None):
        debit_line_vals = {
                    'name': name,
                    'date': date.today(),
                    'debit': amount > 0 and amount or 0,
                    'credit': amount < 0 and -amount or 0,
                    'account_id': debit_account,
                    'analytic_account_id': debit_analytic,
        }
        if quantity:
            debit_line_vals.update({'quantity': quantity,})
        return (0, 0, debit_line_vals)

    @api.model
    def _make_credit_move_line(self, name, amount, credit_account, credit_analytic=None, quantity=None):
        credit_line_vals = {
                    'name': name,
                    'date': date.today(),
                    'debit': amount < 0 and -amount or 0,
                    'credit': amount > 0 and amount or 0,
                    'account_id': credit_account,
                    'analytic_account_id': credit_analytic,
        }
        if quantity:
            credit_line_vals.update({'quantity': quantity,})
        return (0, 0, credit_line_vals)


class timekeeping_line_move_review_line(models.TransientModel):
    _name = "hr.timekeeping.line.review.line"
    _description = "Manual accounting lines for timesheet line reviews"

    review_id = fields.Many2one('hr.timekeeping.line.review', 'Timesheet Line Review')
    name = fields.Char("Description")
    line_type = fields.Selection([('Debit','Debit'), ('Credit','Credit')], required=True)
    amount = fields.Float('Amount', required=True)
    account_id = fields.Many2one('account.account', 'Account', required=True, domain="[('type','not in',['view','closed'])]")
    analytic_id = fields.Many2one('account.analytic.account', 'Analytic', domain="[('state','not in',['template','close','cancelled']),('type','not in',['template'])]")

