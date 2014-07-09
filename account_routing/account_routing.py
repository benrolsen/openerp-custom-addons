import logging
_logger = logging.getLogger(__name__)

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

    def _get_account_types(self, cr, uid, *args, **kwargs):
        routing_id = kwargs['routing_id']
        res = list()
        route_list = self.browse(cr, uid, routing_id)
        route = route_list and route_list[0]
        for routing_line in route.routing_lines:
            res.append(routing_line.account_type_id.id)
        return res


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

    def name_get(self, cr, uid, ids, context=None):
        result = super(account_routing_line, self).name_get(cr, uid, ids, context)
        name_list = []
        for line in result:
            routing_line = self.browse(cr, uid, line[0])
            name_list.append((line[0], routing_line.account_type_id.name))
        return name_list

    def _get_analytic_ids(self, cr, uid, *args, **kwargs):
        routing_line_id = kwargs['routing_line_id']
        res = list()
        line_list = self.browse(cr, uid, routing_line_id)
        line = line_list and line_list[0]
        for subroute in line.subrouting_ids:
            if subroute.account_analytic_id.type != 'view':
                res.append(subroute.account_analytic_id.id)

            id = subroute.account_analytic_id.id
            analytic_rec = subroute.account_analytic_id
            child_ids = analytic_rec.child_ids
            complete_child_ids = analytic_rec.child_complete_ids
            for child in complete_child_ids:
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

    def _dummy_func(self, cr, uid, ids):
        return {}

    def _search_routing_ids(self, cr, uid, obj, name, args, context=None):
        routing_id = args[0][2]
        id_list = list()
        if routing_id:
            route = self.pool.get('account.routing').browse(cr, uid, routing_id)
            id_list = route._get_account_types(cr, uid, routing_id=routing_id)
        res = [('id','in',id_list)]
        return res

    _columns = {
        'allow_routing': fields.boolean('Allow routing', help="Allows you to set special account routing rules via this account type"),
        'routing_filter': fields.function(_dummy_func, method=True, fnct_search=_search_routing_ids, type='one2many')
    }

    _defaults = {
        'allow_routing': False,
    }

class account_analytic_account_routing(osv.Model):
    _inherit = "account.analytic.account"

    def _dummy_func(self, cr, uid, ids):
        return {}

    def _search_routing_line_ids(self, cr, uid, obj, name, args, context=None):
        routing_id = args[0][2][0]
        account_type_id = args[0][2][1]
        id_list = list()
        if routing_id and account_type_id:
            routing_line_id = self.pool.get('account.routing.line').search(cr, uid, [('routing_id','=',routing_id),('account_type_id','=',account_type_id)])[0]
            routing_line = self.pool['account.routing.line'].browse(cr, uid, routing_line_id)
            id_list = routing_line._get_analytic_ids(cr, uid, routing_line_id=routing_line_id)
        res = [('id','in',id_list)]
        return res

    _columns = {
        'routing_line_filter': fields.function(_dummy_func, method=True, fnct_search=_search_routing_line_ids, type='one2many')
    }

    def _search_for_subroute_account(self, cr, uid, *args, **kwargs):
        routing_line_id = kwargs.get('routing_line_id')
        account_analytic_id = kwargs.get('account_analytic_id')
        account_id = None
        subrouting_obj = self.pool.get('account.routing.subrouting')
        subroute_id = subrouting_obj.search(cr, uid, [('routing_line_id','=',routing_line_id),('account_analytic_id','=',account_analytic_id)])
        while not subroute_id:
            analytic = self.browse(cr, uid, account_analytic_id)
            if not analytic.parent_id:
                break
            account_analytic_id = analytic.parent_id.id
            subroute_id = subrouting_obj.search(cr, uid, [('routing_line_id','=',routing_line_id),('account_analytic_id','=',account_analytic_id)])
        if subroute_id:
            subroute = self.pool['account.routing.subrouting'].browse(cr, uid, subroute_id)[0]
            account_id = subroute.account_id.id
        return account_id



class account_invoice_line(osv.Model):
    _inherit = "account.invoice.line"

    _columns = {
        'routing_id': fields.many2one('account.routing', 'Category', required=True,),
        'account_type_id': fields.many2one('account.account.type', 'Purchase Type', required=True,),
    }

    def onchange_routing_id(self, cr, uid, ids):
        return {'value':{'account_type_id': '', 'account_analytic_id': '', 'account_id': ''},}

    def onchange_account_type_id(self, cr, uid, ids, routing_id, account_type_id):
        if not routing_id or not account_type_id:
            return {}
        routing_line_id = self.pool['account.routing.line'].search(cr, uid, [('routing_id','=',routing_id),('account_type_id','=',account_type_id)])[0]
        routing_line = self.pool['account.routing.line'].browse(cr, uid, routing_line_id)
        default_account_id = routing_line.account_id
        return {'value':{'account_analytic_id': '', 'account_id': default_account_id.id},}

    def onchange_analytic_id(self, cr, uid, ids, routing_id, account_type_id, account_analytic_id):
        if not routing_id or not account_type_id or not account_analytic_id:
            return {}
        routing_line_id = self.pool.get('account.routing.line').search(cr, uid, [('routing_id','=',routing_id),('account_type_id','=',account_type_id)])[0]
        analytic = self.pool.get('account.analytic.account').browse(cr, uid, account_analytic_id)
        account_id = analytic._search_for_subroute_account(cr, uid, routing_line_id=routing_line_id, account_analytic_id=account_analytic_id)
        return {'value':{'account_id': account_id}}

    def product_id_change(self, cr, uid, ids, product, uom_id, qty=0, name='', type='out_invoice', partner_id=False, fposition_id=False, price_unit=False, currency_id=False, context=None, company_id=None):
        res = super(account_invoice_line, self).product_id_change(cr, uid, ids, product, uom_id, qty, name, type, partner_id, fposition_id, price_unit, currency_id, context, company_id)
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
    def onchange_routing_id(self, cr, uid, ids):
        return {'value':{'account_type_id': '', 'account_analytic_id': ''},}

    def onchange_account_type_id(self, cr, uid, ids):
        return {'value':{'account_analytic_id': '', },}

    def _prepare_order_line_invoice_line(self, cr, uid, line, account_id=False, context=None):
        routing_id = line.routing_id.id
        account_type_id = line.account_type_id.id
        account_analytic_id = line.account_analytic_id.id

        routing_line_id = self.pool['account.routing.line'].search(cr, uid, [('routing_id','=',routing_id),('account_type_id','=',account_type_id)])[0]
        if account_analytic_id:
            analytic = self.pool.get('account.analytic.account').browse(cr, uid, account_analytic_id)
            account_id = analytic._search_for_subroute_account(cr, uid, routing_line_id=routing_line_id, account_analytic_id=account_analytic_id)
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
            account_id = analytic._search_for_subroute_account(cr, uid, routing_line_id=routing_line_id, account_analytic_id=account_analytic_id)
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

    def onchange_routing_id(self, cr, uid, ids):
        return {'value':{'account_type_id': '', 'account_analytic_id': ''},}

    def onchange_account_type_id(self, cr, uid, ids):
        return {'value':{'account_analytic_id': ''},}


class hr_timesheet_line_routing(osv.Model):
    _inherit = "hr.analytic.timesheet"

    _columns = {
        'routing_id': fields.many2one('account.routing', 'Category', required=True,),
        'account_type_id': fields.many2one('account.account.type', 'Type', required=True,),
    }

    def onchange_routing_id(self, cr, uid, ids, routing_id):
        route = self.pool.get('account.routing').browse(cr, uid, routing_id)
        return {'value':{'account_type_id': route.timesheet_routing_line.account_type_id.id, 'account_id': ''},}

    def onchange_account_type_id(self, cr, uid, ids):
        return {'value':{'account_id': ''},}

