# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Business Applications
#    Copyright (C) 2004-2012 OpenERP S.A. (<http://openerp.com>).
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

from openerp import models, fields, api

class wms_settings(models.TransientModel):
    _inherit = 'stock.config.settings'

    material_account_type_ids = fields.Many2many('account.account.type', 'config_global_material_type_rel', 'config_id', 'account_type_id', string="Material Account Types")
    interim_receiving = fields.Many2one('account.routing.subrouting', string="Interim Receiving Task Code", required=True)
    interim_shipping = fields.Many2one('account.routing.subrouting', string="Interim Shipping Task Code", required=True)
    stock_journal = fields.Many2one('account.journal', string='Stock Journal', required=True)

    @api.model
    def get_default_timekeeping(self, fields):
        user = self.env.user
        res = dict()
        res['material_account_type_ids'] = user.company_id.material_account_type_ids.ids
        res['interim_receiving'] = user.company_id.interim_receiving.id
        res['interim_shipping'] = user.company_id.interim_shipping.id
        res['stock_journal'] = user.company_id.stock_journal.id
        return res

    @api.one
    def set_default_timekeeping(self):
        self.env.user.company_id.write({
            'material_account_type_ids': [(6,0, self.material_account_type_ids.ids)],
            'interim_receiving': self.interim_receiving.id,
            'interim_shipping': self.interim_shipping.id,
            'stock_journal': self.stock_journal.id,
        })

class res_company(models.Model):
    _inherit = 'res.company'

    material_account_type_ids = fields.Many2many('account.account.type', 'company_global_material_type_rel', 'config_id', 'account_type_id', string="Material Account Types")
    interim_receiving = fields.Many2one('account.routing.subrouting', string="Interim Receiving Task Code")
    interim_shipping = fields.Many2one('account.routing.subrouting', string="Interim Shipping Task Code")
    stock_journal = fields.Many2one('account.journal', string='Stock Journal')



