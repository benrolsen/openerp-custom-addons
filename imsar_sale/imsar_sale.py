from openerp.osv import fields, osv

class custom_sale_order(osv.Model):
   _inherit = "sale.order"

   _columns = {
       'sales_contact': fields.many2one('res.partner', 'Point of Contact'),
   }
