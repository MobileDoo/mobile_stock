"""Receipts, deliveries and internal transfers on mobile (stock.picking).

Lists and buttons go through the generic record service; the scanning screen
uses `mobile.stock.service` (`/stock/picking/*`). Validating runs Odoo's own
`button_validate`, so the backorder / immediate transfer wizards of the web
open in the app too.
"""
from odoo import api, models

OPEN_STATES = ('confirmed', 'waiting', 'assigned')
SCOPE_CODES = {'receipts': 'incoming', 'deliveries': 'outgoing', 'internal': 'internal'}
# Printing, returns, scrap, unlock... stay on the web client.
MOBILE_BUTTONS = {'object:button_validate', 'object:action_assign', 'object:action_confirm', 'object:do_unreserve'}


class MobilePickingService(models.AbstractModel):
    _name = 'mobile.picking.service'
    _inherit = 'mobile.record.service'
    _description = 'Mobile Transfer Service'

    _mobile_model = 'stock.picking'
    _mobile_feature = 'stock'
    _mobile_create_capability = None
    # `<scope>_ready`: only the transfers that can be processed now (the ones waiting for stock are noise at the dock).
    _mobile_scope_capabilities = dict.fromkeys(
        [*SCOPE_CODES, *(f'{scope}_ready' for scope in SCOPE_CODES)], 'view')
    _mobile_core_field_names = [
        'partner_id', 'picking_type_id', 'location_id', 'location_dest_id', 'scheduled_date', 'origin', 'state',
    ]
    _mobile_list_field_names = ['name', 'partner_id', 'scheduled_date', 'origin', 'state', 'picking_type_id']
    _mobile_line_field = 'move_ids_without_package'
    _mobile_line_field_names = ['product_id', 'product_uom_qty', 'quantity', 'uom_id']

    @api.model
    def _mobile_domain(self, scope, params):
        if scope in SCOPE_CODES:
            return [('picking_type_code', '=', SCOPE_CODES[scope]), ('state', 'in', OPEN_STATES)]
        if scope.endswith('_ready') and scope[:-len('_ready')] in SCOPE_CODES:
            return [('picking_type_code', '=', SCOPE_CODES[scope[:-len('_ready')]]), ('state', '=', 'assigned')]
        return super()._mobile_domain(scope, params)

    @api.model
    def _mobile_search_domain(self, query):
        return ['|', '|', '|', ('name', 'ilike', query), ('partner_id', 'ilike', query), ('origin', 'ilike', query),
                ('product_id', 'ilike', query)]

    @api.model
    def _mobile_order(self, scope):
        return 'scheduled_date, id'

    @api.model
    def _mobile_buttons(self, record, buttons):
        return [b for b in super()._mobile_buttons(record, buttons) if b['key'] in MOBILE_BUTTONS]
