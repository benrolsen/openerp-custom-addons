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
    'name': "IMSAR Demo Data",
    'version': "1.0",
    'depends': [
        'base', 'imsar_accounting', 'imsar_auth_ldap', 'account_routing',
        # 'imsar_timesheets',
        'imsar_sale', 'imsar_analytic_account', 'imsar_ui_customizations',
        ],
    'author': "Ben Olsen",
    'description': "Loads demo data customized for IMSAR",
    'category': "Uncategorized",
    'data': [
        'ldap_data.xml',
        # 'analytic_data.xml',
        'res.partner.csv',
        'product.template.csv',
        'account.routing.csv',
        'account.routing.line.csv',
        'account.routing.subrouting.csv',
        'account_routing_settings.xml',
        # 'hr.timesheet.worktype.csv',
        # 'config_settings.xml',
        ],
    'installable': True,
    'auto_install': False,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
