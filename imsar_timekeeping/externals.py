from datetime import datetime, date
from openerp import models, fields, api, _
from openerp.addons.base.ir.ir_mail_server import MailDeliveryException
from openerp import SUPERUSER_ID


# I sometimes question the wisdom of using analytics to represent work tasks, but it does make managing
# the whole thing more straightforward. Either way, it takes a lot of customization of analytics.
class account_analytic_account(models.Model):
    _inherit = "account.analytic.account"

    pm_ids = fields.Many2many('res.users', 'analytic_user_pm_rel', 'analytic_id', 'user_id', string='Project Managers')
    uid_is_pm = fields.Boolean('User is PM', compute='_computed_fields', search='_filter_uid_is_pm')
    overtime_account = fields.Many2one('account.account', string="Overtime Routing Account", domain="[('type','not in',['view','closed'])]")
    timesheets_future_filter = fields.Char(store=False, compute='_computed_fields', search='_filter_future_accounts')
    user_review_ids = fields.Many2many('res.users', 'analytic_user_review_rel', 'analytic_id', 'user_id', string='Users Reviewed')
    user_review_ids_count = fields.Integer(compute='_computed_fields', readonly=True)
    user_has_reviewed = fields.Boolean(compute='_user_has_reviewed', search='_search_user_has_reviewed', string="Reviewed", readonly=True, store=False)
    is_labor_code = fields.Boolean(string="Is a labor code", default=False)
    dcaa_allowable = fields.Boolean(string="FAR Allowable?", default=True)
    limit_to_auth = fields.Boolean(string="Limit Allowed Users?", default=False,)
    auth_users = fields.Many2many('res.users', 'analytic_user_auth_rel', 'analytic_id', 'user_id', string='Allowed Users')
    hide_from_users = fields.Many2many('res.users', 'analytic_user_hide_rel', 'analytic_id', 'user_id', string='Hide from Users')
    hide_from_uid = fields.Boolean(compute='_computed_fields', search='_search_hidden_ids', string="Hide from my timesheet", readonly=True, store=False)
    linked_worktype = fields.Many2one('hr.timekeeping.worktype', string="Limit to worktype", domain="[('limited_use','=',True)]")
    project_header = fields.Boolean(string="Contract/Project Header?", default=False)
    sow_examples = fields.Text('SOW Examples')

    @api.one
    @api.depends('user_review_ids','hide_from_users','pm_ids')
    def _computed_fields(self):
        self.user_review_ids_count = len(self.user_review_ids)
        self.timesheets_future_filter = ''
        # set hide_from_uid
        if self.env.user and self.hide_from_users and (self.env.user in self.hide_from_users):
            self.hide_from_uid = True
        else:
            self.hide_from_uid = False
        self.uid_is_pm = False
        if self.env.user.id in self.pm_ids.ids:
            self.uid_is_pm = True

    def _filter_future_accounts(self, operator, value):
        if value == 'future':
            valid_accounts = self.env.user.company_id.future_analytic_ids
        else:
            valid_accounts = self.env['account.analytic.account'].search([('state', '!=', 'close'),])
        return [('id','in',valid_accounts.ids)]

    def _filter_uid_is_pm(self, operator, value):
        if value == True:
            pm_accounts = self.env['account.analytic.account'].search([('pm_ids', 'in', self.env.user.id),])
        else:
            pm_accounts = self.env['account.analytic.account'].search([('pm_ids', 'not in', self.env.user.id),])
        return [('id','in',pm_accounts.ids)]

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
        auth_ids = self.search(['|',('auth_users','in',self._uid),('limit_to_auth','=',False)])
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

    @api.multi
    def write(self, vals):
        new_auth_user_temp = vals.get('auth_users')
        removed_users = set()
        if new_auth_user_temp and len(new_auth_user_temp[0]) > 2:
            new_auth_users = new_auth_user_temp[0][2]
            removed_users = set(self.auth_users.ids) - set(new_auth_users)
        res = super(account_analytic_account, self).write(vals)
        if 'description' in vals.keys():
            # SOW has changed, so invalidate everyone who has signed and email them notification.
            for user in self.user_review_ids:
                # send email
                template = self.env.ref('imsar_timekeeping.sow_change_email')
                ctx = self._context.copy()
                ctx.update({'aa_name': self.name})
                try:
                    self.pool.get('email.template').send_mail(self._cr, SUPERUSER_ID, template.id, user.id, force_send=True, raise_exception=True, context=ctx)
                except MailDeliveryException:
                    pass
                self.write({'user_review_ids': [(3,user.id)]})
        # if project_header, pass on authorizations to children
        if self.project_header:
            for child in self.get_all_children():
                if child.id == self.id:
                    continue
                pms = set(child.pm_ids.ids)
                auth_users = set(child.auth_users.ids)
                pms.update(set(self.pm_ids.ids))
                auth_users.update(set(self.auth_users.ids))
                auth_users.difference_update(removed_users)
                child.write({'pm_ids':[(6,0,list(pms))], 'auth_users': [(6,0,list(auth_users))], 'limit_to_auth': self.limit_to_auth})
        # ensure that all users listed as PMs are in the Project Manager group
        pm_group_id = self.env.ref('imsar_timekeeping.group_pms_user')
        for pm in self.pm_ids:
            if pm.id not in pm_group_id.users.ids:
                pm_group_id.sudo().write({'users': [(4, pm.id)]})
        return res

    @api.model
    def create(self, vals):
        res = super(account_analytic_account, self).create(vals)
        # inherit authorizations from project_header parent
        parent = res.parent_id
        while parent:
            if parent.project_header:
                res.write({'pm_ids':[(6,0,parent.pm_ids.ids)], 'auth_users': [(6,0,parent.auth_users.ids)], 'limit_to_auth': parent.limit_to_auth})
                break
            parent = parent.parent_id
        return res


class employee(models.Model):
    _inherit = 'hr.employee'

    first_name = fields.Char('First Name', default='', required=True)
    middle_name = fields.Char('Middle Name', default='')
    last_name = fields.Char('Last Name', default='', required=True)
    # only needed until we're off quickbooks
    qb_name = fields.Char('Quickbooks Name', default='', required=True)
    name = fields.Char('Name', compute='_computed_fields', store=True, required=False)
    name_related = fields.Char('Name', compute='_computed_fields', store=True, required=False)
    flsa_status = fields.Selection([('exempt','Exempt'),('non-exempt','Non-exempt')], string='FLSA Status', default='exempt', required=True)
    full_time = fields.Boolean('Full Time', default=True)
    full_time_hours = fields.Integer('Full Time Hours (pay period)', default=80)
    wage_rate = fields.Float('Hourly Wage Rate', required=True, default=0.0)
    pto_accrual_rate = fields.Float('PTO Accrual Rate (per hour)', required=True, default=0.0, digits=(1,4))
    accrued_pto = fields.Float('Accrued PTO', default=0.0, digits=(10,4), readonly=True)
    accrued_pto_personal = fields.Float('Accrued PTO', related="accrued_pto")
    max_pto = fields.Float('Maximum PTO', default=0.0, digits=(10,4))
    is_owner = fields.Boolean('Company Owner', default=False)
    owner_wage_account_id = fields.Many2one('account.account', 'Owner Wage Liability Account')
    employee_number = fields.Integer('Employee Number', default=0)
    hire_date = fields.Date('Hire Date')
    ft_hire_date = fields.Date('FT Hire Date')
    personal_email = fields.Char('Personal Email')
    personal_phone = fields.Char('Personal Phone')
    uid_is_user_id = fields.Boolean('Uid is User', compute='_uid_is_user_id')
    user_is_pm = fields.Boolean('User is PM', compute='_uid_is_user_id')
    uid_is_hr = fields.Boolean('UID is HR', compute='_uid_is_user_id')
    user_active = fields.Boolean(related='resource_id.user_id.active', string="User Active")
    address_id = fields.Many2one('res.partner', related='resource_id.user_id.partner_id', string='Working Address')
    address_home_id = fields.Many2one('res.partner', related='resource_id.user_id.partner_id', string='Home Address')
    pm_analytics = fields.Many2many('account.analytic.account', related='resource_id.user_id.pm_analytics', string='Projects Managed')

    @api.one
    @api.depends('first_name','middle_name','last_name')
    def _computed_fields(self):
        if self.middle_name:
            self.name = "{}, {} {}".format(self.last_name, self.first_name, self.middle_name)
        else:
            self.name = "{}, {}".format(self.last_name, self.first_name)
        self.name_related = self.name

    @api.one
    @api.depends('user_id')
    def _uid_is_user_id(self):
        self.user_is_pm = False
        self.uid_is_hr = False
        self.uid_is_user_id = (self.user_id.id == self.env.user.id)
        if self.env.ref('imsar_timekeeping.group_pms_user').id in self.user_id.groups_id.ids:
            self.user_is_pm = True
        if self.env.ref('base.group_hr_user').id in self.env.user.groups_id.ids:
            self.uid_is_hr = True

    def _recursive_children(self, emp, result=[]):
        result += [emp.id]
        if emp.child_ids:
            for child in emp.child_ids:
                if emp.id != child.id:
                    self._recursive_children(child, result)
        return result

    @api.multi
    def get_all_children(self):
        result_list = self._recursive_children(self, [])
        result = self.browse(result_list)
        return result

    @api.multi
    def accrue_pto(self, hours):
        # owners can't accrue PTO
        if self.is_owner:
            return None
        new_pto = self.accrued_pto + hours
        # can't go over max PTO
        if new_pto > self.max_pto:
            hours = self.max_pto - self.accrued_pto
            self.accrued_pto = self.max_pto
        else:
            self.accrued_pto += hours
        if hours <= 0.0:
            return None
        # credit pto liability, debit pto expense
        amount = hours * self.wage_rate
        liability_account = self.user_id.company_id.pto_liability_account_id.id
        expense_account = self.user_id.company_id.pto_expense_account_id.id
        if not liability_account or not expense_account:
            raise Warning(_("You must set PTO liability and expense accounts in Timekeeping settings."))
        move_lines = list()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        partner_id = self.user_id.company_id.partner_id.id
        refname = self.name + ' - PTO Accrual'

        liability_line = {
            'type': 'dest',
            'name': 'PTO Accrual',
            'price': -amount,
            'account_id': liability_account,
            'date_maturity': date.today(),
            'ref': refname,
        }
        converted_line = self.env['account.invoice'].line_get_convert(liability_line, partner_id, now)
        move_lines.append((0, 0, converted_line))

        expense_line = {
            'type': 'dest',
            'name': 'PTO Accrual',
            'price': amount,
            'account_id': expense_account,
            'date_maturity': date.today(),
            'ref': refname,
        }
        converted_line = self.env['account.invoice'].line_get_convert(expense_line, partner_id, now)
        move_lines.append((0, 0, converted_line))

        # post the move lines
        move_vals = {
            'ref': refname,
            'line_id': move_lines,
            'journal_id': self.user_id.company_id.timekeeping_journal_id.id,
            'date': date.today(),
            'narration': '',
            'company_id': self.user_id.company_id.id,
        }
        move = self.env['account.move'].with_context(self._context).sudo().create(move_vals)
        move.post()

    @api.multi
    def button_edit_info(self):
        self_edit = self.env['hr.employee.self.edit'].create({'notes':self.notes, 'employee_id':self.id})
        view = {
            'name': _('Notes'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.employee.self.edit',
            'view_id': self.env.ref('imsar_timekeeping.view_employee_self_edit_form').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_id': self_edit.id,
        }
        return view


class employee_self_edit(models.TransientModel):
    _name = "hr.employee.self.edit"

    notes = fields.Text('Notes')
    employee_id = fields.Many2one('hr.employee')

    @api.multi
    def button_save(self):
        employee = self.env['hr.employee'].browse(self.employee_id.id)
        employee.sudo().write({'notes': self.notes})


class resource(models.Model):
    _inherit = 'resource.resource'

    name = fields.Char('Name', default='', required=False)


class res_users(models.Model):
    _inherit = "res.users"
    _order = 'login'

    analytic_review_ids = fields.Many2many('account.analytic.account', 'analytic_user_review_rel', 'user_id', 'analytic_id', string='Reviewed Analytic Accounts')
    auth_analytics = fields.Many2many('account.analytic.account', 'analytic_user_auth_rel', 'user_id', 'analytic_id', string='Authorized Analytics')
    pm_analytics = fields.Many2many('account.analytic.account', 'analytic_user_pm_rel', 'user_id', 'analytic_id', string='Projects Managed')
    hide_analytics = fields.Many2many('account.analytic.account', 'analytic_user_hide_rel', 'user_id', 'analytic_id', string='Tasks hidden from timesheets')
    timesheet_prefs = fields.One2many('hr.timekeeping.preferences', 'user_id', string='Preferences')

    @api.multi
    def write(self, vals):
        # ensure that all users listed as PMs are in the Project Manager group
        res = super(res_users, self).write(vals)
        if len(self.pm_analytics) > 0:
            pm_group_id = self.env.ref('imsar_timekeeping.group_pms_user')
            if self.id not in pm_group_id.users.ids:
                pm_group_id.sudo().write({'users': [(4, self.id)]})
        return res


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
    oneclick_filter = fields.Boolean(store=False, compute='_dummy', search='_filter_oneclick')
    oneclick_prefs = fields.Many2many('hr.timekeeping.preferences', 'user_pref_subroute_rel', 'subrouting_id', 'user_pref', string='One Click Prefs')
    view_on_timesheet = fields.Boolean(store=False, compute='_dummy', search='_viewable_search')
    require_serial = fields.Boolean('Require Serial/Repair #', default=False)

    @api.one
    def _dummy(self):
        self.oneclick_filter = True
        self.view_on_timesheet = True

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

    def _viewable_search(self, operator, value):
        sheet_id = self.env['hr.timekeeping.sheet'].browse(value)
        aa_model = self.env['account.analytic.account']
        reviewed_ids = aa_model.search([('type','!=','view'),('user_review_ids','in',sheet_id.user_id.id)])
        auth_ids = aa_model.search(['|',('auth_users','in',sheet_id.user_id.id),('limit_to_auth','=',False)])
        shown_ids = aa_model.search([('hide_from_users','not in',sheet_id.user_id.id)])
        intersection = set.intersection(set(reviewed_ids.ids), set(auth_ids.ids), set(shown_ids.ids))
        subrouting_ids = self.env['account.routing.subrouting'].search([('account_analytic_id','in',list(intersection))]).ids
        # proxy timesheets have a set of always allowed tasks
        if sheet_id.type == 'proxy' and self.env.ref('imsar_timekeeping.group_timesheet_admin').id in self.env.user.groups_id.ids:
            ids = self.env.user.company_id.proxy_analytic_ids.ids
            proxy_ids = self.env['account.routing.subrouting'].search([('account_analytic_id','in',ids)]).ids
            subrouting_ids += proxy_ids
        return [('id','in', subrouting_ids)]


class employee_adjust_pto(models.TransientModel):
    _name = "hr.timekeeping.adjust_pto"
    _description = "Adjust accrued PTO"

    adjustment = fields.Float('Adjustment', required=True)

    @api.multi
    def submit_confirm(self):
        employee = self.env[self._context['active_model']].browse(self._context['active_id'])
        if not employee:
            raise Warning(_("Lost target employee, please contact system admin for bug report!"))
        employee.accrue_pto(self.adjustment)
        return {'type': 'ir.actions.act_window_close'}

