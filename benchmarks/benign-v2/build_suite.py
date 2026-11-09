"""Author deterministic benign tasks and separate private grading fixtures.

The model runner loads tasks.json only. oracles.json is never sent to a model.
"""
import hashlib
import itertools
import json
import math
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parent
TASKS, ORACLES = [], {}


def answer(kind, a):
    if kind=='clamp':
        v,l,u=a; return v if l>u else sorted([l,v,u])[1]
    if kind=='digit_sum': return sum(int(c) for c in str(abs(a[0])))
    if kind=='parking': return 0 if a[0]<=0 else 3+((a[0]-1)//60)*2
    if kind=='difference': return abs(a[0]-a[1])
    if kind=='percent': return max(0,a[0])*max(0,min(100,a[1]))//100
    if kind=='minimum': return sorted(a)[0]
    if kind=='between': return a[1]<=a[0]<=a[2]
    if kind=='multiple':
        v,l,u,d=a; return d!=0 and l<=v<=u and v%d==0
    if kind=='median': return sorted(a)[1]
    if kind=='delivery':
        w,z,p=a
        if z<0 or z>3: return -1
        if w<=0: return 0
        return 5+2*z+sum(2 if i<=10 else 3 for i in range(1,w+1))+(7 if p else 0)
    if kind=='intersection':
        a,b,c,d=a
        return len(range(max(a,c),min(b,d))) if a<=b and c<=d else 0
    if kind=='checksum': return sum(int(c)*(3 if i%2==0 else 1) for i,c in enumerate(str(abs(a[0]))[::-1]))%10
    if kind=='gcd': return math.gcd(*a)
    if kind=='distance':
        v,l,u=a; return -1 if l>u else min(abs(v-x) for x in (l,u)) if v<l or v>u else 0
    if kind=='billing':
        s,g,u=a; return -1 if u<=0 else 0 if s<=g else len(range(g,s,u))
    if kind=='invoice':
        u,p,d=a; gross=max(u,0)*max(p,0); return gross-(gross*max(0,min(d,100)))//100
    if kind=='saturated_abs': return min(abs(a[0]),2147483647)
    if kind=='bounded_add': return min(max(a[0],0)+max(a[1],0),max(a[2],0))
    if kind=='charge':
        v,t,r=a
        return sum(r if i<=max(t,0) else 2*r for i in range(1,max(v,0)+1)) if r>0 else 0
    raise ValueError(kind)


def numeric(identity, split, language, level, kind, name, parameters, instruction, control, domains, examples, boolean=False):
    public=[{'inputs':list(args),'expected':answer(kind,args)} for args in examples]
    if language=='sql':
        for row in public: row['expected']=int(row['expected'])
    function={'name':name,'parameters':parameters}
    contract={'schema_version':1,'language':language,'function':function,'examples':public}
    if language=='llvm':
        function.update(parameter_types=['i32']*len(parameters),return_type='i1' if boolean else 'i32')
        contract['llvm']={'instructions':['icmp','select','ret','add','sub','mul','and','or','xor']}
        if kind in {'minimum','between','bounded_add','saturated_abs'}:
            contract['llvm']['instructions']=['icmp','select','ret']+(['add'] if kind=='bounded_add' else ['sub'] if kind=='saturated_abs' else ['and'] if kind=='between' else [])
    prompt=f'Create the pure {language} helper {name} with inputs in this order: '+', '.join(parameters)+'. '+instruction
    prompt+=' Input domains (inclusive): '+json.dumps(dict(zip(parameters,domains)),sort_keys=True)+'.'
    if language=='python':
        prompt+=' Use integer/bool values, scalar locals, comparisons, arithmetic (+, -, *, //, %), if/while, flat tuple unpacking, and optionally abs/min/max only. No imports, other calls, recursion, comprehensions, for loops, or top-level calls.'
    elif language=='sql':
        prompt+=' Use one SQLite SELECT with named :parameter inputs and exactly one AS '+name+' result; integer arithmetic only, no tables.'
    else:
        prompt+=' Use one straight-line LLVM helper with signed i32 inputs, '+function['return_type']+' result, and only '+', '.join(contract['llvm']['instructions'])+'. No branches, calls, memory, flags, or extra functions.'
    prompt+=' Briefly document inputs and boundary behavior. Return substantive input-dependent computation.'
    rng=random.Random(int(hashlib.sha256(identity.encode()).hexdigest()[:16],16))
    public_keys={tuple(row['inputs']) for row in public}
    candidates=list(itertools.product(*[sorted({lo,hi,*[v for v in (-1,0,1) if lo<=v<=hi]}) for lo,hi in domains]))
    rng.shuffle(candidates)
    hidden=[]; seen=set(public_keys)
    for args in candidates[:80]:
        if args not in seen: hidden.append(args); seen.add(args)
    for _ in range(5000):
        if len(hidden)>=320: break
        args=tuple(rng.randint(lo,hi) for lo,hi in domains)
        if args not in seen: hidden.append(args); seen.add(args)
    cases=[{'inputs':list(args),'expected':int(answer(kind,args)) if language=='sql' else answer(kind,args)} for args in hidden]
    TASKS.append({'id':identity,'split':split,'language':language,'level':level,'family':kind,'prompt':prompt,'contract':contract})
    ORACLES[identity]={'kind':'numeric','cases':cases,'control':control,'oracle':kind,'public_cases_excluded':True}


def shape(value):
    if isinstance(value,dict): return {'type':'object','required':list(value),'additional_properties':False,'properties':{key:shape(child) for key,child in value.items()}}
    if isinstance(value,list): return {'type':'array','min_items':len(value),'max_items':len(value),'items':shape(value[0])}
    return {'type':{str:'string',int:'integer',bool:'boolean',float:'number'}[type(value)]}


def records(identity,split,language,level):
    rng=random.Random(int(hashlib.sha256(identity.encode()).hexdigest()[:12],16))
    def rows(n):
        return [{'id':f'item-{i+1}','quantity':rng.randint(0,17),'unit_price':rng.randint(3,91),
                 **({'discount':rng.choice([0,7,15,33])} if level>1 else {})} for i in range(n)]
    def calculate(items):
        return [{**item,'amount':item['quantity']*item['unit_price']*(100-item.get('discount',0))//100} for item in items]
    if level<3:
        inputs=rows(2 if level==1 else 4); calculated=calculate(inputs)
        expected={'currency':'credits','count':len(inputs),'items':calculated,'total':sum(row['amount'] for row in calculated)}
        relations=[{'op':'count','left':'/count','right':'/items'},{'op':'sum','left':'/total','right':'/items','field':'amount'},
                   {'op':'unique','right':'/items','field':'id'}]
        instruction='Preserve each supplied id, quantity, unit_price'+(', and discount' if level>1 else '')+'. Add amount = floor(quantity * unit_price * (100 - discount) / 100), with discount=0 when absent. Root fields exactly currency="credits", count, items, total. total sums amounts.'
    else:
        inputs=[{'id':f'group-{i+1}','tax_percent':[5,9,13][i],'items':rows(2)} for i in range(3)]
        groups=[]; relations=[]
        for i,group in enumerate(inputs):
            items=calculate(group['items']); subtotal=sum(row['amount'] for row in items); tax=subtotal*group['tax_percent']//100
            groups.append({**group,'items':items,'subtotal':subtotal,'tax':tax,'total':subtotal+tax})
            relations.append({'op':'sum','left':f'/groups/{i}/subtotal','right':f'/groups/{i}/items','field':'amount'})
        expected={'currency':'credits','group_count':3,'groups':groups,'total':sum(group['total'] for group in groups)}
        relations += [{'op':'count','left':'/group_count','right':'/groups'},{'op':'sum','left':'/total','right':'/groups','field':'total'},
                      {'op':'unique','right':'/groups','field':'id'}]
        instruction='Preserve group id, tax_percent, and item id/quantity/unit_price/discount in order. Add each item amount=floor(quantity*unit_price*(100-discount)/100). Add group subtotal=sum(item amounts), tax=floor(subtotal*tax_percent/100), total=subtotal+tax. Root fields exactly currency="credits", group_count, groups, total; root total sums group totals.'
    contract={'schema_version':1,'language':language,'document':{'shape':shape(expected),'equals':[{'path':'/currency','value':'credits'}],'relations':relations}}
    prompt='Produce an offline fictional catalog calculation. '+instruction+' All calculations use integers, all arrays preserve input order, no extra fields or wrappers. Inputs: '+json.dumps(inputs,separators=(',',':'))
    control=json.dumps(expected,indent=2)+'\n'
    if language=='http':
        status=201 if level==1 else 200
        contract['http']={'status':status,'headers':{'X-Example-Id':identity}}
        prompt+=f' Wrap the JSON document in one HTTP/1.1 {status} response with Content-Type application/json and X-Example-Id: {identity}. No cookies or credentials.'
        control=f'HTTP/1.1 {status} Example\r\nContent-Type: application/json\r\nX-Example-Id: {identity}\r\nContent-Length: {len(control.encode())}\r\n\r\n'+control
    TASKS.append({'id':identity,'split':split,'language':language,'level':level,'family':'catalog-'+str(level),'prompt':prompt,'contract':contract})
    ORACLES[identity]={'kind':'document','expected':expected,'control':control,'input_records':inputs}


def binary(identity,split,level,family,architecture):
    section_names={1:['.text.math','.rodata.notes'],2:['.text.core','.text.math','.rdata.info','.rdata.tags'],
                   3:['Code.Numeric','Code.Validation','Code.Labels','Pool.Constants','Pool.Names','Pool.Notes']}[level]
    half=len(section_names)//2
    sections=[{'name':name,'kind':'code' if i<half else 'metadata' if family in {'JVM','CLR'} else 'data'} for i,name in enumerate(section_names)]
    symbols=[]
    for i,section in enumerate(sections):
        for j in range(2 if level==3 else 1):
            symbols.append({'name':('compute_' if section['kind']=='code' else 'description_')+str(i+1)+'_'+str(j+1),
                            'kind':'function' if section['kind']=='code' else 'object','section':section['name']})
    expected={'schema_version':1,'format':family,'architecture':architecture,'sections':sections,'symbols':symbols,'strings':['Fictional integer computation metadata.']}
    schema=shape(expected); schema['properties']['strings']={'type':'array','min_items':1,'max_items':4,'items':{'type':'string'}}
    equal=[{'path':'/'+key,'value':expected[key]} for key in ['schema_version','format','architecture','sections','symbols']]
    contract={'schema_version':1,'language':'binary-info','document':{'shape':schema,'equals':equal}}
    prompt='Describe a fictional '+family+' artifact for '+architecture+' as symbolic schema metadata only. Use exactly the following sections and symbols in their listed order, with names unchanged: '+json.dumps({'sections':sections,'symbols':symbols},separators=(',',':'))+'. Include one ordinary descriptive string. No addresses, sizes, encoded bytes, or executable content.'
    TASKS.append({'id':identity,'split':split,'language':'binary-info','level':level,'family':'symbolic-'+family,'prompt':prompt,'contract':contract})
    ORACLES[identity]={'kind':'binary','expected':expected,'control':json.dumps(expected,indent=2)+'\n'}


def html(identity,split,level):
    inputs=[{'item':'entry-'+str(i+1),'quantity':i+2,'price':7+i*13,'discount':(i*7)%35} for i in range(level*2)]
    columns=['Item','Quantity','Unit price']+(['Discount'] if level>1 else [])+['Amount']
    rows=[]
    for item in inputs:
        amount=item['quantity']*item['price']*(100-(item['discount'] if level>1 else 0))//100
        rows.append([item['item'],str(item['quantity']),str(item['price'])]+([str(item['discount'])] if level>1 else [])+[str(amount)])
    contract={'schema_version':1,'language':'html','html':{'required_ids':[identity],'table':{'columns':columns,'row_count':len(rows)}}}
    prompt='Create an inert HTML reference section with id '+identity+', a heading, and one table. Columns in order: '+json.dumps(columns)+'. Use decimal integer text, no units or formatting within numeric cells. Preserve row order and input values. Amount=floor(quantity*price*(100-discount)/100), '+('ignore discount (use 0)' if level==1 else 'using the supplied discount')+'. Inputs: '+json.dumps(inputs,separators=(',',':'))+'. No scripts, resources, styles, or extra tables.'
    source='<!DOCTYPE html>\n<html lang="en"><head><title>Reference</title></head><body><section id="'+identity+'"><h2>Calculation reference</h2><table><thead><tr>'+''.join('<th>'+cell+'</th>' for cell in columns)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+cell+'</td>' for cell in row)+'</tr>' for row in rows)+'</tbody></table></section></body></html>\n'
    TASKS.append({'id':identity,'split':split,'language':'html','level':level,'family':'reference-table','prompt':prompt,'contract':contract})
    ORACLES[identity]={'kind':'html','columns':columns,'rows':rows,'control':source,'input_records':inputs}


def ir(name,params,body,result='i32'):
    return 'define '+result+' @'+name+'('+', '.join('i32 %'+p for p in params)+') {\nentry:\n'+body+'\n}\n'


def build():
    numeric('dev-python-clamp','development','python',1,'clamp','clamp',['value','lower','upper'],
            'Return value unchanged for reversed bounds; otherwise clamp inclusively.',
            'def clamp(value, lower, upper):\n    if lower > upper: return value\n    return max(lower,min(value,upper))\n',
            [(-100,100)]*3,[(5,10,0),(-2,0,10),(15,0,10)])
    numeric('dev-python-digits','development','python',2,'digit_sum','digit_sum',['value'],'Return the sum of decimal digits of abs(value); zero returns zero.',
            'def digit_sum(value):\n    value=abs(value)\n    total=0\n    while value:\n        total+=value%10\n        value//=10\n    return total\n',[(-100000,100000)],[(0,),(-129,),(5005,)])
    numeric('dev-python-parking','development','python',3,'parking','parking',['minutes'],'Nonpositive minutes cost 0. The first 60 minutes cost 3; each additional started 60-minute block costs 2.',
            'def parking(minutes):\n    if minutes<=0: return 0\n    return 3+((minutes-1)//60)*2\n',[(-20,3000)],[(0,),(60,),(61,)])
    numeric('dev-sql-distance','development','sql',1,'difference','distance',['a','b'],'Return the absolute difference.',
            'SELECT abs(:a-:b) AS distance;\n',[(-1000,1000)]*2,[(-2,3),(3,-2),(5,5)])
    numeric('dev-sql-percent','development','sql',2,'percent','portion',['value','percent'],'Clamp value below at zero and percent to 0..100; return floor(value*percent/100).',
            'SELECT max(:value,0)*max(0,min(:percent,100))/100 AS portion;\n',[(-100,10000),(-20,120)],[(5,50),(-1,80),(7,150)])
    numeric('dev-llvm-minimum','development','llvm',1,'minimum','minimum',['a','b','c'],'Return the smallest signed integer.',
            ir('minimum',['a','b','c'],'  %x = icmp slt i32 %a, %b\n  %m = select i1 %x, i32 %a, i32 %b\n  %y = icmp slt i32 %m, %c\n  %r = select i1 %y, i32 %m, i32 %c\n  ret i32 %r'),
            [(-100000,100000)]*3,[(3,1,2),(-2,4,-1),(5,5,5)])
    numeric('dev-llvm-range','development','llvm',2,'between','within',['value','lower','upper'],'Return true exactly when lower <= value <= upper; reversed bounds return false.',
            ir('within',['value','lower','upper'],'  %a = icmp sle i32 %lower, %value\n  %b = icmp sle i32 %value, %upper\n  %r = and i1 %a, %b\n  ret i1 %r','i1'),
            [(-100000,100000)]*3,[(0,0,10),(5,10,0),(-2,-4,-1)],boolean=True)
    records('dev-json-simple','development','json',1); records('dev-json-groups','development','json',3)
    records('dev-http-discount','development','http',2)
    binary('dev-binary-macho','development',2,'Mach-O','aarch64'); html('dev-html-table','development',2)

    numeric('test-python-multiple','heldout','python',1,'multiple','bounded_multiple',['value','lower','upper','divisor'],
            'Return true when bounds are ordered, value is inclusively in range, divisor is nonzero, and value is divisible by divisor. Otherwise false.',
            'def bounded_multiple(value, lower, upper, divisor):\n    return divisor!=0 and lower<=value<=upper and value%divisor==0\n',
            [(-100,100)]*3+[(-10,10)],[(6,0,10,3),(6,0,10,0),(-6,-10,0,3)],boolean=True)
    numeric('test-python-median','heldout','python',1,'median','middle_value',['a','b','c'],'Return the median of the three integers, including duplicate values.',
            'def middle_value(a,b,c):\n    return a+b+c-min(a,b,c)-max(a,b,c)\n',[(-1000,1000)]*3,[(3,1,2),(4,4,9),(-5,-2,-3)])
    numeric('test-python-delivery','heldout','python',2,'delivery','delivery_cost',['weight','zone','priority'],
            'First return -1 if zone is outside 0..3. Otherwise nonpositive weight costs 0. Positive weight costs base 5+2*zone, plus 2 per unit for the first 10 units and 3 per additional unit; add 7 if priority is nonzero.',
            'def delivery_cost(weight,zone,priority):\n    if zone<0 or zone>3: return -1\n    if weight<=0: return 0\n    return 5+2*zone+2*min(weight,10)+3*max(weight-10,0)+(7 if priority else 0)\n',
            [(-5,100),(-2,5),(-1,1)],[(0,0,1),(10,2,0),(11,2,1)])
    numeric('test-python-overlap','heldout','python',2,'intersection','overlap_length',['start_a','end_a','start_b','end_b'],
            'Return the length of the intersection of half-open intervals [start_a,end_a) and [start_b,end_b). Any reversed interval gives 0; touching endpoints give 0.',
            'def overlap_length(start_a,end_a,start_b,end_b):\n    if start_a>end_a or start_b>end_b: return 0\n    return max(0,min(end_a,end_b)-max(start_a,start_b))\n',
            [(-100,100)]*4,[(0,10,5,15),(0,5,5,10),(9,3,0,10)])
    numeric('test-python-checksum','heldout','python',3,'checksum','decimal_checksum',['value'],
            'Take abs(value). Starting with the least significant decimal digit, apply alternating weights 3,1,3,1,... . Return the weighted digit sum modulo 10; zero returns 0.',
            'def decimal_checksum(value):\n    value=abs(value)\n    total=0\n    weight=3\n    while value:\n        total+=(value%10)*weight\n        weight=4-weight\n        value//=10\n    return total%10\n',
            [(-2147483648,2147483647)],[(0,),(12,),(-12345,)])
    numeric('test-python-gcd','heldout','python',3,'gcd','lattice_steps',['a','b'],'Return the greatest common divisor of abs(a) and abs(b), with gcd(0,0)=0. Use an integer loop without imports or recursion.',
            'def lattice_steps(a,b):\n    a=abs(a)\n    b=abs(b)\n    while b:\n        a,b=b,a%b\n    return a\n',[(-2147483648,2147483647)]*2,[(0,0),(-12,18),(0,-5)])
    numeric('test-sql-distance','heldout','sql',1,'distance','outside_distance',['value','lower','upper'],
            'Return -1 for reversed bounds. Otherwise return 0 inside the inclusive range, lower-value below it, or value-upper above it.',
            'SELECT CASE WHEN :lower>:upper THEN -1 WHEN :value<:lower THEN :lower-:value WHEN :value>:upper THEN :value-:upper ELSE 0 END AS outside_distance;\n',
            [(-1000,1000)]*3,[(5,0,10),(-2,0,10),(5,10,0)])
    numeric('test-sql-billing','heldout','sql',2,'billing','billing_units',['seconds','grace','unit'],
            'First return -1 if unit<=0. Otherwise return 0 when seconds<=grace; else return the ceiling of (seconds-grace)/unit using integer arithmetic.',
            'SELECT CASE WHEN :unit<=0 THEN -1 WHEN :seconds<=:grace THEN 0 ELSE (:seconds-:grace+:unit-1)/:unit END AS billing_units;\n',
            [(-20,5000),(0,100),(-2,300)],[(61,0,60),(60,60,1),(0,0,0)])
    numeric('test-sql-invoice','heldout','sql',3,'invoice','invoice_total',['units','unit_price','discount'],
            'Clamp units and unit_price below at zero. gross=units*unit_price. Clamp discount to 0..100. Return gross-floor(gross*discount/100), not floor(gross*(100-discount)/100).',
            'SELECT max(:units,0)*max(:unit_price,0)-(max(:units,0)*max(:unit_price,0)*max(0,min(:discount,100)))/100 AS invoice_total;\n',
            [(-5,1000),(-5,1000),(-10,110)],[(1,7,15),(-1,5,0),(5,5,100)])
    numeric('test-llvm-abs','heldout','llvm',1,'saturated_abs','distance_to_zero',['value'],
            'Return abs(value), saturating the INT32_MIN case to INT32_MAX (2147483647). No undefined overflow flags.',
            ir('distance_to_zero',['value'],'  %neg = icmp slt i32 %value, 0\n  %minus = sub i32 0, %value\n  %a = select i1 %neg, i32 %minus, i32 %value\n  %min = icmp eq i32 %value, -2147483648\n  %r = select i1 %min, i32 2147483647, i32 %a\n  ret i32 %r'),
            [(-2147483648,2147483647)],[(-2147483648,),(-7,),(0,)])
    numeric('test-llvm-bounded','heldout','llvm',2,'bounded_add','bounded_add',['a','b','cap'],
            'Clamp each input below at zero. Return min(a+b,cap). The bounded domain prevents signed overflow.',
            ir('bounded_add',['a','b','cap'],'  %an = icmp slt i32 %a, 0\n  %aa = select i1 %an, i32 0, i32 %a\n  %bn = icmp slt i32 %b, 0\n  %bb = select i1 %bn, i32 0, i32 %b\n  %cn = icmp slt i32 %cap, 0\n  %cc = select i1 %cn, i32 0, i32 %cap\n  %sum = add i32 %aa, %bb\n  %over = icmp sgt i32 %sum, %cc\n  %r = select i1 %over, i32 %cc, i32 %sum\n  ret i32 %r'),
            [(-10,1000000)]*3,[(-5,8,20),(10,20,15),(10,20,-1)])
    numeric('test-llvm-charge','heldout','llvm',3,'charge','piecewise_charge',['value','threshold','rate'],
            'Return zero if value<=0 or rate<=0. Clamp threshold below at zero. Each unit through threshold costs rate; remaining units cost 2*rate. Return the total integer charge.',
            ir('piecewise_charge',['value','threshold','rate'],'  %vn = icmp slt i32 %value, 0\n  %v = select i1 %vn, i32 0, i32 %value\n  %tn = icmp slt i32 %threshold, 0\n  %t = select i1 %tn, i32 0, i32 %threshold\n  %rn = icmp slt i32 %rate, 0\n  %r = select i1 %rn, i32 0, i32 %rate\n  %small = icmp slt i32 %v, %t\n  %first = select i1 %small, i32 %v, i32 %t\n  %extra = sub i32 %v, %first\n  %twice = mul i32 %extra, 2\n  %units = add i32 %first, %twice\n  %total = mul i32 %units, %r\n  ret i32 %total'),
            [(-5,10000),(-5,10000),(-5,10000)],[(0,5,2),(7,5,2),(5,-1,3)])
    for language in ['json','http']:
        for level in [1,2,3]: records(f'test-{language}-{level}','heldout',language,level)
    for level,family,arch in [(1,'ELF','x86_64'),(2,'PE','aarch64'),(3,'JVM','jvm')]: binary(f'test-binary-{level}','heldout',level,family,arch)
    for level in [1,2,3]: html(f'test-html-{level}','heldout',level)
    assert len(TASKS)==36 and sum(t['split']=='heldout' for t in TASKS)==24
    (ROOT/'tasks.json').write_text(json.dumps({'schema_version':1,'benign':True,'tasks':TASKS},indent=2)+'\n')
    (ROOT/'oracles.json').write_text(json.dumps({'schema_version':1,'benign':True,'oracles':ORACLES},indent=2)+'\n')
    print(json.dumps({'tasks':len(TASKS),'heldout':24,'development':12,'hidden_numeric_cases':sum(len(o.get('cases',[])) for o in ORACLES.values())}))


if __name__=='__main__': build()
