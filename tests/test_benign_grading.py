"""Infrastructure failure must not become a measured wrong answer."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('benign_grading',Path(__file__).resolve().parents[1]/'benchmarks/benign-v2/grade.py')
grading=importlib.util.module_from_spec(spec); spec.loader.exec_module(grading)


class NativeGradingTests(unittest.TestCase):
    task={'language':'python','contract':{'function':{'name':'double','parameters':['value']},
          'examples':[{'inputs':[2],'expected':4}]}}
    oracle={'kind':'numeric','cases':[{'inputs':[-3],'expected':-6}]}
    source='def double(value):\n    return value*2\n'

    def test_signal_startup_failure_and_timeout_are_unavailable_not_incorrect(self):
        for code in [-9,-11,1]:
            with self.subTest(code=code),patch.object(grading.subprocess,'run',return_value=subprocess.CompletedProcess([],code,'','')):
                with self.assertRaisesRegex(RuntimeError,'unavailable'): grading.grade(self.task,self.oracle,self.source)
        with patch.object(grading.subprocess,'run',side_effect=subprocess.TimeoutExpired('native',8)):
            with self.assertRaisesRegex(RuntimeError,'unavailable'): grading.grade(self.task,self.oracle,self.source)

    def test_wrong_answers_and_unsupported_candidates_remain_quality_failures(self):
        with patch.object(grading.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'[4, -5]','')):
            result=grading.grade(self.task,self.oracle,self.source)
        self.assertFalse(result['passed']); self.assertEqual(result['public_passed'],1); self.assertEqual(result['hidden_passed'],0)
        with patch.object(grading.subprocess,'run') as native:
            result=grading.grade(self.task,self.oracle,'def double(value):\n    return value//0\n')
            self.assertFalse(result['passed']); native.assert_not_called()


if __name__=='__main__': unittest.main()
