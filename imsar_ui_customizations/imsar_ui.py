# -*- coding: utf-8 -*-
##############################################################################
#
#    IMSAR LLC
#    Author: Ben Olsen
#    Copyright (C) 2014
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

class mrp_bom_custom(osv.Model):
   _inherit = "mrp.bom"

   _columns = {
       'type': fields.selection([('normal','Assembly BoM'),('phantom','Package BoM')], 'BoM Type', required=True,
                                 help= "If a by-product is used in several products, it can be useful to create its own BoM. "\
                                 "Though if you don't want separated production orders for this by-product, select Package as BoM type. "\
                                 "If a Package BoM is used for a root product, it will be sold and shipped as a set of components, instead of being produced."),
   }

