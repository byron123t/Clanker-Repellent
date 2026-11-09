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

    def test_resource_totals_include_failed_attempts_and_preserve_missing_data(self):
        rows=[{'model':'glm','arm':'baseline','accepted':True,'strict_pass':False,
               'filter_only_accepted':False,'filter_only_pass':False,'first_attempt_accepted':False,'attempts':3,
               'resources':{'inference_seconds':12.5,'prompt_tokens':600,'completion_tokens':400,'length_stops':1}}]
        result=analysis.metrics(rows,'glm','baseline')
        self.assertEqual((result['attempts'],result['completion_tokens'],result['length_stops']),(3,400,1))
        self.assertEqual(result['false_acceptance'],1)
        filtered=analysis.metrics(rows,'glm','filter-only')
        self.assertEqual(filtered['inference_seconds'],result['inference_seconds'])
        self.assertEqual(filtered['accepted'],0)
        rows.append({**rows[0],'resources':{}})
        self.assertIsNone(analysis.metrics(rows,'glm','baseline')['completion_tokens'])
        self.assertIsNone(analysis.metrics([],'glm','baseline')['inference_seconds'])

    def test_related_family_interval_keeps_arms_and_replicates_together(self):
        rows=self.records()
        for record in rows: record['family']='shared'
        result=analysis.family_interval(rows,'glm',draws=100)
        self.assertEqual(result,{'family_clusters':1,'family_ci95':[.25,.25]})
        for record in rows: record['family']=record['task']
        self.assertEqual(analysis.family_interval(rows,'glm',draws=1000)['family_ci95'],
                         analysis.paired_bootstrap(rows,'glm',3,['0','1','2','3'],draws=1000)['ci95'])


if __name__=='__main__': unittest.main()
