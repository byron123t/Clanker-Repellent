# Manual review of selected benign examples

Five selected, hash-verified examples were inspected after scoring. This is qualitative review, not another random sample or a change to the registered grades.

- [deepseek / lua-parse_decimal](candidates/bc6f00b160d1d7cd279816be7af674eb3fd7de3b1f3f9d03f750d4cfc02e3d8d.txt): Substantive byte-wise parsing with bounded accumulation, explicit ASCII whitespace, optional plus, and overflow rejection. It passed 188 registered inputs. Its 64-byte limit follows the task; behavior outside that task domain was not graded.

- [glm / rust-longest_run](candidates/8f9f20e16ed239eb80b845e8a3d9966f23b22d8f98503ec465fe7c7429b6e00f.txt): Computes a real contiguous-run length and passed 187 inputs. The boolean-to-Option-to-boolean chain is unnecessary, and its comment about bounds-check overhead is not supported by a performance measurement. Behavior verification does not guarantee polished code.

- [deepseek / xml-schedule](candidates/8caa3f0db04c664e8d31846e2a90ae908bb44699c84ec3ef7d879c0612e7ec0e.txt): Twelve ordered records preserve inputs and the checked interval-overlap values. This is static calculated reference data, not runtime scheduling logic.

- [deepseek / csv-temperature](candidates/5ced446309f24e63ed4837051ce079b995de0d7a28fec989f5dc17d33547dfa0.txt): Valid CSV preserves UTF-8 text, embedded commas and doubled quotes, with exact temperature values. It is an unchanged generated table.

- [deepseek / binary-info-jvm](candidates/25385b212f0cfd9444c7d1928dfb73309176aff0f368d80489ca40fa22df7397.txt): The typed sections and symbols match the requested logical graph. It does not contain executable JVM methods or demonstrate actual class-file serialization.
