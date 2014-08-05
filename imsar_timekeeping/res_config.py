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

from openerp import models, fields, api

class timekeeping_settings(models.TransientModel):
    _inherit = 'hr.config.settings'

    wage_account_id = fields.Many2one('account.account', 'Wage Liability Account')
    general_journal_id = fields.Many2one('account.journal', 'Timekeeping Journal')
    regular_worktype_id = fields.Many2one('hr.timekeeping.worktype', string="Regular Work Type")
    overtime_worktype_id = fields.Many2one('hr.timekeeping.worktype', string="Overtime Work Type")
    future_analytic_ids = fields.Many2many('account.analytic.account', 'config_future_analytic_rel', 'config_id', 'analytic_id', string="Analytics allowed for future dates")

    @api.model
    def get_default_timekeeping(self, fields):
        user = self.env.user
        res = dict()
        res['wage_account_id'] = user.company_id.wage_account_id.id
        res['general_journal_id'] = user.company_id.general_journal_id.id
        res['regular_worktype_id'] = user.company_id.regular_worktype_id.id
        res['overtime_worktype_id'] = user.company_id.overtime_worktype_id.id
        res['future_analytic_ids'] = user.company_id.future_analytic_ids.ids
        return res

    @api.one
    def set_default_timekeeping(self):
        self.env.user.company_id.write({
            'wage_account_id': self.wage_account_id.id,
            'general_journal_id': self.general_journal_id.id,
            'regular_worktype_id': self.regular_worktype_id.id,
            'overtime_worktype_id': self.overtime_worktype_id.id,
            'future_analytic_ids': [(6,0, self.future_analytic_ids.ids)],
        })

class res_company(models.Model):
    _inherit = 'res.company'

    wage_account_id = fields.Many2one('account.account', 'Wage Liability Account')
    general_journal_id = fields.Many2one('account.journal', 'Timekeeping Journal')
    regular_worktype_id = fields.Many2one('hr.timekeeping.worktype', string="Regular Work Type")
    overtime_worktype_id = fields.Many2one('hr.timekeeping.worktype', string="Overtime Work Type")
    future_analytic_ids = fields.Many2many('account.analytic.account', 'company_future_analytic_rel', 'company_id', 'analytic_id', string="Analytics allowed for future dates")


