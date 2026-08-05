# Cost of Goods Sold Calculator

![coverage](https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2FAiden-Farmer%2Fcogs_calc%2Fbadges%2Fcoverage-badge.json)

Computes line item weighted-average inventory cost (AVCO) and total inventory asset valuation from Excel exports and writes the result to `outfile.xlsx`.

`outfile.xlsx` includes columns: ["sku", "

Pretty specific for a transitory period from excel based inventory tracking to Sellercloud adoption at the company I work for, but AbstractReader class should be extensible for pretty much any data format. 
## Usage
Put inventory and Purchase files in cogs_calc/private/ folder, or use `--inventory-file` and/or `--purchase-file` flags specified below.
```sh
uv run main.py
```

Optional flags: `--help`
                `--inventory-file [-i] <file>`, `--inventory-sheet-name <file>`
                `--purchase-file [-p] <file>`, `--purchases-sheet-name <file>` 
                `--kit-upload <file>` to load a Sellercloud kit-component export before the calculation, so kit purchases/inventory get split across their components.
                [In Development] `--inventory-transfer <file>` to load Sellercloud inventory transfer record to correctly allocate cost to skis purchased as different sku.

Rows that fail to parse (bad types, missing SKU, etc.) are skipped and reported at the end rather than aborting the run.

## Layout

- `main.py` — CLI entry point
- `src/adapters.py` — I/O adapters (Excel readers, output workbook writer)
- `src/data/` — domain model (`InventoryRow`, `LandedCostRow`) and the generic reader base
- `src/inventory_kits/` — kit-component export handling
- [In Developement] `src/transfers/` — sku to sku transfer record handler

## Development

```sh
uv run pytest --cov=main --cov=src --cov-report=term-missing
```
