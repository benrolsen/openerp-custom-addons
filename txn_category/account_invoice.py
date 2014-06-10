from osv import fields, osv


class account_invoice_line_category(osv.Model):
    _inherit = "account.invoice.line"

    _columns = {
        'txn_category_id':  fields.many2one('account.txn.category', 'Category', required=True),
    }


