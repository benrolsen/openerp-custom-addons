from datetime import datetime, date, timedelta
from collections import defaultdict
import pytz
import json

from openerp import models, api, _

from openerp import fields as new_fields
from openerp.osv import fields, osv
from openerp.exceptions import Warning
import openerp.addons.decimal_precision as dp


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
            values['user_id'] = uid
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


class imsar_hr_timesheet_sheet(models.Model):
    _inherit = 'hr_timesheet_sheet.sheet'

    move_id = new_fields.Many2one('account.move', string='Journal Entry',
        readonly=True, index=True, ondelete='restrict', copy=False,
        help="Link to the automatically generated Journal Items.")
    subtotal_line = new_fields.Char(string="Subtotals: ", compute='_compute_subtotals')
    subtotal_json = new_fields.Char(string="internal only", compute='_compute_subtotals')
    employee_flsa_status = new_fields.Selection(related='employee_id.flsa_status', readonly=True)

    @api.one
    @api.depends('timesheet_ids')
    def _compute_subtotals(self):
        totals = defaultdict(float)
        worktype_names = dict()
        for line in self.timesheet_ids:
            worktype = self.env['hr.timesheet.worktype'].browse(line.worktype.id)
            worktype_names[line.worktype.id] = worktype.name
            if line.account_id not in worktype.nonexempt_limit_ignore_ids and line.unit_amount > 0.0:
                totals[line.worktype.id] += line.unit_amount
        self.subtotal_line = ", ".join(["%s: %s" % (worktype_names[key], val) for key, val in totals.items()])
        self.subtotal_json = json.dumps(totals)

    @api.one
    @api.constrains('timesheet_ids')
    def _check_subtotals(self):
        subtotals = json.loads(self.subtotal_json)
        regular_worktype_id = str(self.employee_id.user_id.company_id.regular_worktype_id.id)
        overtime_worktype_id = str(self.employee_id.user_id.company_id.overtime_worktype_id.id)
        regular = subtotals.get(regular_worktype_id, 0.0)
        overtime = subtotals.get(overtime_worktype_id, 0.0)
        if self.employee_id.flsa_status != 'exempt':
            if regular > 40.0:
                raise Warning(_("You cannot log more than 40 hours of regular time."))
            if overtime > 0.0 and regular < 40.0:
                raise Warning(_("You cannot log overtime without having 40 hours of regular time first."))
        else:
            if overtime > 0.0:
                raise Warning(_("Exempt employees are not eligible for overtime."))

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
            # make a move line for the base amount
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
            # add another line for the premium addition, if any
            if line.premium_amount != 0.0:
                # some contracts don't allow overtime premiums to be charged to them, so deal with that here
                overtime_worktype_id = self.employee_id.user_id.company_id.overtime_worktype_id.id
                contract_overtime_routing = line.account_id.overtime_account
                if contract_overtime_routing and (line.worktype.id == overtime_worktype_id):
                    final_account_id = contract_overtime_routing.id
                else:
                    final_account_id = line.general_account_id.id
                ts_move_lines.append({
                    'type': 'dest',
                    'name': line.name + ' - ' + line.worktype.name + ' premium',
                    'price': line.premium_amount,
                    'account_id': final_account_id,
                    'date_maturity': self.date_to,
                    'quantity': line.unit_amount,
                    'product_id': line.product_id.id,
                    'product_uom_id': line.product_uom_id.id,
                    'analytic_lines': [(4, line.line_id.id),],
                    'ref': name,
                })
                total_amount += line.premium_amount

        # Get the liability account for the balancing move line (a salary product should have a liability accout as its expense account)
        prod = self.employee_id.product_id
        if prod.property_account_expense:
            ts_account_id = prod.property_account_expense.id
        elif prod.product_tmpl_id.property_account_expense:
            ts_account_id = prod.product_tmpl_id.property_account_expense.id
        elif prod.product_tmpl_id.categ_id.property_account_expense_categ:
            ts_account_id = prod.product_tmpl_id.categ_id.property_account_expense_categ.id
        else:
            ts_account_id = self.env['ir.property'].get('property_account_expense_categ', 'product.category').id

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
            # borrow line_get_convert() from account.invoice to format the lines
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


class imsar_hr_timesheet(models.Model):
    _inherit = 'hr.analytic.timesheet'
    _keys_to_log = ['date','routing_id','account_id','name','unit_amount','location']
    _default_tz = 'America/Denver'

    # new columns
    location = new_fields.Selection([('office','Office'),('home','Home')], string='Work Location', required=True,
                                 help="Location the hours were worked",)
    change_explanation = new_fields.Char(string='Change Explanation')
    previous_date = new_fields.Date(string='Previous Date', invisible=True)
    state = new_fields.Char(compute='_check_state') # 'past','open','future'
    logging_required = new_fields.Boolean(compute='_check_state')
    worktype = new_fields.Many2one('hr.timesheet.worktype', string="Work Type", ondelete='restrict',
                                   required=True, )
    premium_amount = new_fields.Float(string='Premium Amount', required=True, help='The additional amount based on work type, like overtime', digits_compute=dp.get_precision('Account'))

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

    @api.onchange('amount','worktype')
    def onchange_premium(self):
        if self.worktype:
            self.premium_amount = self.amount * self.worktype.premium_rate
        else:
            self.premium_amount = 0.0

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

    @api.model
    def _get_default_worktype(self):
        return self.env.user.company_id.regular_worktype_id.id

    _defaults = {
        'location': 'office',
        'state': 'open',
        'worktype': _get_default_worktype,
        'premium_amount': 0.0,
    }

class imsar_timesheets_account_analytic_account(models.Model):
    _inherit = "account.analytic.account"

    overtime_account = new_fields.Many2one('account.account', string="Overtime Routing Account", domain="[('type','not in',['view','closed'])]")

    def _dummy_func(self, cr, uid, ids):
        return ''

    def _filter_future_accounts(self, cr, uid, obj, name, args, context=None):
        state = args[0][2]
        if state == 'future':
            valid_accounts = self.pool.get('account.analytic.account').search(cr, uid, [('state', '!=', 'close'),('timesheets_future','=',True)])
        else:
            valid_accounts = self.pool.get('account.analytic.account').search(cr, uid, [('state', '!=', 'close'),])
        return [('id','in',valid_accounts)]

    @api.one
    def _add_to_tree(self, row, res):
        account = self
        while account:
            if account.id in res:
                res[account.id]['debit'] += row['debit']
                res[account.id]['credit'] += row['credit']
                res[account.id]['balance'] += row['balance']
            account = account.parent_id

    def _debit_credit_new_bal(self, cr, uid, ids, fields, arg, context=None):
        res = super(imsar_timesheets_account_analytic_account, self)._debit_credit_bal_qtty(cr, uid, ids, fields, arg, context)
        user = self.pool.get('res.users').browse(cr, uid, uid, context)
        regular_worktype_id = user.company_id.regular_worktype_id.id
        overtime_worktype_id = user.company_id.overtime_worktype_id.id

        # add premiums to totals, but ignore overtime premium if the analytic routes overtime premiums somewhere else
        child_ids = tuple(self.search(cr, uid, [('parent_id', 'child_of', ids)]))
        where_date = ''
        where_clause_args = [tuple(child_ids), regular_worktype_id, overtime_worktype_id]
        if context.get('from_date', False):
            where_date += " AND l.date >= %s"
            where_clause_args  += [context['from_date']]
        if context.get('to_date', False):
            where_date += " AND l.date <= %s"
            where_clause_args += [context['to_date']]
        cr.execute("""
                    SELECT
                        a.id,
                        sum(CASE WHEN at.premium_amount > 0 THEN at.premium_amount ELSE 0.0 END) as debit,
                        sum(CASE WHEN at.premium_amount < 0 THEN -at.premium_amount ELSE 0.0 END) as credit,
                        COALESCE(SUM(at.premium_amount),0) AS balance
                    FROM account_analytic_account a
                    LEFT JOIN account_analytic_line l ON (a.id = l.account_id)
                    LEFT JOIN hr_analytic_timesheet at ON (l.id = at.line_id)
                    WHERE a.id IN %s
                        AND at.worktype != %s
                        AND (at.worktype != %s or a.overtime_account is null)
                        """ + where_date + """
                       GROUP BY a.id""", where_clause_args)

        for row in cr.dictfetchall():
            self._add_to_tree(cr, uid, row['id'], row, res, context)
        return res

    _columns = {
        'balance': fields.function(_debit_credit_new_bal, type='float', string='Balance', multi='_debit_credit_new_bal', digits_compute=dp.get_precision('Account')),
        'debit': fields.function(_debit_credit_new_bal, type='float', string='Debit', multi='_debit_credit_new_bal', digits_compute=dp.get_precision('Account')),
        'credit': fields.function(_debit_credit_new_bal, type='float', string='Credit', multi='_debit_credit_new_bal', digits_compute=dp.get_precision('Account')),
        'timesheets_future': fields.boolean('Allow Future Times', help="Check this field if this analytic account is allowed to have timesheet posting in the future"),
        'timesheets_future_filter': fields.function(_dummy_func, method=True, fnct_search=_filter_future_accounts, type='char'),
    }

    _defaults = {
        'timesheets_future': False,
    }

class flsa_employee(models.Model):
    _inherit = 'hr.employee'
    flsa_status = new_fields.Selection([('exempt','Exempt'),('non-exempt','Non-exempt')], string='FLSA Status', required=True)

    _defaults = {
        'flsa_status': 'exempt',
    }


# new model to deal with premium pay rates (overtime, danger, etc)
class hr_timesheet_worktype(models.Model):
    _name = 'hr.timesheet.worktype'

    name = new_fields.Char('Name', required=True)
    active = new_fields.Boolean('Active')
    premium_rate = new_fields.Float('Additional Premium Rate', required=True,
                        help="The additional multiplier to be added on top of the base pay. For example, overtime would be 0.5, for a 50% premium.")
    nonexempt_limit = new_fields.Integer('Non-exempt Limit (Hours)',
                        help="Weekly limit of hours for this type for non-exempt employees. Enter 0 or leave blank for no limit.")
    nonexempt_limit_ignore_ids = new_fields.Many2many('account.analytic.account','premium_analytic_rel','limit_id','account_analytic_id','Ignore Analytic Accounts',
                        help="Enter any analytic accounts this limit should ignore when counting hours worked (like PTO).",
                        domain="[('state','!=','closed'),('use_timesheets','=',1)]")

    _defaults = {
        'active': True,
        'premium_rate': 0.0,
    }
