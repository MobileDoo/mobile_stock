# Mobile Inventory

![Odoo 18.0](https://img.shields.io/badge/Odoo-18.0-714B67) ![License LGPL-3](https://img.shields.io/badge/license-LGPL--3-blue) ![Version 18.0.1.0.0](https://img.shields.io/badge/version-18.0.1.0.0-informational)

> Barcode scanning in the MobileDoo app: product lookup, receipts/deliveries, inventory counts.

Odoo 18 addon of [MobileDoo](https://github.com/MobileDoo) (`mobile_stock`).

## Overview

Warehouse work on a phone: scan to look up a product, receive and deliver against the real transfers, and count inventory, with lot
and serial-number handling. The camera is the scanner; nothing is re-implemented beside Odoo, so reservations, backorders and
validation rules are Odoo's own.

## Features

- **Barcode lookup** resolving a scanned code, in order: product barcode, packaging barcode (adds the packaging quantity),
  internal reference, lot / serial number, transfer reference, location barcode or name. Shows on-hand quantity by location and by lot.
- **Receipts, deliveries and internal transfers**: scan to add one unit (or one packaging) to the line of that product, set quantities
  by hand, then validate with Odoo's real `button_validate`. A shortfall opens Odoo's backorder wizard, as on the web.
- **Lots and serial numbers**: scanning a lot label adds one unit of *that* lot; each lot is a move line; serial numbers are one
  unit each and unique within the transfer. A lot name unknown to Odoo is accepted only when the operation type may create lots.
  Compatible with OCA `stock_picking_auto_create_lot` (lot optional, created at validation) and with OCA `stock_barcodes` (the
  scanned quantity is mirrored to its `qty_picked`).
- **Inventory count** written to `stock.quant` in inventory mode: the count waits in *Inventory > Physical Inventory* until applied;
  inventory administrators can apply it immediately.
- Summary of open and ready transfers per type, pending counts, and management cards `stock_late_deliveries` and
  `stock_receipts_today`.

## Requirements

| | |
|---|---|
| Odoo | 18.0 (Community or Enterprise) |
| Odoo modules | `stock` |
| MobileDoo addons | [`mobile_connector`](https://github.com/MobileDoo/mobile_connector/tree/18.0) (same branch) |
| Client | the [MobileDoo](https://github.com/MobileDoo) app for Android and iPhone |

This branch targets **Odoo 18** only; use the branch of your Odoo version.

## Installation

```bash
git clone --branch 18.0 https://github.com/MobileDoo/mobile_stock.git
git clone --branch 18.0 https://github.com/MobileDoo/mobile_connector.git
# add the cloned folders to addons_path in odoo.conf, then:
odoo -d <database> -i mobile_stock --stop-after-init
```

The addon is the `mobile_stock/` folder at the root of the repository, so the repository folder itself can go on `addons_path`.

`auto_install` is set: Odoo installs `mobile_stock` by itself as soon as all its dependencies are installed, so putting the folders on `addons_path` and updating the Apps list is enough.

To upgrade after pulling a newer version: `odoo -d <database> -u mobile_stock --stop-after-init`.

## How it works

| Endpoint | Request | Response |
|---|---|---|
| `/stock/summary` | `{}` | Open / ready transfers per type, pending counts, default location, `version` |
| `/stock/lookup` | `{"code"}` | `{"type": "product" | "picking" | "location" | "none", ...}` with stock by location |
| `/stock/locations` | `{}` | Internal locations `[{id, name, barcode}]` |
| `/stock/picking/get` | `{"id"}` | Transfer with lines (`demand`, counted `quantity`, `picked`) |
| `/stock/picking/scan` | `{"id", "code"}` | Transfer after adding one unit (or packaging quantity) |
| `/stock/picking/set_quantity` | `{"id", "move_id", "quantity"}` | Transfer after setting the quantity |
| `/stock/picking/set_lot` | `{"id", "move_id", "lot", "quantity"}` | Quantity of one lot / serial (`0` removes it) |
| `/stock/lots` | `{"product_id", "location_id"?}` | Lots in stock, most stock first |
| `/stock/count` | `{"product_id", "location_id"?, "quantity", "apply"?, "lot"?}` | `{applied, action, product, location, lot}` |

Transfer lists and buttons go through the record service `picking` (scopes `receipts`, `deliveries`, `internal`, domain on
`stock.picking`). Change keys: `stock.summary` and the watched `stock.picking` record.

If a tracked product is scanned by its product barcode, nothing is added and the transfer returns `lot_needed_move_id` so the app asks
for the lot. The first lot entered on the phone replaces the lots Odoo had reserved (`suggested_lots` held the previous suggestion).

### Capabilities

| Capability | Granted when |
|---|---|
| `view` | member of `stock.group_stock_user`: lookup, transfers |
| `count` | same group: save counts |
| `apply` | member of `stock.group_stock_manager`: apply a count immediately (also unlocks the management overview) |

## Security

No groups or ACLs of its own. Everything runs as the signed-in user, so stock rules, multi-company and warehouse restrictions of Odoo
apply to lookups, transfers and counts. Counts by non-managers only create inventory-mode quants awaiting approval.

## Extending

`mobile.picking.service` (list scopes and buttons of transfers) and `mobile.stock.service` (lookup, scan, counts) can be inherited to
change what a scan resolves to, add scopes, or hide buttons. The scan logic lives in small `_find`, `_scan_picking`, `_scan_lot`
methods so a customer module can add its own code type.

## Contributing

Issues and pull requests are welcome. Open pull requests against the branch of the Odoo version you are fixing (this one is `18.0`) and
keep the change inside the `mobile_stock/` folder.

These repositories are published from MobileDoo's development repository, which remains the source of truth. A merged pull request is
taken back there, and the branches of the other Odoo versions are updated by the maintainers, so a fix is usually welcome even if you can
only test it on one version. `README.md` and `LICENSE` are generated at each release; changes to them are not carried back.

## License

LGPL-3: see [LICENSE](LICENSE).
