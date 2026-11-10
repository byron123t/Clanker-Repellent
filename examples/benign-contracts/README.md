# Authored benign task contracts

These are authored requests and companion contracts, not generated outputs.

```sh
repel generate examples/benign-contracts/clamp.txt --benign --contract examples/benign-contracts/clamp.contract.json
```

- `clamp`: python
- `distance`: sql
- `minimum`: llvm
- `catalog`: json
- `response`: http
- `binary-description`: binary-info
- `reference-table`: html

See [the contract guide](../../docs/task-contracts.md) for supported fields and limits. Public examples and document-shape checks do not prove complete correctness.

## Configuration and markup invoices

`invoice.txt` has matching `invoice.yaml.contract.json`, `invoice.toml.contract.json`,
`invoice.xml.contract.json`, `invoice.csv.contract.json`, and `invoice.ini.contract.json` files.
Each contract preserves two records' inputs and checks `total_cents = quantity * unit_cents`.
These are authored specifications, not generated outputs.

```sh
repel generate examples/benign-contracts/invoice.txt --benign --contract examples/benign-contracts/invoice.yaml.contract.json
```
