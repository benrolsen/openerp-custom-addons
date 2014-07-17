from datetime import datetime, date, timedelta
import pytz

from openerp import api
from openerp.osv import fields, osv
from openerp.tools.translate import _


class imsar_hr_timesheet_current_open(osv.osv_memory):
    _inherit = 'hr.timesheet.current.open'

    def open_timesheet(self, cr, uid, ids, context=None):
        if context is None:
            context = {}
        today = date.today()
        ts = self.pool.get('hr_timesheet_sheet.sheet')

        user_ids = self.pool.get('hr.employee').search(cr, uid, [('user_id','=',uid)], context=context)
        if not len(user_ids):
            raise osv.except_osv(_('Error!'), _('Please create an employee and associate it with this user.'))
        ids = ts.search(cr, uid, [('user_id','=',uid),('state','in',('draft','new')),('date_from','<=',today.strftime('%Y-%m-%d')), ('date_to','>=',today.strftime('%Y-%m-%d'))], context=context)

        if len(ids) < 1:
            values = dict()
            values['name'] = 'Week %d' % today.isocalendar()[1]
            values['date_from'] = today - timedelta(days=today.isoweekday()-1)
            values['date_to'] = values['date_from'] + timedelta(days=6)
            values['state'] = 'draft'
            self.pool.get('hr_timesheet_sheet.sheet').create(cr, uid, values, context)

        return super(imsar_hr_timesheet_current_open, self).open_timesheet(cr, uid, ids, context)


# class hr_timesheet_sheet(osv.Model):
#     _inherit = 'hr_timesheet_sheet.sheet'
#
#     def onchange_line(self, cr, uid, ids, thing, *args, **kwargs):
#         print(thing, args, kwargs)

class imsar_hr_timesheet(osv.Model):
    _inherit = 'hr.analytic.timesheet'
    _keys_to_log = ['date','routing_id','account_id','name','unit_amount','location']
    _default_tz = 'America/Denver'

    def _invalid_date(self, cr, uid, ids, vals):
        line = self.browse(cr, uid, ids)[0]
        user = self.pool.get('res.users').browse(cr, uid, uid)

        old_date_str = line['date']
        old_date = datetime.strptime(old_date_str, '%Y-%m-%d')
        old_deadline = old_date + timedelta(days=1, hours=11)
        # use the edited date if it changed, otherwise use the line's date
        new_date_str = vals.get('date') or line['date']
        new_date = datetime.strptime(new_date_str, '%Y-%m-%d')
        new_deadline = new_date + timedelta(days=1, hours=11)

        # use a timezone, but then strip out tz info for the comparison
        if user.tz:
            now = datetime.now(pytz.timezone(user.tz))
        else:
            default_tz_res = self.pool.get('ir.config_parameter').search(cr, uid, [('key','=','user.default_tz')])
            default_tz_id = default_tz_res and default_tz_res[0]
            if default_tz_id:
                default_tz = self.pool.get('ir.config_parameter').browse(cr, uid, default_tz_id).value
                now = datetime.now(pytz.timezone(default_tz))
            else:
                now = datetime.now(pytz.timezone(self._default_tz))
        now = now.replace(tzinfo=None)
        # log changes if old/new date is past the deadline or in the future
        if not (old_date < now < old_deadline) or not (new_date < now < new_deadline):
            return True, line
        else:
            return False, line

    def _date_check(self, cr, uid, ids, vals, new_record=False):
        invalid_date, line = self._invalid_date(cr, uid, ids, vals)
        if invalid_date:
            body = ''
            for key in list(set(self._keys_to_log) & set(vals.keys())):
                val = vals.get(key)
                key_str = line._all_columns[key].column.string
                if isinstance(line[key], osv.Model):
                    oldval = line[key].name
                    newval = line[key].browse(val).name
                else:
                    oldval = line[key]
                    newval = val
                body += ('<strong>%s</strong> from <strong>%s</strong> to <strong>%s</strong><br>' % (key_str, oldval, newval))
            if new_record:
                subject = "New record, Line ID: %s" % line.id
            else:
                subject = 'Changes made to Line ID: %s' % line.id
            line.sheet_id.message_post(subject=subject, body=body,)

    def write(self, cr, uid, ids, vals, context=None):
        self._date_check(cr, uid, ids, vals)
        return super(imsar_hr_timesheet, self).write(cr, uid, ids, vals, context)

    def create(self, cr, uid, vals, context=None):
        id = super(imsar_hr_timesheet, self).create(cr, uid, vals, context)
        self._date_check(cr, uid, [id], vals, new_record=True)
        return id

    def unlink(self, cr, uid, ids, context=None):
        print(ids)
        for id in ids:
            invalid_date, line = self._invalid_date(cr, uid, [id], {},)
            if invalid_date:
                subject = 'Deleted Line ID: %s' % line.id
                body = ''
                for key in self._keys_to_log:
                    key_str = line._all_columns[key].column.string
                    if isinstance(line[key], osv.Model):
                        oldval = line[key].name
                    else:
                        oldval = line[key]
                    body += 'Removed %s: %s' % (key_str, oldval)

                line.sheet_id.message_post(subject=subject, body=body,)
        return super(imsar_hr_timesheet, self).unlink(cr, uid, ids, context)

    def onchange_date(self, cr, uid, ids, date_str, date_from_str, date_to_str, *args, **kwargs):
        if not date_str:
            return {}
        date = datetime.strptime(date_str, '%Y-%m-%d')
        from_date = datetime.strptime(date_from_str, '%Y-%m-%d')
        to_date = datetime.strptime(date_to_str, '%Y-%m-%d')
        if from_date > date:
            return {'value':{'date': date_from_str, },}
        if to_date < date:
            return {'value':{'date': date_to_str, },}
        return {'value':{'date': date_str, },}

    # @api.multi
    # def unlock_button(self):
    #     env = self.env
    #     popup_form = self.env.ref('imsar_timesheets.imsar_hr_timesheet_change_explanation', False)
    #     return {
    #         'name': 'Change Explanation',
    #         'type': 'ir.actions.act_window',
    #         'view_type': 'form',
    #         'view_mode': 'form',
    #         'res_model': 'hr.analytic.timesheet',
    #         'views': [(popup_form.id, 'form')],
    #         'view_id': popup_form.id,
    #         'target': 'new',
    #         'context': {},
    #     }

    _columns = {
        'location': fields.selection([('office','Office'),('home','Home')], 'Work Location', required=True,
                                     help="Location the hours were worked",),
        'change_explanation': fields.char('Change Explanation')
    }

    _defaults = {
        'location': 'office',
    }