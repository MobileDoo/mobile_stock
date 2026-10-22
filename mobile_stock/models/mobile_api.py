from odoo import _, api, models


class MobileApi(models.AbstractModel):
    _inherit = 'mobile.api'

    @api.model
    def _mobile_features(self):
        return super()._mobile_features() + ['stock']

    @api.model
    def _mobile_record_services(self):
        return dict(super()._mobile_record_services(), picking='mobile.picking.service')

    @api.model
    def _mobile_access(self):
        access = super()._mobile_access()
        user = self.env.user
        if not user.has_group('stock.group_stock_user'):
            return access
        access['stock'] = {
            # Look up products, process receipts / deliveries / internal transfers.
            'view': True,
            # Count: the quantities wait in Inventory > Physical Inventory until applied.
            'count': True,
            # Apply counts right away (stock moves): inventory administrators, as on the web.
            'apply': user.has_group('stock.group_stock_manager'),
        }
        if access['stock']['apply']:
            access.setdefault('dashboard', {})['view'] = True  # the overview shows what they can manage
        return access

    @api.model
    def _mobile_list_versions(self, keys):
        versions = super()._mobile_list_versions(keys)
        if 'stock.summary' in keys and self._mobile_can('stock'):
            versions['stock.summary'] = self.env['mobile.stock.service']._summary_version()
        return versions

    @api.model
    def _mobile_home_tiles(self):
        return super()._mobile_home_tiles() + [
            {'key': 'stock_scan', 'label': _('Product lookup'), 'feature': 'stock', 'capability': 'view', 'sequence': 60},
            {'key': 'stock_receipts', 'label': _('Receipts'), 'feature': 'stock', 'capability': 'view', 'sequence': 61},
            {'key': 'stock_deliveries', 'label': _('Deliveries'), 'feature': 'stock', 'capability': 'view', 'sequence': 62},
            {'key': 'stock_count', 'label': _('Inventory count'), 'feature': 'stock', 'capability': 'count', 'sequence': 63},
        ]

    @api.model
    def _mobile_home_shortcuts(self):
        return super()._mobile_home_shortcuts() + [
            {'key': 'stock_scan', 'label': _('Scan a barcode'), 'feature': 'stock', 'capability': 'view'},
        ]

    @api.model
    def _mobile_home_tabs(self):
        return super()._mobile_home_tabs() + [
            {'key': 'stock', 'label': _('Inventory'), 'feature': 'stock', 'capability': 'view', 'sequence': 60},
        ]
