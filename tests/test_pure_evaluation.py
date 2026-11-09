import unittest

from clanker_repellent.generate.pure_evaluation import IntegerProgram,evaluate_predicate


class PureEvaluationTests(unittest.TestCase):
    def test_boundary_negative_equal_and_reversed_cases(self):
        source = 'def in_range(value: int, lower: int, upper: int) -> bool:\n    return lower <= value <= upper'
        for arguments, expected in [((5, 0, 10), True), ((0, 0, 10), True), ((10, 0, 10), True),
                                    ((-1, 0, 10), False), ((11, 0, 10), False), ((-5, -10, -1), True),
                                    ((3, 3, 3), True), ((4, 3, 3), False), ((5, 10, 0), False)]:
            self.assertIs(evaluate_predicate(source, 'in_range', arguments), expected)

    def test_conditionals_locals_and_short_circuiting(self):
        source = 'def valid(value):\n    if value < 0:\n        return False\n    remainder = value % 2\n    return remainder == 0 and (value == 0 or 10 // value > 0)'
        self.assertIs(evaluate_predicate(source, 'valid', [0]), True)
        self.assertIs(evaluate_predicate(source, 'valid', [-2]), False)
        self.assertIs(evaluate_predicate(source, 'valid', [3]), False)

    def test_unsupported_operations_are_rejected_without_evaluation(self):
        for source in ['def valid(value):\n    return value.method()',
                       'def valid(value):\n    return bool(value)',
                       'def valid(value):\n    while True:\n        pass',
                       'def valid(value):\n    return value ** value > 0',
                       'def valid(value):\n    return value > 0\nvalid(1)',
                       '@decorator\ndef valid(value):\n    return value > 0',
                       'def valid(value):\n    return 1']:
            with self.subTest(source=source), self.assertRaises(ValueError):
                evaluate_predicate(source, 'valid', [2])

    def test_definition_time_annotations_and_invalid_control_flow_are_rejected(self):
        for signature in ['value: MissingType','value: abs(unknown)','value: 10 // 0']:
            with self.subTest(signature=signature), self.assertRaisesRegex(ValueError,'annotations'):
                IntegerProgram('def increment('+signature+') -> int:\n    return value + 1','increment')
        with self.assertRaisesRegex(ValueError,'annotations'):
            IntegerProgram('def increment(value) -> Unknown:\n    return value + 1','increment')
        with self.assertRaisesRegex(ValueError,'control flow'):
            IntegerProgram('def increment(value):\n    if False:\n        break\n    return value + 1','increment')
        for signature in ['value', 'value: int', 'value: "ExternalInteger"']:
            source='def increment('+signature+') -> "int":\n    return value + 1'
            self.assertEqual(IntegerProgram(source,'increment').evaluate([2]),3)

    def test_authored_expressions_agree_with_native_python_values_and_types(self):
        # Only fixed, hand-written expressions execute here; never model output.
        expressions=['left and right','left or right','left // right if right else 0',
                     'left % right if right else 0','left < right < 3',
                     'min(left,right)','max(left,right)','abs(left) + -right',
                     '(left or right) and (right or left)','not left']
        for expression in expressions:
            source='def authored(left, right):\n    return '+expression
            namespace={}
            exec(compile(source,'<authored-test>','exec'),namespace)
            program=IntegerProgram(source,'authored')
            for left in [-7,-1,0,1,7,False,True]:
                for right in [-3,-1,0,1,3,False,True]:
                    with self.subTest(expression=expression,left=left,right=right):
                        expected=namespace['authored'](left,right)
                        actual=program.evaluate([left,right])
                        self.assertIs(type(actual),type(expected))
                        self.assertEqual(actual,expected)


if __name__ == '__main__':
    unittest.main()
