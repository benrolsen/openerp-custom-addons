import logging
_logger = logging.getLogger(__name__)

from openerp.osv import fields, osv


class imsar_accounting(osv.Model):
    _inherit = 'account.account'

    def _clean_default_accounting(self, cr, uid, ids=[], context=None):
        cr.execute("truncate account_chart_template cascade")