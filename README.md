# Mobile Inventory (`mobile_stock`)

Barcode scanning in the MobileDoo app: product lookup, receipts/deliveries, inventory counts.

Odoo addon for [MobileDoo](https://github.com/MobileDoo), the mobile app for Odoo. This branch (`17.0`) is for **Odoo 17**; every supported Odoo version has its own branch with the same addon name.

## Installation

Requires [`mobile_connector`](https://github.com/MobileDoo/mobile_connector) (same branch) and the Odoo module(s) `stock`.

Add this repository to `addons_path` (the addon is the `mobile_stock/` folder at the root) and install `mobile_stock` from *Apps*, or:

```bash
odoo -d <database> -i mobile_stock --stop-after-init
```

The addon installs itself automatically once its dependencies are installed (`auto_install`).

## License

LGPL-3 - see [LICENSE](LICENSE).
