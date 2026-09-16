# Test fixtures

`medicines_synthetic.csv` is **synthetic test data**. Every product name starts
with `SYNTHETIC`, manufacturers are "Synthetic Test Pharma", and prices are
invented to exercise matching/pricing edge cases (unit conversion, release
type, dosage form, zero pack size, invalid rows, duplicate ids). It must never
be imported into a real database. Real reference data is imported only from
the verified public dataset via `scripts/import_medicines.py`.
