from openerp import api
from openerp.osv import fields, osv


class account_routing(osv.Model):
    _name = 'account.routing'
    _description = 'Account Routing'

    _columns = {
        'name': fields.char('Routing Category', size=128, required=True),
        'routing_lines': fields.one2many('account.routing.line', 'routing_id', 'Account Type Routes', ondelete='cascade'),
        'timesheet_routing_line': fields.many2one('account.routing.line', 'Timesheet Routing Type'),
    }

    _defaults = {
        'timesheet_routing_line': None,
    }

    @api.multi
    def _get_account_types(self):
        return [routing_line.account_type_id.id for routing_line in self.routing_lines]


class account_routing_line(osv.Model):
    _name = 'account.routing.line'
    _description = 'Account Routing Line'

    _columns = {
        'routing_id':  fields.many2one('account.routing', 'Account Routing', required=True,),
        'account_type_id': fields.many2one('account.account.type', 'Account Type', required=True, select=True),
        'account_id':  fields.many2one('account.account', 'Default Account', required=True, select=True),
        'subrouting_ids': fields.one2many('account.routing.subrouting', 'routing_line_id', 'Analytic Routes', ondelete='cascade'),
    }

    _sql_constraints = [
        ('routing_account_type_uniq', 'unique (routing_id,account_type_id)', 'Only one account type allowed per account routing!')
    ]

    @api.multi
    def name_get(self):
        result = super(account_routing_line, self).name_get()
        return [(line[0], self.account_type_id.name) for line in result]

    @api.multi
    def _get_analytic_ids(self):
        res = list()
        for subroute in self.subrouting_ids:
            analytic = subroute.account_analytic_id
            if analytic.type != 'view':
                res.append(analytic.id)
            for child in analytic.child_complete_ids:
                if child.type != 'view':
                    res.append(child.id)
        return res


class account_routing_subrouting(osv.Model):
    _name = 'account.routing.subrouting'
    _description = 'Account Subrouting'

    _columns = {
        'routing_line_id':  fields.many2one('account.routing.line', 'Account Routing Line', required=True,),
        'account_analytic_id': fields.many2one('account.analytic.account', 'Analytic Account', required=True, select=True),
        'account_id': fields.many2one('account.account', 'Real Account', required=True, select=True),
    }

    _sql_constraints = [
        ('routing_line_analytic_uniq', 'unique (routing_line_id,account_analytic_id)', 'Only one analytic allowed per account routing line!')
    ]

class account_account_type_routing(osv.Model):
    _inherit = "account.account.type"

    def _dummy_func(self):
        return ''

    def _search_routing_ids(self, cr, uid, obj, name, args, context=None):
        routing_id = args[0][2]
        id_list = list()
        if routing_id:
            route = self.pool.get('account.routing').browse(cr, uid, routing_id)
            id_list = route._get_account_types()
        res = [('id','in',id_list)]
        return res

    _columns = {
        'allow_routing': fields.boolean('Allow routing', help="Allows you to set special account routing rules via this account type"),
        'routing_filter': fields.function(_dummy_func, method=True, fnct_search=_search_routing_ids, type='char')
    }

    _defaults = {
        'allow_routing': False,
    }

class account_analytic_account_routing(osv.Model):
    _inherit = "account.analytic.account"

    def _dummy_func(self, cr, uid, ids):
        return ''

    def _search_routing_line_ids(self, cr, uid, obj, name, args, context=None):
        routing_id = args[0][2][0]
        account_type_id = args[0][2][1]
        id_list = list()
        if routing_id and account_type_id:
            routing_line_id = self.pool.get('account.routing.line').search(cr, uid, [('routing_id','=',routing_id),('account_type_id','=',account_type_id)])[0]
            routing_line = self.pool['account.routing.line'].browse(cr, uid, routing_line_id)
            id_list = routing_line._get_analytic_ids()
        res = [('id','in',id_list)]
        return res

    _columns = {
        'routing_line_filter': fields.function(_dummy_func, method=True, fnct_search=_search_routing_line_ids, type='char')
    }

    @api.multi
    def _search_for_subroute_account(self, routing_line_id):
        routing_line = self.env['account.routing.line'].browse(routing_line_id)
        subrouting_obj = self.env['account.routing.subrouting']

        # because multi and onchange pass "self" in as different things
        if isinstance(self.id, int):
            analytic = self
        else:
            analytic = self.id
        subroute = False
        while not subroute:
            subroute = subrouting_obj.search([('routing_line_id','=',routing_line_id),('account_analytic_id','=',analytic.id)])
            if not analytic.parent_id:
                break
            analytic = analytic.parent_id
        if subroute:
            return subroute.account_id.id
        return routing_line.account_id.id


class account_invoice_line(osv.Model):
    _inherit = "account.invoice.line"

    _columns = {
        'routing_id': fields.many2one('account.routing', 'Category', required=True,),
        'account_type_id': fields.many2one('account.account.type', 'Purchase Type', required=True,),
    }

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        self.account_type_id = ''
        self.account_id = ''
        self.account_analytic_id = ''

    @api.onchange('account_type_id')
    def onchange_account_type_id(self):
        if not self.routing_id or not self.account_type_id:
            return {}
        domain = [('routing_id','=',self.routing_id.id),('account_type_id','=',self.account_type_id.id)]
        routing_line_id = self.pool['account.routing.line'].search(self._cr, self._uid, domain)[0]
        routing_line = self.pool['account.routing.line'].browse(self._cr, self._uid, routing_line_id)
        self.account_id = routing_line.account_id.id
        self.account_analytic_id = ''

    @api.onchange('account_analytic_id')
    def onchange_analytic_id(self):
        if not self.routing_id or not self.account_type_id or not self.account_analytic_id:
            return {}
        domain = [('routing_id','=',self.routing_id.id),('account_type_id','=',self.account_type_id.id)]
        routing_line_id = self.pool.get('account.routing.line').search(self._cr, self._uid, domain)[0]
        analytic = self.pool.get('account.analytic.account').browse(self._cr, self._uid, self.account_analytic_id.id)
        self.account_id = analytic._search_for_subroute_account(routing_line_id=routing_line_id)

    def product_id_change(self, *args, **kwargs):
        res = super(account_invoice_line, self).product_id_change(*args, **kwargs)
        if 'account_id' in res['value']:
            del res['value']['account_id']
        return res


class sale_order_line(osv.Model):
    _inherit = "sale.order.line"

    _columns = {
        'routing_id': fields.many2one('account.routing', 'Category', required=True,),
        'account_type_id': fields.many2one('account.account.type', 'Income Type', required=True,),
        'account_analytic_id': fields.many2one('account.analytic.account', 'Analytic', ),
    }

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        self.account_type_id = ''
        self.account_analytic_id = ''

    @api.onchange('account_type_id')
    def onchange_account_type_id(self):
        self.account_analytic_id = ''

    def _prepare_order_line_invoice_line(self, cr, uid, line, account_id=False, context=None):
        routing_id = line.routing_id.id
        account_type_id = line.account_type_id.id
        account_analytic_id = line.account_analytic_id.id

        routing_line_id = self.pool['account.routing.line'].search(cr, uid, [('routing_id','=',routing_id),('account_type_id','=',account_type_id)])[0]
        if account_analytic_id:
            analytic = self.pool.get('account.analytic.account').browse(cr, uid, account_analytic_id)
            account_id = analytic._search_for_subroute_account(routing_line_id=routing_line_id)
        else:
            routing_line = self.pool['account.routing.line'].browse(cr, uid, routing_line_id)
            account_id = routing_line.account_id.id

        res = super(sale_order_line, self)._prepare_order_line_invoice_line(cr, uid, line, account_id, context)
        res['routing_id'] = routing_id
        res['account_type_id'] = account_type_id
        res['account_analytic_id'] = account_analytic_id

        return res


class purchase_order(osv.Model):
    _inherit = "purchase.order"

    def _prepare_inv_line(self, cr, uid, account_id, order_line, context=None):
        routing_id = order_line.routing_id.id
        account_type_id = order_line.account_type_id.id
        account_analytic_id = order_line.account_analytic_id.id

        routing_line_id = self.pool['account.routing.line'].search(cr, uid, [('routing_id','=',routing_id),('account_type_id','=',account_type_id)])[0]
        if account_analytic_id:
            analytic = self.pool.get('account.analytic.account').browse(cr, uid, account_analytic_id)
            account_id = analytic._search_for_subroute_account(routing_line_id=routing_line_id)
        else:
            routing_line = self.pool['account.routing.line'].browse(cr, uid, routing_line_id)
            account_id = routing_line.account_id.id

        res = super(purchase_order, self)._prepare_inv_line(cr, uid, account_id, order_line, context)
        res['routing_id'] = routing_id
        res['account_type_id'] = account_type_id
        res['account_analytic_id'] = account_analytic_id
        return res


class purchase_order_line(osv.Model):
    _inherit = "purchase.order.line"

    _columns = {
        'routing_id': fields.many2one('account.routing', 'Category', required=True,),
        'account_type_id': fields.many2one('account.account.type', 'Purchase Type', required=True,),
    }

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        self.account_type_id = ''
        self.account_analytic_id = ''

    @api.onchange('account_type_id')
    def onchange_account_type_id(self):
        self.account_analytic_id = ''


class hr_timesheet_line_routing(osv.Model):
    _inherit = "hr.analytic.timesheet"

    _columns = {
        'routing_id': fields.many2one('account.routing', 'Category', required=True,),
        'account_type_id': fields.many2one('account.account.type', 'Type', required=True,),
    }

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        route = self.pool.get('account.routing').browse(self._cr, self._uid, self.routing_id.id)
        self.account_type_id = route.timesheet_routing_line.account_type_id.id
        self.general_account_id = route.timesheet_routing_line.account_id.id
        self.account_id = ''

    @api.onchange('account_type_id')
    def onchange_account_type_id(self):
        self.account_analytic_id = ''

    @api.onchange('account_id')
    def onchange_account_type_id(self):
        self.journal_id = self.sheet_id.employee_id.journal_id
        if self.routing_id and self.account_id:
            route = self.pool.get('account.routing').browse(self._cr, self._uid, self.routing_id.id)
            analytic = self.pool.get('account.analytic.account').browse(self._cr, self._uid, self.account_id)
            account_id = analytic._search_for_subroute_account(routing_line_id=route.timesheet_routing_line.id)
            self.general_account_id = account_id

    @api.onchange('unit_amount')
    def onchange_unit_amount(self):
        res = self.pool.get('hr.analytic.timesheet').on_change_unit_amount(self._cr, self._uid, None, self.product_id.id, self.unit_amount, False, self.product_uom_id.id, self.journal_id.id, context=self._context)
        if 'amount' in res['value']:
            self.amount = res['value']['amount']
        if self.unit_amount == 0.0:
            self.amount = 0.0


