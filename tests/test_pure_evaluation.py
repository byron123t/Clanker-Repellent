import unittest

from clanker_repellent.generate.pure_evaluation import evaluate_predicate


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


if __name__ == '__main__':
    unittest.main()
