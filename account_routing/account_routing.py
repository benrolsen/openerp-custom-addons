from openerp import models, fields, api, _


class account_routing(models.Model):
    _name = 'account.routing'
    _description = 'Account Routing'
    _order = "name"

    name = fields.Char('Routing Category', size=128, required=True)
    routing_lines = fields.One2many('account.routing.line', 'routing_id', 'Account Type Routes', ondelete='cascade')
    section_ids = fields.Many2many('account.routing.section','account_routing_section_rel', 'routing_id', 'section_id', string="Applies to sections")

    @api.multi
    def _get_account_types(self):
        return [routing_line.account_type_id.id for routing_line in self.routing_lines]


class account_routing_line(models.Model):
    _name = 'account.routing.line'
    _description = 'Account Routing Line'
    _order = "account_type_id"

    name = fields.Char(related='account_type_id.name')
    routing_id = fields.Many2one('account.routing', 'Account Routing', required=True, ondelete='cascade')
    account_type_id = fields.Many2one('account.account.type', 'Account Type', required=True, select=True, ondelete='cascade')
    subrouting_ids = fields.One2many('account.routing.subrouting', 'routing_line_id', 'Analytic Routes', ondelete='cascade')
    section_ids = fields.Many2many('account.routing.section','account_routing_line_section_rel', 'routing_line_id', 'section_id', string="Applies to sections")

    _sql_constraints = [
        ('routing_account_type_uniq', 'unique (routing_id,account_type_id)', 'Only one account type allowed per account routing!')
    ]


class account_routing_subrouting(models.Model):
    _name = 'account.routing.subrouting'
    _description = 'Account Subrouting'
    _order = "account_analytic_id"

    name = fields.Char(related='account_analytic_id.name')
    routing_id = fields.Many2one('account.routing', related='routing_line_id.routing_id', readonly=True)
    routing_line_id =  fields.Many2one('account.routing.line', 'Account Routing Line', required=True)
    account_type_id = fields.Many2one('account.account.type', related='routing_line_id.account_type_id', readonly=True)
    account_analytic_id = fields.Many2one('account.analytic.account', 'Analytic Account', required=True, select=True)
    account_id = fields.Many2one('account.account', 'Real Account', required=True, select=True)
    from_parent = fields.Boolean('Added by parent', readonly=True, default=False)
    type = fields.Selection(related='account_analytic_id.type', readonly=True)

    @api.model
    def create(self, vals):
        existing_subroute = self.search([('routing_line_id','=',vals.get('routing_line_id')),('account_analytic_id','=',vals.get('account_analytic_id'))])
        if not existing_subroute:
            subroute = super(account_routing_subrouting, self).create(vals)
        else:
            subroute = existing_subroute
        account_analytic_id = self.env['account.analytic.account'].browse(vals.get('account_analytic_id'))
        if len(account_analytic_id.child_ids) > 0:
            for analytic in account_analytic_id.child_ids:
                if analytic.type in ('normal', 'contract'):
                    vals['account_analytic_id'] = analytic.id
                    vals['from_parent'] = True
                    self.env['account.routing.subrouting'].create(vals)
        return subroute

    @api.multi
    def unlink(self):
        if len(self.account_analytic_id.child_ids) > 0:
            for subroute in self.search([('routing_line_id','=',self.routing_line_id.id),('account_analytic_id','in',self.account_analytic_id.child_ids.ids)]):
                if subroute.from_parent:
                    subroute.unlink()
        super(account_routing_subrouting, self).unlink()

    @api.multi
    def write(self, vals):
        # Well this is just stupid. If you try to delete some records in a write, for some reason it chains the write
        # to the records that got deleted and tries to call write on them. I have no idea what's going on. But if you
        # leave out the delete calls, it works as normal. This check is to see if the system is trying to call write
        # on an already deleted record.
        if not self.search([('id','=',self.id)]):
            return True
        # if the analytic didn't change, do the write and end here
        account_analytic_id = self.env['account.analytic.account'].browse(vals.get('account_analytic_id'))
        if not account_analytic_id:
            return super(account_routing_subrouting, self).write(vals)

        # if we're changing analytics, first delete any children of the existing subroute
        if len(self.account_analytic_id.child_ids) > 0:
            for subroute in self.search([('routing_line_id','=',self.routing_line_id.id),('account_analytic_id','in',self.account_analytic_id.child_ids.ids)]):
                if subroute and subroute.from_parent:
                    subroute.unlink()

        # now create subroutes for any children
        if len(account_analytic_id.child_ids) > 0:
            childvals = {
                'routing_line_id': self.routing_line_id.id,
                'account_id': vals.get('account_id') or self.account_id.id,
                'from_parent': True,
            }
            for child_id in account_analytic_id.child_ids.ids:
                childvals['account_analytic_id'] = child_id
                self.env['account.routing.subrouting'].create(childvals)
        return super(account_routing_subrouting, self).write(vals)

    _sql_constraints = [
        ('routing_line_analytic_uniq', 'unique (routing_line_id,account_analytic_id)', 'Only one analytic allowed per account routing line!')
    ]


class account_routing_section(models.Model):
    _name = 'account.routing.section'
    _description = 'Sections (or apps) the routes/lines apply to'

    name = fields.Char('Section', size=64, required=True)


class account_analytic_account(models.Model):
    _inherit = "account.analytic.account"

    account_routing_subrouting_ids = fields.One2many('account.routing.subrouting', 'account_analytic_id', 'Routing Subroutes')

class account_account_type(models.Model):
    _inherit = "account.account.type"

    allow_routing = fields.Boolean('Allow routing', default=False, help="Allows you to set special account routing rules via this account type")


class account_invoice_line(models.Model):
    _inherit = "account.invoice.line"

    routing_id = fields.Many2one('account.routing', 'Category', required=True,)
    routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True,)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True,)

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        self.routing_line_id = ''
        self.routing_subrouting_id = ''
        self.account_id = ''

    @api.onchange('routing_line_id')
    def onchange_account_type_id(self):
        self.routing_subrouting_id = ''
        self.account_id = ''

    @api.onchange('routing_subrouting_id')
    def onchange_analytic_id(self):
        self.account_id = self.routing_subrouting_id.account_id
        self.account_analytic_id = self.routing_subrouting_id.account_analytic_id

    def product_id_change(self, *args, **kwargs):
        res = super(account_invoice_line, self).product_id_change(*args, **kwargs)
        if 'account_id' in res['value']:
            del res['value']['account_id']
        return res


class sale_order_line(models.Model):
    _inherit = "sale.order.line"

    routing_id = fields.Many2one('account.routing', 'Category', required=True,)
    routing_line_id = fields.Many2one('account.routing.line', 'Purchase Type', required=True,)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True,)

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        self.routing_line_id = ''
        self.routing_subrouting_id = ''

    @api.onchange('account_type_id')
    def onchange_account_type_id(self):
        self.routing_subrouting_id = ''

    @api.v7
    def _prepare_order_line_invoice_line(self, cr, uid, line, account_id=False, context=None):
        account_id = line.routing_subrouting_id.account_id.id
        res = super(sale_order_line, self)._prepare_order_line_invoice_line(cr, uid, line, account_id, context)
        res['routing_id'] = line.routing_id.id
        res['routing_line_id'] = line.routing_line_id.id
        res['routing_subrouting_id'] = line.routing_subrouting_id.id
        res['account_analytic_id'] = line.routing_subrouting_id.account_analytic_id.id
        return res


class purchase_order(models.Model):
    _inherit = "purchase.order"

    @api.v7
    def _prepare_inv_line(self, cr, uid, account_id, order_line, context=None):
        account_id = order_line.routing_subrouting_id.account_id.id
        res = super(purchase_order, self)._prepare_inv_line(cr, uid, account_id, order_line, context)
        res['routing_id'] = order_line.routing_id.id
        res['routing_line_id'] = order_line.routing_line_id.id
        res['routing_subrouting_id'] = order_line.routing_subrouting_id.id
        res['account_analytic_id'] = order_line.routing_subrouting_id.account_analytic_id.id
        return res


class purchase_order_line(models.Model):
    _inherit = "purchase.order.line"

    routing_id = fields.Many2one('account.routing', 'Category', required=True,)
    routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True,)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True,)

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        self.routing_line_id = ''
        self.routing_subrouting_id = ''

    @api.onchange('account_type_id')
    def onchange_account_type_id(self):
        self.routing_subrouting_id = ''
