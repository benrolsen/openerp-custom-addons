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
    "name" : "IMSAR Interface Customizations",
    "version" : "1.0",
    "author" : "IMSAR LLC",
    "category": 'Uncategorized',
    'complexity': "normal",
    "description": """
    Interface customizations:
    """,
    'website': 'http://www.imsar.com',
    "depends" : ['base', 'web_m2x_options', 'mail',
                 'imsar_default_install', 'imsar_accounting', 'imsar_sale', 'account_budget',
                 "purchase", "sale",
                 'product', 'account', 'stock',
                 'mrp',
    ],
    'data': [
        'product_view.xml',
        'invoice_view.xml',
        'partner_view.xml',
        'account_view.xml',
        'purchase_view.xml',
        'menus.xml',
        'imsar_settings.xml',
        'views/imsar_ui.xml',
    ],
    'qweb': ['static/src/xml/mail.xml'],
    'installable': True,
    'auto_install': False,
}

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
