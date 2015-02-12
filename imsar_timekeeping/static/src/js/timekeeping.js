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
            // make a hash of the tasks (routing_id + routing_subrouting_id) mapped to a list of entries for that task
            var task_objects;
            if (this.lines.length != 0) {
                task_objects = _(this.lines).chain().map(function(el) {
                    return el;
                }).groupBy(function(el) {
                    if ((!!el) && (el.constructor === Object)) {
                        return el.routing_subrouting_id[1] + ' (' + el.routing_id[1] + ')';
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
                grid.push({'task':key, 'days':sum_line, 'total':sum_line.total, 'style':'color:' + task_line[0].display_color});
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
        }
    });

    instance.web.form.custom_widgets.add('timekeeping_weekly_summary', 'instance.imsar_timekeeping.WeeklySummary');


    // custom time picker for timekeeping, copied from instance.web.DateTimeWidget
    instance.web.TimeWidget = instance.web.Widget.extend({
        template: "web.datepicker",
        jqueryui_object: 'timepicker',
        type_of_date: "time",

        events: {
            'change .oe_datepicker_master': 'change_datetime',
            'keypress .oe_datepicker_master': 'change_datetime'
        },
        init: function(parent) {
            this._super(parent);
            this.name = parent.name;
        },
        start: function() {
            var self = this;
            this.$input = this.$el.find('input.oe_datepicker_master');
            this.$input_picker = this.$el.find('input.oe_datepicker_container');
            $.timepicker.setDefaults({
                timeOnlyTitle: _t('Choose Time'),
                timeText: _t('Time'),
                hourText: _t('Hour'),
                minuteText: _t('Minute'),
                secondText: _t('Second'),
                currentText: _t('Now'),
                stepMinute: 15,
                timeFormat: 'hh:mm',
                closeText: _t('Done')
            });
            this.picker({
                onClose: this.on_picker_select,
                onSelect: this.on_picker_select
            });
            // Some clicks in the datepicker dialog are not stopped by the
            // datepicker and "bubble through", unexpectedly triggering the bus's
            // click event. Prevent that.
            this.picker('widget').click(function (e) { e.stopPropagation(); });

            this.$el.find('img.oe_datepicker_trigger').click(function() {
                if (self.get("effective_readonly") || self.picker('widget').is(':visible')) {
                    self.$input.focus();
                    return;
                }
                self.picker('setDate', self.get('value') ? instance.web.auto_str_to_date(self.get('value')) : new Date());
                self.$input_picker.show();
                self.picker('show');
                self.$input_picker.hide();
            });
            this.set_readonly(false);
            this.set({'value': false});
        },
        picker: function() {
            return $.fn[this.jqueryui_object].apply(this.$input_picker, arguments);
        },
        on_picker_select: function(text, instance_) {
            var date = this.picker('getDate');
            text = text + ":00";
            this.$input.val(text ? this.format_client(text) : '').change().focus();
        },
        set_value: function(value_) {
            this.set({'value': value_});
            this.$input.val(value_ ? this.format_client(value_) : '');
        },
        get_value: function() {
            return this.get('value');
        },
        set_value_from_ui_: function() {
            var value_ = this.$input.val() || false;
            this.set({'value': this.parse_client(value_)});
        },
        set_readonly: function(readonly) {
            this.readonly = readonly;
            this.$input.prop('readonly', this.readonly);
            this.$el.find('img.oe_datepicker_trigger').toggleClass('oe_input_icon_disabled', readonly);
        },
        is_valid_: function() {
            var value_ = this.$input.val();
            if (value_ === "") {
                return true;
            } else {
                try {
                    this.parse_client(value_);
                    return true;
                } catch(e) {
                    return false;
                }
            }
        },
        parse_client: function(v) {
            return instance.web.parse_value(v, {"widget": this.type_of_date});
        },
        format_client: function(v) {
            return instance.web.format_value(v, {"widget": this.type_of_date});
        },
        change_datetime: function(e) {
            if ((e.type !== "keypress" || e.which === 13) && this.is_valid_()) {
                this.set_value_from_ui_();
                this.trigger("datetime_changed");
            }
        },
        commit_value: function () {
            this.change_datetime();
        }
    });
    instance.web.form.FieldTime = instance.web.form.FieldDatetime.extend({
        build_widget: function() {
            return new instance.web.TimeWidget(this);
        }
    });
    instance.web.form.widgets.add('time', 'instance.web.form.FieldTime');

    function approval_check() {
        var self = this;
        var uid = openerp.session.uid;
        try {
            app_ids = new openerp.Model("hr.timekeeping.approval").call("ajax_approval_count", ['my_direct_approvals']).then(function(num){
                if(num > 0) {
                    $.titleAlert(num + " approvals waiting!", {interval:1000});
                }
            }, function(unused, e) {
                // no error popup if request is interrupted or fails for any reason
                e.preventDefault();
            });
        }
        catch (error) {}
    }

    if(openerp.web && openerp.web.UserMenu) {
        openerp.web.UserMenu.include({
            do_update: function(){
                approval_check();
                var tid = setInterval(approval_check, 90000);
                return this._super.apply(this, arguments);
            }
        });
    }
};