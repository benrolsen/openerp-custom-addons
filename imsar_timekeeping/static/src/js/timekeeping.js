openerp.imsar_timekeeping = function (instance) {
    var QWeb = instance.web.qweb;
    var _t = instance.web._t;
    module = instance.imsar_timekeeping;

    module.WeeklySummary = instance.web.form.FormWidget.extend(instance.web.form.ReinitializeWidgetMixin, {
        template: 'imsar_timekeeping.WeeklySummary',

        init: function(parent) {
            this._super.apply(this, arguments);
            this.res_o2m_drop = new instance.web.DropMisordered();
            this.dates = [];
            this.lines = [];
            this.grid = [];
            this.totals = {};
            this.total = 0;
            this.field_manager.on("field_changed:line_ids", this, this.line_ids_changed);
        },

        initialize_content: function() {
            // get the date_from and date_to and make a list of the range
            var dates = [];
            var totals = {};
            var total = 0;
            this.date_from = instance.web.str_to_date(this.field_manager.get_field_value("date_from"));
            this.date_to = instance.web.str_to_date(this.field_manager.get_field_value("date_to"));
            var start = this.date_from;
            var end = this.date_to;
            while (start <= end) {
                dates.push(start);
                totals[instance.web.date_to_str(start)] = 0;
                start = start.clone().addDays(1);
            }
            // make a hash of the tasks (routing_id + analytic) mapped to a list of entries for that task
            var task_objects;
            if (this.lines.length != 0) {
                task_objects = _(this.lines).chain().map(function(el) {
                    return el;
                }).groupBy(function(el) {
                    if ((!!el) && (el.constructor === Object)) {
                        return el.analytic_account_id[1] + ' (' + el.routing_id[1] + ')';
                    }
                }).value();
            }
            // fill out the grid, put in nice formatting
            var grid = [];
            _(task_objects).map(function(task_line, key) {
                sum_line = _(task_line).reduce(function(mem,d) {
                    mem[d.date] = (mem[d.date] || 0) + d.unit_amount;
                    mem['total'] = (mem['total'] || 0) + d.unit_amount;
                    totals[d.date] = (totals[d.date] || 0) + d.unit_amount;
                    return mem;
                }, {});
                total += sum_line.total;
                _(sum_line).map(function(day_total, index) {
                    sum_line[index] = instance.web.format_value(day_total, { type:"float_time" });
                });
                grid.push({'task':key, 'days':sum_line, 'total':sum_line.total});
            });
            _(totals).map(function(day_total, index) {
                totals[index] = instance.web.format_value(day_total, { type:"float_time" });
            });
            // wrap it up and display it
            this.dates = dates;
            this.grid = grid;
            this.totals = totals;
            this.total = instance.web.format_value(total, { type:"float_time" });
            this.$el.html(instance.web.qweb.render(this.template, {widget: this}));
        },

        line_ids_changed: function() {
            // good old javascript namespacing--need to make "this" a global for sub-functions
            var self = this;
            this.lines = this.field_manager.get_field_value("line_ids");
            this.res_o2m_drop.add(new instance.web.Model(this.view.model)
                .call("resolve_2many_commands", ["line_ids", this.lines, [], new instance.web.CompoundContext()]))
                .done(function(result) {
                    self.lines = result;
                    self.reinitialize();
            });
        },
    });


    instance.web.form.custom_widgets.add('timekeeping_weekly_summary', 'instance.imsar_timekeeping.WeeklySummary');

};