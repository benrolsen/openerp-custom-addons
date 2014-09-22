# -*- coding: utf-8 -*-
##############################################################################
#
#    Ursa Information Systems
#    Author: Balaji Kannan
#    Copyright (C) 2014 (<http://www.ursainfosystems.com>).
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

import datetime

from openerp.osv import fields, osv
from openerp.tools import ustr
from openerp.tools.translate import _

class crossovered_budget_lines(osv.osv):

    _inherit = 'crossovered.budget.lines'

    def get_analytic_lines(self, cr, uid, ids, context=None):
	
        for bline in self.browse(cr, uid, ids, context=context):
        
            analytic_account_id = bline.analytic_account_id and  bline.analytic_account_id.id or False
            date_from = bline.date_from
            date_to = bline.date_to
            acc_ids = [x.id for x in bline.general_budget_id.account_ids]
            
            item_ids=[]
            
            if analytic_account_id:
                cr.execute("SELECT id FROM account_analytic_line WHERE account_id=%s AND (date between to_date(%s,'yyyy-mm-dd') AND to_date(%s,'yyyy-mm-dd')) AND general_account_id=ANY(%s)", (analytic_account_id, date_from, date_to, acc_ids,))
                item_ids = [x[0] for x in cr.fetchall()]
                
            return {
                'name': _('Analytic Account Lines'),
                'view_type': 'form',
                "view_mode": 'tree,form',
                'res_model': 'account.analytic.line',
                'type': 'ir.actions.act_window',
                'domain': [('id','=',item_ids)],
            }

