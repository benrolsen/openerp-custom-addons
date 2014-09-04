from openerp import models, fields, api, _
from openerp.exceptions import Warning


class product_template(models.Model):
    _inherit = 'product.template'

    _defaults = {
        'type' : 'product',
    }
