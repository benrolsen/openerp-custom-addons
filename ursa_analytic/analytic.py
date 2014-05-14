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
import time
from datetime import datetime

from openerp.osv import fields, osv
from openerp import tools
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp

class account_analytic_account(osv.osv):
    _inherit = 'account.analytic.account'

class sale_order(osv.osv):

    _inherit = 'sale.order'
    
    _columns = {
        'project_id': fields.many2one('account.analytic.account', 'Contract / Analytic', readonly=True, 
        states={'draft': [('readonly', False)], 'prepared': [('readonly', False)], 'sent': [('readonly', False)]}, 
        help="The analytic account related to a sale order."),
        }

    def _prepare_invoice(self, cr, uid, order, lines, context=None):
    
        res = super(sale_order, self)._prepare_invoice(cr, uid, order, lines, context=context)
        res['project_id'] = order.project_id and order.project_id.id or False

        return res

    def _prepare_order_picking(self, cr, uid, order, context=None):

        retval =super(sale_order, self)._prepare_order_picking(cr, uid, order, context=context)
        retval['project_id'] = order.project_id and order.project_id.id or False

        return retval
    
sale_order()
    
class purchase_order(osv.osv):

    _inherit = 'purchase.order'
    
    _columns = {
        'project_id': fields.many2one('account.analytic.account', 'Contract / Analytic', readonly=True, 
        states={'draft': [('readonly', False)], 'proforma': [('readonly', False)], 'sent': [('readonly', False)]}, 
        help="The analytic account related to a purchase order."),
        }

    def action_invoice_create(self, cr, uid, ids, context=None):
    
        inv = super(purchase_order, self).action_invoice_create(cr, uid, ids, context=context)
        
        assert len(ids) == 1, 'This option should only be used for a single id at a time.'

        purchase_obj = self.pool.get('purchase.order')
        order = self.browse(cr, uid, ids[0], context=context)

        if order.partner_invoice_id:
        
            invoice_obj = self.pool.get('account.invoice')
            invoice = invoice_obj.browse(cr, uid, inv, context=context)
            
            inv_vals = {'project_id':order.project_id and order.project_id.id or False}
                           
            invoice_obj.write(cr, uid, [inv], inv_vals, context=context)
        
        return inv
        
    def _prepare_order_picking(self, cr, uid, order, context=None):

        retval = super(purchase_order, self)._prepare_order_picking(cr, uid, order, context=context)
        retval['project_id'] = order.project_id and order.project_id.id or False
            
        return retval
        
class stock_picking(osv.osv):

    _inherit = 'stock.picking'
    
    _columns = {
        'project_id': fields.many2one('account.analytic.account', 'Contract / Analytic', readonly=True, 
        states={'draft': [('readonly', False)], 'confirmed': [('readonly', False)], 'assigned': [('readonly', False)]}, 
        help="The analytic account related to stock picking (in/out)."),
        } 

    # update the information on the invoice    
    def _prepare_invoice(self, cr, uid, picking, partner, inv_type, journal_id, context=None):

        res =super(stock_picking, self)._prepare_invoice(cr, uid, picking, partner, inv_type, journal_id, context=context)

        res['project_id'] = picking.project_id and picking.project_id.id or False
        
        return res
        
class stock_picking_in(osv.osv):

    _inherit = 'stock.picking.in'
    
    _columns = {
        'project_id': fields.many2one('account.analytic.account', 'Contract / Analytic', readonly=True, 
        states={'draft': [('readonly', False)], 'confirmed': [('readonly', False)], 'assigned': [('readonly', False)]}, 
        help="The analytic account related to stock picking (in/out)."),
        } 
class stock_picking_out(osv.osv):

    _inherit = 'stock.picking.out'
    
    _columns = {
        'project_id': fields.many2one('account.analytic.account', 'Contract / Analytic', readonly=True, 
        states={'draft': [('readonly', False)], 'confirmed': [('readonly', False)], 'assigned': [('readonly', False)]}, 
        help="The analytic account related to stock picking (in/out)."),
        } 

class account_invoice(osv.osv):

    _inherit = 'account.invoice'
    
    _columns = {
        'project_id': fields.many2one('account.analytic.account', 'Contract / Analytic', readonly=True, 
        states={'draft': [('readonly', False)], 'proforma': [('readonly', False)], 'proforma2': [('readonly', False)], 'open': [('readonly', False)]}, 
        help="The analytic account related to invoices."),
        }         
        
class sale_advance_payment_inv(osv.osv_memory):
    _inherit = "sale.advance.payment.inv"

    def _prepare_advance_invoice_vals(self, cr, uid, ids, context=None):

        res = super(sale_advance_payment_inv, self)._prepare_advance_invoice_vals(cr, uid, ids, context=context)

        sale_obj = self.pool.get('sale.order')        
        sale_ids = context.get('active_ids', [])
        if context is None:
            context = {}

        for order in sale_obj.browse(cr, uid, sale_ids, context=context):
        
            res[0][1]['project_id'] = order.project_id and order.project_id.id or False
        
        return res
        
