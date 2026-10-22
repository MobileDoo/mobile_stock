from odoo import http
from odoo.http import request

from odoo.addons.mobile_connector.controllers.utils import MobileApiError, mobile_route, require_access


def _number(payload, key, required=True):
    value = payload.get(key)
    if value is None and not required:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise MobileApiError('bad_request', f'{key} must be a number')


def _id(payload, key):
    try:
        return int(payload[key])
    except (KeyError, TypeError, ValueError):
        raise MobileApiError('bad_request', f'{key} is required')


class MobileStockController(http.Controller):
    """Barcode work: lookup, transfers (lists/buttons: record service `picking`), inventory counts."""

    @mobile_route('/mobile/api/v1/stock/summary')
    def summary(self, payload):
        require_access('stock', 'view')
        return request.env['mobile.stock.service']._summary()

    @mobile_route('/mobile/api/v1/stock/lookup')
    def lookup(self, payload):
        require_access('stock', 'view')
        return request.env['mobile.stock.service']._lookup(payload.get('code'))

    @mobile_route('/mobile/api/v1/stock/locations')
    def locations(self, payload):
        require_access('stock', 'view')
        return request.env['mobile.stock.service']._locations()

    @mobile_route('/mobile/api/v1/stock/picking/get')
    def picking_get(self, payload):
        require_access('stock', 'view')
        service = request.env['mobile.stock.service']
        return service._picking_data(service._get_picking(_id(payload, 'id')))

    @mobile_route('/mobile/api/v1/stock/picking/scan')
    def picking_scan(self, payload):
        require_access('stock', 'view')
        return request.env['mobile.stock.service']._scan_picking(_id(payload, 'id'), payload.get('code'))

    @mobile_route('/mobile/api/v1/stock/picking/set_quantity')
    def picking_set_quantity(self, payload):
        require_access('stock', 'view')
        return request.env['mobile.stock.service']._set_line(
            _id(payload, 'id'), _id(payload, 'move_id'), _number(payload, 'quantity'))

    @mobile_route('/mobile/api/v1/stock/picking/set_lot')
    def picking_set_lot(self, payload):
        require_access('stock', 'view')
        return request.env['mobile.stock.service']._set_lot(
            _id(payload, 'id'), _id(payload, 'move_id'), payload.get('lot'), _number(payload, 'quantity'))

    @mobile_route('/mobile/api/v1/stock/lots')
    def lots(self, payload):
        require_access('stock', 'view')
        return request.env['mobile.stock.service']._lots(_id(payload, 'product_id'), payload.get('location_id'))

    @mobile_route('/mobile/api/v1/stock/count')
    def count(self, payload):
        require_access('stock', 'count')
        return request.env['mobile.stock.service']._count(
            _id(payload, 'product_id'), payload.get('location_id'), _number(payload, 'quantity'),
            apply=bool(payload.get('apply')), lot=payload.get('lot'))
