"""Bounded interpretation of scalar LLVM integer helpers, without loading native code."""
import re

from .llvm_structure import llvm_metrics

TYPE = r'i(?:1|8|16|32|64)'
NAME = r'[A-Za-z_][A-Za-z_0-9]*'
INSTRUCTIONS = {'add', 'sub', 'mul', 'and', 'or', 'xor', 'icmp', 'select', 'ret'}


class IntegerIR:
    def __init__(self, source, name, parameters, parameter_types, return_type, allowed_instructions):
        llvm_metrics(source)
        code = '\n'.join(line.split(';', 1)[0] for line in source.splitlines())
        match = re.fullmatch(r'\s*define\s+('+TYPE+r')\s+@('+NAME+r')\s*\(([^()]*)\)\s*\{([^{}]*)\}\s*', code)
        if not match or match[1] != return_type or match[2] != name:
            raise ValueError('LLVM requires exactly the named helper with the contracted return type.')
        signature = [part.strip() for part in match[3].split(',')] if match[3].strip() else []
        parsed = [re.fullmatch(r'('+TYPE+r')\s+%('+NAME+r')',part) for part in signature]
        if any(part is None for part in parsed) or [part.groups() for part in parsed] != list(zip(parameter_types,parameters)):
            raise ValueError('LLVM parameter names, types, or order differ from the contract.')
        self.parameters, self.parameter_types, self.return_type = parameters, parameter_types, return_type
        self.instructions = []
        self.opcodes = []
        for line in match[4].splitlines():
            line = line.strip()
            if not line or re.fullmatch(NAME+r':', line):
                continue
            assignment = re.fullmatch(r'%('+NAME+r')\s*=\s*(\w+)\s+(.+)', line)
            if assignment:
                target, opcode, arguments = assignment.groups()
            elif line.startswith('ret '):
                target, opcode, arguments = None, 'ret', line[4:]
            else:
                raise ValueError('Contracted LLVM helpers require straight-line integer instructions.')
            if opcode not in allowed_instructions or opcode not in INSTRUCTIONS:
                raise ValueError('LLVM instruction is outside the contract: '+opcode)
            self.instructions.append((target, opcode, arguments))
            self.opcodes.append(opcode)
        if not self.instructions or self.opcodes[-1] != 'ret' or self.opcodes.count('ret') != 1:
            raise ValueError('LLVM contract requires one final return.')

    def evaluate(self, arguments):
        def width(kind):
            if not re.fullmatch(TYPE, kind):
                raise ValueError('Unsupported LLVM integer type.')
            return int(kind[1:])

        def wrap(value, kind):
            return int(value) & ((1 << width(kind)) - 1)

        def signed(value, kind):
            bits = width(kind)
            return value - (1 << bits) if value & (1 << (bits - 1)) else value

        if len(arguments) != len(self.parameters) or any(type(value) not in {int, bool} for value in arguments):
            raise ValueError('LLVM argument arity/type differs from contract.')
        values = {'%'+name:(kind, wrap(value, kind)) for name,kind,value in zip(self.parameters,self.parameter_types,arguments)}

        def operand(token, kind):
            token = token.strip()
            if token.startswith('%'):
                if token not in values or values[token][0] != kind:
                    raise ValueError('LLVM operand is undefined or has a different type.')
                return values[token][1]
            if kind == 'i1' and token in {'true','false'}:
                return int(token == 'true')
            if not re.fullmatch(r'-?\d{1,24}', token):
                raise ValueError('Use bounded LLVM integer operands.')
            return wrap(int(token), kind)

        for target, opcode, text in self.instructions:
            if opcode == 'ret':
                match = re.fullmatch(r'('+TYPE+r')\s+(.+)', text)
                if not match or match[1] != self.return_type:
                    raise ValueError('LLVM returned type differs from contract.')
                value = operand(match[2], match[1])
                return bool(value) if match[1] == 'i1' else signed(value,match[1])
            if opcode == 'select':
                match = re.fullmatch(r'i1\s+([^,]+),\s*('+TYPE+r')\s+([^,]+),\s*('+TYPE+r')\s+(.+)', text)
                if not match or match[2] != match[4]:
                    raise ValueError('LLVM select types differ.')
                kind = match[2]
                # Validate both operands even when one is not selected.
                left, right = operand(match[3],kind), operand(match[5],kind)
                result = left if operand(match[1],'i1') else right
            elif opcode == 'icmp':
                match = re.fullmatch(r'(eq|ne|[su](?:gt|ge|lt|le))\s+('+TYPE+r')\s+([^,]+),\s*(.+)',text)
                if not match:
                    raise ValueError('Unsupported LLVM comparison.')
                predicate, compare_type = match[1], match[2]
                left,right = operand(match[3],compare_type),operand(match[4],compare_type)
                if predicate.startswith('s'):
                    left,right = signed(left,compare_type),signed(right,compare_type)
                relation = predicate[-2:]
                result = {'eq':left==right,'ne':left!=right,'gt':left>right,'ge':left>=right,'lt':left<right,'le':left<=right}[relation]
                kind = 'i1'
            else:
                match = re.fullmatch(r'('+TYPE+r')\s+([^,]+),\s*(.+)',text)
                if not match:
                    raise ValueError('Unsupported LLVM arithmetic operands.')
                kind = match[1]
                left,right = operand(match[2],kind),operand(match[3],kind)
                result = {'add':lambda:left+right,'sub':lambda:left-right,'mul':lambda:left*right,
                          'and':lambda:left&right,'or':lambda:left|right,'xor':lambda:left^right}[opcode]()
            if '%'+target in values:
                raise ValueError('LLVM SSA names must be unique.')
            values['%'+target] = kind,wrap(result,kind)
        raise ValueError('LLVM helper has no result.')
