"""Versioned, offline task contracts for explicitly benign generation.

This is a bounded Repel schema, not a general JSON Schema implementation. Unknown
keywords are errors. No contract contains executable callbacks or external references.
"""
import hashlib
import json
import math
import re
import sqlite3
from pathlib import Path

from .document_formats import strict_json, _http_parts, binary_metrics
from .integer_ir import IntegerIR, INSTRUCTIONS
from .pure_evaluation import IntegerProgram
from .sql_structure import inspect_sql, _code, _PURE_FUNCTIONS

LANGUAGES = {'python', 'sql', 'llvm', 'json', 'http', 'binary-info', 'html'}
IDENTIFIER = re.compile(r'[A-Za-z_][A-Za-z_0-9]*\Z')
TYPES = {'object', 'array', 'string', 'integer', 'number', 'boolean', 'null'}


def _keys(value, allowed, required=()):
    if not isinstance(value, dict) or set(value) - set(allowed) or set(required) - set(value):
        raise ValueError('Contract has missing or unknown fields; expected '+', '.join(sorted(allowed)))


def _strings(value, *, names=False, limit=128):
    if (not isinstance(value, list) or not 1 <= len(value) <= limit
            or not all(isinstance(v, str) and v and len(v) <= 256 and (not names or IDENTIFIER.fullmatch(v)) for v in value)
            or len(set(value)) != len(value)):
        raise ValueError('Contract requires a nonempty list of distinct valid names/strings.')


def _pointer(path):
    if not isinstance(path, str) or len(path) > 1024 or path and not path.startswith('/') or re.search(r'~(?![01])', path):
        raise ValueError('Use a bounded JSON pointer with valid ~0/~1 escapes.')


def _shape(schema, depth=0):
    if depth > 12:
        raise ValueError('Contract shape nesting exceeds 12 levels.')
    _keys(schema, {'type', 'required', 'properties', 'items', 'additional_properties', 'min_items', 'max_items', 'enum'}, {'type'})
    if not isinstance(schema['type'],str) or schema['type'] not in TYPES:
        raise ValueError('Unsupported contract shape type.')
    if 'required' in schema:
        _strings(schema['required'])
    if 'properties' in schema:
        if not isinstance(schema['properties'], dict) or len(schema['properties']) > 128 or not all(isinstance(k,str) and k for k in schema['properties']):
            raise ValueError('Contract shape properties require bounded named fields.')
        for value in schema['properties'].values():
            _shape(value, depth+1)
    if 'items' in schema:
        _shape(schema['items'], depth+1)
    if 'additional_properties' in schema and type(schema['additional_properties']) is not bool:
        raise ValueError('additional_properties must be Boolean.')
    for key in ('min_items','max_items'):
        if key in schema and (type(schema[key]) is not int or not 0 <= schema[key] <= 10000):
            raise ValueError('Array bounds must be integers in 0..10000.')
    if schema.get('min_items',0) > schema.get('max_items',10000):
        raise ValueError('Array bounds are reversed.')
    if 'enum' in schema and (not isinstance(schema['enum'],list) or not 1 <= len(schema['enum']) <= 128):
        raise ValueError('enum must have 1..128 entries.')
    object_fields = {'properties','required','additional_properties'} & schema.keys()
    array_fields = {'items','min_items','max_items'} & schema.keys()
    if object_fields and schema['type'] != 'object' or array_fields and schema['type'] != 'array':
        raise ValueError('Shape keywords do not apply to this type.')


def _validate_contract(value):
    """Return a canonical copy after validating every supported contract field."""
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, allow_nan=False)
    if len(encoded) > 131072:
        raise ValueError('Contract exceeds 128 KiB.')
    value = strict_json(encoded)
    _keys(value, {'schema_version','language','function','examples','document','http','llvm','html'}, {'schema_version','language'})
    if type(value['schema_version']) is not int or value['schema_version'] != 1 or not isinstance(value['language'],str) or value['language'] not in LANGUAGES:
        raise ValueError('Unsupported contract version or language.')
    language = value['language']
    applicable = {'python':{'function','examples'}, 'sql':{'function','examples'}, 'llvm':{'function','examples','llvm'},
                  'json':{'document'}, 'binary-info':{'document'}, 'http':{'document','http'}, 'html':{'html'}}[language]
    if set(value)-{'schema_version','language'}-applicable:
        raise ValueError('Contract fields are incompatible with the selected language.')
    if language in {'python','sql','llvm'}:
        function = value.get('function')
        _keys(function, {'name','parameters','parameter_types','return_type'} if language == 'llvm' else {'name','parameters'}, {'name','parameters'})
        if not isinstance(function['name'],str) or not IDENTIFIER.fullmatch(function['name']):
            raise ValueError('Contract helper name must be a plain identifier.')
        _strings(function['parameters'], names=True, limit=16)
        examples = value.get('examples',[])
        if not isinstance(examples,list) or not 1 <= len(examples) <= 128:
            raise ValueError('Code contracts require 1..128 public examples.')
        for example in examples:
            _keys(example, {'inputs','expected'}, {'inputs','expected'})
            if (not isinstance(example['inputs'],list) or len(example['inputs']) != len(function['parameters'])
                    or any(type(item) not in {int,bool} or abs(item)>2**63 for item in example['inputs'])
                    or type(example['expected']) not in {int,bool} or abs(example['expected'])>2**63):
                raise ValueError('Contract examples require bounded integer/Boolean values matching the signature.')
            if language=='sql' and type(example['expected']) is not int:
                raise ValueError('SQLite predicates return integer 0/1; expected values must be integers.')
        if language == 'llvm':
            types = function.get('parameter_types')
            if (not isinstance(types,list) or len(types)!=len(function['parameters'])
                    or any(not isinstance(t,str) or not re.fullmatch(r'i(?:1|8|16|32|64)',t) for t in types)
                    or not isinstance(function.get('return_type'),str) or function['return_type'] not in {'i1','i8','i16','i32','i64'}):
                raise ValueError('LLVM contract requires scalar integer parameter/return types.')
            _keys(value.get('llvm'), {'instructions'}, {'instructions'})
            _strings(value['llvm']['instructions'])
            if set(value['llvm']['instructions'])-INSTRUCTIONS or 'ret' not in value['llvm']['instructions']:
                raise ValueError('Contracted LLVM supports straight-line integer instructions and a final ret.')
            for example in examples:
                for item,kind in zip(example['inputs']+[example['expected']],types+[function['return_type']]):
                    bits=int(kind[1:])
                    if (type(item) is not bool if bits==1 else type(item) is not int or not -(2**(bits-1))<=item<2**(bits-1)):
                        raise ValueError('LLVM examples must match signed integer widths (Boolean for i1).')
    if language in {'json','binary-info','http'}:
        document = value.get('document')
        _keys(document, {'shape','equals','relations'}, {'shape'})
        _shape(document['shape'])
        if document['shape']['type'] != 'object':
            raise ValueError('Document contracts require an object at the root.')
        for field in ('equals','relations'):
            if not isinstance(document.get(field,[]),list) or len(document.get(field,[]))>128:
                raise ValueError('Document rules must be bounded lists.')
        for rule in document.get('equals',[]):
            _keys(rule, {'path','value'}, {'path','value'}); _pointer(rule['path'])
        for rule in document.get('relations',[]):
            _keys(rule, {'op','left','right','field'}, {'op','right'})
            if rule['op'] not in {'count','sum','unique'}:
                raise ValueError('Unsupported document relation.')
            if rule['op']=='unique':
                if 'left' in rule: raise ValueError('unique does not accept a left operand.')
            else:
                if 'left' not in rule: raise ValueError('count/sum require a left operand.')
                _pointer(rule['left'])
            _pointer(rule['right'])
            if 'field' in rule and (not isinstance(rule['field'],str) or not rule['field'] or len(rule['field'])>256):
                raise ValueError('Relation field must be a plain field name.')
            if rule['op']=='count' and 'field' in rule:
                raise ValueError('count does not accept a field.')
    if 'http' in value:
        _keys(value['http'], {'status','headers'}, {'status'})
        if type(value['http']['status']) is not int or value['http']['status'] not in {200,201,202,400,404,409,422,500,503}:
            raise ValueError('HTTP contract status is outside the supported fixture profile.')
        headers = value['http'].get('headers',{})
        if not isinstance(headers,dict) or len(headers)>32 or any(not isinstance(k,str) or not isinstance(v,str)
                or not re.fullmatch(r'[A-Za-z][A-Za-z0-9-]*',k) or re.search(r'[^\x20-\x7e]',v) for k,v in headers.items()):
            raise ValueError('Contract HTTP headers require plain ASCII names and values.')
        if len({key.lower() for key in headers}) != len(headers):
            raise ValueError('Contract HTTP headers must be unique ignoring case.')
    if language == 'html':
        html = value.get('html')
        _keys(html, {'required_ids','table'}, {'table'})
        if 'required_ids' in html:
            _strings(html['required_ids'])
        table = html['table']; _keys(table, {'columns','row_count','rows'}, {'columns','row_count'})
        _strings(table['columns'], limit=32)
        if type(table['row_count']) is not int or not 1 <= table['row_count'] <= 512:
            raise ValueError('HTML table row_count must be in 1..512.')
        if 'rows' in table and (not isinstance(table['rows'],list) or len(table['rows']) != table['row_count']
                or any(not isinstance(row,list) or len(row) != len(table['columns']) or any(not isinstance(cell,str) for cell in row) for row in table['rows'])):
            raise ValueError('HTML rows must match the specified table shape, with text cells.')
    return value


def validate_contract(value):
    """Reject malformed types consistently, including malformed nested schema fields."""
    try:
        return _validate_contract(value)
    except (TypeError,KeyError,OverflowError,RecursionError):
        raise ValueError('Contract contains invalid field types or excessive nesting.') from None


def load_contract(path):
    path = Path(path)
    if path.stat().st_size > 131072:
        raise ValueError('Contract exceeds 128 KiB.')
    return validate_contract(strict_json(path.read_text(encoding='utf-8')))


def contract_digest(contract):
    return hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()


def _at(document, path):
    if path == '':
        return document
    for component in path.split('/')[1:]:
        component = component.replace('~1','/').replace('~0','~')
        if isinstance(document,list):
            if not re.fullmatch(r'0|[1-9][0-9]*',component):
                raise ValueError('Array pointer needs a nonnegative canonical index: '+path)
            index = int(component)
            if index >= len(document):
                raise ValueError('Missing array index: '+path)
            document = document[index]
        elif isinstance(document,dict) and component in document:
            document = document[component]
        else:
            raise ValueError('Missing document field: '+path)
    return document


def _same(left,right):
    if type(left) is not type(right): return False
    if isinstance(left,dict): return left.keys()==right.keys() and all(_same(left[key],right[key]) for key in left)
    if isinstance(left,list): return len(left)==len(right) and all(_same(a,b) for a,b in zip(left,right))
    return left==right


def _check_shape(item, shape, path='$'):
    matches = {'object':type(item) is dict,'array':type(item) is list,'string':type(item) is str,
               'integer':type(item) is int,'number':type(item) in {int,float},'boolean':type(item) is bool,'null':item is None}
    if not matches[shape['type']]: raise ValueError(path+' requires '+shape['type'])
    if 'enum' in shape and not any(_same(item,entry) for entry in shape['enum']): raise ValueError(path+' is outside its enum')
    if isinstance(item,dict):
        for key in shape.get('required',[]):
            if key not in item: raise ValueError(path+' missing required field '+key)
        properties = shape.get('properties',{})
        if shape.get('additional_properties') is False and item.keys()-properties.keys():
            raise ValueError(path+' contains unrequested fields')
        for key,schema in properties.items():
            if key in item: _check_shape(item[key],schema,path+'/'+key)
    if isinstance(item,list):
        if not shape.get('min_items',0) <= len(item) <= shape.get('max_items',10000): raise ValueError(path+' array length is outside the contract')
        if 'items' in shape:
            for index,value in enumerate(item): _check_shape(value,shape['items'],path+'/'+str(index))


def _check_document(document, contract):
    _check_shape(document,contract['shape'])
    for rule in contract.get('equals',[]):
        if not _same(_at(document,rule['path']),rule['value']):
            raise ValueError('Document value differs at '+rule['path'])
    for rule in contract.get('relations',[]):
        left = _at(document,rule['left']) if rule['op']!='unique' else None
        right = _at(document,rule['right'])
        if not isinstance(right,list): raise ValueError('Relation requires an array at '+rule['right'])
        if rule['op']=='count':
            if type(left) is not int or left != len(right): raise ValueError('Count does not match '+rule['right'])
        else:
            values = [entry[rule['field']] for entry in right] if 'field' in rule else right
            if rule['op']=='sum':
                if (type(left) not in {int,float} or any(type(v) not in {int,float} for v in values)
                        or (left!=sum(values) if type(left) is int and all(type(v) is int for v in values)
                            else not math.isclose(left,sum(values),rel_tol=1e-12,abs_tol=1e-12))):
                    raise ValueError('Sum does not match '+rule['right'])
            elif len({json.dumps(value,sort_keys=True) for value in values}) != len(values):
                raise ValueError('Duplicate values in '+rule['right'])


def check_contract(source, contract):
    """Return bounded diagnostics; integer examples are interpreted, never imported/executed."""
    contract = validate_contract(contract)
    language = contract['language']
    metrics = {'contract_sha256':contract_digest(contract),'examples':0}
    try:
        if language in {'json','http','binary-info'}:
            if language=='http':
                status,headers,body,_ = _http_parts(source)
                required = contract.get('http',{})
                if required and int(status.split()[1]) != required['status']: raise ValueError('HTTP status differs from contract')
                actual = {name.lower():value for name,value in headers}
                for key,value in required.get('headers',{}).items():
                    if actual.get(key.lower()) != value: raise ValueError('HTTP header differs: '+key)
                document = strict_json(body)
            else:
                if language=='binary-info': binary_metrics(source)
                document = strict_json(source)
            _check_document(document,contract['document'])
        elif language=='html':
            import html5lib
            root = html5lib.parse(source,namespaceHTMLElements=False)
            ids = [element.get('id') for element in root.iter() if element.get('id')]
            if len(set(ids)) != len(ids) or set(contract['html'].get('required_ids',[]))-set(ids):
                raise ValueError('HTML required IDs are missing or duplicated')
            for element in root.iter():
                for attribute in ('aria-labelledby','aria-describedby'):
                    if set(element.get(attribute,'').split())-set(ids): raise ValueError('HTML ARIA reference has no matching ID')
            tables = list(root.iter('table'))
            if len(tables)!=1: raise ValueError('HTML contract requires exactly one reference table')
            rows = [[' '.join(''.join(cell.itertext()).split()) for cell in row if cell.tag in {'th','td'}] for row in tables[0].iter('tr')]
            table = contract['html']['table']
            if not rows or rows[0]!=table['columns']: raise ValueError('HTML column names or order differ from contract')
            if len(rows)-1!=table['row_count'] or any(len(row)!=len(table['columns']) for row in rows[1:]): raise ValueError('HTML table dimensions differ from contract')
            if 'rows' in table and rows[1:]!=table['rows']: raise ValueError('HTML table cells differ from contract')
            metrics['rows']=len(rows)-1
        else:
            function = contract['function']
            if language=='python':
                program = IntegerProgram(source,function['name'],function['parameters'])
                evaluate = program.evaluate
            elif language=='llvm':
                program = IntegerIR(source,function['name'],function['parameters'],function['parameter_types'],function['return_type'],contract['llvm']['instructions'])
                evaluate = program.evaluate
            else:
                inspect_sql(source)
                code,aliases = _code(source)
                if aliases != {function['name']} or set(re.findall(r'(?<!:):([A-Za-z_][A-Za-z_0-9]*)',code)) != set(function['parameters']):
                    raise ValueError('SQL alias or parameter names differ from contract')
                connection = sqlite3.connect(':memory:')
                def authorize(action,first,second,_db,_trigger):
                    return sqlite3.SQLITE_OK if action==sqlite3.SQLITE_SELECT or action==sqlite3.SQLITE_FUNCTION and (second or first or '').lower() in _PURE_FUNCTIONS else sqlite3.SQLITE_DENY
                connection.set_authorizer(authorize)
                def evaluate(arguments):
                    budget=[10000]
                    def progress():
                        budget[0]-=100
                        return int(budget[0]<=0)
                    connection.set_progress_handler(progress,100)
                    cursor = connection.execute(source,dict(zip(function['parameters'],arguments)))
                    rows = cursor.fetchall()
                    if len(rows)!=1 or len(rows[0])!=1 or [c[0] for c in cursor.description] != [function['name']]:
                        raise ValueError('SQL must return one contracted scalar column')
                    return rows[0][0]
            try:
                for number,example in enumerate(contract['examples'],1):
                    actual = evaluate(example['inputs'])
                    if not _same(actual,example['expected']):
                        raise ValueError('Public example '+str(number)+' failed: expected '+repr(example['expected'])+', got '+repr(actual))
                    metrics['examples']+=1
            finally:
                if language=='sql': connection.close()
    except (ValueError,TypeError,KeyError,IndexError,RecursionError,ArithmeticError,sqlite3.Error) as error:
        return {'passed':False,'diagnostic':str(error)[:1200],'metrics':metrics}
    return {'passed':True,'diagnostic':'','metrics':metrics}
