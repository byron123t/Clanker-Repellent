import copy
import json
from pathlib import Path
import tempfile
import unittest

from clanker_repellent.generate.contracts import validate_contract, check_contract
from clanker_repellent.generate.pure_evaluation import IntegerProgram
from clanker_repellent.generate.integer_ir import IntegerIR
from clanker_repellent.generate.source_generation import generate_source_run, select_languages
from clanker_repellent.generate.functional_structure import FUNCTIONAL_PROFILE
from clanker_repellent.generate.functional_structure import functional_metrics


def numeric(language='python'):
    return {'schema_version':1,'language':language,'function':{'name':'clamp','parameters':['value','lower','upper']},
            'examples':[{'inputs':[5,10,0],'expected':5},{'inputs':[-2,0,10],'expected':0},
                        {'inputs':[15,0,10],'expected':10},{'inputs':[4,4,4],'expected':4}]}


def document(language='json'):
    return {'schema_version':1,'language':language,'document':{'shape':{'type':'object','required':['items','total','count'],
            'additional_properties':False,'properties':{'items':{'type':'array','min_items':1,'items':{'type':'object','required':['id','amount'],
            'properties':{'id':{'type':'string'},'amount':{'type':'integer'}},'additional_properties':False}},
            'total':{'type':'integer'},'count':{'type':'integer'}}},'relations':[
            {'op':'count','left':'/count','right':'/items'}, {'op':'sum','left':'/total','right':'/items','field':'amount'},
            {'op':'unique','right':'/items','field':'id'}]}}


class ContractTests(unittest.TestCase):
    def test_numerical_boundary_checks_reject_valid_but_wrong_code(self):
        correct='def clamp(value, lower, upper):\n    if lower > upper: return value\n    return max(lower, min(value, upper))\n'
        self.assertTrue(check_contract(correct,numeric())['passed'])
        self.assertFalse(check_contract(correct.replace('return value','return lower'),numeric())['passed'])
        self.assertFalse(check_contract(correct.replace('clamp(', 'clip('),numeric())['passed'])
        self.assertFalse(check_contract(correct.replace('value, lower, upper','lower, value, upper'),numeric())['passed'])

    def test_integer_loops_tuple_assignment_and_work_bound(self):
        source='def gcd(a, b):\n    a = abs(a)\n    b = abs(b)\n    while b:\n        a, b = b, a % b\n    return a\n'
        program=IntegerProgram(source,'gcd',['a','b'])
        for args,expected in [([12,18],6),([-12,0],12),([0,0],0),([100,37],1)]:
            self.assertEqual(program.evaluate(args),expected)
        with self.assertRaisesRegex(ValueError,'step budget'):
            IntegerProgram('def forever(a):\n    while a: pass\n    return 0','forever').evaluate([1],max_steps=20)
        with self.assertRaises(ValueError):
            IntegerProgram('def bad(a):\n    return a.__class__','bad')
        with self.assertRaises(ValueError):
            IntegerProgram('def bad(a):\n    abs = a\n    return abs(a)','bad')

    def test_augmented_accumulator_is_input_dependent_not_a_no_op(self):
        source='def digit_sum(value):\n    total=0\n    while value:\n        total+=value%10\n        value//=10\n    return total\n'
        self.assertEqual(functional_metrics('python',source)['qualifying_functions'],1)
        self.assertEqual(IntegerProgram(source,'digit_sum').evaluate([129]),12)
        self.assertEqual(functional_metrics('python','def constant(value):\n    total=0\n    total+=7\n    return total')['qualifying_functions'],0)

    def test_sql_progress_budget_resets_per_example(self):
        contract=numeric('sql'); contract['examples']*=32
        source='SELECT CASE WHEN :lower>:upper THEN :value ELSE max(:lower,min(:value,:upper)) END AS clamp;'
        self.assertTrue(check_contract(source,contract)['passed'])

    def test_sql_checks_values_names_and_read_only_profile(self):
        contract=numeric('sql')
        correct='SELECT CASE WHEN :lower > :upper THEN :value ELSE max(:lower,min(:value,:upper)) END AS clamp;'
        self.assertTrue(check_contract(correct,contract)['passed'])
        self.assertFalse(check_contract(correct.replace('THEN :value','THEN :lower'),contract)['passed'])
        self.assertFalse(check_contract('DELETE FROM notes;',contract)['passed'])

    def test_llvm_signed_boundaries_and_forbidden_branches(self):
        contract=numeric('llvm')
        contract['function'].update(parameter_types=['i32']*3,return_type='i32')
        contract['llvm']={'instructions':['icmp','select','ret']}
        source='''define i32 @clamp(i32 %value, i32 %lower, i32 %upper) {
entry:
  %rev = icmp sgt i32 %lower, %upper
  %lo = icmp slt i32 %value, %lower
  %a = select i1 %lo, i32 %lower, i32 %value
  %hi = icmp sgt i32 %a, %upper
  %b = select i1 %hi, i32 %upper, i32 %a
  %result = select i1 %rev, i32 %value, i32 %b
  ret i32 %result
}'''
        self.assertTrue(check_contract(source,contract)['passed'])
        self.assertFalse(check_contract(source.replace('icmp slt','icmp ult'),contract)['passed'])
        self.assertFalse(check_contract(source.replace('entry:', 'entry:\n  br label %body\nbody:'),contract)['passed'])

    def test_fixed_width_ir_wraparound_and_boolean_results(self):
        source='define i8 @step(i8 %value) {\nentry:\n  %result = add i8 %value, 1\n  ret i8 %result\n}'
        program=IntegerIR(source,'step',['value'],['i8'],'i8',['add','ret'])
        for value in range(-128,128):
            self.assertEqual(program.evaluate([value]),((value+1+128)%256)-128)
        source='define i64 @step(i64 %value) {\nentry:\n  %result = add i64 %value, 1\n  ret i64 %result\n}'
        self.assertEqual(IntegerIR(source,'step',['value'],['i64'],'i64',['add','ret']).evaluate([2**63-1]),-2**63)
        source='define i1 @negative(i8 %value) {\nentry:\n  %result = icmp slt i8 %value, 0\n  ret i1 %result\n}'
        predicate=IntegerIR(source,'negative',['value'],['i8'],'i1',['icmp','ret'])
        for value in range(-128,128): self.assertIs(predicate.evaluate([value]),value<0)

    def test_loop_signals_and_tuple_assignment_match_integer_semantics(self):
        source='''def odd_total(value):
    total=0
    while value>0:
        value-=1
        if value%2==0: continue
        total+=value
        if total>10: break
    else:
        total+=100
    return total
'''
        self.assertEqual(IntegerProgram(source,'odd_total').evaluate([5]),104)
        self.assertEqual(IntegerProgram(source,'odd_total').evaluate([10]),16)
        source='def swap_total(a,b):\n    a,b=b,a+b\n    return a*10+b\n'
        self.assertEqual(IntegerProgram(source,'swap_total').evaluate([2,3]),35)

    def test_json_relations_exact_integer_totals_types_and_fields(self):
        contract=document()
        value={'items':[{'id':'a','amount':10**15},{'id':'b','amount':3}],'count':2,'total':10**15+3}
        self.assertTrue(check_contract(json.dumps(value),contract)['passed'])
        for change in [{'total':10**15+4},{'count':True},{'count':3},{'extra':'wrapper'},
                       {'items':[{'id':'a','amount':1},{'id':'a','amount':2}],'total':3}]:
            with self.subTest(change=change):
                self.assertFalse(check_contract(json.dumps({**value,**change}),contract)['passed'])
        self.assertFalse(check_contract(json.dumps({'wrapper':value}),contract)['passed'])

    def test_http_status_and_headers(self):
        contract=document('http'); contract['http']={'status':201,'headers':{'X-Example':'catalog'}}
        body=json.dumps({'items':[{'id':'a','amount':2}],'count':1,'total':2})
        text='HTTP/1.1 201 Created\r\nContent-Type: application/json\r\nX-Example: catalog\r\n\r\n'+body
        self.assertTrue(check_contract(text,contract)['passed'])
        self.assertFalse(check_contract(text.replace('201 Created','200 OK'),contract)['passed'])

    def test_html_exact_table_and_reference_checks(self):
        contract={'schema_version':1,'language':'html','html':{'required_ids':['reference'],
            'table':{'columns':['Input','Result'],'row_count':1,'rows':[['2','4']]}}}
        source='<section id="reference"><table><tr><th>Input</th><th>Result</th></tr><tr><td>2</td><td>4</td></tr></table></section>'
        self.assertTrue(check_contract(source,contract)['passed'])
        self.assertFalse(check_contract(source.replace('<td>4','<td>5'),contract)['passed'])
        self.assertFalse(check_contract(source.replace('<section ','<section aria-labelledby="missing" '),contract)['passed'])

    def test_unknown_inapplicable_and_unbounded_contracts_are_errors(self):
        for change in [{'unknown':True},{'language':'javascript'},{'schema_version':True},{'http':{'status':200}},
                       {'examples':[]},{'function':{'name':'x','parameters':['v','v']}}]:
            with self.subTest(change=change),self.assertRaises(ValueError): validate_contract({**numeric(),**change})
        bad=document(); bad['document']['shape']['typo']=True
        with self.assertRaises(ValueError): validate_contract(bad)

    def test_retry_feedback_and_seed_then_integrity_checked_resume(self):
        class Provider:
            calls=[]
            def complete(self,**kwargs):
                self.calls.append(kwargs)
                code='def clamp(value, lower, upper):\n    return max(lower,min(value,upper))' if len(self.calls)==1 else 'def clamp(value, lower, upper):\n    if lower>upper: return value\n    return max(lower,min(value,upper))'
                return {'response_text':'```python\n'+code+'\n```','resolved_model':'test','finish_reason':'stop'}
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'benign'; provider=Provider()
            kwargs=dict(provider=provider,model='test',payload='Benign clamp helper',targets=select_languages(['python']),
                        output_dir=output,benign=True,contract=numeric(),seed=7,run_linters=False,retries=1,structure_profile=FUNCTIONAL_PROFILE)
            run=generate_source_run(**kwargs)
            self.assertEqual(run['summary']['accepted'],1)
            self.assertEqual(len(provider.calls),2)
            self.assertEqual([call['extra_body']['seed'] for call in provider.calls],[7,8])
            self.assertIn('Public example 1 failed',provider.calls[1]['messages'][1]['content'])
            self.assertEqual(run['settings']['mode'],'benign')
            (output/'python/generated.py').write_text('def changed(x): return x+1')
            with self.assertRaisesRegex(ValueError,'integrity'): generate_source_run(**kwargs)
            changed=copy.deepcopy(kwargs); changed['contract']=numeric(); changed['contract']['examples'][0]['expected']=0
            with self.assertRaisesRegex(ValueError,'contract changed'): generate_source_run(**changed)
        with self.assertRaisesRegex(ValueError,'--benign'):
            generate_source_run(**{**kwargs,'benign':False})


if __name__=='__main__': unittest.main()
