# Benign format exercises

These are hand-written task inputs and reference controls, **not model-generated results**.
They contain no real credentials, captured traffic, executable bytes, or material from existing
generation runs. Use a fresh output directory for each model.

From the repository root, with the DeepSeek tunnel open:

```sh
repel generate examples/benign-formats/inputs/range-reference.txt --benign \
  --endpoint http://127.0.0.1:18473/v1 --language json,http,binary-info,llvm \
  --max-tokens 2048 --no-thinking --output-dir .repel-workspaces/benign-formats-deepseek
```

Use port `18474` and a different output directory for GLM. The model ID is discovered from the server.
An existing run cannot be resumed with a different model.

More exercises:

- `catalog-response.txt`: JSON and HTTP data consistency (`total_count` equals the book count).
- `invoice-records.txt`: try `--format yaml,toml,xml,csv,ini` for native configuration, markup,
  and tabular records with integer calculations. Syntax acceptance is separate from correct totals.
- `pe-description.txt`, `macho-description.txt`, `jvm-description.txt`, `clr-description.txt`:
  select `--language binary-info` and review format/architecture/section/symbol consistency.
- `clamp-helper.txt`: select `--language llvm`; test both ordinary and reversed bounds after review.

The references in `controls/` are deliberately authored independently of any model output.
`python examples/benign-formats/check_controls.py` validates all controls, checks UTF-8 HTTP framing
and symbolic cross-references, and compiles the two reviewed LLVM controls into a temporary library
to test their results on 729 input triples each. Generation itself never executes model output.

Do not execute newly generated IR simply because the reference-control check passes. The control
checker refuses changes to its two hand-reviewed IR files; review and independently test new samples.
The native check uses Clang and runs on macOS/Linux with a C-compatible shared-library loader.
