from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta, SU

from openerp import models, fields, api, _
from openerp.exceptions import Warning
from openerp.tools import DEFAULT_SERVER_DATE_FORMAT as DATE_FORMAT


class hr_timekeeping_wizards(models.TransientModel):
    _name = 'hr.timekeeping.wizards'
    _description = 'Wizards for timekeeping'

    @api.model
    def open_timesheet(self, context=None): # leave the unused kwarg in there, just... trust me
        today = self._context.get('date_override') or date.today()

        # get the pay period for the given date
        this_payperiod = self.env['hr.timekeeping.payperiod'].get_payperiod(today)
        week_ab = this_payperiod.get_week_ab(today)
        sunday = today + relativedelta(weekday=SU(-1))
        saturday = sunday + timedelta(days=6)

        employee = self.env['hr.employee'].search([('user_id','=',self._uid)])
        if not employee:
            raise Warning(_('Error!'), _("Please create an employee and associate it with this user."))
        if len(employee.ids) > 1:
            raise Warning(_('Error!'), _("This user has multiple employees and I haven't dealt with that yet."))
        sheet_ids = self.env['hr.timekeeping.sheet'].search([
            ('employee_id','=',employee.id),
            ('payperiod_id','=',this_payperiod.id),
            ('week_ab','=',week_ab),
            ('type','=','regular'),
            ])

        if len(sheet_ids) < 1:
            values = dict()
            values['payperiod_id'] = this_payperiod.id
            values['week_ab'] = week_ab
            values['date_from'] = sunday
            values['date_to'] = saturday
            values['type'] = 'regular'
            values['state'] = 'draft'
            values['employee_id'] = employee.id
            sheet_ids = self.env['hr.timekeeping.sheet'].sudo().create(values)

        view = {
            'name': _('Open Timesheet'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.timekeeping.sheet',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'inline',
            'res_id': sheet_ids[0].id,
        }
        return view

    @api.model
    def open_addendum(self):
        """
        Funny story about this piece of code. I originally copied this from the above class
        (imsar_hr_timesheet_current_open) and the related ir.actions.server resource
        (action_hr_timekeeping_current_open). But I didn't want to tie this to a menuitem, I
        wanted it to be button on an original timesheet. Turns out that you can't link a button of
        type 'action' to ir.actions.server resources, only ir.actions.act_window resources.
        After banging my head against it for a few hours, I came up with the solution of having
        a button of type 'object' link to the button_addendum function on the timesheet, which grabs
        the ir.actions.server object and action_hr_timekeeping_addendum_open resource ID, and
        runs the action manually with the run() command. It's pretty tricky and I haven't seen
        any other examples of something like that in the Odoo code.
        Only when I finished and had it working did it occur to me that I could have simply
        put all this code in open_addendum() into the button_addendum() function and skipped
        the code gymnastics.
        I'm leaving it this way because both of these are so similar and I'd rather have them
        together if we need to change the way timesheets are created, rather than taking care
        of one way here and hunting down the other one inside the hr.timekeeping.sheet model.
        """
        regular_timesheet_id = self._context.get('regular_timesheet_id')
        if not regular_timesheet_id:
            raise Warning(_('Error!'), _("You must create a regular timesheet before you can create an addendum."))
        regular_timesheet = self.env['hr.timekeeping.sheet'].browse(regular_timesheet_id)
        if regular_timesheet.state != 'done':
            raise Warning(_('Error!'), _("You cannot create an addendum on an unapproved timesheet."))

        sheet_ids = self.env['hr.timekeeping.sheet'].search([
            ('employee_id', '=', regular_timesheet.employee_id.id),
            ('payperiod_id', '=', regular_timesheet.payperiod_id.id),
            ('week_ab', '=', regular_timesheet.week_ab),
            ('type', '=', 'addendum'),
            ('state', '!=', 'done'),
            ])
        if len(sheet_ids) < 1:
            values = dict()
            values['payperiod_id'] = regular_timesheet.payperiod_id.id
            values['week_ab'] = regular_timesheet.week_ab
            values['date_from'] = regular_timesheet.date_from
            values['date_to'] = regular_timesheet.date_to
            values['type'] = 'addendum'
            values['state'] = 'draft'
            values['employee_id'] = regular_timesheet.employee_id.id
            sheet_ids = self.env['hr.timekeeping.sheet'].sudo().create(values)

        view = {
            'name': _('Open Addendum'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.timekeeping.sheet',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'inline',
            'res_id': sheet_ids[0].id,
        }
        return view

    @api.model
    def open_preferences(self):
        prefs = self.env['hr.timekeeping.preferences'].search([('user_id','=',self._uid),])
        if len(prefs) < 1:
            values = dict()
            values['user_id'] = self._uid
            prefs = self.env['hr.timekeeping.preferences'].sudo().create(values)

        view = {
            'name': _('Open Preferences'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.timekeeping.preferences',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'res_id': prefs[0].id,
        }
        return view


class hr_timesheet_proxy_wizard(models.TransientModel):
    _name = 'hr.timekeeping.proxy'
    _description = 'hr.timekeeping.proxy'

    week_date = fields.Date('Week For ', required=True)
    employee = fields.Many2one('hr.employee', string="Employee", required=True)

    @api.multi
    def submit(self):
        # get the pay period for the given date
        week_date = datetime.strptime(self.week_date, DATE_FORMAT)
        payperiod = self.env['hr.timekeeping.payperiod'].get_payperiod(week_date)
        week_ab = payperiod.get_week_ab(week_date)
        sunday = week_date + relativedelta(weekday=SU(-1))
        saturday = sunday + timedelta(days=6)

        sheet_ids = self.env['hr.timekeeping.sheet'].search([
            ('employee_id','=',self.employee.id),
            ('payperiod_id','=',payperiod.id),
            ('week_ab','=',week_ab),
            ('type','=','proxy'),
            ('state', '!=', 'done'),
            ])
        if len(sheet_ids) < 1:
            values = dict()
            values['payperiod_id'] = payperiod.id
            values['week_ab'] = week_ab
            values['date_from'] = sunday
            values['date_to'] = saturday
            values['type'] = 'proxy'
            values['state'] = 'draft'
            values['employee_id'] = self.employee.id
            sheet_ids = self.env['hr.timekeeping.sheet'].sudo().create(values)

        view = {
            'name': _('Open Proxy'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.timekeeping.sheet',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'res_id': sheet_ids[0].id,
        }
        return view


class hr_timesheet_comment(models.TransientModel):
    _name = 'hr.timekeeping.comment'
    _description = 'hr.timekeeping.comment'

    comment = fields.Char('Comment', required=True)

    @api.multi
    def submit_explanation(self):
        model = self._context['active_model']
        id = self._context['active_id']
        approval = self.env[model].browse(id)
        approval.log_rejection(comment=self.comment)
        return { 'type': 'ir.actions.client', 'tag': 'reload' }


class hr_timekeeping_sheet_payroll_confirm(models.TransientModel):
    _name = "hr.timekeeping.sheet.payroll.confirm"
    _description = "Confirm payroll submission"

    @api.multi
    def submit_confirm(self):
        ids = self._context['active_ids']
        sheets = self.env['hr.timekeeping.sheet'].browse(ids)
        # just using a pseudo-workflow for payroll_state
        for sheet in sheets:
            if sheet.state == 'done' and sheet.payroll_state == 'draft' and sheet.type == 'regular':
                sheet.payroll_state = 'pending'
        return {'type': 'ir.actions.act_window_close'}

