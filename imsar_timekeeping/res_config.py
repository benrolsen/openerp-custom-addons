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
    timekeeping_journal_id = fields.Many2one('account.journal', 'Timekeeping Journal')
    regular_worktype_id = fields.Many2one('hr.timekeeping.worktype', string="Regular Work Type")
    overtime_worktype_id = fields.Many2one('hr.timekeeping.worktype', string="Overtime Work Type")
    pto_analytic_id = fields.Many2one('account.analytic.account', string="PTO Analytic")
    pto_liability_account_id = fields.Many2one('account.account', 'PTO Liability Account')
    pto_expense_account_id = fields.Many2one('account.account', 'PTO Expense Account')
    proxy_analytic_ids = fields.Many2many('account.analytic.account', 'config_proxy_analytic_rel', 'config_id', 'analytic_id', string="Analytics always allowed on proxy timesheets")
    future_analytic_ids = fields.Many2many('account.analytic.account', 'config_future_analytic_rel', 'config_id', 'analytic_id', string="Analytics allowed for future dates")
    global_approval_user_ids = fields.Many2many('res.users', 'config_global_approval_user_rel', 'config_id', 'user_id', string="Users with global approval rights")
    pto_accrual_rate_under_1 = fields.Float('PTO Accrual Rate (per hour): under 1 year', required=True, default=0.0, digits=(1,4))
    pto_accrual_rate_1_to_5 = fields.Float('PTO Accrual Rate (per hour): 1 to 5 years', required=True, default=0.0, digits=(1,4))
    pto_accrual_rate_5_to_10 = fields.Float('PTO Accrual Rate (per hour): 5 to 15 years', required=True, default=0.0, digits=(1,4))
    pto_accrual_rate_10_to_15 = fields.Float('PTO Accrual Rate (per hour): 10 to 15 years', required=True, default=0.0, digits=(1,4))
    pto_accrual_rate_over_15 = fields.Float('PTO Accrual Rate (per hour): over 15 years', required=True, default=0.0, digits=(1,4))
    default_auth_departments = fields.Many2many('hr.department', 'config_dept_rel', 'config_id', 'dept_id', string="Default HR Departments with project/contract authorization")

    @api.model
    def get_default_timekeeping(self, fields):
        user = self.env.user
        res = dict()
        res['wage_account_id'] = user.company_id.wage_account_id.id
        res['timekeeping_journal_id'] = user.company_id.timekeeping_journal_id.id
        res['regular_worktype_id'] = user.company_id.regular_worktype_id.id
        res['overtime_worktype_id'] = user.company_id.overtime_worktype_id.id
        res['pto_analytic_id'] = user.company_id.pto_analytic_id.id
        res['pto_liability_account_id'] = user.company_id.pto_liability_account_id.id
        res['pto_expense_account_id'] = user.company_id.pto_expense_account_id.id
        res['proxy_analytic_ids'] = user.company_id.proxy_analytic_ids.ids
        res['future_analytic_ids'] = user.company_id.future_analytic_ids.ids
        res['global_approval_user_ids'] = user.company_id.global_approval_user_ids.ids
        res['pto_accrual_rate_under_1'] = user.company_id.pto_accrual_rate_under_1
        res['pto_accrual_rate_1_to_5'] = user.company_id.pto_accrual_rate_1_to_5
        res['pto_accrual_rate_5_to_10'] = user.company_id.pto_accrual_rate_5_to_10
        res['pto_accrual_rate_10_to_15'] = user.company_id.pto_accrual_rate_10_to_15
        res['pto_accrual_rate_over_15'] = user.company_id.pto_accrual_rate_over_15
        res['default_auth_departments'] = user.company_id.default_auth_departments.ids
        return res

    @api.one
    def set_default_timekeeping(self):
        self.env.user.company_id.write({
            'wage_account_id': self.wage_account_id.id,
            'timekeeping_journal_id': self.timekeeping_journal_id.id,
            'regular_worktype_id': self.regular_worktype_id.id,
            'overtime_worktype_id': self.overtime_worktype_id.id,
            'pto_analytic_id': self.pto_analytic_id.id,
            'pto_liability_account_id': self.pto_liability_account_id.id,
            'pto_expense_account_id': self.pto_expense_account_id.id,
            'proxy_analytic_ids': [(6,0, self.proxy_analytic_ids.ids)],
            'future_analytic_ids': [(6,0, self.future_analytic_ids.ids)],
            'global_approval_user_ids': [(6,0, self.global_approval_user_ids.ids)],
            'pto_accrual_rate_under_1': self.pto_accrual_rate_under_1,
            'pto_accrual_rate_1_to_5': self.pto_accrual_rate_1_to_5,
            'pto_accrual_rate_5_to_10': self.pto_accrual_rate_5_to_10,
            'pto_accrual_rate_10_to_15': self.pto_accrual_rate_10_to_15,
            'pto_accrual_rate_over_15': self.pto_accrual_rate_over_15,
            'default_auth_departments': [(6,0, self.default_auth_departments.ids)],
        })

class res_company(models.Model):
    _inherit = 'res.company'

    wage_account_id = fields.Many2one('account.account', 'Wage Liability Account')
    timekeeping_journal_id = fields.Many2one('account.journal', 'Timekeeping Journal')
    regular_worktype_id = fields.Many2one('hr.timekeeping.worktype', string="Regular Work Type")
    overtime_worktype_id = fields.Many2one('hr.timekeeping.worktype', string="Overtime Work Type")
    pto_analytic_id = fields.Many2one('account.analytic.account', string="PTO Analytic")
    pto_liability_account_id = fields.Many2one('account.account', 'PTO Liability Account')
    pto_expense_account_id = fields.Many2one('account.account', 'PTO Expense Account')
    proxy_analytic_ids = fields.Many2many('account.analytic.account', 'company_proxy_analytic_rel', 'config_id', 'analytic_id', string="Analytics always allowed on proxy timesheets")
    future_analytic_ids = fields.Many2many('account.analytic.account', 'company_future_analytic_rel', 'company_id', 'analytic_id', string="Analytics allowed for future dates")
    global_approval_user_ids = fields.Many2many('res.users', 'company_global_approval_user_rel', 'company_id', 'user_id', string="Users with global approval rights")
    pto_accrual_rate_under_1 = fields.Float('PTO Accrual Rate (per hour): under 1 year', required=True, default=0.0, digits=(1,4))
    pto_accrual_rate_1_to_5 = fields.Float('PTO Accrual Rate (per hour): 1 to 5 years', required=True, default=0.0, digits=(1,4))
    pto_accrual_rate_5_to_10 = fields.Float('PTO Accrual Rate (per hour): 5 to 10 years', required=True, default=0.0, digits=(1,4))
    pto_accrual_rate_10_to_15 = fields.Float('PTO Accrual Rate (per hour): 10 to 15 years', required=True, default=0.0, digits=(1,4))
    pto_accrual_rate_over_15 = fields.Float('PTO Accrual Rate (per hour): over 15 years', required=True, default=0.0, digits=(1,4))
    default_auth_departments = fields.Many2many('hr.department', 'company_dept_rel', 'company_id', 'dept_id', string="Default HR Departments with project/contract authorization")


