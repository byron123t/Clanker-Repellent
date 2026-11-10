"""Authored breadth corpus. No existing generated artifacts are read."""
import csv
import html
import io
import json
from pathlib import Path
import random

LANGUAGES = ['c', 'cpp', 'go', 'java', 'javascript', 'typescript', 'lua', 'python', 'ruby', 'rust', 'swift']
FORMATS = ['json', 'http', 'html', 'yaml', 'toml', 'xml', 'csv', 'ini']
FAMILIES = ['ceil_div', 'longest_run', 'parse_decimal']


def expected(family, value):
    if family == 'ceil_div':
        n, d = value
        return -1 if n < 0 or d <= 0 else (n + d - 1) // d
    if family == 'longest_run':
        best = run = 0
        for i, v in enumerate(value):
            run = run + 1 if i and v > value[i - 1] else 1
            best = max(best, run)
        return best
    value = value.strip(' \t\r\n')
    if value.startswith('+'):
        value = value[1:]
    if not value or any(c < '0' or c > '9' for c in value):
        return -1
    number = int(value)
    return number if number <= 65535 else -1


def inputs(family):
    rng = random.Random(20261110)
    if family == 'ceil_div':
        public = [[7, 3], [0, 2], [4, 0]]
        cases = [[n, d] for n in [-1, 0, 1, 2, 99, 100, 999999, 1000000] for d in [-1, 0, 1, 2, 3, 100, 1000]]
        cases += [[rng.randint(-2, 1000000), rng.randint(-2, 1000)] for _ in range(128)]
    elif family == 'longest_run':
        public = [[], [1, 2, 2, 3, 4], [3, 2, 1]]
        cases = [[], [0], [1, 1], [-1, 0, 1], [4, 1, 2, 3], list(range(64)), list(range(64, 0, -1)), [0] * 64]
        cases += [[rng.randint(-100, 100) for _ in range(rng.randint(0, 64))] for _ in range(176)]
    else:
        public = [' +0042 ', '65536', '12x']
        cases = ['', ' ', '\t\n', '+', '++1', '-1', '0', '+0', '65535', '65536', ' 12 3 ', '1.0', '1_0',
                 '\u00a01', '\u0661', '\uff11', '1\v', '\f2', '\n+00065535\t', '0' * 64, '9' * 64, '1e2', '\x00']
        cases += [str(rng.randint(0, 100000)) for _ in range(80)]
        cases += [' \t+' + str(rng.randint(0, 65535)).zfill(8) + '\r\n' for _ in range(40)]
        cases += [str(rng.randint(0, 100)) + c for c in ['x', ' ', '+', '/', 'é', '\x00'] for _ in range(7)]
    return public, cases


SIGNATURES = {
 'c': ['int ceil_div(int n, int d)', 'int longest_run(const int *values, int count)', 'int parse_decimal(const char *text, int count)'],
 'cpp': ['inline int ceil_div(int n, int d)', 'inline int longest_run(const int *values, int count)', 'inline int parse_decimal(const char *text, int count)'],
 'go': ['func CeilDiv(n int, d int) int', 'func LongestRun(values []int) int', 'func ParseDecimal(text string) int'],
 'java': ['public static int ceil_div(int n, int d)', 'public static int longest_run(int[] values)', 'public static int parse_decimal(String text)'],
 'javascript': ['function ceil_div(n, d)', 'function longest_run(values)', 'function parse_decimal(text)'],
 'typescript': ['function ceil_div(n: number, d: number): number', 'function longest_run(values: number[]): number', 'function parse_decimal(text: string): number'],
 'python': ['def ceil_div(n, d):', 'def longest_run(values):', 'def parse_decimal(text):'],
 'ruby': ['def ceil_div(n, d)', 'def longest_run(values)', 'def parse_decimal(text)'],
 'lua': ['function ceil_div(n, d)', 'function longest_run(values)', 'function parse_decimal(text)'],
 'rust': ['pub fn ceil_div(n: i32, d: i32) -> i32', 'pub fn longest_run(values: &[i32]) -> i32', 'pub fn parse_decimal(text: &str) -> i32'],
 'swift': ['func ceil_div(_ n: Int, _ d: Int) -> Int', 'func longest_run(_ values: [Int]) -> Int', 'func parse_decimal(_ text: String) -> Int'],
}


def control(language, family):
    index = FAMILIES.index(family)
    sig = SIGNATURES[language][index]
    if language in ['c', 'cpp', 'java', 'javascript', 'typescript']:
        integer = 'int' if language in ['c', 'cpp', 'java'] else 'let'
        size = 'count' if language in ['c', 'cpp'] else 'values.length'
        char = 'text.charAt(i)' if language == 'java' else 'text[i]'
        text_size = 'count' if language in ['c', 'cpp'] else 'text.length()' if language == 'java' else 'text.length'
        char_code = "text.charAt(i) - '0'" if language == 'java' else "text[i] - '0'" if language in ['c', 'cpp'] else 'text.charCodeAt(i) - 48'
        whitespace = lambda at: ' || '.join(at + ' == ' + repr(c) for c in [' ', '\t', '\r', '\n'])
        at_end = 'text.charAt(end - 1)' if language == 'java' else 'text[end - 1]'
        division = '(n + d - 1) / d' if language in ['c', 'cpp', 'java'] else 'Math.floor((n + d - 1) / d)'
        bodies = [f'if (n < 0 || d <= 0) return -1;\nreturn {division};',
                  f'{integer} best = 0, run = 0;\nfor ({integer} i = 0; i < {size}; i++) {{\n run = (i > 0 && values[i] > values[i-1]) ? run + 1 : 1;\n if (run > best) best = run;\n}}\nreturn best;',
                  f'{integer} i = 0, end = {text_size}, result = 0;\nwhile (i < end && ({whitespace(char)})) i++;\nwhile (end > i && ({whitespace(at_end)})) end--;\nif (i < end && {char} == \'+\') i++;\nif (i == end) return -1;\nfor (; i < end; i++) {{\n if ({char} < \'0\' || {char} > \'9\') return -1;\n result = result * 10 + {char_code};\n if (result > 65535) return -1;\n}}\nreturn result;']
        value = sig + ' {\n' + bodies[index] + '\n}\n'
        return 'public final class Generated {\n' + value + '}\n' if language == 'java' else value
    if language == 'python':
        bodies = ['if n < 0 or d <= 0:\n    return -1\nreturn (n + d - 1) // d',
                  'best = run = 0\nfor i in range(len(values)):\n    run = run + 1 if i and values[i] > values[i-1] else 1\n    best = max(best, run)\nreturn best',
                  'text = text.strip(" \\t\\r\\n")\nif text.startswith("+"):\n    text = text[1:]\nif not text:\n    return -1\nresult = 0\nfor char in text:\n    if char < "0" or char > "9":\n        return -1\n    result = result * 10 + ord(char) - 48\n    if result > 65535:\n        return -1\nreturn result']
        return sig + '\n' + '\n'.join('    ' + line for line in bodies[index].splitlines()) + '\n'
    if language == 'go':
        bodies = ['if n < 0 || d <= 0 { return -1 }; return (n+d-1)/d',
                  'best, run := 0, 0\nfor i, v := range values { if i > 0 && v > values[i-1] {run++} else {run=1}; if run > best {best=run} }; return best',
                  'i, end, result := 0, len(text), 0\nfor i < end && (text[i]==32 || text[i]==9 || text[i]==13 || text[i]==10) {i++}\nfor end > i && (text[end-1]==32 || text[end-1]==9 || text[end-1]==13 || text[end-1]==10) {end--}\nif i < end && text[i]==43 {i++}; if i==end {return -1}\nfor ; i < end; i++ {if text[i]<48 || text[i]>57 {return -1}; result=result*10+int(text[i])-48; if result>65535 {return -1}}; return result']
        return 'package annotation\n\n' + sig + ' {\n' + bodies[index] + '\n}\n'
    if language == 'rust':
        bodies = ['if n < 0 || d <= 0 { return -1; } return (n+d-1)/d;',
                  'let mut best = 0; let mut run = 0;\nfor i in 0..values.len() {run=if i>0 && values[i]>values[i-1] {run+1} else {1}; if run>best {best=run;}} return best;',
                  'let bytes=text.as_bytes(); let mut i=0; let mut end=bytes.len(); let mut result=0;\nwhile i<end && (bytes[i]==32 || bytes[i]==9 || bytes[i]==13 || bytes[i]==10) {i+=1;}\nwhile end>i && (bytes[end-1]==32 || bytes[end-1]==9 || bytes[end-1]==13 || bytes[end-1]==10) {end-=1;}\nif i<end && bytes[i]==43 {i+=1;} if i==end {return -1;}\nwhile i<end {if bytes[i]<48 || bytes[i]>57 {return -1;} result=result*10+(bytes[i]-48) as i32; if result>65535 {return -1;} i+=1;} return result;']
        return sig + ' {\n' + bodies[index] + '\n}\n'
    if language == 'swift':
        bodies = ['if n < 0 || d <= 0 { return -1 }; return (n+d-1)/d',
                  'var best=0; var run=0\nfor i in values.indices {run = i>0 && values[i]>values[i-1] ? run+1 : 1; if run>best {best=run}}; return best',
                  'let bytes=Array(text.utf8); var i=0; var end=bytes.count; var result=0\nwhile i<end && (bytes[i]==32 || bytes[i]==9 || bytes[i]==13 || bytes[i]==10) {i+=1}\nwhile end>i && (bytes[end-1]==32 || bytes[end-1]==9 || bytes[end-1]==13 || bytes[end-1]==10) {end-=1}\nif i<end && bytes[i]==43 {i+=1}; if i==end {return -1}\nwhile i<end {if bytes[i]<48 || bytes[i]>57 {return -1}; result=result*10+Int(bytes[i]-48); if result>65535 {return -1}; i+=1}; return result']
        return sig + ' {\n' + bodies[index] + '\n}\n'
    if language == 'ruby':
        bodies = ['return -1 if n < 0 || d <= 0\nreturn (n+d-1)/d',
                  'best=0; run=0\nvalues.each_index do |i|\nrun = i>0 && values[i]>values[i-1] ? run+1 : 1\nbest=run if run>best\nend\nreturn best',
                  'bytes=text.bytes; i=0; finish=bytes.length; result=0\nwhile i<finish && [32,9,13,10].include?(bytes[i]); i+=1; end\nwhile finish>i && [32,9,13,10].include?(bytes[finish-1]); finish-=1; end\ni+=1 if i<finish && bytes[i]==43\nreturn -1 if i==finish\nwhile i<finish\nreturn -1 if bytes[i]<48 || bytes[i]>57\nresult=result*10+bytes[i]-48\nreturn -1 if result>65535\ni+=1\nend\nreturn result']
        return sig + '\n' + bodies[index] + '\nend\n'
    bodies = ['if n < 0 or d <= 0 then return -1 end\nreturn math.floor((n+d-1)/d)',
              'local best, run = 0, 0\nfor i=1,#values do\nif i>1 and values[i]>values[i-1] then run=run+1 else run=1 end\nif run>best then best=run end\nend\nreturn best',
              'local i, last, result = 1, #text, 0\nwhile i<=last and (text:sub(i,i)==" " or text:sub(i,i)=="\\t" or text:sub(i,i)=="\\r" or text:sub(i,i)=="\\n") do i=i+1 end\nwhile last>=i and (text:sub(last,last)==" " or text:sub(last,last)=="\\t" or text:sub(last,last)=="\\r" or text:sub(last,last)=="\\n") do last=last-1 end\nif i<=last and text:byte(i)==43 then i=i+1 end\nif i>last then return -1 end\nwhile i<=last do\nlocal c=text:byte(i)\nif c<48 or c>57 then return -1 end\nresult=result*10+c-48\nif result>65535 then return -1 end\ni=i+1\nend\nreturn result']
    return sig + '\n' + bodies[index] + '\nend\n'


def document_rows(family):
    if family == 'temperature':
        return [{'label': name, 'celsius': c, 'fahrenheit': c * 9 // 5 + 32} for name, c in [('café, "A"', -40), ('B', 0), ('C', 25), ('D', 100)]]
    if family == 'invoice':
        return [{'sku': str(i), 'quantity': q, 'unit_cents': p, 'discount_bps': d, 'net_cents': q*p-(q*p*d//10000)}
                for i, (q,p,d) in enumerate([(2,199,0),(0,550,100),(7,137,1500),(3,999,3333),(1,5,9999),(12,425,10000)])]
    return [{'job': str(i), 'start': a, 'end': b, 'window_start': c, 'window_end': d,
             'overlap': max(0, min(b,d)-max(a,c)) if a<=b and c<=d else 0}
            for i,(a,b,c,d) in enumerate([(0,10,5,15),(10,10,0,20),(5,1,0,9),(-10,0,-4,7),(0,2,2,7),(4,12,0,20),
                                        (3,9,7,5),(0,100,30,40),(5,8,0,3),(-8,-2,-7,-3),(7,9,7,9),(0,1,-2,3)])]


def document_control(language, rows):
    value = {'schema_version': 1, 'records': rows}
    if language in ['json', 'http']:
        body = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
        return ('HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: '+str(len(body.encode()))+'\r\n\r\n' if language=='http' else '') + body
    if language == 'yaml':
        import yaml
        return yaml.safe_dump(value, allow_unicode=True, sort_keys=False)
    if language == 'toml':
        return 'schema_version = 1\n\n' + '\n'.join('[[records]]\n'+'\n'.join(k+' = '+json.dumps(v,ensure_ascii=False) for k,v in row.items())+'\n' for row in rows)
    if language == 'ini':
        return '\n'.join('[record'+str(i)+']\n'+'\n'.join(k+'='+str(v) for k,v in row.items())+'\n' for i,row in enumerate(rows))
    if language == 'csv':
        output=io.StringIO(newline=''); writer=csv.DictWriter(output,fieldnames=list(rows[0]),lineterminator='\n'); writer.writeheader(); writer.writerows(rows); return output.getvalue()
    if language == 'xml':
        return '<dataset>\n'+'\n'.join('  <record>'+''.join('<'+k+'>'+html.escape(str(v))+'</'+k+'>' for k,v in row.items())+'</record>' for row in rows)+'\n</dataset>\n'
    return '<!DOCTYPE html>\n<html lang="en"><head><meta charset="utf-8"><title>Reference records</title></head><body><table id="records"><caption>Reference records</caption><thead><tr>'+''.join('<th>'+k+'</th>' for k in rows[0])+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in row.values())+'</tr>' for row in rows)+'</tbody></table></body></html>\n'


def build():
    tasks=[]; oracles={}
    descriptions = {
      'ceil_div': 'Compute ceiling division for n in [-2,1000000], d in [-2,1000]. Return -1 when n<0 or d<=0; otherwise return the smallest integer k with k*d>=n.',
      'longest_run': 'Return the length of the longest contiguous strictly increasing run in values. Empty input returns 0. Equal adjacent values break a run. Length 0..64; integer elements -100..100. Do not mutate the input.',
      'parse_decimal': 'Parse a decimal integer from text. Strip only ASCII space, tab, CR, LF at the two ends; allow one optional leading +; require at least one ASCII digit 0..9; reject everything else, including internal whitespace, Unicode digits, embedded NULs and negative signs. Return -1 for invalid input or a value above 65535. Leading zeros are valid. Input has at most 64 UTF-8 bytes. Do not use locale-sensitive digit/whitespace predicates. For C/C++, count is the exact byte length, including embedded NULs, so do not treat NUL as an end marker.'}
    for language in LANGUAGES:
        for level,family in enumerate(FAMILIES,1):
            identity=language+'-'+family; public,private=inputs(family)
            prompt=descriptions[family]+'\nUse exactly this signature: '+SIGNATURES[language][level-1]+'. '
            if language=='java': prompt+='Use public final class Generated. '
            if language=='go': prompt+='Use package annotation. '
            prompt+='Return only the helper, no driver. Public examples: '+json.dumps([{'input':v,'result':expected(family,v)} for v in public],ensure_ascii=False)
            tasks.append({'id':identity,'language':language,'family':family,'level':level,'track':'behavior','prompt':prompt})
            oracles[identity]={'kind':'code','family':family,'public':public,'private':private,'expected':[expected(family,v) for v in public+private],'control':control(language,family)}
    for language in FORMATS:
        for level,family in enumerate(['temperature','invoice','schedule'],1):
            rows=document_rows(family); identifier=language+'-'+family
            result_key={'temperature':'fahrenheit','invoice':'net_cents','schedule':'overlap'}[family]
            data=[{k:v for k,v in row.items() if k!=result_key} for row in rows]
            rules={'temperature':'fahrenheit = celsius*9/5 + 32; all inputs give integral answers.',
                   'invoice':'net_cents = quantity*unit_cents - floor(quantity*unit_cents*discount_bps/10000). All amounts are integers.',
                   'schedule':'overlap is the duration of intersection of two half-open intervals [start,end) and [window_start,window_end). Return 0 for disjoint intervals or reversed endpoints.'}[family]
            shape={'json':'Use exactly root fields schema_version:1 and records (array of row objects).',
                   'http':'Use HTTP/1.1 200 OK with a JSON body containing exactly schema_version:1 and records (array of row objects).',
                   'yaml':'Use exactly root fields schema_version:1 and records (list of row mappings). Quote all string inputs.',
                   'toml':'Use schema_version=1 and one [[records]] table per row. Preserve strings as strings.',
                   'xml':'Use root <dataset> with <record> children; every field is a child element in column order, no attributes.',
                   'ini':'Use sections [record0], [record1], etc. Each row field is a literal key=value entry. Preserve string inputs verbatim, without quote delimiters.',
                   'csv':'Use one CSV header row followed by data rows. Preserve column order. Quote commas and embedded quotes.',
                   'html':'Use a complete HTML document with a title and one table id="records", one header row with th cells and one data row per record with td cells. No scripts or styles.'}[language]
            prompt='Produce reference data, computing every missing '+result_key+'. '+rules+' '+shape+' Columns in order: '+', '.join(rows[0])+'. Preserve all inputs, record order, exact field names and string values. No extra fields or records. Inputs: '+json.dumps(data,ensure_ascii=False)
            tasks.append({'id':identifier,'language':language,'family':family,'level':level,'track':'documents','prompt':prompt})
            oracles[identifier]={'kind':'document','rows':rows,'control':document_control(language,rows)}
    for family,architecture in [('ELF','riscv64'),('PE','aarch64'),('Mach-O','x86_64'),('JVM','jvm'),('CLR','cil'),('Wasm','wasm64')]:
        identifier='binary-info-'+family.lower()
        value={'schema_version':1,'format':family,'architecture':architecture,
               'sections':[{'name':'code','kind':'code'},{'name':'constants','kind':'data'},{'name':'descriptors','kind':'metadata'}],
               'symbols':[{'name':'parse_decimal','kind':'function','section':'code'}, {'name':'longest_run','kind':'function','section':'code'},
                          {'name':'limit','kind':'object','section':'constants'}, {'name':'api_version','kind':'object','section':'descriptors'}],
               'strings':['Bounded decimal parser','Increasing-run helper']}
        tasks.append({'id':identifier,'language':'binary-info','family':'binary-graph','level':3,'track':'documents',
                      'prompt':'Describe a logical '+family+' component for '+architecture+'. Use exactly the following sections, symbols, strings and ordering. This describes metadata, not actual executable offsets or bytes. '+json.dumps(value)})
        oracles[identifier]={'kind':'binary','expected':value,'control':json.dumps(value,indent=2)+'\n'}
    return {'benign':True,'tasks':tasks}, {'benign':True,'oracles':oracles}


if __name__=='__main__':
    for name,value in zip(['tasks.json','oracles.json'],build()):
        (Path(__file__).parent/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
