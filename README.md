# Cost of Goods Sold Calculator

![coverage](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2FAiden-Farmer%2Fcogs_calc%2Fbadges%2Fcoverage-badge.json)

Computes weighted-average inventory cost (AVCO) and inventory asset valuation from Excel exports (inventory on-hand + purchase/landed-cost history), and writes the result to `outfile.xlsx`.
Pretty specific for a transitory period from excel based inventory tracking to Sellercloud adoption at the company I work for, but AbstractReader class should be extensible for pretty much any data format. 
## Usage
Put inventory and Purchase files in cogs_calc/private/ folder, or point program at correct location with --purchase-file [-p] and --inventory-file [-i] flags.
```sh
uv run main.py
```

Optional flags: `--inventory-sheet-name`, `--purchases-sheet-name` (worksheet names within those files), and `--kit-upload <file>` to load a Sellercloud kit-component export before the calculation, so kit purchases/inventory get split across their components.

Rows that fail to parse (bad types, missing SKU, etc.) are skipped and reported at the end rather than aborting the run.

## Layout

- `main.py` — CLI entry point
- `src/adapters.py` — I/O adapters (Excel readers, output workbook writer)
- `src/data/` — domain model (`InventoryRow`, `LandedCostRow`) and the generic reader base
- `src/inventory_kits/` — kit-component export handling
- `src/transfers/` — sku to sku transfer record handler — Currently working on this.

## Development

```sh
uv run pytest --cov=main --cov=src --cov-report=term-missing
```
