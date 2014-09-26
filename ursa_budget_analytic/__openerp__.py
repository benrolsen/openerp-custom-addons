# -*- coding: utf-8 -*-
##############################################################################
#
#    Ursa Information Systems, IMSAR LLC
#    Author: Balaji Kannan, Ben Olsen
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
############################################################################################################################################################

{
    "name" : "Budget Analytic Customizations",
    "version" : "1.0",
    "author" : ["Ursa Information Systems, USA"],
    "category": 'Accounting',
    'complexity': "normal",
    "description": """
    1. Exposes Analytic Account Lines form and tree
    2. Allows for drilldown from Budget lines to corresponding analytic account lines
    """,
    'website': 'http://www.ursainfosystems.com',
    "depends" : ['analytic','account','account_budget'],
    'init_xml': [],
    'data': ['budget_view.xml'],
    'demo_xml': [],
    'installable': True,
    'auto_install': False,
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
