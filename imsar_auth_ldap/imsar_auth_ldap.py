import ldap
import logging
_logger = logging.getLogger(__name__)

from openerp.osv import fields, osv
from openerp import SUPERUSER_ID


class imsar_auth_ldap(osv.Model):
    _inherit = "res.company.ldap"

    _columns = {
        'create_employee': fields.boolean('Create HR Employee',
            help="Automatically create HR Employee for new users authenticating via LDAP"),
        'ldap_ssl': fields.boolean('Use SSL',
            help="Connect over LDAPS, using SSL (default port 636)."),
    }
    _defaults = {
        'create_employee': True,
        'ldap_ssl': False,
    }

    def map_ldap_attributes(self, cr, uid, conf, login, ldap_entry):
        values = super(imsar_auth_ldap, self).map_ldap_attributes(cr, uid, conf, login, ldap_entry)
        values['telephoneNumber'] = ldap_entry[1].get('telephoneNumber',['',])[0] or ''
        values['description'] = ldap_entry[1].get('description',['',])[0] or ''
        values['email'] = ldap_entry[1].get('mail',['',])[0] or ''
        return values

    def get_ldap_dicts(self, cr, ids=None):
        if ids:
            id_clause = 'AND id IN (%s)'
            args = [tuple(ids)]
        else:
            id_clause = ''
            args = []
        cr.execute("""
            SELECT id, company, ldap_server, ldap_server_port, ldap_binddn,
                   ldap_password, ldap_filter, ldap_base, "user", create_user,
                   ldap_tls, ldap_ssl, create_employee
            FROM res_company_ldap
            WHERE ldap_server != '' """ + id_clause + """ ORDER BY sequence
        """, args)
        return cr.dictfetchall()

    # doesn't actually return employee id since it's not used anywhere
    # probably more accurately named create_employee_if_does_not_exist, but whatever
    def get_or_create_employee(self, cr, uid, conf, login, ldap_entry, user_id):
        user_values = self.map_ldap_attributes(cr, uid, conf, login, ldap_entry)
        empl_obj = self.pool.get('hr.employee')
        empl_list = empl_obj.search(cr, uid, [('user_id','=',user_id)])
        if not empl_list:
            values = dict()
            values['last_name'] = user_values['name'].split(' ', 1)[1]
            values['first_name'] = user_values['name'].split(' ', 1)[0]
            values['user_id'] = user_id
            values['notes'] = user_values['description']
            values['work_email'] = user_values['email']
            values['mobile_phone'] = user_values['telephoneNumber']
            empl_id = empl_obj.create(cr, SUPERUSER_ID, values)

    def get_or_create_user(self, cr, uid, conf, login, ldap_entry, context=None):
        user_id = super(imsar_auth_ldap, self).get_or_create_user(cr, uid, conf, login, ldap_entry, context)
        user = self.pool.get('res.users').browse(cr, uid, user_id)
        default_tz_res = self.pool.get('ir.config_parameter').search(cr, uid, [('key','=','user.default_tz')])
        default_tz_id = default_tz_res and default_tz_res[0]
        if default_tz_id and not user.tz:
            default_tz = self.pool.get('ir.config_parameter').browse(cr, uid, default_tz_id).value
            user.write({'tz': default_tz})
        if conf['create_employee']:
            self.get_or_create_employee(cr, uid, conf, login, ldap_entry, user_id)
        return user_id

    def connect(self, conf):
        """
        Connect to an LDAP server specified by an ldap
        configuration dictionary.

        :param dict conf: LDAP configuration
        :return: an LDAP object
        """

        protocol = 'ldap'
        if conf['ldap_ssl']:
            ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)
            protocol = 'ldaps'
        uri = '%s://%s:%d' % (protocol, conf['ldap_server'], conf['ldap_server_port'])

        connection = ldap.initialize(uri)
        if conf['ldap_tls']:
            connection.start_tls_s()
        return connection


class res_users(osv.Model):
    _name = 'res.users'
    _inherit = ['res.users']

    _defaults = {
        'display_groups_suggestions': False,
        'display_employees_suggestions': False,
    }

    def create(self, cr, uid, values, context=None):
        if context is None:
            ctx = {}
        else:
            ctx = context.copy()
        ctx.update({'no_reset_password': True})
        user_id = super(res_users, self).create(cr, uid, values, context=ctx)
        return user_id

class res_partner(osv.Model):
    _name = "res.partner"
    _inherit = ['res.partner']

    _defaults = {
        'notify_email': lambda *args: 'none'
    }
