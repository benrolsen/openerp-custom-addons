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
    "name" : "IMSAR DCAA Timekeeping",
    "version" : "1.0",
    "author" : "IMSAR LLC",
    "category": 'Uncategorized',
    'complexity': "normal",
    "description": """
    Timesheet customizations, attempting to be compliant with DCAA
    """,
    'website': 'http://www.imsar.com',
    "depends" : ['account_routing','imsar_accounting',
    ],
    'data': [
            'res_config_view.xml',
            'analytic_view.xml',
            'security/hr_timekeeping_security.xml',
            'security/hr_timekeeping_access.xml',
            'timekeeping_workflow.xml',
            'timekeeping_worktype_view.xml',
            'timekeeping_view.xml',
            'timekeeping_review_view.xml',
            'views/hr_timekeeping_sheet.xml',
            ],
    'qweb': ['static/src/xml/timesheet.xml',],
    'installable': True,
    'auto_install': False,
}
