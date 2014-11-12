from openerp import models, fields, api, _
from openerp import SUPERUSER_ID


# I sometimes question the wisdom of using analytics to represent work tasks, but it does make managing
# the whole thing more straightforward. Either way, it takes a lot of customization of analytics.
class account_analytic_account(models.Model):
    _inherit = "account.analytic.account"

    pm_ids = fields.Many2many('res.users', 'analytic_user_pm_rel', 'analytic_id', 'user_id', string='Project Managers')
    overtime_account = fields.Many2one('account.account', string="Overtime Routing Account", domain="[('type','not in',['view','closed'])]")
    timesheets_future_filter = fields.Char(store=False, compute='_computed_fields', search='_filter_future_accounts')
    user_review_ids = fields.Many2many('res.users', 'analytic_user_review_rel', 'analytic_id', 'user_id', string='Users Reviewed')
    user_review_ids_count = fields.Integer(compute='_computed_fields', readonly=True)
    user_has_reviewed = fields.Boolean(compute='_user_has_reviewed', search='_search_user_has_reviewed', string="Reviewed", readonly=True, store=False)
    is_labor_code = fields.Boolean(string="Is a labor code", default=False)
    dcaa_allowable = fields.Boolean(string="DCAA Allowable", default=True)
    limit_to_auth = fields.Boolean(string="Limit Contract/Project to set of users:", default=False,)
    auth_users = fields.Many2many('res.users', 'analytic_user_auth_rel', 'analytic_id', 'user_id', string='Users Authorized')
    hide_from_users = fields.Many2many('res.users', 'analytic_user_hide_rel', 'analytic_id', 'user_id', string='Hide from Users')
    hide_from_uid = fields.Boolean(compute='_computed_fields', search='_search_hidden_ids', string="Hide from my timesheet", readonly=True, store=False)
    linked_worktype = fields.Many2one('hr.timekeeping.worktype', string="Limit to worktype", domain="[('limited_use','=',True)]")

    @api.one
    @api.depends('user_review_ids','hide_from_users')
    def _computed_fields(self):
        self.user_review_ids_count = len(self.user_review_ids)
        self.timesheets_future_filter = ''
        # set hide_from_uid
        if self.env.user and self.hide_from_users and (self.env.user in self.hide_from_users):
            self.hide_from_uid = True
        else:
            self.hide_from_uid = False

    def _filter_future_accounts(self, operator, value):
        if value == 'future':
            valid_accounts = self.env.user.company_id.future_analytic_ids
        else:
            valid_accounts = self.env['account.analytic.account'].search([('state', '!=', 'close'),])
        return [('id','in',valid_accounts.ids)]

    @api.one
    @api.depends('user_review_ids')
    def _user_has_reviewed(self):
        if self.env.user and self.user_review_ids and (self.env.user in self.user_review_ids):
            self.user_has_reviewed = True
        else:
            self.user_has_reviewed = False

    def _search_user_has_reviewed(self, operator, value):
        if value == False:
            reviewed_ids = self.search([('user_review_ids','not in',self._uid)])
        elif value == True:
            reviewed_ids = self.search([('user_review_ids','in',self._uid)])
        else:
            reviewed_ids = self.search([])
        # this next filter actually depends on auth users, not reviewed users, but I didn't want to make yet another
        # field and search just for one line, and auth_users always applies in this case
        auth_ids = reviewed_ids.search(['|',('auth_users','in',self._uid),('limit_to_auth','=',False)])
        intersection = set.intersection(set(reviewed_ids.ids), set(auth_ids.ids))
        return [('id','in', list(intersection))]

    def _search_hidden_ids(self, operator, value):
        if value == False:
            shown_ids = self.search([('hide_from_users','not in',self._uid)])
        elif value == True:
            shown_ids = self.search([('hide_from_users','in',self._uid)])
        else:
            shown_ids = self.search([])
        return [('id','in', shown_ids.ids)]

    @api.multi
    def action_button_hide(self):
        self.sudo().write({'hide_from_users': [(4,self.env.user.id)]})

    @api.multi
    def action_button_show(self):
        self.sudo().write({'hide_from_users': [(3,self.env.user.id)]})

    @api.multi
    def action_button_sign(self):
        # this would take you back to the tree view, but the header breadcrumbs get ridiculous
        # resource = self.env['ir.model.data'].xmlid_to_res_id('imsar_timekeeping.analytic_review_view',raise_if_not_found=True)
        # res = self.pool.get('ir.actions.act_window.view').read(self._cr, self._uid, [resource], context=self._context)[0]
        # this is a useful way to reload the page that I didn't end up needing
        # res = { 'type': 'ir.actions.client', 'tag': 'reload' }
        self.sudo().write({'user_review_ids': [(4,self.env.user.id)]})
        return True

    @api.multi
    def button_reviewed_users(self):
        view = {
            'name': _('Users reviewed'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'res.users',
            'view_id': False,
            'type': 'ir.actions.act_window',
            # 'target': 'inline',
            'domain': [('analytic_review_ids','in',self.ids)],
        }
        return view


class employee(models.Model):
    _inherit = 'hr.employee'

    first_name = fields.Char('First Name', default='', required=True)
    middle_name = fields.Char('Middle Name')
    last_name = fields.Char('Last Name', default='', required=True)
    name = fields.Char('Name', compute='_computed_fields', store=True, required=False)
    name_related = fields.Char('Name', compute='_computed_fields', store=True, required=False)
    flsa_status = fields.Selection([('exempt','Exempt'),('non-exempt','Non-exempt')], string='FLSA Status', default='exempt', required=True)
    full_time = fields.Boolean('Full Time', default=True, required=True)
    full_time_hours = fields.Integer('Full Time Hours (pay period)')
    wage_rate = fields.Float('Hourly Wage Rate', required=True, default=0.0)
    pto_accrual_rate = fields.Float('PTO Accrual Rate (per hour)', required=True, default=0.0)
    is_owner = fields.Boolean('Company Owner', default=False)
    owner_wage_account_id = fields.Many2one('account.account', 'Owner Wage Liability Account')

    @api.one
    @api.depends('first_name','middle_name','last_name')
    def _computed_fields(self):
        self.name = "{}, {} {}".format(self.last_name, self.first_name, self.middle_name)
        self.name_related = self.name


class resource(models.Model):
    _inherit = 'resource.resource'

    name = fields.Char('Name', default='', required=False)

class res_users(models.Model):
    _inherit = "res.users"

    analytic_review_ids = fields.Many2many('account.analytic.account', 'analytic_user_review_rel', 'user_id', 'analytic_id', string='Reviewed Analytic Accounts')
    auth_analytics = fields.Many2many('account.analytic.account', 'analytic_user_auth_rel', 'user_id', 'analytic_id', string='Authorized Analytics')
    pm_analytics = fields.Many2many('account.analytic.account', 'analytic_user_pm_rel', 'user_id', 'analytic_id', string='Projects Managed')
    hide_analytics = fields.Many2many('account.analytic.account', 'analytic_user_hide_rel', 'user_id', 'analytic_id', string='Tasks hidden from timesheets')
    timesheet_prefs = fields.One2many('hr.timekeeping.preferences', 'user_id', string='Preferences')


class account_move_line(models.Model):
    _inherit = "account.move.line"

    timekeeping_line_ids = fields.Many2many('hr.timekeeping.line', 'timekeeping_line_move_line_rel', 'move_line_id', 'timekeeping_line_id', string='Related timekeeping lines')


class account_routing_subrouting(models.Model):
    _inherit = "account.routing.subrouting"

    # these are part of the analytic but need to be exposed for the subroute
    timesheets_future_filter = fields.Char(related='account_analytic_id.timesheets_future_filter', readonly=True)
    user_has_reviewed = fields.Boolean(related='account_analytic_id.user_has_reviewed', readonly=True)
    dcaa_allowable = fields.Boolean(related='account_analytic_id.dcaa_allowable', readonly=True)
    hide_from_uid = fields.Boolean(related='account_analytic_id.hide_from_uid', readonly=True)
    oneclick_filter = fields.Boolean(store=False, compute='_oneclick', search='_filter_oneclick')
    oneclick_prefs = fields.Many2many('hr.timekeeping.preferences', 'user_pref_subroute_rel', 'subrouting_id', 'user_pref', string='One Click Prefs')

    @api.one
    def _oneclick(self):
        self.oneclick_filter = True

    def _filter_oneclick(self, operator, value):
        timekeeping_id = self.env['ir.model.data'].xmlid_to_res_id('imsar_timekeeping.ar_section_timekeeping')
        routing_ids = self.env['account.routing'].search([('section_ids','in',[timekeeping_id]),])
        routing_line_ids = self.env['account.routing.line'].search([
            ('routing_id','in',routing_ids.ids),('section_ids','in',[timekeeping_id]),
        ])
        subrouting_ids = self.env['account.routing.subrouting'].search([
            ('routing_line_id','in',routing_line_ids.ids),('user_has_reviewed','=',True),('hide_from_uid','=',False),
        ])
        return [('id','in', subrouting_ids.ids)]
