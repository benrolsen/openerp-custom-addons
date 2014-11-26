openerp.imsar_ui = function (instance) {
    var QWeb = instance.web.qweb;
    var _t = instance.web._t;
    module = instance.imsar_ui;

    // For some reason this breaks the interface
    //instance.web.ListView = instance.web.ListView.extend({});

    // Whereas this works fine, but I can't get the interface to use it
    instance.web.ColorListView = instance.web.ListView.extend( /** @lends instance.web.ListView# */ {
        style_for: function (record) {
            //console.log("in my colorlist code");
            var len, style= '';
            return style += 'color: fuchsia;';
        }
    });
    instance.web.views.add('colorlist', 'instance.web.ColorListView');

    // I'm leaving these stubs here until I can figure out how to properly extend lists
    instance.web.ListView.List = instance.web.ListView.List.extend( {
        init: function (group, opts) {
            //console.log("in list init ");
            this._super(group, opts);
        },
        render: function() {
            //console.log("in list render " + this.options.selectable);
            this._super();
        }

    });
    instance.web.ListView.Groups = instance.web.ListView.Groups.extend( /** @lends instance.web.ListView.Groups# */ {
        init: function (view, options) {
            //console.log("in groups init ");
            this._super(view, options);
        }
    });

};