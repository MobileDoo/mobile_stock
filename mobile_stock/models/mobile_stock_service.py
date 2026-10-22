"""Barcode work of warehouse staff: look up a product, scan a transfer, count stock.

Everything runs with the user's own rights (stock user / administrator), with
Odoo's own methods: setting a move's quantity, `button_validate`, quants in
inventory mode and `action_apply_inventory`, so the web and the app agree.
Products tracked by lot / serial number: the lot (or serial) is scanned or chosen
per line, quantities go to one move line per lot. Receipts may name new lots; with
OCA `stock_picking_auto_create_lot` the lots are created by Odoo on validation.
"""
import hashlib
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .mobile_picking_service import OPEN_STATES, SCOPE_CODES


class MobileStockService(models.AbstractModel):
    _name = 'mobile.stock.service'
    _description = 'Mobile Inventory Service'

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @api.model
    def _ref(self, record):
        return [record.id, record.display_name] if record else False

    @api.model
    def _default_location(self):
        warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        return warehouse.lot_stock_id

    @api.model
    def _product_ref(self, product):
        return {
            'id': product.id,
            'name': product.display_name,
            'default_code': product.default_code or False,
            'barcode': product.barcode or False,
            'uom': product.uom_id.name,
            'tracking': product.tracking or 'none',
        }

    @api.model
    def _find(self, code):
        """What a scanned code is: product (barcode, packaging, internal reference), transfer or location."""
        code = (code or '').strip()
        if not code:
            raise UserError(_('Nothing was scanned.'))
        Product = self.env['product.product']
        product = Product.search([('barcode', '=', code)], limit=1)
        if product:
            return 'product', product, 1.0
        # Odoo 19: packagings are units of measure with their own barcode (product.uom).
        packaging = self.env['product.uom'].search([('barcode', '=', code)], limit=1)
        if packaging:
            product = packaging.product_id
            return 'product', product, packaging.uom_id._compute_quantity(1.0, product.uom_id) or 1.0
        product = Product.search([('default_code', '=', code)], limit=1)
        if product:
            return 'product', product, 1.0
        lot = self.env['stock.lot'].search([('name', '=', code)], limit=1)
        if lot:
            return 'lot', lot, 1.0
        picking = self.env['stock.picking'].search([('name', '=', code)], limit=1)
        if picking:
            return 'picking', picking, 0.0
        location = self.env['stock.location'].search(
            ['|', ('barcode', '=', code), ('complete_name', '=', code), ('usage', '=', 'internal')], limit=1)
        if location:
            return 'location', location, 0.0
        return 'none', None, 0.0

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    @api.model
    def _stock_of(self, product, location=None):
        domain = [('product_id', '=', product.id), ('location_id.usage', '=', 'internal')]
        if location:
            domain.append(('location_id', 'child_of', location.id))
        quants = self.env['stock.quant'].search(domain, order='location_id')
        by_location = {}
        for quant in quants:
            row = by_location.setdefault(quant.location_id.id, {
                'location': self._ref(quant.location_id), 'quantity': 0.0, 'reserved': 0.0})
            row['quantity'] += quant.quantity
            row['reserved'] += quant.reserved_quantity
        rows = list(by_location.values())
        lots = {}
        for quant in quants.filtered('lot_id'):
            row = lots.setdefault((quant.lot_id.id, quant.location_id.id), {
                'lot': self._ref(quant.lot_id), 'location': self._ref(quant.location_id), 'quantity': 0.0})
            row['quantity'] += quant.quantity
        return {
            'quants': rows,
            'lots': [row for row in lots.values() if row['quantity']],
            'on_hand': sum(r['quantity'] for r in rows),
            'available': sum(r['quantity'] - r['reserved'] for r in rows),
            'incoming': product.incoming_qty,
            'outgoing': product.outgoing_qty,
        }

    @api.model
    def _lookup(self, code):
        kind, record, _qty = self._find(code)
        if kind == 'product':
            return {'type': 'product', 'product': dict(self._product_ref(record), **self._stock_of(record)), 'lot': False}
        if kind == 'lot':
            product = record.product_id
            return {'type': 'product', 'product': dict(self._product_ref(product), **self._stock_of(product)),
                    'lot': self._ref(record)}
        if kind == 'picking':
            return {'type': 'picking', 'picking': {'id': record.id, 'name': record.name, 'state': record.state}}
        if kind == 'location':
            return {'type': 'location', 'location': self._ref(record)}
        return {'type': 'none', 'code': code}

    # ------------------------------------------------------------------
    # Summary (home of the Inventory tab)
    # ------------------------------------------------------------------

    @api.model
    def _summary(self):
        Picking = self.env['stock.picking']
        counts = {scope: Picking.search_count([('picking_type_code', '=', code), ('state', 'in', OPEN_STATES)])
                  for scope, code in SCOPE_CODES.items()}
        ready = {scope: Picking.search_count([('picking_type_code', '=', code), ('state', '=', 'assigned')])
                 for scope, code in SCOPE_CODES.items()}
        counted = self.env['stock.quant'].search_count([('inventory_quantity_set', '=', True), ('user_id', '=', self.env.uid)])
        return {
            'pickings': counts,
            'ready': ready,
            'counted': counted,
            'location': self._ref(self._default_location()),
            'version': self._summary_version(),
        }

    @api.model
    def _summary_version(self):
        api_ = self.env['mobile.api']
        parts = [api_._mobile_domain_version('stock.picking', [('picking_type_code', '=', code), ('state', 'in', OPEN_STATES)])
                 for code in SCOPE_CODES.values()]
        return hashlib.sha1(json.dumps(parts).encode()).hexdigest()[:16]

    @api.model
    def _locations(self):
        locations = self.env['stock.location'].search([('usage', '=', 'internal')], order='complete_name', limit=200)
        return [{'id': l.id, 'name': l.complete_name, 'barcode': l.barcode or False} for l in locations]

    # ------------------------------------------------------------------
    # Transfers
    # ------------------------------------------------------------------

    @api.model
    def _get_picking(self, picking_id):
        picking = self.env['stock.picking'].browse(int(picking_id)).exists()
        if not picking:
            raise UserError(_('This transfer does not exist anymore.'))
        picking.check_access('read')
        return picking

    @api.model
    def _picking_data(self, picking, scanned_move=None):
        moves = picking.move_ids.filtered(lambda m: m.state != 'cancel')
        lines = []
        for move in moves.sorted(lambda m: (m.sequence, m.id)):
            tracked = move.product_id.tracking
            lines.append({
                # Lots counted on the phone; before that, the lots Odoo reserved (a suggestion).
                'lots': [{'name': ml.lot_id.name or ml.lot_name, 'quantity': ml.quantity,
                          'location': self._ref(ml.location_id)}
                         for ml in move.move_line_ids if move.picked and (ml.lot_id or ml.lot_name)] if tracked else [],
                'suggested_lots': [{'name': ml.lot_id.name, 'quantity': ml.quantity, 'location': self._ref(ml.location_id)}
                                   for ml in move.move_line_ids if not move.picked and ml.lot_id] if tracked else [],
                'lot_optional': self._lot_optional(move),
                'move_id': move.id,
                'product': self._product_ref(move.product_id),
                'uom': move.uom_id.name,
                'demand': move.product_uom_qty,
                # Counted on the phone: Odoo pre-fills `quantity` with the reservation, `picked` says it was checked.
                'quantity': move.quantity if move.picked else 0.0,
                'reserved': move.quantity,
                'picked': move.picked,
            })
        editable = picking.state not in ('done', 'cancel', 'draft')
        return {
            'id': picking.id,
            'name': picking.name,
            'state': picking.state,
            'state_label': dict(picking._fields['state']._description_selection(self.env)).get(picking.state),
            'type': picking.picking_type_code,
            'picking_type': self._ref(picking.picking_type_id),
            'partner': self._ref(picking.partner_id),
            'origin': picking.origin or False,
            'scheduled_date': fields.Datetime.to_string(picking.scheduled_date) if picking.scheduled_date else False,
            'location': self._ref(picking.location_id),
            'location_dest': self._ref(picking.location_dest_id),
            'note': picking.note and str(picking.note) or False,
            'lines': lines,
            # Receipts may name lots that do not exist yet (they are created on validation).
            'new_lots': bool(picking.picking_type_id.use_create_lots),
            'editable': editable,
            'scanned_move_id': scanned_move.id if scanned_move else False,
            'version': self.env['mobile.api']._mobile_record_versions('stock.picking', picking.ids).get(picking.id),
        }

    @api.model
    def _set_move_quantity(self, move, quantity):
        if move.picking_id.state in ('done', 'cancel', 'draft'):
            raise UserError(_('This transfer cannot be changed anymore.'))
        if move.product_id.tracking and not self._lot_optional(move):
            raise UserError(_('%s is tracked by lot / serial number: scan or choose the lot.',
                              move.product_id.display_name))
        if quantity < 0:
            raise UserError(_('The quantity cannot be negative.'))
        # Quantity first (it may reserve / unreserve move lines), then mark the line as checked.
        move.quantity = quantity
        move.picked = not move.uom_id.is_zero(quantity)
        self._sync_picked_quantity(move)

    @api.model
    def _sync_picked_quantity(self, move):
        """OCA stock_barcodes keeps its own `qty_picked` on the lines and validates with it: mirror what the phone counted."""
        lines = move.move_line_ids
        if 'qty_picked' in lines._fields:
            for line in lines:
                line.qty_picked = line.quantity if line.picked else 0.0

    @api.model
    def _lot_optional(self, move):
        """Receipt of a product whose lots Odoo creates by itself (OCA stock_picking_auto_create_lot)."""
        picking_type = move.picking_id.picking_type_id
        product = move.product_id
        return bool(move.product_id.tracking and picking_type.use_create_lots
                    and picking_type._fields.get('auto_create_lot') and picking_type.auto_create_lot
                    and product._fields.get('auto_create_lot') and product.auto_create_lot)

    @api.model
    def _lot_of(self, product, name):
        return self.env['stock.lot'].search([('product_id', '=', product.id), ('name', '=', name),
                                             ('company_id', 'in', [self.env.company.id, False])], limit=1)

    @api.model
    def _lot_lines(self, move, lot, name):
        return move.move_line_ids.filtered(lambda ml: ml.lot_id == lot if lot else ml.lot_name == name)

    @api.model
    def _set_lot_quantity(self, move, name, quantity):
        """Quantity of one lot / serial on a line (0 removes it). The first lot entered replaces Odoo's reservation."""
        picking = move.picking_id
        product = move.product_id
        if picking.state in ('done', 'cancel', 'draft'):
            raise UserError(_('This transfer cannot be changed anymore.'))
        if not product.tracking:
            raise UserError(_('%s is not tracked by lot / serial number.', product.display_name))
        name = (name or '').strip()
        if not name:
            raise UserError(_('Enter the lot / serial number.'))
        if quantity < 0:
            raise UserError(_('The quantity cannot be negative.'))
        uom = move.uom_id
        if product.tracking == 'serial' and uom.compare(quantity, 1.0) > 0:
            raise UserError(_('%s is tracked by serial number: one unit per serial number.', product.display_name))
        lot = self._lot_of(product, name)
        if not lot and not picking.picking_type_id.use_create_lots:
            raise UserError(_('Lot %(lot)s of %(product)s is not in stock.', lot=name, product=product.display_name))
        if product.tracking == 'serial' and quantity:
            others = (picking.move_ids.move_line_ids - self._lot_lines(move, lot, name)).filtered(
                lambda ml: ml.product_id == product and ml.move_id.picked and (ml.lot_id == lot if lot else ml.lot_name == name))
            if others:
                raise UserError(_('Serial number %s is already on this transfer.', name))
        if not move.picked:
            # From now on the phone says which lots: Odoo's suggested reservation is released.
            move.move_line_ids.unlink()
        lines = self._lot_lines(move, lot, name)
        if uom.is_zero(quantity):
            lines.unlink()
        elif lines:
            lines[1:].unlink()
            lines[0].write({'quantity': quantity, 'picked': True})
        else:
            location = move.location_id
            if lot and picking.picking_type_id.code != 'incoming':
                # Take it where the lot is (a shelf under the transfer's source location).
                quant = self.env['stock.quant'].search([
                    ('product_id', '=', product.id), ('lot_id', '=', lot.id), ('quantity', '>', 0),
                    ('location_id', 'child_of', move.location_id.id)], order='quantity desc', limit=1)
                location = quant.location_id or location
            values = {
                'move_id': move.id, 'picking_id': picking.id, 'product_id': product.id,
                'uom_id': move.uom_id.id, 'location_id': location.id,
                'location_dest_id': move.location_dest_id.id, 'quantity': quantity, 'picked': True,
            }
            values.update({'lot_id': lot.id} if lot else {'lot_name': name})
            self.env['stock.move.line'].create(values)
        move.picked = bool(move.move_line_ids)
        self._sync_picked_quantity(move)

    @api.model
    def _set_lot(self, picking_id, move_id, name, quantity):
        picking = self._get_picking(picking_id)
        move = picking.move_ids.filtered(lambda m: m.id == int(move_id))
        if not move:
            raise UserError(_('This line is not on the transfer.'))
        self._set_lot_quantity(move, name, float(quantity))
        return self._picking_data(picking, move)

    @api.model
    def _lots(self, product_id, location_id=None):
        """Lots of a product in stock (under a location), most stock first: to choose one on the phone."""
        product = self.env['product.product'].browse(int(product_id)).exists()
        if not product:
            raise UserError(_('This product does not exist anymore.'))
        location = self.env['stock.location'].browse(int(location_id)).exists() if location_id else None
        domain = [('product_id', '=', product.id), ('lot_id', '!=', False), ('location_id.usage', '=', 'internal')]
        if location:
            domain.append(('location_id', 'child_of', location.id))
        lots = {}
        for quant in self.env['stock.quant'].search(domain):
            row = lots.setdefault(quant.lot_id.id, {'id': quant.lot_id.id, 'name': quant.lot_id.name, 'quantity': 0.0,
                                                    'available': 0.0})
            row['quantity'] += quant.quantity
            row['available'] += quant.quantity - quant.reserved_quantity
        return sorted((r for r in lots.values() if r['quantity'] > 0), key=lambda r: (-r['quantity'], r['name']))

    @api.model
    def _scan_picking(self, picking_id, code):
        picking = self._get_picking(picking_id)
        kind, product, qty = self._find(code)
        if kind == 'lot':
            return self._scan_lot(picking, product)
        if kind != 'product':
            raise UserError(_('%s is not a product.', code))
        moves = picking.move_ids.filtered(lambda m: m.product_id == product and m.state not in ('done', 'cancel'))
        if not moves:
            raise UserError(_('%s is not in %s.', product.display_name, picking.name))
        # The first line still missing quantities, else the last one (more than ordered: Odoo asks on validation).
        move = next((m for m in moves if m.uom_id.compare(self._counted(m), m.product_uom_qty) < 0), moves[-1])
        if product.tracking and not self._lot_optional(move):
            # Which lot? The app asks (scan the lot label, type it or pick one in stock).
            return dict(self._picking_data(picking, move), lot_needed_move_id=move.id)
        qty = product.uom_id._compute_quantity(qty, move.uom_id)
        self._set_move_quantity(move, self._counted(move) + qty)
        return self._picking_data(picking, move)

    @api.model
    def _scan_lot(self, picking, lot):
        """A lot / serial label scanned: one more unit of that lot on the line of its product."""
        product = lot.product_id
        moves = picking.move_ids.filtered(lambda m: m.product_id == product and m.state not in ('done', 'cancel'))
        if not moves:
            raise UserError(_('%s is not in %s.', product.display_name, picking.name))
        move = next((m for m in moves if m.uom_id.compare(self._counted(m), m.product_uom_qty) < 0), moves[-1])
        current = sum(self._lot_lines(move, lot, lot.name).mapped('quantity')) if move.picked else 0.0
        if product.tracking == 'serial' and current:
            raise UserError(_('Serial number %s is already on this transfer.', lot.name))
        self._set_lot_quantity(move, lot.name, current + 1.0)
        return self._picking_data(picking, move)

    @api.model
    def _counted(self, move):
        return move.quantity if move.picked else 0.0

    @api.model
    def _set_line(self, picking_id, move_id, quantity):
        picking = self._get_picking(picking_id)
        move = picking.move_ids.filtered(lambda m: m.id == int(move_id))
        if not move:
            raise UserError(_('This line is not on the transfer.'))
        self._set_move_quantity(move, float(quantity))
        return self._picking_data(picking, move)

    # ------------------------------------------------------------------
    # Inventory count
    # ------------------------------------------------------------------

    @api.model
    def _count(self, product_id, location_id, quantity, apply=False, lot=None):
        product = self.env['product.product'].browse(int(product_id)).exists()
        location = self.env['stock.location'].browse(int(location_id)).exists() if location_id else self._default_location()
        if not product or not location or location.usage != 'internal':
            raise UserError(_('Choose a product and a stock location.'))
        if not product.is_storable:  # Odoo 18: storable = goods with "Track Inventory"
            raise UserError(_('%s is not a storable product: its stock is not counted.', product.display_name))
        if quantity < 0:
            raise UserError(_('The quantity cannot be negative.'))
        values = {'product_id': product.id, 'location_id': location.id, 'inventory_quantity': quantity}
        if product.tracking:
            name = (lot or '').strip()
            if not name:
                raise UserError(_('%s is tracked by lot / serial number: scan or enter the lot.', product.display_name))
            if product.tracking == 'serial' and quantity > 1:
                raise UserError(_('%s is tracked by serial number: one unit per serial number.', product.display_name))
            # A lot found on the shelf but unknown to Odoo is created, as in the web's count.
            values['lot_id'] = (self._lot_of(product, name) or self.env['stock.lot'].create(
                {'name': name, 'product_id': product.id, 'company_id': self.env.company.id})).id
        Quant = self.env['stock.quant'].with_context(inventory_mode=True)
        quant = Quant.create(values)
        quant.user_id = self.env.user
        result = {'applied': False, 'action': False}
        if apply:
            if not self.env.user.has_group('stock.group_stock_manager'):
                raise UserError(_('Only inventory administrators can apply counts.'))
            action = quant.action_apply_inventory()
            if isinstance(action, dict):
                # Conflict with a count made meanwhile, etc.: Odoo's own wizard, opened by the app.
                result['action'] = self.env['mobile.form.spec']._normalize_action(action, quant)
            else:
                result['applied'] = True
        result['product'] = dict(self._product_ref(product), **self._stock_of(product))
        result['location'] = self._ref(location)
        result['lot'] = self._ref(quant.lot_id)
        return result
