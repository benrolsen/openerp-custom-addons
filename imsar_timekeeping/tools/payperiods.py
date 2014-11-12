#!/usr/bin/python

from datetime import datetime, date, timedelta
from dateutil.relativedelta import *
from dateutil.rrule import *

epoch = datetime(2014, 1, 10)
DF = "%Y-%m-%d"

# 20 years is enough, right?
paydates = list(rrule(WEEKLY, count=520, byweekday=FR, interval=2, dtstart=epoch))

outfile = open('pay.period.csv', 'w+')
this_year = epoch.year
period_num = 1
outfile.write("start_date,end_date,pay_date,year,period_num\n")
for paydate in paydates:
    if paydate.year != this_year:
        this_year = paydate.year
        period_num = 1
    enddate = paydate - timedelta(days=6)
    startdate = enddate - timedelta(days=13)
    outfile.write("{},{},{},{},{}\n".format(startdate.strftime(DF),enddate.strftime(DF),paydate.strftime(DF),this_year,period_num))
    period_num += 1

outfile.close()
