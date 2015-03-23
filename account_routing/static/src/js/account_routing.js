openerp.account_routing = function (instance) {
    var QWeb = instance.web.qweb;
    var _t = instance.web._t;
    module = instance.account_routing;

    // This was a failed attempt to make a custom widget for a task code picker. I really want to get back to this
    // some time, so I'm leaving the stubs in place.
    instance.web.form.FieldTaskCode = instance.web.form.AbstractField.extend(instance.web.form.ReinitializeFieldMixin, {
        template: 'FieldTaskCode',
        init: function(field_manager, node) {
            this._super.apply(this, arguments);
        },
        start: function() {
            this._super.apply(this, arguments);
        }
    });

    instance.web.form.widgets.add('taskcode', 'instance.web.form.FieldTaskCode');


};