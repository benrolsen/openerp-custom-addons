from datetime import datetime, date, timedelta
from collections import defaultdict
import pytz
import json

from openerp import models, fields, api, _
from openerp.exceptions import Warning
import openerp.addons.decimal_precision as dp
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as DATE_FORMAT

# helper function since sheets are primarily based off week number
def week_start_date(year, week):
    if not year:
        year = date.today().year
    if not week:
        week = date.today().isocalendar()[1]
    d = date(year, 1, 1)
    delta_days = d.isoweekday() - 1
    delta_weeks = week
    if year == d.isocalendar()[0]:
        delta_weeks -= 1
    delta = timedelta(days=-delta_days, weeks=delta_weeks)
    return d + delta

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
    _order = 'year,week_number desc'

    # model columns
    name = fields.Char('Week Number', compute='_computed_fields', readonly=True, store=True)
    type = fields.Selection([('regular','Regular'),('addendum','Addendum'),], 'Type', default='regular', required=True, readonly=True,)
    year = fields.Integer(string="Year")
    week_number = fields.Integer(string="Week Number")
    date_from = fields.Date(compute='_computed_fields', readonly=True)
    date_to = fields.Date(compute='_computed_fields', readonly=True)
    state = fields.Selection([('draft','Open'),('confirm','Waiting For Approval'),('done','Approved')],
                             'Status', select=True, required=True, readonly=True,)
    uid_is_user_id = fields.Boolean(compute='_computed_fields', readonly=True)
    user_id = fields.Many2one('res.users', string='User', readonly=True, default=lambda self: self.env.user)
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    employee_flsa_status = fields.Selection(related='employee_id.flsa_status', string='FLSA Status', readonly=True)
    line_ids = fields.One2many('hr.timekeeping.line', 'sheet_id', 'Timesheet lines', readonly=True, states={'draft':[('readonly', False)]})
    view_line_ids = fields.One2many('hr.timekeeping.line', 'sheet_id', 'Timesheet lines', related='line_ids', readonly=True,)
    subtotal_line = fields.Char(string="Subtotals: ", compute='_compute_subtotals')
    subtotal_json = fields.Char(string="internal only", compute='_compute_subtotals')
    total_time = fields.Float(string="Total Time", compute='_compute_subtotals', store=True)
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True, ondelete='restrict',)
    approval_line_ids = fields.One2many('hr.timekeeping.approval', 'sheet_id', 'Approval lines', readonly=True, states={'draft':[('readonly', False)]})

    @api.one
    @api.depends('line_ids')
    def _compute_subtotals(self):
        totals = defaultdict(float)
        worktype_names = dict()
        total_time = 0.0
        for line in self.line_ids:
            worktype = self.env['hr.timekeeping.worktype'].browse(line.worktype.id)
            worktype_names[line.worktype.id] = worktype.name
            if line.routing_subrouting_id.account_analytic_id not in worktype.nonexempt_limit_ignore_ids:
                totals[line.worktype.id] += line.unit_amount
            total_time += line.unit_amount
        self.subtotal_line = ", ".join(["%s: %s" % (worktype_names[key], val) for key, val in totals.items()])
        self.subtotal_json = json.dumps(totals)
        self.total_time = total_time

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
    @api.depends('week_number', 'year', 'user_id')
    def _computed_fields(self):
        self.name = "Week {} of {}".format(self.week_number, self.year)
        self.date_from = week_start_date(self.year, self.week_number)
        self.date_to = week_start_date(self.year, self.week_number) + timedelta(days=6)
        self.uid_is_user_id = (self.user_id.id == self._context.get('uid'))

    @api.multi
    def button_confirm(self):
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

    @api.multi
    def _make_move_lines(self):
        ts_move_lines = list()
        name = self.employee_id.name + ' - ' + self.name
        partner_id = self.employee_id.user_id.company_id.partner_id.id
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # prepare move lines per timesheet entry
        total_amount = 0.0
        for line in self.line_ids:
            # if this line already has a move line associated, skip it
            if(line.move_line_ids):
                continue
            temp_line = {
                'type': 'dest',
                'quantity': line.unit_amount,
                'account_analytic_id': line.routing_subrouting_id.account_analytic_id.id,
                'date_maturity': date.today(),
                'ref': name,
            }
            # make a move line for the base amount
            temp_line.update({
                'name': line.name,
                'price': line.amount,
                'account_id': line.routing_subrouting_id.account_id.id,
            })
            # adding values post conversion takes an extra step
            converted_line = self.env['account.invoice'].line_get_convert(temp_line, partner_id, now)
            converted_line.update({'timekeeping_line': line.id})
            ts_move_lines.append((0, 0, converted_line))
            total_amount += line.amount

            # add another line for the premium addition, if any
            if line.premium_amount != 0.0:
                # some contracts don't allow overtime premiums to be charged to them, so deal with that here
                overtime_worktype_id = self.user_id.company_id.overtime_worktype_id.id
                contract_overtime_routing = line.routing_subrouting_id.account_analytic_id.overtime_account
                if contract_overtime_routing and (line.worktype.id == overtime_worktype_id):
                    final_account_id = contract_overtime_routing.id
                else:
                    final_account_id = line.account_id.id
                temp_line.update({
                    'name': line.name + ' - ' + line.worktype.name + ' premium',
                    'price': line.premium_amount,
                    'account_id': final_account_id,
                })
                converted_line = self.env['account.invoice'].line_get_convert(temp_line, partner_id, now)
                converted_line.update({'timekeeping_line': line.id})
                ts_move_lines.append((0, 0, converted_line))
                total_amount += line.premium_amount

        # Get the liability account for the balancing move line
        expense_account = self.user_id.company_id.wage_account_id.id

        if total_amount != 0.0:
            # add one move line to balance journal entry
            balance_line = {
                'type': 'dest',
                'name': name,
                'price': -total_amount,
                'account_id': expense_account,
                'date_maturity': date.today(),
                'ref': name,
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
        if lines:
            name = self.employee_id.name + ' - ' + self.name
            if not self.employee_id.user_id.company_id.general_journal_id:
                raise Warning(_('You must set a timesheet journal in the Settings->HR Settings before you can approve timesheets.'))

            move_vals = {
                'ref': name,
                'line_id': lines,
                'journal_id': self.employee_id.user_id.company_id.general_journal_id.id,
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
        # refresh the page
        return { 'type': 'ir.actions.client', 'tag': 'reload' }

    @api.model
    def create(self, vals):
        new_id = super(hr_timekeeping_sheet, self).create(vals)
        approval_vars = {'type': 'hr', 'state': 'draft', 'sheet_id': new_id[0].id,}
        self.env['hr.timekeeping.approval'].sudo().create(approval_vars)
        approval_vars.update({'type': 'manager'})
        self.env['hr.timekeeping.approval'].sudo().create(approval_vars)
        return new_id

    @api.multi
    def write(self, vals):
        # add PM approval lines for any timesheet lines for contracts/projects
        res = super(hr_timekeeping_sheet, self).write(vals)
        existing_approval_project_ids = set()
        for approval_line in self.approval_line_ids:
            if approval_line.account_analytic_id:
                existing_approval_project_ids.add(approval_line.account_analytic_id.id)
        existing_project_ids = set()
        for line in self.line_ids:
            analytic = line.routing_subrouting_id.account_analytic_id
            existing_project_ids.add(analytic.id)
            if analytic.type == 'contract' and analytic.id not in existing_approval_project_ids:
                approval_vars = {'type': 'project', 'state': 'draft', 'sheet_id': self.id, 'account_analytic_id': analytic.id}
                self.env['hr.timekeeping.approval'].sudo().create(approval_vars)
                existing_approval_project_ids.add(analytic.id)
        # remove approval lines if no timesheet lines exist for those projects
        for approval_line in self.approval_line_ids:
            if approval_line.account_analytic_id.type == 'contract' and approval_line.account_analytic_id.id not in existing_project_ids:
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
    name = fields.Char('Description')
    unit_amount = fields.Float('Quantity', help='Specifies the amount of quantity to count.')
    amount = fields.Float('Amount', required=True, default=0.0, digits_compute=dp.get_precision('Account'))
    premium_amount = fields.Float(string='Premium Amount', required=True, default=0.0, help='The additional amount based on work type, like overtime', digits_compute=dp.get_precision('Account'))
    date = fields.Date(string='Date', required=True, default=date.today().strftime(DATE_FORMAT))
    date_mirror = fields.Date(related='date', string='Date', readonly=True)
    previous_date = fields.Date(string='Previous Date', invisible=True)
    day_name = fields.Char(compute='_day_name', string='Day')
    routing_id = fields.Many2one('account.routing', 'Category', required=True,)
    routing_line_id = fields.Many2one('account.routing.line', 'Billing Type', required=True,)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code', required=True,)
    location = fields.Selection([('office','Office'),('home','Home')], string='Work Location', required=True, default='office', help="Location the hours were worked",)
    change_explanation = fields.Char(string='Change Explanation')
    state = fields.Char(compute='_check_state', default='open') # 'past','open','future'
    sheet_state = fields.Selection(related='sheet_id.state', readonly=True)
    logging_required = fields.Boolean(compute='_check_state')
    worktype = fields.Many2one('hr.timekeeping.worktype', string="Work Type", ondelete='restrict', required=True, )
    move_line_ids = fields.One2many('account.move.line', 'timekeeping_line', string='Journal Line Item', readonly=True, ondelete='restrict',)

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
            if not (prev_date < now < prev_deadline):
                self.logging_required = True

        # see if the selected date is within the open window
        check_date = datetime.strptime(self.date, '%Y-%m-%d')
        if check_date > now:
            self.state = 'future'
            self.logging_required = True
        else:
            deadline = check_date + timedelta(days=1, hours=11)
            if (check_date < now < deadline):
                self.state = 'open'
            else:
                self.state = 'past'
                self.logging_required = True

    @api.one
    @api.constrains('unit_amount', 'worktype')
    def _check_hours(self):
        if self.unit_amount > 24.0:
            raise Warning(_("You cannot have more than 24 hours entered a single day."))
        self.sheet_id._check_subtotals()

    @api.multi
    def _log_changes(self, vals, new_record=False):
        if not vals:
            return True
        # log any changes that are outside the valid time window
        body = "<strong>Change explanation:</strong> {}<br>".format(vals['change_explanation_log'])
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
    @api.depends('user_id')
    def _computed_fields(self):
        # You'd think you could just use a related field to self.sheet.uid_is_user_id, right?
        # Guess again! Related field to computed field loses the self._uid of the function call
        self.uid_is_user_id = (self.user_id.id == self._uid)

    @api.model
    def _safety_checks(self, sheet):
        if sheet.state != 'draft':
            raise Warning(_("You cannot make changes to this timesheet!"))
        if not sheet.uid_is_user_id:
            raise Warning(_("You cannot make changes to this timesheet!"))

    @api.multi
    def write(self, vals):
        # for some reason write gets called twice with this setup, the second time with context as first arg
        if vals.get('active_model') != None:
            return True
        self._safety_checks(self.sheet_id)
        vals['previous_date'] = vals.get('date') or self.date
        if self.logging_required:
            vals['change_explanation_log'] = vals.get('change_explanation')
            vals['change_explanation'] = ''
            self._log_changes(vals)
        unit_amount = vals.get('unit_amount') or self.unit_amount
        worktype_id = vals.get('worktype') or self.worktype.id
        worktype = self.env['hr.timekeeping.worktype'].browse(worktype_id)
        vals['amount'] = self.sheet_id.employee_id.wage_rate * unit_amount
        vals['premium_amount'] = vals['amount'] * worktype.premium_rate
        return super(hr_timekeeping_line, self).write(vals)

    @api.model
    def create(self, vals):
        vals['previous_date'] = vals['date']
        vals['change_explanation_log'] = vals['change_explanation']
        vals['change_explanation'] = ''
        unit_amount = vals.get('unit_amount', 0.0)
        worktype_id = vals.get('worktype')
        worktype = self.env['hr.timekeeping.worktype'].browse(worktype_id)
        sheet_id = vals.get('sheet_id')
        sheet = self.env['hr.timekeeping.sheet'].browse(sheet_id)
        self._safety_checks(sheet)
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

    @api.onchange('unit_amount')
    def onchange_unit_amount(self):
        if self.unit_amount > 24.0:
            raise Warning(_("You cannot have more than 24 hours entered a single day."))

    @api.onchange('date')
    def onchange_date(self):
        if not self.sheet_id:
            self.sheet_id = self.env['hr.timekeeping.sheet'].browse(self._context['active_id'])
        date = datetime.strptime(self.date, '%Y-%m-%d')
        from_date = datetime.strptime(self.sheet_id.date_from, '%Y-%m-%d')
        to_date = datetime.strptime(self.sheet_id.date_to, '%Y-%m-%d')
        if from_date > date:
            self.date = self.sheet_id.date_from
        if to_date < date:
            self.date = self.sheet_id.date_to
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
            'view_id': False,
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
        self.routing_line_id = routing_line
        self.routing_subrouting_id = ''

    @api.onchange('routing_subrouting_id')
    def onchange_account_type_id(self):
        # this onchange can probably be removed
        pass

    @api.multi
    def _get_default_date(self):
        today_str = fields.Date.to_string(date.today())
        today = fields.Date.from_string(today_str)
        date_to = fields.Date.from_string(self.sheet_id.date_to)
        if today > date_to:
            return self.sheet_id.date_to
        return today_str

    @api.multi
    def _get_default_worktype(self):
        return self.env.user.company_id.regular_worktype_id.id

    @api.multi
    def _get_user_default_route(self):
        return self.env.user.default_account_routing

    @api.multi
    def _get_user_default_subroute(self):
        return self.env.user.default_routing_subrouting

    _defaults = {
        'worktype': _get_default_worktype,
        'routing_id': _get_user_default_route,
        'routing_subrouting_id': _get_user_default_subroute,
    }


class hr_timekeeping_approval(models.Model):
    _name = 'hr.timekeeping.approval'
    _description = 'Timekeeping Approval Line'

    type = fields.Selection([('hr','HR'),('manager','Manager'),('project','PM'),], string="Approval Source", required=True, readonly=True)
    sheet_id = fields.Many2one('hr.timekeeping.sheet', string='Timekeeping Sheet', required=True)
    state = fields.Selection([('draft','Open'),('confirm','Waiting For Approval'),('done','Approved')],
                             'Status', select=True, required=True, readonly=True,)
    account_analytic_id = fields.Many2one('account.analytic.account', 'Contract/Project', readonly=True,)
    uid_can_approve = fields.Boolean(compute='_computed_fields', readonly=True)

    @api.one
    def _computed_fields(self):
        user = self.env.user
        # check if the user has global approval rights
        if user in self.sheet_id.employee_id.user_id.company_id.global_approval_user_ids:
            self.uid_can_approve = True
            return
        # check to see if user is HR Officer (should include HR Manager automatically)
        if self.type == 'hr':
            hr_category = self.env['ir.module.category'].search([('name','=','Human Resources')])
            hr_officer = self.env['res.groups'].search([('name','=','Officer'),('category_id','=',hr_category.id)])
            if hr_officer in user.groups_id:
                self.uid_can_approve = True
            else:
                self.uid_can_approve = False
            return
        # check to see if user is PM on this project
        elif self.type == 'project':
            if user in self.account_analytic_id.pm_ids:
                self.uid_can_approve = True
            else:
                self.uid_can_approve = False
            return
        # check to see if user is manager for the timesheet's owner
        elif self.type == 'manager':
            self.uid_can_approve = False
            manager = self.sheet_id.employee_id.parent_id
            while manager:
                if user == manager.resource_id.user_id:
                    self.uid_can_approve = True
                    break
                manager = manager.parent_id
            return
        else:
            self.uid_can_approve = False

    @api.multi
    def log_rejection(self, comment=''):
        now = get_now_tz(self.env.user, self.env['ir.config_parameter'])
        subject = "Submission rejected"
        body = "{} rejected timesheet for approval on {}".format(self.env.user.name, now.strftime('%c'))
        if comment:
            body += "<br><strong>Comment:</strong> {}".format(comment)
        self.sheet_id.message_post(subject=subject, body=body,)
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
            # 'res_id': self.id,
        }
        return view

    @api.multi
    def button_approve(self):
        # log approval line approval
        now = get_now_tz(self.env.user, self.env['ir.config_parameter'])
        subject = "Submission approved"
        body = "{} approved timesheet on {}".format(self.env.user.name, now.strftime('%c'))
        self.sheet_id.message_post(subject=subject, body=body,)
        self.signal_workflow('done')
        # if everything is approved, signal done for the whole sheet
        all_done = True
        for approval_line in self.sheet_id.approval_line_ids:
            if approval_line.state != 'done':
                all_done = False
        if all_done:
            # this has to sudo because it makes the accounting move lines
            return self.sheet_id.sudo().button_done()


# additional fields for employees
class employee(models.Model):
    _inherit = 'hr.employee'
    flsa_status = fields.Selection([('exempt','Exempt'),('non-exempt','Non-exempt')], string='FLSA Status', required=True)
    wage_rate = fields.Float('Hourly Wage Rate', required=True,)

    _defaults = {
        'flsa_status': 'exempt',
        'wage_rate': 0.0,
    }


# new model to deal with premium pay rates (overtime, danger, etc)
class hr_timesheet_worktype(models.Model):
    _name = 'hr.timekeeping.worktype'

    name = fields.Char('Name', required=True)
    active = fields.Boolean('Active')
    premium_rate = fields.Float('Additional Premium Rate', required=True,
                        help="The additional multiplier to be added on top of the base pay. For example, overtime would be 0.5, for a 50% premium.")
    nonexempt_limit = fields.Integer('Non-exempt Limit (Hours)',
                        help="Weekly limit of hours for this type for non-exempt employees. Enter 0 or leave blank for no limit.")
    nonexempt_limit_ignore_ids = fields.Many2many('account.analytic.account','premium_analytic_rel','limit_id','account_analytic_id','Ignore Analytic Accounts',
                        help="Enter any analytic accounts this limit should ignore when counting hours worked (like PTO).",
                        domain="[('state','!=','closed'),('use_timesheets','=',1)]")

    _defaults = {
        'active': True,
        'premium_rate': 0.0,
    }


# additional fields for res.users
class res_users(models.Model):
    _inherit = "res.users"

    analytic_review_ids = fields.Many2many('account.analytic.account', 'analytic_user_review_rel', 'user_id', 'analytic_id', string='Reviewed Analytic Accounts')
    auth_analytics = fields.Many2many('account.analytic.account', 'analytic_user_auth_rel', 'user_id', 'analytic_id', string='Authorized Analytics')
    pm_analytics = fields.Many2many('account.analytic.account', 'analytic_user_pm_rel', 'user_id', 'analytic_id', string='Projects Managed')
    default_account_routing = fields.Many2one('account.routing', 'Default Category')
    default_routing_subrouting = fields.Many2one('account.routing.subrouting', 'Default Task')


# I sometimes question the wisdom of using analytics to represent work tasks, but it does make managing
# the whole thing more straightforward. Either way, it takes a lot of customization of analytics.
class account_analytic_account(models.Model):
    _inherit = "account.analytic.account"

    pm_ids = fields.Many2many('res.users', 'analytic_user_pm_rel', 'analytic_id', 'user_id', string='Project Managers')
    overtime_account = fields.Many2one('account.account', string="Overtime Routing Account", domain="[('type','not in',['view','closed'])]")
    timesheets_future_filter = fields.Char(store=False, compute='_dummy_func', search='_filter_future_accounts')
    user_review_ids = fields.Many2many('res.users', 'analytic_user_review_rel', 'analytic_id', 'user_id', string='Users Reviewed')
    user_review_ids_count = fields.Integer(compute='_computed_fields', readonly=True)
    user_has_reviewed = fields.Boolean(compute='_user_has_reviewed', search='_search_user_has_reviewed', string="Reviewed", readonly=True, store=False)
    is_labor_code = fields.Boolean(string="Is a labor code", default=False)
    dcaa_allowable = fields.Boolean(string="DCAA Allowable", default=True)
    limit_to_auth = fields.Boolean(string="Limit Contract/Project to set of users:", default=False,)
    auth_users = fields.Many2many('res.users', 'analytic_user_auth_rel', 'analytic_id', 'user_id', string='Users Authorized')

    @api.one
    def _computed_fields(self):
        self.user_review_ids_count = len(self.user_review_ids)

    @api.one
    def _dummy_func(self):
        return ''

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


class account_move_line(models.Model):
    _inherit = "account.move.line"

    timekeeping_line = fields.Many2one('hr.timekeeping.line', 'Timekeeping Line', ondelete='restrict')


class account_routing_subrouting(models.Model):
    _inherit = "account.routing.subrouting"

    # these are part of the analytic but need to be exposed for the subroute
    timesheets_future_filter = fields.Char(related='account_analytic_id.timesheets_future_filter', readonly=True)
    user_has_reviewed = fields.Boolean(related='account_analytic_id.user_has_reviewed', readonly=True)
    dcaa_allowable = fields.Boolean(related='account_analytic_id.dcaa_allowable', readonly=True)
