# cogs-calc

Computes weighted-average inventory cost (AVCO) and inventory asset valuation from Excel exports (inventory on-hand + purchase/landed-cost history), and writes the result to `outfile.xlsx`.

Landed cost purchases must be sorted by date, descending (handled automatically by the reader).

## Usage

```sh
uv run main.py -i private/inventory.xlsx -p "private/landed cost.xlsx"
```

Optional flags: `--inventory-sheet-name`, `--purchases-sheet-name` (worksheet names within those files), and `--kit-upload <file>` to load a Sellercloud kit-component export before the calculation, so kit purchases/inventory get split across their components.

Rows that fail to parse (bad types, missing SKU, etc.) are skipped and reported at the end rather than aborting the run.

## Layout

- `main.py` — CLI entry point
- `src/adapters.py` — I/O adapters (Excel readers, output workbook writer)
- `src/data/` — domain model (`InventoryRow`, `LandedCostRow`) and the generic reader base
- `src/inventory_kits/` — kit-component export handling

## Development

```sh
uv run pytest --cov=main --cov=src --cov-report=term-missing
```
