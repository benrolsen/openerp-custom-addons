# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2013 IMSAR
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

{
    'name': "IMSAR Accounting",
    'version': "1.0",
    'depends': ['account_accountant', 'analytic', 'l10n_us', 'hr_timesheet_sheet',],
    'author': "Ben Olsen",
    'description': "Customized IMSAR accounts and analytics",
    'category': "Uncategorized",
    'data': [
            'imsar_accounting_wizard.xml',
            'imsar_account_type.xml',
            'account.account.csv',
            'account.analytic.account.csv',
            'account.journal.csv',
            'account.analytic.journal.csv',
            'ir_property.xml',
            ],
    'installable': True,
    'auto_install': False,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
