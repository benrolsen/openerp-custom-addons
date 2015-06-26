from openerp import models, fields, api

class wms_settings(models.TransientModel):
    _inherit = 'stock.config.settings'

    material_account_type_ids = fields.Many2many('account.account.type', 'config_global_material_type_rel', 'config_id', 'account_type_id', string="Material Account Types")
    interim_receiving = fields.Many2one('account.routing.subrouting', string="Interim Receiving Task Code", )
    interim_shipping = fields.Many2one('account.routing.subrouting', string="Interim Shipping Task Code", )
    attrition = fields.Many2one('account.routing.subrouting', string="Attrition Task Code", )
    stock_journal = fields.Many2one('account.journal', string='Stock Journal', )
    pnl_mat_debit = fields.Many2one('account.account', "P&L Material Debit Account", domain="[('type','!=','view')]")
    pnl_mat_credit = fields.Many2one('account.account', "P&L Material Credit Account", domain="[('type','!=','view')]")
    pnl_labor_debit = fields.Many2one('account.account', "P&L Labor Debit Account", domain="[('type','!=','view')]")
    pnl_labor_credit = fields.Many2one('account.account', "P&L Labor Credit Account", domain="[('type','!=','view')]")
    pnl_mfg_oh = fields.Many2one('account.account', "P&L MFG Overhead Account", domain="[('type','!=','view')]")
    mfg_oh_mat_writeoff = fields.Many2one('account.account', "MFG Material Write-off Account", domain="[('type','!=','view')]")
    mfg_oh_labor_writeoff = fields.Many2one('account.account', "MFG Labor Write-off Account", domain="[('type','!=','view')]")

    @api.model
    def get_default_wms(self, fields):
        user = self.env.user
        res = dict()
        res['material_account_type_ids'] = user.company_id.material_account_type_ids.ids
        res['interim_receiving'] = user.company_id.interim_receiving.id
        res['interim_shipping'] = user.company_id.interim_shipping.id
        res['attrition'] = user.company_id.attrition.id
        res['stock_journal'] = user.company_id.stock_journal.id
        res['pnl_mat_debit'] = user.company_id.pnl_mat_debit.id
        res['pnl_mat_credit'] = user.company_id.pnl_mat_credit.id
        res['pnl_labor_debit'] = user.company_id.pnl_labor_debit.id
        res['pnl_labor_credit'] = user.company_id.pnl_labor_credit.id
        res['pnl_mfg_oh'] = user.company_id.pnl_mfg_oh.id
        res['mfg_oh_mat_writeoff'] = user.company_id.mfg_oh_mat_writeoff.id
        res['mfg_oh_labor_writeoff'] = user.company_id.mfg_oh_labor_writeoff.id
        return res

    @api.one
    def set_default_wms(self):
        self.env.user.company_id.write({
            'material_account_type_ids': [(6,0, self.material_account_type_ids.ids)],
            'interim_receiving': self.interim_receiving.id,
            'interim_shipping': self.interim_shipping.id,
            'attrition': self.attrition.id,
            'stock_journal': self.stock_journal.id,
            'pnl_mat_debit': self.pnl_mat_debit.id,
            'pnl_mat_credit': self.pnl_mat_credit.id,
            'pnl_labor_debit': self.pnl_labor_debit.id,
            'pnl_labor_credit': self.pnl_labor_credit.id,
            'pnl_mfg_oh': self.pnl_mfg_oh.id,
            'mfg_oh_mat_writeoff': self.mfg_oh_mat_writeoff.id,
            'mfg_oh_labor_writeoff': self.mfg_oh_labor_writeoff.id,
        })

class mrp_settings(models.TransientModel):
    _inherit = 'mrp.config.settings'

    wip_task_code = fields.Many2one('account.routing.subrouting', string="Inventory/WIP Task Code")
    mfg_task_code = fields.Many2one('account.routing.subrouting', string="MFG Process Task Code")
    kitting_mat_locations = fields.Many2many('stock.location', 'config_mrp_rm_loc', 'config_id', 'location_id', string="MFG Materials Kitting Locations", domain="[('usage','=','internal')]")
    prod_ready_locations = fields.Many2many('stock.location', 'config_mrp_prod_loc', 'config_id', 'location_id', string="Production Accessible Locations", domain="[('usage','=','internal')]")
    rm_product_categories = fields.Many2many('product.category', 'config_mrp_rm_prod_categ', 'config_id', 'category_id', string="Raw Materials Product Categories")

    @api.model
    def get_default_mrp(self, fields):
        user = self.env.user
        res = dict()
        res['wip_task_code'] = user.company_id.wip_task_code.id
        res['mfg_task_code'] = user.company_id.mfg_task_code.id
        res['kitting_mat_locations'] = user.company_id.kitting_mat_locations.ids
        res['prod_ready_locations'] = user.company_id.prod_ready_locations.ids
        res['rm_product_categories'] = user.company_id.rm_product_categories.ids
        return res

    @api.one
    def set_default_mrp(self):
        self.env.user.company_id.write({
            'wip_task_code': self.wip_task_code.id,
            'mfg_task_code': self.mfg_task_code.id,
            'kitting_mat_locations': [(6,0, self.kitting_mat_locations.ids)],
            'prod_ready_locations': [(6,0, self.prod_ready_locations.ids)],
            'rm_product_categories': [(6,0, self.rm_product_categories.ids)],
        })

class res_company(models.Model):
    _inherit = 'res.company'

    # From WMS
    material_account_type_ids = fields.Many2many('account.account.type', 'company_global_material_type_rel', 'config_id', 'account_type_id', string="Material Account Types")
    interim_receiving = fields.Many2one('account.routing.subrouting', string="Interim Receiving Task Code")
    interim_shipping = fields.Many2one('account.routing.subrouting', string="Interim Shipping Task Code")
    attrition = fields.Many2one('account.routing.subrouting', string="Attrition Task Code", )
    stock_journal = fields.Many2one('account.journal', string='Stock Journal')
    pnl_mat_debit = fields.Many2one('account.account', "P&L Material Debit Account", domain="[('type','!=','view')]")
    pnl_mat_credit = fields.Many2one('account.account', "P&L Material Credit Account", domain="[('type','!=','view')]")
    pnl_labor_debit = fields.Many2one('account.account', "P&L Labor Debit Account", domain="[('type','!=','view')]")
    pnl_labor_credit = fields.Many2one('account.account', "P&L Labor Credit Account", domain="[('type','!=','view')]")
    pnl_mfg_oh = fields.Many2one('account.account', "P&L MFG Overhead Account", domain="[('type','!=','view')]")
    mfg_oh_mat_writeoff = fields.Many2one('account.account', "MFG Material Write-off Account", domain="[('type','!=','view')]")
    mfg_oh_labor_writeoff = fields.Many2one('account.account', "MFG Labor Write-off Account", domain="[('type','!=','view')]")

    # From MRP
    wip_task_code = fields.Many2one('account.routing.subrouting', string="Inventory/WIP Task Code")
    expense_wip_task_code = fields.Many2one('account.routing.subrouting', string="Expense/WIP Task Code")
    mfg_task_code = fields.Many2one('account.routing.subrouting', string="MFG Process Task Code")
    mfg_location = fields.Many2one('stock.location', string="Default Mfg Location", domain="[('usage','=','internal')]")
    kitting_mat_locations = fields.Many2many('stock.location', 'company_mrp_rm_loc', 'company_id', 'location_id', string="Raw Materials Kitting Locations", domain="[('usage','=','internal')]")
    prod_ready_locations = fields.Many2many('stock.location', 'company_mrp_prod_loc', 'company_id', 'location_id', string="Production Accessible Locations", domain="[('usage','=','internal')]")
    rm_product_categories = fields.Many2many('product.category', 'company_mrp_rm_prod_categ', 'company_id', 'category_id', string="Raw Materials Product Categories")



