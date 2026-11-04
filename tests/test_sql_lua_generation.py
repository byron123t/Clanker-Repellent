import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from clanker_repellent.generate.functional_structure import FUNCTIONAL_PROFILE, functional_metrics
from clanker_repellent.generate.source_generation import build_generation_messages, generate_source_run, select_languages, validate_snippet, validation_metadata
from clanker_repellent.generate.sql_structure import inspect_sql


SQL = 'SELECT CASE WHEN :lower <= :value AND :value <= :upper THEN 1 ELSE 0 END AS in_range;'
LUA = 'function in_range(value, lower, upper)\n  return lower <= value and value <= upper\nend\n'


class SQLLuaGenerationTests(unittest.TestCase):
    def validate(self, language, source, **kwargs):
        return validate_snippet(select_languages([language])[0], source, run_linters=False,
                                require_structure=True, structure_profile=FUNCTIONAL_PROFILE, **kwargs)

    def test_sql_is_compiled_as_a_parameterized_computation(self):
        result = self.validate('sql', SQL)
        self.assertTrue(result['accepted'])
        self.assertEqual([check['name'] for check in result['checks']], ['sql_prepare', 'source_structure'])
        metrics = result['checks'][0]['metrics']
        self.assertEqual(metrics['parameters'], 3)
        self.assertEqual(metrics['qualifying_queries'], 1)

    def test_sql_compilation_does_not_evaluate_expressions(self):
        # Executing abs(minimum signed 64-bit integer) raises integer overflow.
        report = self.validate('sql', 'SELECT abs(-9223372036854775808) + :value AS result;')
        self.assertTrue(report['accepted'])

    def test_quoted_sql_alias_is_supported_without_counting_its_text_as_code(self):
        self.assertTrue(self.validate('sql', SQL.replace('AS in_range', 'AS "in_range"'))['accepted'])
        self.assertFalse(self.validate('sql', 'SELECT 1 AS ":value < :upper";')['accepted'])

    def test_sql_cast_type_is_not_a_result_alias(self):
        self.assertFalse(self.validate('sql', 'SELECT CAST(:value AS INTEGER) + 1;')['accepted'])
        self.assertTrue(self.validate('sql', 'SELECT CAST(:value AS INTEGER) + 1 AS result;')['accepted'])

    def test_sql_subtraction_supplies_a_computation(self):
        self.assertTrue(self.validate('sql', 'SELECT :value - 1 AS result;')['accepted'])

    def test_sql_rejects_nonselect_statements_external_functions_and_real_tables(self):
        for source in ['CREATE TABLE example(value INTEGER);', "ATTACH ':memory:' AS other;",
                       'PRAGMA user_version=1;', "SELECT load_extension('example') AS result;",
                       'SELECT name FROM sqlite_master;', 'SELECT 1 AS a; SELECT 2 AS b;',
                       'WITH values_cte AS (SELECT 1 AS a) SELECT a FROM values_cte;',
                       'SELECT (WITH t AS (SELECT 1) SELECT 2) AS result;', 'SELECT ( AS broken;']:
            with self.subTest(source=source):
                self.assertFalse(self.validate('sql', source, allow_missing_toolchains=True)['accepted'])

    def test_sql_comments_literals_constants_and_identity_do_not_supply_computation(self):
        for source in ['SELECT 1 AS result;', 'SELECT :value AS result;',
                       "SELECT ':value < :upper' AS result;", 'SELECT 1 AS result; -- :value < :upper']:
            with self.subTest(source=source):
                self.assertFalse(self.validate('sql', source)['accepted'])

    def test_sql_raw_errors_and_parameter_names_are_not_serialized(self):
        report = self.validate('sql', 'SELECT :PRIVATE_VALUE < 2 AS PRIVATE_RESULT;')
        self.assertTrue(report['accepted'])
        self.assertNotIn('PRIVATE', json.dumps(validation_metadata(report)))
        failed = self.validate('sql', 'SELECT PRIVATE_COLUMN FROM PRIVATE_TABLE;')
        self.assertNotIn('PRIVATE', failed['checks'][0]['_stderr'])

    def test_sql_statement_contract_replaces_function_declaration_prompt(self):
        prompt = build_generation_messages(select_languages(['sql'])[0], 'Ordinary helper', benign=True,
                                            structure_profile=FUNCTIONAL_PROFILE)[0]['content']
        self.assertIn('SQLite SELECT', prompt)
        self.assertNotIn('named function or method', prompt)

    @unittest.skipUnless(shutil.which('luac'), 'Lua compiler required')
    def test_lua_native_syntax_and_function_checks(self):
        self.assertTrue(self.validate('lua', LUA)['accepted'])
        self.assertFalse(self.validate('lua', LUA.replace('end', ''))['accepted'])
        self.assertFalse(self.validate('lua', 'function example(value) return value end')['accepted'])
        self.assertFalse(self.validate('lua', 'function example(value) return 1 end')['accepted'])

    def test_sql_and_lua_generation_use_the_same_retry_flow(self):
        for language, source in [('sql', SQL), ('lua', LUA)]:
            if language == 'lua' and not shutil.which('luac'):
                continue
            with self.subTest(language=language), tempfile.TemporaryDirectory() as directory:
                provider = mock.Mock(spec=['complete'])
                provider.complete.return_value = {'response_text': '```' + language + '\n' + source + '\n```'}
                run = generate_source_run(provider=provider, model='fixture', payload='Ordinary helper',
                                          targets=select_languages([language]), output_dir=Path(directory) / 'run',
                                          benign=True, run_linters=False, retries=0, structure_profile=FUNCTIONAL_PROFILE)
                self.assertEqual(run['summary']['status'], 'passed')


if __name__ == '__main__':
    unittest.main()
