import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('benign_analysis',Path(__file__).resolve().parents[1]/'benchmarks/benign-v2/analyze.py')
analysis=importlib.util.module_from_spec(spec); spec.loader.exec_module(analysis)


class PairedAnalysisTests(unittest.TestCase):
    def records(self):
        return [{'model':'glm','arm':arm,'task':str(task),'trial':trial,'strict_pass':(task<2 if arm=='baseline' else task<3)}
                for task in range(4) for trial in range(3) for arm in ['baseline','contract']]

    def test_pairing_clusters_replicates_and_rejects_missing_cells(self):
        rows=self.records(); result=analysis.paired_bootstrap(rows,'glm',3,['0','1','2','3'],draws=1000)
        self.assertEqual(result['paired_tasks'],4)
        self.assertEqual(result['difference'],.25)
        self.assertTrue(result['ci95'][0]<=.25<=result['ci95'][1])
        self.assertEqual(result,analysis.paired_bootstrap(rows,'glm',3,['0','1','2','3'],draws=1000))
        self.assertIsNone(analysis.paired_bootstrap(rows[:-1],'glm',3,['0','1','2','3'],draws=10))

    def test_identical_arms_have_zero_paired_effect(self):
        rows=self.records()
        for record in rows: record['strict_pass']=int(record['task'])<2
        result=analysis.paired_bootstrap(rows,'glm',3,['0','1','2','3'],draws=1000)
        self.assertEqual(result['difference'],0)
        self.assertEqual(result['ci95'],[0,0])


if __name__=='__main__': unittest.main()
