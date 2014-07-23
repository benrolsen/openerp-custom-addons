from datetime import datetime, date, timedelta
import pytz

from openerp import models, api, _

from openerp import fields as new_fields
from openerp.osv import fields, osv
from openerp.exceptions import Warning


class imsar_hr_timesheet_current_open(osv.osv_memory):
    _inherit = 'hr.timesheet.current.open'

    def open_timesheet(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        today = date.today()
        ts_name = 'Week %d' % today.isocalendar()[1]
        ts = self.pool.get('hr_timesheet_sheet.sheet')

        user_ids = self.pool.get('hr.employee').search(cr, uid, [('user_id','=',uid)], context=context)
        if not len(user_ids):
            raise osv.except_osv(_('Error!'), _('Please create an employee and associate it with this user.'))
        ids = ts.search(cr, uid, [('user_id','=',uid),('name','=',ts_name)], context=context)

        if len(ids) < 1:
            values = dict()
            values['name'] = ts_name
            values['date_from'] = today - timedelta(days=today.isoweekday()-1)
            values['date_to'] = values['date_from'] + timedelta(days=6)
            values['state'] = 'draft'
            ids = [self.pool.get('hr_timesheet_sheet.sheet').create(cr, uid, values, context)]

        view = {
            'domain': "[('user_id', '=', uid)]",
            'name': _('Open Timesheet'),
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'hr_timesheet_sheet.sheet',
            'view_id': False,
            'type': 'ir.actions.act_window',
            'res_id': ids[0],
        }
        return view


class hr_timesheet_sheet(models.Model):
    _inherit = 'hr_timesheet_sheet.sheet'

    move_id = new_fields.Many2one('account.move', string='Journal Entry',
        readonly=True, index=True, ondelete='restrict', copy=False,
        help="Link to the automatically generated Journal Items.")

    @api.one
    def name_get(self):
        return (self.id, self.name)

    @api.multi
    def _make_move_lines(self):
        ts_move_lines = list()
        name = self.employee_id.name + ' - ' + self.name

        # prepare move lines per timesheet entry
        total_amount = 0.0
        for line in self.timesheet_ids:
            # if this line already has a move line associated, skip it
            if(line.line_id.move_id):
                continue
            ts_move_lines.append({
                'type': 'dest',
                'name': line.name,
                'price': line.amount,
                'account_id': line.general_account_id.id,
                'date_maturity': self.date_to,
                'quantity': line.unit_amount,
                'product_id': line.product_id.id,
                'product_uom_id': line.product_uom_id.id,
                'analytic_lines': [(4, line.line_id.id),],
                'ref': name,
            })
            total_amount += line.amount

        # Get the expense account for the balancing move line
        prod = self.employee_id.product_id
        if prod.property_account_expense:
            ts_account_id = prod.property_account_expense.id
        elif prod.product_tmpl_id.property_account_expense:
            ts_account_id = prod.product_tmpl_id.property_account_expense.id
        elif prod.product_tmpl_id.categ_id.property_account_expense_categ:
            ts_account_id = prod.product_tmpl_id.categ_id.property_account_expense_categ.id
        else:
            ts_account_id = self.env['ir.property'].get('property_account_expense_categ', 'product.category').id
            # acc_id = property_obj.get(cr, uid, 'property_account_expense_categ', 'product.category', context=context).id

        if abs(total_amount) > 0.0:
            # add one move line to balance journal entry
            ts_move_lines.append({
                'type': 'dest',
                'name': name,
                'price': -total_amount,
                'account_id': ts_account_id,
                'date_maturity': self.date_to,
                'ref': name,
            })

        if ts_move_lines:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # borrow line_get_convert() to format the lines
            lines = [(0, 0, self.env['account.invoice'].line_get_convert(l, self.employee_id.user_id.company_id.partner_id.id, now)) for l in ts_move_lines]
            return lines
        else:
            return []

    @api.multi
    def button_done(self):
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
        self.signal_workflow('done')
        return True


class imsar_hr_timesheet(osv.Model):
    _inherit = 'hr.analytic.timesheet'
    _keys_to_log = ['date','routing_id','account_id','name','unit_amount','location']
    _default_tz = 'America/Denver'
    state = new_fields.Char(compute='_check_state')
    logging_required = new_fields.Boolean(compute='_check_state')

    @api.one
    @api.depends('date', 'previous_date')
    def _check_state(self):
        # use a timezone, but then strip out tz info for the comparison
        user = self.env.user
        if user.tz:
            now = datetime.now(pytz.timezone(user.tz))
        else:
            default_tz_res = self.env['ir.config_parameter'].search([('key','=','user.default_tz')])
            default_tz_id = default_tz_res and default_tz_res[0]
            if default_tz_id:
                default_tz = self.env['ir.config_parameter'].browse(default_tz_id).value
                now = datetime.now(pytz.timezone(default_tz))
            else:
                now = datetime.now(pytz.timezone(self._default_tz))
        now = now.replace(tzinfo=None)

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

    @api.multi
    def _log_changes(self, vals, new_record=False):
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
            if isinstance(self[key], osv.Model):
                oldval = self[key].name
                newval = self[key].browse(val).name
            else:
                oldval = self[key]
                newval = val
            body += (line_str.format(key_str, oldval, newval))
        sheet.message_post(subject=subject, body=body,)

    @api.multi
    def write(self, vals):
        vals['previous_date'] = vals.get('date') or self.date
        if self.logging_required:
            vals['change_explanation_log'] = vals.get('change_explanation')
            vals['change_explanation'] = ''
            self._log_changes(vals)
        return super(imsar_hr_timesheet, self).write(vals)

    @api.model
    def create(self, vals):
        vals['previous_date'] = vals['date']
        vals['change_explanation_log'] = vals['change_explanation']
        vals['change_explanation'] = ''
        vals['id'] = super(imsar_hr_timesheet, self).create(vals)
        if vals['id'].logging_required:
            self._log_changes(vals, new_record=True)
        return vals.get('id')

    @api.multi
    def unlink(self):
        if self.amount > 0.0 or self.unit_amount > 0.0:
            raise Warning(_('You cannot delete a timesheet entry with more than 0 hours. Please edit the entry to 0 hours first.'))
        if self.logging_required:
            subject = 'Deleted Line ID: %s' % self.id
            body = ''
            for key in self._keys_to_log:
                key_str = self._all_columns[key].column.string
                if isinstance(self[key], osv.Model):
                    oldval = self[key].name
                else:
                    oldval = self[key]
                body += 'Removed <strong>%s</strong>: <strong>%s</strong><br>' % (key_str, oldval)

            self.sheet_id.message_post(subject=subject, body=body,)
        return super(imsar_hr_timesheet, self).unlink()

    @api.onchange('date')
    def onchange_date(self):
        date = datetime.strptime(self.date, '%Y-%m-%d')
        from_date = datetime.strptime(self.sheet_id.date_from, '%Y-%m-%d')
        to_date = datetime.strptime(self.sheet_id.date_to, '%Y-%m-%d')
        if from_date > date:
            self.date = self.sheet_id.date_from
        if to_date < date:
            self.date = self.sheet_id.date_to
        self._check_state()
        if self.state == 'future':
            if not (self.account_id and self.account_id.timesheets_future):
                self.routing_id = ''



    _columns = {
        'location': fields.selection([('office','Office'),('home','Home')], 'Work Location', required=True,
                                     help="Location the hours were worked",),
        'change_explanation': fields.char('Change Explanation'),
        'previous_date': fields.date('Previous Date', invisible=True),
    }

    _defaults = {
        'location': 'office',
        'state': 'open',
    }

class account_analytic_account_routing(osv.Model):
    _inherit = "account.analytic.account"

    def _dummy_func(self, cr, uid, ids):
        return ''

    def _filter_future_accounts(self, cr, uid, obj, name, args, context=None):
        state = args[0][2]
        if state == 'future':
            valid_accounts = self.pool.get('account.analytic.account').search(cr, uid, [('state', '!=', 'close'),('timesheets_future','=',True)])
        else:
            valid_accounts = self.pool.get('account.analytic.account').search(cr, uid, [('state', '!=', 'close'),])
        return [('id','in',valid_accounts)]

    _columns = {
        'timesheets_future': fields.boolean('Allow Future Times', help="Check this field if this analytic account is allowed to have timesheet posting in the future"),
        'timesheets_future_filter': fields.function(_dummy_func, method=True, fnct_search=_filter_future_accounts, type='char')
    }

    _defaults = {
        'timesheets_future': False,
    }
