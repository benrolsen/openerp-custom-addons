from datetime import datetime, date, timedelta

from openerp import tools, models, fields, api, _
import openerp.addons.decimal_precision as dp
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as DATE_FORMAT


class payroll_report_wizard(models.TransientModel):
    _name = "hr.timekeeping.payroll.report.wizard"
    _description = "Timekeeping Entries Statistics"

    year = fields.Integer('Year', default=lambda self: datetime.now().year)
    payperiod_id = fields.Many2one('hr.timekeeping.payperiod', 'Pay Period', required=True, default=lambda self: self.default_payperiod())

    @api.model
    def default_payperiod(self):
        today = datetime.today()
        this_payperiod = self.env['hr.timekeeping.payperiod'].get_payperiod(today)
        prev_day = datetime.strptime(this_payperiod.start_date, DATE_FORMAT) + timedelta(days=-1)
        last_payperiod = self.env['hr.timekeeping.payperiod'].get_payperiod(prev_day)
        return last_payperiod or ''

    @api.multi
    def open_report(self):
        ctx = {}
        if self._context:
            ctx = self._context.copy()
        return {
            'name': _('Payroll Report'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.timekeeping.payroll.report',
            'view_type': 'form',
            'view_mode': 'graph,tree',
            'domain': "[('date', '>=', '{}'),('date','<=','{}')]".format(self.payperiod_id.start_date, self.payperiod_id.end_date),
            'context': ctx,
        }


class timekeeping_payroll_report(models.Model):
    _name = "hr.timekeeping.payroll.report"
    _description = "Timekeeping Entries Statistics"
    _auto = False

    date = fields.Date('Date', readonly=True)
    user_id = fields.Many2one('res.users', string='User', readonly=True)
    unit_amount = fields.Float('Quantity', readonly=True)
    amount = fields.Float('Amount', readonly=True, default=0.0, digits_compute=dp.get_precision('Account'))
    worktype = fields.Many2one('hr.timekeeping.worktype', string="Work Type", readonly=True)
    state = fields.Char('Timesheet State', readonly=True)
    task_code = fields.Char('Task Code', readonly=True)

    @api.cr
    def init(self, cr):
        tools.drop_view_if_exists(cr, 'hr_timekeeping_payroll_report')
        # left join timekeeping_line_move_line_rel to see which have move lines?
        # join move lines and check for reconciled/unreconciled?
        cr.execute("""
            create or replace view hr_timekeeping_payroll_report as (
                select
                    min(tl.id) as id,
                    tl.date as date,
                    tl.user_id as user_id,
                    sum(tl.unit_amount) as unit_amount,
                    sum(tl.amount + tl.premium_amount) as amount,
                    tl.worktype as worktype,
                    ts.state as state,
                    (ar.name || ' - ' || aa.name) as task_code
                from
                    hr_timekeeping_line tl
                join hr_timekeeping_sheet ts on tl.sheet_id = ts.id
                join account_routing ar on tl.routing_id = ar.id
                join account_routing_subrouting ars on tl.routing_subrouting_id = ars.id
                join account_analytic_account aa on ars.account_analytic_id = aa.id
                group by
                    tl.date, tl.user_id, tl.worktype, ts.state, task_code
            )
        """)


class timekeeping_inventory_wizard(models.TransientModel):
    _name = "hr.timekeeping.inventory.wizard"
    _description = "Timekeeping Inventory List"

    date_from = fields.Date('Start Date', required=True, default=lambda self: self.default_date_from())
    date_to = fields.Date('End Date', required=True, default=lambda self: self.default_date_to())

    @api.model
    def default_date_from(self):
        return datetime.today() - timedelta(days=7)

    @api.model
    def default_date_to(self):
        return datetime.today()

    @api.multi
    def open_report(self):
        report_view = self.env.ref('imsar_timekeeping.timesheet_inventory_report_tree', False)
        return {
            'name': _('Inventory Report'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.timekeeping.line',
            'view_id': report_view.id,
            'view_type': 'form',
            'view_mode': 'tree',
            'domain': "[('date', '>=', '{}'),('date','<=','{}'),('serial_reference','!=','')]".format(self.date_from, self.date_to),
        }


class timekeeping_search_sheets_by_task(models.TransientModel):
    _name = "hr.timekeeping.by_task.wizard"
    _description = "Timesheets by Task"

    week = fields.Char('Week', default=lambda self: self._get_last_week())
    analytic = fields.Many2one('account.analytic.account', string="Contract/Project", domain="[('project_header','=',True)]")

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

