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

    module.WeeklySummary = instance.web.form.FormWidget.extend({
        template: 'imsar_timekeeping.WeeklySummary',
        init: function(parent) {
            this._super.apply(this, arguments);
            this.field_manager.on("field_changed:line_ids", this, this.log_result);
            this.lines = [];
            this.accounts = [1,2,3];
        },
        start: function(){
            this.date_from = instance.web.str_to_date(this.field_manager.get_field_value("date_from"));
            this.date_to = instance.web.str_to_date(this.field_manager.get_field_value("date_to"));
            this.date_from_display = $.datepicker.formatDate('M dd, yy', this.date_from)
            this.date_to_display = $.datepicker.formatDate('M dd, yy', this.date_to);
            this.$('#testline_id').html("<p>From " + this.date_from_display + " to " + this.date_to_display + "</p>");
        },
        log_result: function() {
            console.log(this.field_manager.get_field_value("name"));
        }
    });

    instance.web.form.custom_widgets.add('timekeeping_weekly_summary', 'instance.imsar_timekeeping.WeeklySummary');

};