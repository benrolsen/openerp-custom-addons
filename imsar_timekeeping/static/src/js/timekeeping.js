openerp.imsar_timekeeping = function (instance) {
    var QWeb = instance.web.qweb;
    var _t = instance.web._t;
    module = instance.imsar_timekeeping;

    module.StopWatch = instance.web.Widget.extend({
        template: 'imsar_timekeeping.stopwatch',
        events: {
            'click .timekeeping_start button': 'watch_start',
            'click .timekeeping_stop button': 'watch_stop'
        },
        init: function () {
            this._super.apply(this, arguments);
            this._start = null;
            this._watch = null;
        },
        update_counter: function () {
            var h, m, s;
            var diff = new Date() - this._start;
            s = diff / 1000;
            m = Math.floor(s / 60);
            s -= 60*m;
            h = Math.floor(m / 60);
            m -= 60*h;
            this.$('.timekeeping_timer').text(_.str.sprintf("%02d:%02d:%02d", h, m, s));
        },
        watch_start: function () {
            console.log("Hit the start button");
            this.$el.addClass('timekeeping_started').removeClass('timekeeping_stopped');
            this._start = new Date();
            this.update_counter();
            this._watch = setInterval(this.proxy('update_counter'),100);
        },
        watch_stop: function () {
            console.log("Hit the stop button");
            clearInterval(this._watch);
            this.update_counter();
            this._start = this._watch = null;
            this.$el.removeClass('timekeeping_started').addClass('timekeeping_stopped');
        },
        destroy: function () {
            if (this._watch) {
                clearInterval(this._watch);
            }
            this._super();
        }
    });

    module.QuickTaskView = instance.web.form.FormWidget.extend({
        template: 'imsar_timekeeping.QuickTaskView',
        init: function(parent) {
            this._super.apply(this, arguments);
            this.field_manager.on("change:oe_timekeeping_input", this, this.log_result);
            this.parent_model = parent.dataset.model;
            this.parent_id = parent.dataset.ids[0];
        },
        start: function(){
            var model = new instance.web.Model("hr.timekeeping.line");
            var res = model.call('search', [[ ['user_id','=',instance.session.uid], ['sheet_id','=',this.parent_id] ]])
                .then(function(res_list) {
                    console.log(res_list);
                });
            //console.log($('.timekeeping_start').text());
            //console.log(context);
        },
        log_result: function(source, options) {
            console.log(source);
            console.log(options);
        }
    });

    instance.web.form.custom_widgets.add('timekeeping_quick_tasks', 'instance.imsar_timekeeping.QuickTaskView');

};