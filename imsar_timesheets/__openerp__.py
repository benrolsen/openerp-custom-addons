# -*- coding: utf-8 -*-
##############################################################################
#
#    IMSAR LLC
#    Author: IMSAR LLC
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
############################################################################################################################################################

{
    "name" : "IMSAR Timesheet Customizations",
    "version" : "1.0",
    "author" : "IMSAR LLC",
    "category": 'Uncategorized',
    'complexity': "normal",
    "description": """
    Timesheet customizations, attempting to be compliant with DCAA
    """,
    'website': 'http://www.imsar.com',
    "depends" : ['account_routing','hr_timesheet','hr_timesheet_sheet',
    ],
    'data': ['hr_timesheet_view.xml','security/ir.model.access.csv','res_config_view.xml'],
    'installable': True,
    'auto_install': False,
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
