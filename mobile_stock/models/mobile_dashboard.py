from datetime import timedelta

from odoo import _, api, fields, models


class MobileDashboardService(models.AbstractModel):
    _inherit = 'mobile.dashboard.service'

    @api.model
    def _card_defs(self):
        return super()._card_defs() + [
            {'key': 'stock_late_deliveries', 'section': 'stock', 'feature': 'stock', 'capability': 'apply',
             'build': '_card_stock_late_deliveries'},
            {'key': 'stock_receipts_today', 'section': 'stock', 'feature': 'stock', 'capability': 'apply',
             'build': '_card_stock_receipts_today'},
        ]

    @api.model
    def _card_stock_late_deliveries(self):
        domain = [('picking_type_code', '=', 'outgoing'), ('state', 'in', ('confirmed', 'waiting', 'assigned')),
                  ('scheduled_date', '<', fields.Datetime.now())]
        return self._count_card('stock.picking', domain, _('Late deliveries'), 'truck-delivery-outline', 'amber',
                                tile='stock_deliveries', tone_if_any='bad')

    @api.model
    def _card_stock_receipts_today(self):
        today = self._today()
        domain = [('picking_type_code', '=', 'incoming'), ('state', 'in', ('confirmed', 'waiting', 'assigned')),
                  ('scheduled_date', '<', self._local_day_start_utc(today + timedelta(days=1)))]
        return self._count_card('stock.picking', domain, _('Receipts due'), 'package-down', 'cyan',
                                tile='stock_receipts')
