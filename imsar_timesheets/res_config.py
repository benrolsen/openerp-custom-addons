# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Business Applications
#    Copyright (C) 2004-2012 OpenERP S.A. (<http://openerp.com>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp.osv import fields, osv

class hr_timesheet_settings(osv.osv_memory):
    _inherit = 'hr.config.settings'

    _columns = {
        'general_journal_id': fields.many2one('account.journal', 'Timesheet Journal'),
    }

    def get_default_timesheet(self, cr, uid, fields, context=None):
        user = self.pool.get('res.users').browse(cr, uid, uid, context=context)
        res = super(hr_timesheet_settings,self).get_default_timesheet(cr, uid, fields, context)
        res['general_journal_id'] = user.company_id.general_journal_id.id
        return res

    def set_default_timesheet(self, cr, uid, ids, context=None):
        config = self.browse(cr, uid, ids[0], context)
        user = self.pool.get('res.users').browse(cr, uid, uid, context)
        res = super(hr_timesheet_settings,self).set_default_timesheet(cr, uid, ids, context)
        user.company_id.write({
            'general_journal_id': config.general_journal_id.id,
        })

class res_company(osv.osv):
    _inherit = 'res.company'
    _columns = {
        'general_journal_id': fields.many2one('account.journal', 'Timesheet Journal'),
    }

