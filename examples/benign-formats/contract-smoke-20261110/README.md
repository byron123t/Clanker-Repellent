# Benign new-format contract examples

Both local models generated the same two-row invoice example in five formats with public task contracts. DeepSeek accepted and independently verified **5/5**; GLM accepted and independently verified **2/5**, with the other three rejected. One example per format/model is a smoke check, not a general model ranking or an estimate of contract-induced improvement. These ten runs are separate from the frozen 126-run breadth study.

All seven linked files are unchanged, explicitly benign generation artifacts. The inputs, contract files, settings, model identities, attempt outcomes and source checksums are in [results.json](results.json). These are static calculated reference records; they do not execute invoice logic.

| Format | DeepSeek | GLM |
| --- | --- | --- |
| yaml | [Verified example](deepseek/generated.yaml) | Rejected |
| toml | [Verified example](deepseek/generated.toml) | Rejected |
| xml | [Verified example](deepseek/generated.xml) | [Verified example](glm/generated.xml) |
| csv | [Verified example](deepseek/generated.csv) | Rejected |
| ini | [Verified example](deepseek/generated.ini) | [Verified example](glm/generated.ini) |

Generate a fresh example with the supplied contract (format is inferred):

```sh
repel generate examples/benign-contracts/invoice.txt --benign --contract examples/benign-contracts/invoice.csv.contract.json --endpoint http://127.0.0.1:18473/v1
```

The independent check parsed each accepted file and checked exact field names, order, types and values: A = 3 × 125 = 375; B = 2 × 240 = 480. GLM’s rejected terminal examples renamed YAML fields, nested TOML records incorrectly, or returned unrelated content instead of CSV. Rejections were retained and not regenerated.
