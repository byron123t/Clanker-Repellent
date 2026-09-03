import json
import tempfile
import unittest
from pathlib import Path

from clanker_repellent.datasets.benign_repos import load_repository_manifest
from clanker_repellent.datasets.repo_tasks import load_repository_tasks


ROOT = Path(__file__).resolve().parents[1]


class RepositoryTaskTests(unittest.TestCase):
    def _write(self, root: Path, tasks):
        path = root / "tasks.json"
        path.write_text(
            json.dumps({"schema_version": "1.0", "tasks": tasks}),
            encoding="utf-8",
        )
        return path

    def test_loads_tasks_against_a_repository_superset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = self._write(
                root,
                [
                    {
                        "id": "sample_test",
                        "repository_id": "sample",
                        "task_type": "test",
                        "task": "Add a deterministic test.",
                        "safety": "benign_software_engineering",
                    }
                ],
            )

            tasks = load_repository_tasks(path, {"sample"})

            self.assertEqual(tasks[0]["id"], "sample_test")
            self.assertEqual(
                len(load_repository_tasks(path, {"sample", "taskless_fixture"})),
                1,
            )

    def test_rejects_unknown_repository_and_extra_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = {
                "id": "sample_test",
                "repository_id": "unknown",
                "task_type": "test",
                "task": "Add a deterministic test.",
                "safety": "benign_software_engineering",
            }
            path = self._write(root, [task])
            with self.assertRaisesRegex(ValueError, "unknown repository"):
                load_repository_tasks(path, {"sample"})

            task["notes"] = "not allowed"
            path = self._write(root, [task])
            with self.assertRaisesRegex(ValueError, "fields must be exactly"):
                load_repository_tasks(path, {"sample"})

    def test_checked_in_catalog_has_40_tasks_across_12_repositories(self):
        repositories = load_repository_manifest(
            ROOT / "data" / "benign_repositories.json"
        )
        tasks = load_repository_tasks(
            ROOT / "data" / "repository_tasks.json",
            {repository["id"] for repository in repositories},
        )

        self.assertEqual(len(tasks), 40)
        self.assertEqual(len({task["repository_id"] for task in tasks}), 12)


if __name__ == "__main__":
    unittest.main()
