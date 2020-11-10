# This file is part of the CERN Indico plugins.
# Copyright (C) 2014 - 2020 CERN
#
# The CERN Indico plugins are free software; you can redistribute
# them and/or modify them under the terms of the MIT License; see
# the LICENSE file for more details.

from dateutil.relativedelta import relativedelta
from flask import jsonify, session
from webargs import fields, validate
from webargs.flaskparser import use_kwargs

from indico.modules.rb.controllers import RHRoomBookingBase
from indico.util.date_time import format_datetime
from indico.util.spreadsheets import send_csv
from indico.web.rh import RHProtected
from indico.web.views import WPNewBase

from indico_burotel import _
from indico_burotel.util import calculate_monthly_stats


def get_month_dates(start_month, end_month):
    start_dt = start_month.replace(day=1, hour=0, minute=0)
    end_dt = end_month.replace(hour=23, minute=59) + relativedelta(months=1, days=-1)
    return start_dt, end_dt


class WPBurotelBase(WPNewBase):
    template_prefix = 'rb/'
    title = _('Burotel')
    bundles = ('common.js', 'common.css', 'react.js', 'react.css', 'semantic-ui.js', 'semantic-ui.css')


class RHLanding(RHRoomBookingBase):
    def _process(self):
        return WPBurotelBase.display('room_booking.html')


class RHUserExperiment(RHProtected):
    def _process_GET(self):
        from indico_burotel.plugin import BurotelPlugin
        return jsonify(value=BurotelPlugin.user_settings.get(session.user, 'default_experiment'))

    @use_kwargs({
        'value': fields.String(validate=validate.OneOf({'ATLAS', 'CMS', 'ALICE', 'LHCb'}), allow_none=True)
    })
    def _process_POST(self, value):
        from indico_burotel.plugin import BurotelPlugin
        BurotelPlugin.user_settings.set(session.user, 'default_experiment', value)


class RHBurotelStats(RHProtected):
    @use_kwargs({
        'start_month': fields.DateTime("%Y-%m"),
        'end_month': fields.DateTime("%Y-%m")
    })
    def process(self, start_month, end_month):
        start_dt, end_dt = get_month_dates(start_month, end_month)
        result, months = calculate_monthly_stats(start_dt, end_dt)
        # number of days within the boundary dates (inclusive)
        num_days = ((end_dt - start_dt).days + 1)

        return jsonify(
            data=result,
            num_days=num_days,
            months=[{
                'name': format_datetime(m, "MMMM YYYY", locale=session.lang),
                'id': format_datetime(m, "YYYY-M"),
                'num_days': ((m + relativedelta(months=1, days=-1)) - m).days + 1
            } for m in months]
        )


class RHBurotelStatsCSV(RHProtected):
    @use_kwargs({
        'start_month': fields.DateTime('%Y-%m'),
        'end_month': fields.DateTime('%Y-%m')
    })
    def process(self, start_month, end_month):
        start_dt, end_dt = get_month_dates(start_month, end_month)
        result, months = calculate_monthly_stats(start_dt, end_dt)
        # number of days within the boundary dates (inclusive)
        num_days = ((end_dt - start_dt).days + 1)

        headers = ['Building', 'Experiment', 'Number of desks']
        for m in months:
            headers += [m.strftime('%b %Y'), m.strftime('%b %Y (%%)')]
        headers.append('Total')
        headers.append('Total (%)')

        rows = []
        for building, experiments in result:
            for experiment, row_data in experiments:
                row = {
                    'Building': building,
                    'Experiment': experiment,
                    'Number of desks': row_data['desk_count']
                }
                for i, m in enumerate(row_data['months']):
                    month_dt = months[i]
                    month_duration = ((months[i] + relativedelta(months=1, days=-1)) - months[i]).days + 1
                    percent = float(m) / (row_data['desk_count'] * month_duration) * 100
                    row[month_dt.strftime('%b %Y')] = m
                    row[month_dt.strftime('%b %Y (%%)')] = f'{percent:.2f}%'
                row['Total'] = row_data['bookings']
                percent = float(row_data['bookings']) / (row_data['desk_count'] * num_days) * 100
                row['Total (%)'] = f'{percent:.2f}%'
                rows.append(row)
        return send_csv('burotel_stats.csv', headers, rows)
