from datetime import datetime, date, timedelta
from dateutil.relativedelta import *
import dateutil.parser
from collections import defaultdict
import pytz
import json

from openerp import models, fields, api, _
from openerp.exceptions import Warning
import openerp.addons.decimal_precision as dp
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as DATE_FORMAT

import logging
_logger = logging.getLogger(__name__)

# helper function to get now in the correct timezone
def get_now_tz(user, config):
    _default_tz = 'America/Denver'
    if user.tz:
        now = datetime.now(pytz.timezone(user.tz))
    else:
        config_default_tz = config.search([('key','=','user.default_tz')])
        if config_default_tz:
            now = datetime.now(pytz.timezone(config_default_tz.value))
        else:
            now = datetime.now(pytz.timezone(_default_tz))
    # use a timezone, but then strip out tz info for the comparison
    return now.replace(tzinfo=None)


class hr_timekeeping_sheet(models.Model):
    _name = 'hr.timekeeping.sheet'
    _inherit = ['mail.thread']
    _description = 'Timekeeping Sheet'
    _order = 'name desc'

    # model columns
    name = fields.Char('Week Number', compute='_computed_fields', readonly=True, store=True)
    type = fields.Selection([('regular','Regular'),('addendum','Addendum'),('proxy','Proxy'),], 'Type', default='regular', required=True, readonly=True,)
    payperiod_id = fields.Many2one('hr.timekeeping.payperiod', 'Pay Period', index=True, required=True)
    week_ab = fields.Selection([('A','A'),('B','B'),], 'Pay Period Week A/B', required=True)
    date_from = fields.Date('Start Date', readonly=True, required=True)
    date_to = fields.Date('End Date', readonly=True, required=True)
    state = fields.Selection([('draft','Open'),('confirm','Waiting For Approval'),('done','Approved')],
                             'Status', index=True, required=True, readonly=True,)
    payroll_state = fields.Selection([('draft','Open'),('pending','Pending'),('submitted','Submitted to Payroll'),('failed','Failed to Submt')],
                             'Payroll Status', default="draft", index=True, required=True, readonly=True,)
    payroll_comment = fields.Char('Payroll Comment')
    uid_is_user_id = fields.Boolean(compute='_computed_fields', readonly=True)
    uid_is_proxy = fields.Boolean(compute='_computed_fields', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', index=True, required=True)
    user_id = fields.Many2one('res.users', related='employee_id.user_id', string='User', readonly=True)
    employee_flsa_status = fields.Selection(related='employee_id.flsa_status', string='FLSA Status', readonly=True)
    employee_full_time = fields.Boolean(related='employee_id.full_time', string='Full Time', readonly=True)
    line_ids = fields.One2many('hr.timekeeping.line', 'sheet_id', 'Timesheet lines', readonly=True, states={'draft':[('readonly', False)]})
    view_line_ids = fields.One2many('hr.timekeeping.line', 'sheet_id', 'Timesheet lines', related='line_ids', readonly=True,)
    subtotal_line = fields.Char(string="Subtotals: ", compute='_compute_subtotals')
    subtotal_json = fields.Char(string="internal only", compute='_compute_subtotals')
    total_time = fields.Float(string="Total Time", compute='_compute_subtotals', store=True)
    pp_total_time = fields.Float(string="Pay Period Total Time", compute='_compute_subtotals')
    pp_total_time_display = fields.Char(string="Pay Period:", compute='_compute_subtotals')
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True, ondelete='restrict',)
    approval_line_ids = fields.One2many('hr.timekeeping.approval', 'sheet_id', 'Approval lines', readonly=True, states={'draft':[('readonly', False)]})
    adv_search = fields.Char('Advanced Filter Search', compute='_computed_fields', search='_adv_search')
    editable_view = fields.Boolean(compute='_computed_fields', )
    submit_button_view = fields.Boolean(compute='_computed_fields', )
    proxy_button_view = fields.Boolean(compute='_computed_fields', )

    @api.one
    @api.depends('line_ids')
    def _compute_subtotals(self):
        totals = defaultdict(float)
        worktype_names = dict()
        total_time = 0.0
        for line in self.line_ids:
            worktype = self.env['hr.timekeeping.worktype'].browse(line.worktype.id)
            worktype_names[line.worktype.id] = worktype.name
            totals[line.worktype.id] += line.unit_amount
            total_time += line.unit_amount
        self.subtotal_line = ", ".join(["%s: %s" % (worktype_names[key], val) for key, val in totals.items()])
        self.subtotal_json = json.dumps(totals)
        self.total_time = total_time
        self.pp_total_time = 0
        for sheet in self.search([('payperiod_id','=',self.payperiod_id.id), ('employee_id','=',self.employee_id.id)]):
            self.pp_total_time += sheet.total_time
        self.pp_total_time_display = "Total time this pay period: {} (of {} for full time)".format(self.pp_total_time, self.employee_id.full_time_hours)

    @api.one
    @api.constrains('line_ids')
    def _check_subtotals(self):
        # check subtotals for each day
        day_totals = defaultdict(float)
        for line in self.line_ids:
            day_totals[line.date] += line.unit_amount
        for day, total in day_totals.items():
            if total > 24.0:
                raise Warning(_("You have more than 24 hours entered for {}, please fix before saving.".format(day)))

        subtotals = json.loads(self.subtotal_json)
        regular_worktype_id = str(self.employee_id.user_id.company_id.regular_worktype_id.id)
        overtime_worktype_id = str(self.employee_id.user_id.company_id.overtime_worktype_id.id)
        regular = subtotals.get(regular_worktype_id, 0.0)
        overtime = subtotals.get(overtime_worktype_id, 0.0)
        if self.employee_flsa_status != 'exempt':
            if regular > 40.0 and self.type == 'regular':
                raise Warning(_("You cannot log more than 40 hours of regular time."))
            if overtime > 0.0 and regular < 40.0 and self.type == 'regular':
                raise Warning(_("You cannot log overtime without having 40 hours of regular time first."))
        else:
            if overtime > 0.0:
                raise Warning(_("Exempt employees are not eligible for overtime."))

    @api.one
    @api.depends('payperiod_id', 'user_id', 'type', 'state')
    def _computed_fields(self):
        self.name = "{}-{}".format(self.payperiod_id.name, self.week_ab)
        self.uid_is_user_id = (self.user_id.id == self._context.get('uid'))
        self.adv_search = ''
        self.uid_is_proxy = False
        if self.env.ref('imsar_timekeeping.group_tk_proxy_user').id in self.env.user.groups_id.ids:
            self.uid_is_proxy = True
        # whether or not a timesheet is editable/submittable has gotten complicated, so put the logic in python
        self.editable_view = False
        self.submit_button_view = False
        self.proxy_button_view = False
        if self.state == 'draft':
            if self.uid_is_user_id:
                self.editable_view = True
                self.submit_button_view = True
            elif self.uid_is_proxy and self.type == 'proxy':
                self.editable_view = True
                self.proxy_button_view = True

    def _adv_search(self, operator, value):
        today = date.today()
        this_payperiod = self.env['hr.timekeeping.payperiod'].get_payperiod(today)
        prev_payperiod_date = datetime.strptime(this_payperiod.start_date, DATE_FORMAT) + timedelta(days=-1)
        prev_payperiod = self.env['hr.timekeeping.payperiod'].get_payperiod(prev_payperiod_date)
        week_ab = this_payperiod.get_week_ab(today)

        if value == 'this_week':
            sheets = self.env['hr.timekeeping.sheet'].search([('payperiod_id','=',this_payperiod.id), ('week_ab','=',week_ab)]).ids
        elif value == 'this_payperiod':
            sheets = self.env['hr.timekeeping.sheet'].search([('payperiod_id','=',this_payperiod.id)]).ids
        elif value == 'prev_payperiod':
            sheets = self.env['hr.timekeeping.sheet'].search([('payperiod_id','=',prev_payperiod.id)]).ids
        elif value == 'my_approvals':
            sheets = set()
            for sheet in self.env['hr.timekeeping.sheet'].search([('state','=','confirm')]):
                for approval_line in sheet.approval_line_ids:
                    if approval_line.state == 'confirm' and approval_line.uid_can_approve:
                        sheets.add(sheet.id)
            sheets = list(sheets)
        elif value == 'my_direct_approvals':
            sheets = set()
            for sheet in self.env['hr.timekeeping.sheet'].search([('state','=','confirm')]):
                for approval_line in sheet.approval_line_ids:
                    if approval_line.state == 'confirm' and approval_line.uid_can_approve and sheet.employee_id.parent_id.user_id.id == self._uid:
                        sheets.add(sheet.id)
            sheets = list(sheets)
        else:
            sheets = self.env['hr.timekeeping.sheet'].search([]).ids
        return [('id','in',sheets)]

    @api.multi
    def button_confirm(self):
        # recalc computed fields
        self._compute_subtotals()
        if self.env.user.id != self.user_id.id and self.env.ref('imsar_timekeeping.group_tk_proxy_user').id in self.env.user.groups_id.ids:
            for line in self.line_ids:
                pto_analytic_id = self.env.user.company_id.pto_analytic_id.id
                in_absentia_id = self.env.user.company_id.in_absentia_id.id
                if line.account_analytic_id.id not in [pto_analytic_id, in_absentia_id]:
                    raise Warning(_("You may only submit a timesheet for someone else if the timesheet contains only PTO and In Absentia task codes."))
        # log submission for approval
        now = get_now_tz(self.env.user, self.env['ir.config_parameter'])
        subject = "Submitted for approval"
        body = "{} submitted timesheet for approval on {}".format(self.env.user.name, now.strftime('%c'))
        self.message_post(subject=subject, body=body,)
        self.signal_workflow('confirm')
        # mark all approval lines as confirm status
        for appr_line in self.approval_line_ids:
            appr_line.signal_workflow('confirm')
        return True

    @api.multi
    def button_cancel(self):
        self.signal_workflow('cancel')
        # mark all approval lines as open status
        for appr_line in self.approval_line_ids:
            appr_line.approved_by = ''
            if appr_line.state == 'confirm':
                appr_line.signal_workflow('cancel')
            elif appr_line.state == 'done':
                appr_line.state = 'draft'
                appr_line.create_workflow()
        return { 'type': 'ir.actions.client', 'tag': 'reload' }

    @api.multi
    def button_self_cancel(self):
        now = get_now_tz(self.env.user, self.env['ir.config_parameter'])
        subject = "Submission set back to Open"
        body = "{} set timesheet back to Open on {}".format(self.env.user.name, now.strftime('%c'))
        self.message_post(subject=subject, body=body,)
        return self.button_cancel()

    @api.multi
    def button_addendum(self):
        ctx = {'regular_timesheet_id': self.id}
        ctx.update(self._context)
        # make sure to get v7 version of ir.actions.server with self.pool.get
        action_server_obj = self.pool.get('ir.actions.server')
        action_id = self.env.ref('imsar_timekeeping.action_hr_timekeeping_addendum_open').id
        return action_server_obj.run(self._cr, self._uid, action_id, context=ctx)

    @api.multi
    def button_previous_timesheet(self):
        ctx = dict()
        ctx['date_override'] = datetime.strptime(self.date_from, DATE_FORMAT) - timedelta(days=7)
        ctx.update(self._context)
        action_server_obj = self.pool.get('ir.actions.server')
        action_id = self.env.ref('imsar_timekeeping.action_hr_timekeeping_current_open').id
        return action_server_obj.run(self._cr, self._uid, action_id, context=ctx)

    @api.multi
    def button_next_timesheet(self):
        ctx = dict()
        ctx['date_override'] = datetime.strptime(self.date_from, DATE_FORMAT) + timedelta(days=7)
        ctx.update(self._context)
        action_server_obj = self.pool.get('ir.actions.server')
        action_id = self.env.ref('imsar_timekeeping.action_hr_timekeeping_current_open').id
        return action_server_obj.run(self._cr, self._uid, action_id, context=ctx)

    @api.multi
    def button_oneclick_add(self):
        today_lines = self.line_ids.search([('sheet_id','=',self.id),('date','=',date.today().strftime(DATE_FORMAT))])
        today_tasks = [line.routing_subrouting_id for line in today_lines]
        for task in self.env.user.timesheet_prefs.oneclick_tasks:
            if task not in today_tasks:
                vals = {
                    'sheet_id': self.id,
                    'routing_id': task.routing_id.id,
                    'routing_line_id': task.routing_line_id.id,
                    'routing_subrouting_id': task.id,
                    'date': date.today().strftime(DATE_FORMAT),
                    'change_explanation': '',
                }
                id = self.env['hr.timekeeping.line'].create(vals)

    @api.multi
    def button_retry_payroll(self):
        self.payroll_state = 'pending'
        self.payroll_comment = ''

    @api.multi
    def button_process_addendum(self):
        self.payroll_state = 'submitted'

    @api.multi
    def button_create_line(self):
        view = {
            'name': _('Create Entry'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.timekeeping.line',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'res_id': False,
        }
        return view

    def accrue_pto(self, pp_total):
        # all full-time employees can accrue PTO from a maximum of 80 hours per pay period
        overage = pp_total - 80
        if overage > 0:
            accrue_hours = self.total_time - overage
        else:
            accrue_hours = self.total_time
        if accrue_hours > 0:
            accrued_pto = accrue_hours * self.employee_id.pto_accrual_rate
            self.employee_id.accrue_pto(accrued_pto)

    @api.multi
    def _make_move_lines(self):
        ts_move_lines = list()
        partner_id = self.employee_id.user_id.company_id.partner_id.id
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        refname = self.employee_id.name + ' - ' + self.name

        # prepare move lines per subrouting
        total_amount = 0.0
        move_line_summary = defaultdict(float)
        overtime_worktype_id = self.user_id.company_id.overtime_worktype_id.id
        for line in self.line_ids:
            # if this line already has a move line associated, skip it
            if(line.move_line_ids):
                continue
            category = line.routing_id.name
            task = line.routing_subrouting_id.name
            worktype = line.worktype.name
            name = "{0} - {1} ({2})".format(category, task, worktype)
            if name not in move_line_summary:
                move_line_summary[name] = {
                    'worktype_id': line.worktype.id,
                    'subroute': line.routing_subrouting_id,
                    'line_ids': list(),
                    'sums': defaultdict(float)
                }
            move_line_summary[name]['sums']['quantity'] += line.unit_amount
            move_line_summary[name]['sums']['price'] += line.amount
            move_line_summary[name]['sums']['premium_amount'] += line.premium_amount
            move_line_summary[name]['line_ids'].append(line.id)
            total_amount += line.amount + line.premium_amount

        for name, vals in move_line_summary.iteritems():
            # make a move line for the base amount
            temp_line = {
                'name': name,
                'price': vals['sums']['price'],
                'account_id': vals['subroute'].account_id.id,
                'type': 'dest',
                'quantity': vals['sums']['quantity'],
                'account_analytic_id': vals['subroute'].account_analytic_id.id,
                'date_maturity': date.today(),
                'ref': refname,
            }
            # adding values post conversion takes an extra step
            converted_line = self.env['account.invoice'].line_get_convert(temp_line, partner_id, now)
            converted_line.update({'timekeeping_line_ids': [(6, 0, vals['line_ids'])]})
            ts_move_lines.append((0, 0, converted_line))

            # add another line for the premium addition, if any
            if vals['sums']['premium_amount'] != 0.0:
                # some contracts don't allow overtime premiums to be charged to them, so deal with that here
                contract_overtime_routing = vals['subroute'].account_analytic_id.overtime_account
                if contract_overtime_routing and vals['worktype_id'] == overtime_worktype_id:
                    temp_line.update({'account_id': contract_overtime_routing.id})
                temp_line.update({
                    'name': name + ' premium',
                    'price': vals['sums']['premium_amount'],
                })
                converted_line = self.env['account.invoice'].line_get_convert(temp_line, partner_id, now)
                converted_line.update({'timekeeping_line_ids': [(6, 0, vals['line_ids'])]})
                ts_move_lines.append((0, 0, converted_line))

        # Get the wage liability account for the balancing move line
        liability_account = self.user_id.company_id.wage_account_id.id
        # Get the wage liability account for owners (currently only 2, yay for random exceptions)
        if self.employee_id.is_owner:
            liability_account = self.employee_id.owner_wage_account_id.id

        if total_amount != 0.0:
            # add one move line to balance journal entry
            balance_line = {
                'type': 'dest',
                'name': 'Payroll entry',
                'price': -total_amount,
                'account_id': liability_account,
                'date_maturity': date.today(),
                'ref': refname,
            }
            converted_line = self.env['account.invoice'].line_get_convert(balance_line, partner_id, now)
            ts_move_lines.append((0, 0, converted_line))

        if ts_move_lines:
            return ts_move_lines
        else:
            return []

    @api.multi
    def button_done(self):
        # this is called (with sudo) once all approval lines are done
        lines = self._make_move_lines()
        if lines and not self.move_id:
            name = self.employee_id.name + ' - ' + self.name
            if not self.employee_id.user_id.company_id.timekeeping_journal_id:
                raise Warning(_('You must set a timesheet journal in the Settings->HR Settings before you can approve timesheets.'))
            move_vals = {
                'ref': name,
                'line_id': lines,
                'journal_id': self.employee_id.user_id.company_id.timekeeping_journal_id.id,
                'date': date.today(),
                'narration': '',
                'company_id': self.employee_id.user_id.company_id.id,
            }
            move = self.env['account.move'].with_context(self._context).create(move_vals)
            # mark this move on this timesheet, post the journal entry, go to 'done' workflow
            self.move_id = move.id
            move.post()
        now = get_now_tz(self.env.user, self.env['ir.config_parameter'])
        subject = "Submission final approval"
        body = "All approvals met on {}".format(now.strftime('%c'))
        self.message_post(subject=subject, body=body,)
        self.signal_workflow('done')

        if self.employee_id.full_time and not self.employee_id.is_owner:
            pp_total = 0
            for sheet in self.search([('payperiod_id','=',self.payperiod_id.id), ('employee_id','=',self.employee_id.id), ('state','=','done')]):
                pp_total += sheet.total_time
            # full-time employees accrue PTO
            self.accrue_pto(pp_total)
            # also need to decrement PTO if they used it
            pto_analytic_id = self.employee_id.user_id.company_id.pto_analytic_id.id
            for line in self.line_ids:
                if line.account_analytic_id.id == pto_analytic_id:
                    self.employee_id.accrued_pto -= line.unit_amount
        # refresh the page
        return {'type': 'ir.actions.client', 'tag': 'reload'}

    @api.model
    def create(self, vals):
        new_id = super(hr_timekeeping_sheet, self).create(vals)
        approval_vars = {'type': 'Admin', 'state': 'draft', 'sheet_id': new_id[0].id,}
        self.env['hr.timekeeping.approval'].sudo().create(approval_vars)
        approval_vars.update({'type': 'Manager'})
        self.env['hr.timekeeping.approval'].sudo().create(approval_vars)
        return new_id

    @api.multi
    def write(self, vals):
        # add PM approval lines for any timesheet lines for contracts/projects, and SeniorManagement if there are any Unallowable lines
        res = super(hr_timekeeping_sheet, self).write(vals)
        existing_approval_project_ids = set()
        contains_seniormanagement_approval = False
        for approval_line in self.approval_line_ids:
            if approval_line.account_analytic_id:
                existing_approval_project_ids.add(approval_line.account_analytic_id.id)
            if approval_line.type == 'SeniorManagement':
                contains_seniormanagement_approval = True
        existing_project_ids = set()
        # add approval lines for contracts that have non-zero hours
        time_sum = defaultdict(float)
        contains_unallowable_task = False
        for line in self.line_ids:
            analytic = line.routing_subrouting_id.account_analytic_id
            existing_project_ids.add(analytic.id)
            time_sum[analytic.id] += line.unit_amount
            if analytic.type == 'contract' and analytic.id not in existing_approval_project_ids and time_sum[analytic.id] > 0:
                approval_vars = {'type': 'Project', 'state': 'draft', 'sheet_id': self.id, 'account_analytic_id': analytic.id}
                self.env['hr.timekeeping.approval'].sudo().create(approval_vars)
                existing_approval_project_ids.add(analytic.id)
            if not analytic.dcaa_allowable:
                contains_unallowable_task = True
                if not contains_seniormanagement_approval:
                    approval_vars = {'type': 'SeniorManagement', 'state': 'draft', 'sheet_id': self.id}
                    self.env['hr.timekeeping.approval'].sudo().create(approval_vars)
                    contains_seniormanagement_approval = True
        # remove approval lines if no timesheet lines exist for those projects, or total time for it is 0
        # remove 'SeniorManagement' approval lines if no unallowable tasks exist
        for approval_line in self.approval_line_ids:
            analytic = approval_line.account_analytic_id
            if approval_line.account_analytic_id.type == 'contract' and (approval_line.account_analytic_id.id not in existing_project_ids or time_sum[analytic.id] == 0):
                approval_line.sudo().unlink()
            elif approval_line.type == 'SeniorManagement' and not contains_unallowable_task:
                approval_line.sudo().unlink()
        return res


class hr_timekeeping_line(models.Model):
    _name = 'hr.timekeeping.line'
    _keys_to_log = ['date','routing_id','routing_subrouting_id','name','unit_amount','location']
    _description = 'Timekeeping Sheet Line'
    _order = 'date desc, create_date desc'

    # model columns
    sheet_id = fields.Many2one('hr.timekeeping.sheet', string='Timekeeping Sheet', required=True)
    user_id = fields.Many2one('res.users', string='User', readonly=True, default=lambda self: self.env.user)
    uid_is_user_id = fields.Boolean(compute='_computed_fields', readonly=True)
    uid_is_proxy = fields.Boolean(compute='_computed_fields', readonly=True)
    name = fields.Char('Description')
    unit_amount = fields.Float('Quantity', help='Specifies the amount of quantity to count.')
    amount = fields.Float('Amount', required=True, default=0.0, digits=dp.get_precision('Account'))
    premium_amount = fields.Float(string='Premium Amount', required=True, default=0.0, help='The additional amount based on work type, like overtime', digits=dp.get_precision('Account'))
    full_amount = fields.Float(string='Final Amount', digits=dp.get_precision('Account'), compute='_computed_fields', readonly=True, store=True)
    # NOTE: when using a functional default, make sure to use a lambda, or else the default will be a static value from the server start
    date = fields.Date(string='Date', required=True, default=lambda self: date.today().strftime(DATE_FORMAT))
    previous_date = fields.Date(string='Previous Date', invisible=True)
    day_name = fields.Char(compute='_day_name', string='Day')
    routing_id = fields.Many2one('account.routing', 'Category', required=True, default=lambda self: self._get_user_default_route())
    routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True, default=lambda self: self._get_user_default_subroute())
    account_analytic_id = fields.Many2one('account.analytic.account', related='routing_subrouting_id.account_analytic_id', readonly=True)
    aa_dcaa_allowable = fields.Boolean(related='routing_subrouting_id.account_analytic_id.dcaa_allowable', readonly=True)
    location = fields.Selection([('office','Office'),('home','Home')], string='Work Location', required=True, default='office', help="Location the hours were worked",)
    change_reason = fields.Selection([('Correction','Task Code Correction'),('Travel','On Travel'),
                                      ('Forgot','Forgot Previous Entry'),('Other','Other (requires explanation)')], string="Change Reason")
    change_explanation = fields.Char(string='Change Explanation')
    state = fields.Char(compute='_check_state', default='open') # 'past','open','future'
    sheet_state = fields.Selection(related='sheet_id.state', readonly=True)
    logging_required = fields.Boolean(compute='_check_state')
    worktype = fields.Many2one('hr.timekeeping.worktype', string="Work Type", ondelete='restrict', required=True, default=lambda self: self._get_default_worktype())
    # this timekeeping_line_move_line_rel table is going to get massive, but I don't know of another way to do it
    move_line_ids = fields.Many2many('account.move.line', 'timekeeping_line_move_line_rel', 'timekeeping_line_id', 'move_line_id', string='Related move lines')
    dcaa_allowable = fields.Boolean("FAR 31.2 Allowable", default=True)
    # At some point this will need to directly link to quant (serial) for direct MFG, warranty repair for repair order, and sales order for customer support
    # for now, we'll just leave a comment and get a report for accounting to record the expense
    serial_reference = fields.Char(string='Serial/Repair #')
    # this would be much easier with a fields.Time
    start_time = fields.Char("Start time")
    end_time = fields.Char("End time")
    display_color = fields.Selection(related='routing_subrouting_id.account_analytic_id.display_color', readonly=True)
    old_task_code = fields.Char("Old Task Code", related="routing_subrouting_id.old_task_code", readonly=True)

    @api.one
    @api.depends('date')
    def _day_name(self):
        self.day_name = fields.Date.from_string(self.date).strftime('%A')

    @api.one
    @api.depends('date', 'previous_date')
    def _check_state(self):
        now = get_now_tz(self.env.user, self.env['ir.config_parameter'])
        # if editing an existing record and the old date not within open window, require logging regardless
        self.logging_required = False
        if self.previous_date:
            prev_date = datetime.strptime(self.previous_date, '%Y-%m-%d')
            prev_deadline = prev_date + timedelta(days=1, hours=11)
            if not (now < prev_deadline):
                self.logging_required = True
        if not self.date:
            return
        # see if the selected date is within the open window
        check_date = datetime.strptime(self.date, '%Y-%m-%d')
        if check_date > now:
            self.state = 'future'
            # self.logging_required = True
        else:
            deadline = check_date + timedelta(days=1, hours=11)
            if (check_date < now < deadline):
                self.state = 'open'
            else:
                self.state = 'past'
                self.logging_required = True
        # in addition to all that, if someone else is editing this timesheet, log it
        if self.user_id.id != self.env.user.id:
            self.logging_required = True

    @api.one
    @api.constrains('unit_amount', 'worktype')
    def _check_hours(self):
        if self.unit_amount > 24.0:
            raise Warning(_("You cannot have more than 24 hours entered a single day."))
        if self.unit_amount % 0.25 != 0:
            raise Warning(_("You may only submit time in quarter-hour increments."))
        self.sheet_id._check_subtotals()

    @api.one
    @api.constrains('routing_id', 'routing_line_id', 'routing_subrouting_id', 'worktype')
    def _check_routing(self):
        if (self.routing_line_id not in self.routing_id.routing_lines) or (self.routing_subrouting_id not in self.routing_line_id.subrouting_ids):
            raise Warning(_("You have an invalid task code. Please fix before saving."))
        if self.routing_subrouting_id.account_analytic_id.linked_worktype and (self.worktype != self.routing_subrouting_id.account_analytic_id.linked_worktype):
            raise Warning(_("You cannot have that task with that work type. Please fix before saving."))
        if self.worktype.id == 2 and not self.routing_subrouting_id.qb_payroll_item_ot:
            raise Warning(_("This task code doesn't have an overtime mapping to Quickbooks. Please contact accounting."))

    @api.multi
    def _log_changes(self, vals, new_record=False):
        if not vals:
            return True
        # log any changes that are outside the valid time window
        body = "<strong>Change reason:</strong> {}<br>".format(vals['change_reason_log'])
        if vals['change_reason_log'] == 'Other':
            body += "<strong>Change explanation:</strong> {}<br>".format(vals['change_explanation_log'])
        if new_record:
            record = vals.get('id')
            subject = "New record, Line ID: %s" % record.id
            line_str = "<strong>{0}</strong> set to {2}<br>"
            sheet = record.sheet_id
        else:
            subject = 'Changes made to Line ID: %s' % self.id
            line_str = "<strong>{0}</strong> from {1} to {2}<br>"
            sheet = self.sheet_id
        for key in list(set(self._keys_to_log) & set(vals.keys())):
            val = vals.get(key)
            key_str = self._all_columns[key].column.string
            if isinstance(self[key], models.Model):
                oldval = self[key].name
                newval = self[key].browse(val).name
            else:
                oldval = self[key]
                newval = val
            body += (line_str.format(key_str, oldval, newval))
        sheet.message_post(subject=subject, body=body,)

    @api.one
    @api.depends('user_id', 'amount', 'premium_amount')
    def _computed_fields(self):
        # You'd think you could just use a related field to self.sheet.uid_is_user_id, right?
        # Guess again! Related field to computed field loses the self._uid of the function call
        self.uid_is_user_id = (self.user_id.id == self._uid)
        self.full_amount = self.amount + self.premium_amount
        self.uid_is_proxy = False
        if self.env.ref('imsar_timekeeping.group_tk_proxy_user').id in self.env.user.groups_id.ids:
            self.uid_is_proxy = True

    @api.model
    def _safety_checks(self, sheet):
        if sheet.state != 'draft':
            raise Warning(_("You cannot make changes to this timesheet!"))
        if not sheet.uid_is_user_id and not sheet.uid_is_proxy:
            raise Warning(_("You cannot make changes to this timesheet!"))

    @api.multi
    def write(self, vals):
        # because the details button allows editing when the sheet isn't in edit mode, need to manually call _compute_subtotals
        self.sheet_id._compute_subtotals()
        # for some reason write gets called twice with this setup, the second time with context as first arg
        if vals.get('active_model') != None:
            return True
        self._safety_checks(self.sheet_id)
        vals['previous_date'] = vals.get('date') or self.date
        if self.logging_required:
            vals['change_explanation_log'] = vals.get('change_explanation')
            vals['change_explanation'] = ''
            vals['change_reason_log'] = vals.get('change_reason')
            vals['change_reason'] = ''
            self._log_changes(vals)
            del vals['change_explanation_log']
            del vals['change_reason_log']
        unit_amount = vals.get('unit_amount') or self.unit_amount
        worktype_id = vals.get('worktype') or self.worktype.id
        worktype = self.env['hr.timekeeping.worktype'].browse(worktype_id)
        vals['amount'] = self.sheet_id.employee_id.wage_rate * unit_amount
        vals['premium_amount'] = vals['amount'] * worktype.premium_rate
        return super(hr_timekeeping_line, self).write(vals)

    @api.model
    def create(self, vals, override=False):
        vals['previous_date'] = vals['date']
        vals['change_explanation_log'] = vals['change_explanation']
        vals['change_explanation'] = ''
        vals['change_reason_log'] = vals.get('change_reason')
        vals['change_reason'] = ''
        unit_amount = vals.get('unit_amount', 0.0)
        worktype_id = vals.get('worktype')
        worktype = self.env['hr.timekeeping.worktype'].browse(worktype_id)
        sheet_id = vals.get('sheet_id')
        sheet = self.env['hr.timekeeping.sheet'].browse(sheet_id)
        if not override:
            self._safety_checks(sheet)
        vals['user_id'] = sheet.user_id.id
        vals['amount'] = sheet.employee_id.wage_rate * unit_amount
        vals['premium_amount'] = vals['amount'] * worktype.premium_rate
        vals['id'] = super(hr_timekeeping_line, self).create(vals)
        if vals['id'].logging_required:
            self._log_changes(vals, new_record=True)
        return vals.get('id')

    @api.multi
    def unlink(self):
        self._safety_checks(self.sheet_id)
        if self.logging_required:
            subject = 'Deleted Line ID: %s' % self.id
            body = ''
            for key in self._keys_to_log:
                key_str = self._all_columns[key].column.string
                if isinstance(self[key], models.Model):
                    oldval = self[key].name
                else:
                    oldval = self[key]
                body += 'Removed <strong>%s</strong>: <strong>%s</strong><br>' % (key_str, oldval)

            self.sheet_id.message_post(subject=subject, body=body,)
        super(hr_timekeeping_line, self).unlink()
        return { 'type': 'ir.actions.client', 'tag': 'reload' }

    def _compute_duration(self):
        if self.start_time and self.end_time:
            start_time = dateutil.parser.parse(self.start_time, fuzzy=True)
            end_time = dateutil.parser.parse(self.end_time, fuzzy=True)
            diff = end_time - start_time
            diff_hours = diff.seconds/60.0/60.0
            if diff_hours:
                self.unit_amount = diff_hours

    @api.onchange('unit_amount')
    def onchange_unit_amount(self):
        if self.unit_amount > 24.0:
            raise Warning(_("You cannot have more than 24 hours entered a single day."))
        if self.start_time and self.unit_amount:
            start_time = dateutil.parser.parse(self.start_time, fuzzy=True)
            new_end_time = start_time + timedelta(seconds=self.unit_amount*60*60)
            new_end_time_str = new_end_time.strftime('%H:%M:00')
            if self.end_time != new_end_time_str:
                self.end_time = new_end_time_str
        if self.unit_amount % 0.25 != 0:
            return {'warning': {'title': 'Invalid time entry', 'message': 'You may only submit time in quarter-hour increments.'}}

    @api.onchange('start_time')
    def onchange_start_time(self):
        self._compute_duration()

    @api.onchange('end_time')
    def onchange_end_time(self):
        self._compute_duration()

    @api.onchange('date')
    def onchange_date(self):
        if not self.sheet_id:
            self.sheet_id = self.env['hr.timekeeping.sheet'].browse(self._context['active_id'])
        date = datetime.strptime(self.date, '%Y-%m-%d')
        from_date = datetime.strptime(self.sheet_id.date_from, '%Y-%m-%d')
        to_date = datetime.strptime(self.sheet_id.date_to, '%Y-%m-%d')
        if from_date > date:
            self.date = ''
        if to_date < date:
            self.date = ''
        self._check_state()
        if self.state == 'future':
            future_analytics = self.env.user.company_id.future_analytic_ids
            if not (self.routing_subrouting_id.account_analytic_id and self.routing_subrouting_id.account_analytic_id in future_analytics.ids):
                self.routing_id = ''

    @api.multi
    def button_details(self):
        view = {
            'name': _('Entry Details'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.timekeeping.line',
            'view_id': self.env.ref('imsar_timekeeping.hr_timekeeping_line_form_editable').id,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'readonly': True,
            'res_id': self.id,
        }
        return view

    @api.model
    def _get_timekeeping_routing_line(self, routing_id):
        timekeeping_id = self.env['ir.model.data'].xmlid_to_res_id('imsar_timekeeping.ar_section_timekeeping')
        routing_line = self.env['account.routing.line'].search([
            ('routing_id','=',routing_id),
            ('section_ids','in',[timekeeping_id]),
        ])
        # this is admittedly sketchy, but there *should* only ever be one labor routing line per category
        if routing_line and len(routing_line) > 1:
            routing_line = routing_line[0]
        return routing_line

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        routing_line = self._get_timekeeping_routing_line(self.routing_id.id)
        self.routing_line_id = routing_line or ''
        if not (routing_line and self.routing_subrouting_id in routing_line.subrouting_ids and self.state != 'future'):
            self.routing_subrouting_id = ''

    @api.onchange('routing_subrouting_id')
    def onchange_subrouting_id(self):
        if self.routing_subrouting_id.account_analytic_id.linked_worktype:
            self.worktype = self.routing_subrouting_id.account_analytic_id.linked_worktype.id
        else:
            general_worktypes = self.env['hr.timekeeping.worktype'].search([('limited_use','=',False)])
            if self.worktype.id not in general_worktypes.ids:
                self.worktype = general_worktypes[0].id

    @api.onchange('dcaa_allowable')
    def onchange_dcaa(self):
        if self.dcaa_allowable != self.routing_subrouting_id.account_analytic_id.dcaa_allowable:
            self.routing_subrouting_id = ''

    @api.model
    def _get_default_worktype(self):
        return self.env.user.company_id.regular_worktype_id.id

    @api.model
    def _get_user_default_route(self):
        return self.env.user.timesheet_prefs.routing_id or ''

    @api.model
    def _get_user_default_subroute(self):
        return self.env.user.timesheet_prefs.routing_subrouting_id or ''


class hr_timekeeping_approval(models.Model):
    _name = 'hr.timekeeping.approval'
    _description = 'Timekeeping Approval Line'

    type = fields.Selection([('Admin','Admin'),('Manager','Manager'),('Project','Project'),('SeniorManagement', 'Senior Management')], string="Approval Type", required=True, readonly=True)
    sheet_id = fields.Many2one('hr.timekeeping.sheet', string='Timekeeping Sheet', required=True)
    state = fields.Selection([('draft','Open'),('confirm','Waiting For Approval'),('done','Approved')],
                             'Status', index=True, required=True, readonly=True,)
    account_analytic_id = fields.Many2one('account.analytic.account', 'Contract/Project', readonly=True,)
    uid_can_approve = fields.Boolean(compute='_computed_fields', readonly=True)
    relevant_time = fields.Float(compute='_computed_fields', readonly=True)
    approved_by = fields.Many2one('res.users', 'Approved By')

    @api.one
    def _computed_fields(self):
        # defaults to false unless condition is met
        self.uid_can_approve = False
        self.relevant_time = self.sheet_id.total_time

        user = self.env.user
        # check to see if user is timesheet admin
        if self.type == 'Admin':
            ts_admin = self.env['res.groups'].search([('name','=','Timesheet Admin')])
            if ts_admin in user.groups_id:
                self.uid_can_approve = True
        # check to see if user is PM on this project
        elif self.type == 'Project':
            if user in self.account_analytic_id.pm_ids:
                self.uid_can_approve = True
            lines = self.env['hr.timekeeping.line'].search([('sheet_id','=',self.sheet_id.id),('account_analytic_id','=',self.account_analytic_id.id),])
            self.relevant_time = sum(line.unit_amount for line in lines)
        # check to see if user is manager for the timesheet's owner
        elif self.type == 'Manager':
            manager = self.sheet_id.employee_id.parent_id
            while manager:
                if user == manager.resource_id.user_id:
                    self.uid_can_approve = True
                    break
                manager = manager.parent_id
        # calculate relevant unallowable time
        elif self.type == 'SeniorManagement':
            lines = self.env['hr.timekeeping.line'].search([('sheet_id','=',self.sheet_id.id),('aa_dcaa_allowable','=',False),])
            self.relevant_time = sum(line.unit_amount for line in lines)
        # check if the user has global approval rights (this includes SeniorManagement lines)
        if user in self.sheet_id.employee_id.user_id.company_id.global_approval_user_ids:
            self.uid_can_approve = True

    @api.multi
    def log_rejection(self, comment=''):
        now = get_now_tz(self.env.user, self.env['ir.config_parameter'])
        subject = "Submission rejected"
        body = "{} rejected timesheet for approval on {}".format(self.env.user.name, now.strftime('%c'))
        if comment:
            body += "<br><strong>Comment:</strong> {}".format(comment)
        self.sheet_id.message_post(subject=subject, body=body,)
        # send email
        template = self.env.ref('imsar_timekeeping.reject_timesheet_email')
        ctx = self._context.copy()
        ctx.update({'body': body, 'comment': comment})
        self.pool.get('email.template').send_mail(self._cr, self._uid, template.id, self.id, force_send=True, raise_exception=True, context=ctx)
        return self.sheet_id.button_cancel()

    @api.multi
    def button_reject(self):
        view = {
            'name': _('Rejection Comment'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.timekeeping.comment',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'readonly': True,
        }
        return view

    @api.multi
    def button_approve(self):
        # log approval line approval
        now = get_now_tz(self.env.user, self.env['ir.config_parameter'])
        subject = "Submission approved"
        body = "{} approved {} line on {}".format(self.env.user.name, self.type, now.strftime('%c'))
        self.sheet_id.message_post(subject=subject, body=body,)
        self.signal_workflow('done')
        self.approved_by = self.env.user
        # if everything is approved, signal done for the whole sheet
        all_done = True
        for approval_line in self.sheet_id.approval_line_ids:
            if approval_line.state != 'done':
                all_done = False
        if all_done:
            # this has to sudo because it makes the accounting move lines
            return self.sheet_id.sudo().button_done()


# new model to deal with premium pay rates (overtime, danger, etc)
class hr_timekeeping_worktype(models.Model):
    _name = 'hr.timekeeping.worktype'

    name = fields.Char('Name', required=True)
    active = fields.Boolean('Active', default=True)
    premium_rate = fields.Float('Additional Premium Rate', required=True, default=0.0,
                        help="The additional multiplier to be added on top of the base pay. For example, overtime would be 0.5, for a 50% premium.")
    nonexempt_limit = fields.Integer('Non-exempt Limit (Hours)',
                        help="Weekly limit of hours for this type for non-exempt employees. Enter 0 or leave blank for no limit.")
    limited_use = fields.Boolean('Limit To Specific Analytic Accounts', default=False)
    linked_analytic_ids = fields.One2many('account.analytic.account', 'linked_worktype', string='Linked Analytics')
    task_worktype_search = fields.Boolean(compute='_computed_fields', search='_task_worktype_search', readonly=True, store=False)

    @api.one
    def _computed_fields(self):
        self.task_worktype_search = False

    def _task_worktype_search(self, operator, value):
        worktypes = self.env['hr.timekeeping.worktype'].search([])
        subroute = self.env['account.routing.subrouting'].browse([value])
        if subroute.account_analytic_id.linked_worktype:
            worktypes = subroute.account_analytic_id.linked_worktype
        else:
            worktypes = self.env['hr.timekeeping.worktype'].search([('limited_use','=',False)])
        return [('id','in',worktypes.ids)]


class hr_timekeeping_preferences(models.Model):
    _name = "hr.timekeeping.preferences"
    _description = "hr.timekeeping.preferences"

    name = fields.Char(compute='_computed_fields', readonly=True)
    user_id = fields.Many2one('res.users', 'User', )
    routing_id = fields.Many2one('account.routing', 'Category',)
    routing_line_id = fields.Many2one('account.routing.line', 'Billing Type',)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code',)
    oneclick_tasks = fields.Many2many('account.routing.subrouting', 'user_pref_subroute_rel', 'user_pref', 'subrouting_id', string='One Click Tasks')

    @api.one
    def _computed_fields(self):
        self.name = self.user_id.name + ' Timesheet Preferences'

    @api.onchange('routing_id')
    def onchange_routing_id_pref(self):
        routing_line = self.env['hr.timekeeping.line']._get_timekeeping_routing_line(self.routing_id.id)
        self.routing_line_id = routing_line
        if self.routing_subrouting_id not in routing_line.subrouting_ids:
            self.routing_subrouting_id = ''


class hr_timekeeping_payperiod(models.Model):
    _name = "hr.timekeeping.payperiod"
    _description = "hr.timekeeping.payperiod"
    _order = 'year,period_num'

    name = fields.Char('Pay Period', compute='_computed_fields', readonly=True)
    year = fields.Integer('Year', default=lambda self: datetime.now().year)
    period_num = fields.Integer('Pay Period Number')
    start_date = fields.Date('Start Date', index=True)
    end_date = fields.Date('End Date', index=True)
    pay_date = fields.Date('Pay Date', index=True)
    sheet_ids = fields.One2many('hr.timekeeping.sheet', 'payperiod_id', 'Timesheets')

    @api.one
    def _computed_fields(self):
        self.name = "{}-{}".format(self.year, self.period_num)

    @api.model
    def get_payperiod(self, search_date):
        # try fuzzy parse on date if str?
        pp = self.search([('start_date','<=',search_date),('end_date','>=',search_date)])
        return pp

    @api.model
    def get_first_day_of_week(self, search_date):
        return search_date + relativedelta(weekday=SU(-1))

    @api.multi
    def get_week_ab(self, search_date):
        mid_date = datetime.strptime(self.start_date, DATE_FORMAT) + timedelta(days=7)
        search_date = datetime(search_date.year, search_date.month, search_date.day)
        if search_date < mid_date:
            return 'A'
        return 'B'