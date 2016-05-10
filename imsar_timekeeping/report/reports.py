from datetime import datetime, date, timedelta

from openerp import tools, models, fields, api, _
import openerp.addons.decimal_precision as dp
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as DATE_FORMAT
import pytz
import logging
logger = logging.getLogger(__name__)


class timekeeping_lines_report(models.Model):
    _name = "hr.timekeeping.lines.report"
    _description = "Timekeeping Entries Statistics"
    _auto = False

    week_name = fields.Char('Week Number')
    # type = fields.Selection([('regular','Regular'),('addendum','Addendum'),('proxy','Proxy'),], 'Type', default='regular', required=True, readonly=True,)
    payperiod_id = fields.Many2one('hr.timekeeping.payperiod', 'Pay Period')
    date = fields.Date('Date', readonly=True)
    user_id = fields.Many2one('res.users', string='User', readonly=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    manager_id = fields.Many2one('hr.employee', string='Manager', readonly=True)
    unit_amount = fields.Float('Quantity', readonly=True)
    amount = fields.Float('Amount', readonly=True, default=0.0, digits_compute=dp.get_precision('Account'), groups="imsar_accounting.group_finance_reports,account.group_account_user")
    worktype = fields.Many2one('hr.timekeeping.worktype', string="Work Type", readonly=True)
    state = fields.Char('Timesheet State', readonly=True)
    task_category = fields.Char('Task Category', readonly=True)
    task_code = fields.Char('Task Code', readonly=True)
    adv_search = fields.Char('Advanced Filter Search', compute='_computed_fields', search='_adv_search')

    @api.one
    def _computed_fields(self):
        self.adv_search = ''

    def _adv_search(self, operator, value):
        today = date.today()
        this_payperiod = self.env['hr.timekeeping.payperiod'].get_payperiod(today)
        prev_payperiod_date = datetime.strptime(this_payperiod.start_date, DATE_FORMAT) + timedelta(days=-1)
        prev_payperiod = self.env['hr.timekeeping.payperiod'].get_payperiod(prev_payperiod_date)

        ids = []
        if value == 'this_week':
            week_ab = this_payperiod.get_week_ab(today)
            this_week = this_payperiod.name + '-' + week_ab
            ids = self.search([('week_name','=',this_week)]).ids
        elif value == 'last_week':
            prev_week_date = today - timedelta(days=7)
            prev_week_pp = self.env['hr.timekeeping.payperiod'].get_payperiod(prev_week_date)
            prev_week_ab = prev_week_pp.get_week_ab(prev_week_date)
            prev_week = prev_week_pp.name + '-' + prev_week_ab
            ids = self.search([('week_name','=',prev_week)]).ids
        elif value == 'this_payperiod':
            ids = self.search([('payperiod_id','=',this_payperiod.id)]).ids
        elif value == 'prev_payperiod':
            ids = self.search([('payperiod_id','=',prev_payperiod.id)]).ids
        elif value == 'this_year':
            year = datetime.now().year
            ids = self.search([('date','>=',date(year, 01, 01)), ('date','<=',date(year, 12, 31))]).ids
        elif value == 'prev_year':
            year = datetime.now().year - 1
            ids = self.search([('date','>=',date(year, 01, 01)), ('date','<=',date(year, 12, 31))]).ids
        else:
            ids = self.search([]).ids
        return [('id','in',ids)]

    @api.cr
    def init(self, cr):
        tools.drop_view_if_exists(cr, 'hr_timekeeping_lines_report')
        # left join timekeeping_line_move_line_rel to see which have move lines?
        # join move lines and check for reconciled/unreconciled?
        cr.execute("""
            create or replace view hr_timekeeping_lines_report as (
                select
                    min(tl.id) as id,
                    tl.date as date,
                    tl.user_id as user_id,
                    ts.employee_id as employee_id,
                    hre.parent_id as manager_id,
                    sum(tl.unit_amount) as unit_amount,
                    sum(tl.amount + tl.premium_amount) as amount,
                    tl.worktype as worktype,
                    ts.state as state,
                    ts.name as week_name,
                    ts.payperiod_id as payperiod_id,
                    ar.name as task_category,
                    (ar.name || ' - ' || aa.name) as task_code
                from
                    hr_timekeeping_line tl
                join hr_timekeeping_sheet ts on tl.sheet_id = ts.id
                join account_routing ar on tl.routing_id = ar.id
                join account_routing_subrouting ars on tl.routing_subrouting_id = ars.id
                join account_analytic_account aa on ars.account_analytic_id = aa.id
                join hr_employee hre on hre.id = ts.employee_id
                group by
                    tl.date, tl.user_id, employee_id, hre.parent_id, tl.worktype, ts.state, ts.payperiod_id, week_name, task_category, task_code
            )
        """)


class timekeeping_log_report(models.Model):
    _name = "hr.timekeeping.log.report"
    _description = "Timekeeping Log Report"
    _auto = False

    rec_count = fields.Integer('Hits', readonly=True)
    author = fields.Char('Author', readonly=True)
    subject = fields.Char('Subject', readonly=True)
    body = fields.Char('Message', readonly=True)
    date = fields.Datetime('Date', readonly=True)
    sheet_id = fields.Many2one('hr.timekeeping.sheet', string='Sheet', readonly=True,)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    manager_id = fields.Many2one('hr.employee', related='employee_id.parent_id', string='Manager', readonly=True)
    sheet_type = fields.Char('Sheet Type', readonly=True)
    state = fields.Char('Sheet State', readonly=True)
    week_name = fields.Char('Week Name', readonly=True)
    payperiod_id = fields.Many2one('hr.timekeeping.payperiod', 'Pay Period', readonly=True)
    adv_sub_search = fields.Char('Advanced Submit Search', compute='_computed_fields', search='_adv_sub_search')
    adv_change_search = fields.Char('Advanced Change Search', compute='_computed_fields', search='_adv_change_search')

    def _get_first_submission_ids(self):
        sql = """select id from
                  (select m.*, row_number() over (partition by sheet_id order by date asc) as rn
                    from hr_timekeeping_log_report m
                    where subject ='Submitted for approval'
                  ) m2
                  where m2.rn=1;
            """
        self.env.cr.execute(sql)
        return [row[0] for row in self.env.cr.fetchall()]

    def _get_last_submission_ids(self):
        sql = """select id from
                  (select m.*, row_number() over (partition by sheet_id order by date desc) as rn
                    from hr_timekeeping_log_report m
                    where subject ='Submitted for approval'
                  ) m2
                  where m2.rn=1;
            """
        self.env.cr.execute(sql)
        return [row[0] for row in self.env.cr.fetchall()]

    def _get_next_valid_deadline(self, deadline):
        holidays_str = [rec.holiday_date for rec in self.env['hr.timekeeping.holiday'].search([])]
        holidays = [datetime.strptime(date_str, '%Y-%m-%d').date() for date_str in holidays_str]
        while deadline.weekday() in (5,6) or deadline.date() in holidays:
            deadline += timedelta(days=1)
        deadline = pytz.timezone('America/Denver').localize(deadline).astimezone(pytz.utc).replace(tzinfo=None)
        return deadline

    def _get_logged_changes(self):
        return self.search(['|',('subject','ilike','New record'),('subject','ilike','Changes made to')])

    @api.one
    def _computed_fields(self):
        self.adv_sub_search = ''
        self.adv_change_search = ''
        if 'Change reason:' in self.body:
            self.change_reason = 'some reason'
        else:
            self.change_reason = ''

    def _adv_sub_search(self, operator, value):
        ids = list()
        first_subs = self.browse(self._get_first_submission_ids())
        last_subs = self.browse(self._get_last_submission_ids())
        # first submissions
        if value == 'first_sub_early':
            for log in first_subs:
                deadline = datetime.strptime(log.sheet_id.date_to, '%Y-%m-%d') + timedelta(days=1, hours=8)
                deadline = self._get_next_valid_deadline(deadline)
                log_date = datetime.strptime(log.date, '%Y-%m-%d %H:%M:%S')
                if log_date < deadline:
                    ids.append(log.id)
        elif value == 'first_sub_ontime':
            for log in first_subs:
                deadline = datetime.strptime(log.sheet_id.date_to, '%Y-%m-%d') + timedelta(days=1, hours=11)
                deadline = self._get_next_valid_deadline(deadline)
                log_date = datetime.strptime(log.date, '%Y-%m-%d %H:%M:%S')
                if log_date <= deadline:
                    ids.append(log.id)
        elif value == 'first_sub_late':
            for log in first_subs:
                deadline = datetime.strptime(log.sheet_id.date_to, '%Y-%m-%d') + timedelta(days=1, hours=11)
                deadline = self._get_next_valid_deadline(deadline)
                log_date = datetime.strptime(log.date, '%Y-%m-%d %H:%M:%S')
                if log_date > deadline:
                    ids.append(log.id)
        # last submissions
        elif value == 'last_sub_early':
            for log in last_subs:
                deadline = datetime.strptime(log.sheet_id.date_to, '%Y-%m-%d') + timedelta(days=1, hours=8)
                deadline = self._get_next_valid_deadline(deadline)
                log_date = datetime.strptime(log.date, '%Y-%m-%d %H:%M:%S')
                if log_date < deadline:
                    ids.append(log.id)
        elif value == 'last_sub_ontime':
            for log in last_subs:
                deadline = datetime.strptime(log.sheet_id.date_to, '%Y-%m-%d') + timedelta(days=1, hours=11)
                deadline = self._get_next_valid_deadline(deadline)
                log_date = datetime.strptime(log.date, '%Y-%m-%d %H:%M:%S')
                if log_date <= deadline:
                    ids.append(log.id)
        elif value == 'last_sub_late':
            for log in last_subs:
                deadline = datetime.strptime(log.sheet_id.date_to, '%Y-%m-%d') + timedelta(days=1, hours=11)
                deadline = self._get_next_valid_deadline(deadline)
                log_date = datetime.strptime(log.date, '%Y-%m-%d %H:%M:%S')
                if log_date > deadline:
                    ids.append(log.id)
        else:
            ids = self.search([]).ids
        return [('id','in',ids)]

    def _adv_change_search(self, operator, value):
        ids = list()
        all_changes = self._get_logged_changes()
        if value == 'all_changes':
            ids = all_changes.ids
        elif value == 'correction':
            for log in all_changes:
                if 'Change reason:</strong> Correction' in log.body:
                    ids.append(log.id)
        elif value == 'working':
            for log in all_changes:
                if 'Change reason:</strong> Working' in log.body:
                    ids.append(log.id)
        elif value == 'travel':
            for log in all_changes:
                if 'Change reason:</strong> Travel' in log.body:
                    ids.append(log.id)
        elif value == 'forgot':
            for log in all_changes:
                if 'Change reason:</strong> Forgot' in log.body:
                    ids.append(log.id)
        elif value == 'other':
            for log in all_changes:
                if 'Change reason:</strong> Other' in log.body:
                    ids.append(log.id)
        elif value == 'comments':
            ids = self.search([('subject','ilike','Timesheet Comment')]).ids
        else:
            ids = self.search([]).ids
        return [('id','in',ids)]

    @api.cr
    def init(self, cr):
        tools.drop_view_if_exists(cr, 'hr_timekeeping_log_report')
        cr.execute("""
            create or replace view hr_timekeeping_log_report as (
                select
                    min(mm.id) as id,
                    count(distinct mm.id) as rec_count,
                    mm.author_id as author,
                    mm.subject as subject,
                    mm.body as body,
                    mm.date as date,
                    ts.id as sheet_id,
                    ts.employee_id as employee_id,
                    ts.type as sheet_type,
                    ts.state as state,
                    ts.name as week_name,
                    ts.payperiod_id as payperiod_id
                from
                    mail_message mm
                join hr_timekeeping_sheet ts on mm.res_id = ts.id and mm.model = 'hr.timekeeping.sheet'
                where
                    ts.type = 'regular'
                group by
                    sheet_id, author, subject, body, date, employee_id, sheet_type, state, week_name, payperiod_id
            )
        """)


class timekeeping_search_sheets_by_task(models.TransientModel):
    _name = "hr.timekeeping.by_task.wizard"
    _description = "Timesheets by Task"

    week = fields.Char('Week', default=lambda self: self._get_last_week())
    analytic = fields.Many2one('account.analytic.account', string="Contract/Project",
                       domain="[('project_header','=',True),('state','not in',['close','cancelled'])]")

    @api.model
    def _get_last_week(self):
        last_week = date.today() - timedelta(days=7)
        this_payperiod = self.env['hr.timekeeping.payperiod'].get_payperiod(last_week)
        week_ab = this_payperiod.get_week_ab(last_week)
        week = "{}-{}".format(this_payperiod.name, week_ab)
        return week

    @api.multi
    def open_report(self):
        ids = set()
        timesheets = self.env['hr.timekeeping.sheet'].search([('name','=',self.week)])
        child_accounts = self.analytic.get_all_children()
        for sheet in timesheets:
            if self.analytic:
                for line in sheet.line_ids:
                    if line.account_analytic_id.id in child_accounts.ids:
                        ids.add(sheet.id)
            else:
                ids.add(sheet.id)
        return {
            'name': _('Timesheets by Task'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.timekeeping.sheet',
            'view_id': False,
            'view_type': 'form',
            'view_mode': 'tree,form',
            'domain': [('id','in',list(ids))],
        }

    @api.multi
    def paid_report(self):
        pp_year, pp_num, week_ab = self.week.split('-')
        payperiod = self.env['hr.timekeeping.payperiod'].search([('year','=',pp_year),('period_num','=',pp_num)])[0]
        if week_ab.upper() == 'A':
            start_date = datetime.strptime(payperiod.start_date, DATE_FORMAT)
            end_date = datetime.strptime(payperiod.start_date, DATE_FORMAT) + timedelta(days=6, hours=23, minutes=59)
        elif week_ab.upper() == 'B':
            start_date = datetime.strptime(payperiod.start_date, DATE_FORMAT) + timedelta(days=7)
            end_date = datetime.strptime(payperiod.start_date, DATE_FORMAT) + timedelta(days=13, hours=23, minutes=59)
        else:
            raise Warning('Week name did not include -A or -B')
        timesheets = self.env['hr.timekeeping.sheet'].search([('payroll_state','=','paid'),('payment_date','>=',start_date),('payment_date','<=',end_date)])
        return {
            'name': _('Timesheets by Task'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.timekeeping.sheet',
            'view_id': False,
            'view_type': 'form',
            'view_mode': 'tree,form',
            'domain': [('id','in',timesheets.ids)],
        }

