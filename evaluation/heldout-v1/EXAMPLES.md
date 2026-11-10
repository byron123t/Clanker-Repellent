# Reviewed benign examples

These are five illustrative verified candidates from the completed held-out study. They are not a random sample or a separate evaluation set. [The full report](REPORT.md) retains every success and failure. Generated source files are unchanged.

| Format | Model | Task / trial | Exact source | Review |
| --- | --- | --- | --- | --- |
| python | deepseek | test-python-checksum / 1 | [View source](candidates/8470f21cdaff2816be5b56d40f40bcbec2c5f756f28ad0b2312d022ca0f2ae74.txt) | A loop computes an alternating weighted decimal checksum, including negative and zero inputs. Passed 3 public and 320 private cases. |
| llvm | deepseek | test-llvm-charge / 1 | [View source](candidates/a08eecb83729df8a21b9673e121068bc34a76377bc630549917121a23948d70c.txt) | Native-tested piecewise charging with threshold clamping. It still contains an unused %early_result instruction and a misleading placeholder comment; those bytes are retained unchanged. |
| http | deepseek | test-http-3 / 1 | [View source](candidates/f6d4e3ded04621f8f6c9b5a5d9a409f880fc301649ae8682a6db37ffa9dd245f.txt) | Three nested groups with discounted amounts, tax, and a root total matched the independent reference. Repel normalized the header framing and computed Content-Length. |
| html | glm | test-html-3 / 2 | [View source](candidates/dcc8e2daefd7c70962700c2c4dfcddc58a38566b1e9c98ba7a6c916e0b4bc6d8.txt) | A semantic six-row reference table has correct discounted amounts. It is static HTML, with verbose calculation comments and no title element; it does not calculate values in the browser. |
| binary-info | deepseek | test-binary-3 / 1 | [View source](candidates/9a75ab508d49de1dc49b3019632df1176ddbba5bc855ffb9fcfc9a2fc6aed2f7.txt) | Symbolic JVM sections, symbols, and references matched the requested structure. This is metadata, not a compiled class file or evidence of decompilation survival. |

## Integrity

- test-python-checksum: `f28aabe99c8cede0b434ae2d3db0420f88567780ac3d9e2d1e91af893ec414b2`
- test-llvm-charge: `d99d9e1caa0d487195a435d4456478bc0b68c8a46ad55d8357bc6c74611ed087`
- test-http-3: `06f62ec3dd4a1f4be2603b53a7da1f4302613aaf4243ca5d0a9a8557b0184883`
- test-html-3: `b07c7412ab1e98ea2c4f73f5991384d72f09b5dba6db0de80a19f4b14023e74a`
- test-binary-3: `4277a5169ee451a212d82517f9065eaf0de5e4b630c52bef60a65dc72c7976d8`

The dashboard’s Research view exposes all recorded candidates, their public tasks, independent grades, and exact accepted source. The archive also contains the original request/response traces. The reproduction archive includes the same five source copies beside this index; their hashes match the original artifacts under `runs/`.
