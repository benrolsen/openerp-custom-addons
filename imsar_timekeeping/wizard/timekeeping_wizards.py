from datetime import datetime, date, timedelta

from openerp import models, fields, api, _
from openerp.exceptions import Warning


class imsar_hr_timesheet_current_open(models.TransientModel):
    _name = 'hr.timekeeping.current.open'
    _description = 'hr.timekeeping.current.open'

    @api.model
    def open_timesheet(self):
        today = date.today()
        thisyear = today.isocalendar()[0]
        week_number = today.isocalendar()[1]

        employee = self.env['hr.employee'].search([('user_id','=',self._uid)])
        if not employee:
            raise Warning(_('Error!'), _("Please create an employee and associate it with this user."))
        if len(employee.ids) > 1:
            raise Warning(_('Error!'), _("This user has multiple employees and I haven't dealt with that yet."))
        sheet_ids = self.env['hr.timekeeping.sheet'].search([
            ('employee_id','=',employee.id),
            ('year','=',thisyear),
            ('week_number','=',week_number),
            ('type','=','regular'),
            ])

        if len(sheet_ids) < 1:
            values = dict()
            values['year'] = today.year
            values['week_number'] = week_number
            values['type'] = 'regular'
            values['state'] = 'draft'
            values['employee_id'] = employee.id
            values['user_id'] = self._uid
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


class imsar_hr_timesheet_addendum_open(models.TransientModel):
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
    _name = 'hr.timekeeping.addendum.open'
    _description = 'hr.timekeeping.addendum.open'

    @api.model
    def open_addendum(self):
        regular_timesheet_id = self._context.get('regular_timesheet_id')
        if not regular_timesheet_id:
            raise Warning(_('Error!'), _("You must create a regular timesheet before you can create an addendum."))
        regular_timesheet = self.env['hr.timekeeping.sheet'].browse(regular_timesheet_id)
        if regular_timesheet.state != 'done':
            raise Warning(_('Error!'), _("You cannot create an addendum on an unapproved timesheet."))

        employee = self.env['hr.employee'].search([('user_id','=',self._uid)])
        if not employee:
            raise Warning(_('Error!'), _("Please create an employee and associate it with this user."))
        if len(employee.ids) > 1:
            raise Warning(_('Error!'), _("This user has multiple employees and I haven't dealt with that yet."))

        sheet_ids = self.env['hr.timekeeping.sheet'].search([
            ('employee_id','=',employee.id),
            ('year','=',regular_timesheet.year),
            ('week_number','=',regular_timesheet.week_number),
            ('type','=','addendum'),
            ('state','!=','done'),
            ])
        if len(sheet_ids) < 1:
            values = dict()
            values['year'] = regular_timesheet.year
            values['week_number'] = regular_timesheet.week_number
            values['type'] = 'addendum'
            values['state'] = 'draft'
            values['employee_id'] = employee.id
            values['user_id'] = self._uid
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


class filter_timesheets_need_my_approval(models.TransientModel):
    _name = 'hr.timekeeping.my_approval_filter'
    _description = 'hr.timekeeping.my_approval_filter'

    @api.model
    def my_approval_filter(self):
        sheet_ids = set()
        for sheet in self.env['hr.timekeeping.sheet'].search([]):
            if sheet.state != 'confirm':
                continue
            for approval_line in sheet.approval_line_ids:
                if approval_line.state == 'confirm' and approval_line.uid_can_approve:
                    sheet_ids.add(sheet.id)

        view = {
            'name': _('Waiting for my approval'),
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'hr.timekeeping.sheet',
            'view_id': False,
            'type': 'ir.actions.act_window',
            # 'target': 'inline',
            'domain': [('id','in',list(sheet_ids))],
        }
        return view


class hr_timesheet_preferences(models.TransientModel):
    _name = "hr.timekeeping.preferences"
    _description = "hr.timekeeping.preferences"

    user_id = fields.Many2one('res.users', 'User', )
    routing_id = fields.Many2one('account.routing', 'Category',)
    routing_line_id = fields.Many2one('account.routing.line', 'Billing Type',)
    routing_subrouting_id = fields.Many2one('account.routing.subrouting', 'Task Code',)

    @api.onchange('routing_id')
    def onchange_routing_id(self):
        routing_line = self.env['hr.timekeeping.line']._get_timekeeping_routing_line(self.routing_id.id)
        self.routing_line_id = routing_line
        if self.routing_subrouting_id not in routing_line.subrouting_ids:
            self.routing_subrouting_id = ''

    @api.multi
    def save(self):
        user = self.env.user
        user.default_account_routing = self.routing_id
        user.default_routing_subrouting = self.routing_subrouting_id
        return True

    @api.multi
    def _get_user_default_route(self):
        return self.env.user.default_account_routing

    @api.multi
    def _get_user_default_subroute(self):
        return self.env.user.default_routing_subrouting

    _defaults = {
        'routing_id': _get_user_default_route,
        'routing_subrouting_id': _get_user_default_subroute,
    }


class hr_timesheet_comment(models.TransientModel):
    _name = 'hr.timekeeping.comment'
    _description = 'hr.timekeeping.comment'

    # sheet_id = fields.Many2one('hr.timekeeping.sheet', string='Timekeeping Sheet', required=True)
    comment = fields.Char('Comment', required=True)

    @api.model
    def open_comment(self):
        view = {
            'name': _('Open Comment'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr.timekeeping.comment',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
            'nodestroy': True,
            # 'res_id': sheet_ids[0].id,
        }
        return view

    @api.multi
    def submit_explanation(self):
        model = self._context['active_model']
        id = self._context['active_id']
        approval = self.env[model].browse(id)
        approval.log_rejection(comment=self.comment)
        return { 'type': 'ir.actions.client', 'tag': 'reload' }

