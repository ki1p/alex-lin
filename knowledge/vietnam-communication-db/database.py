"""Build and search the knowledge database using only Python's standard library."""
import argparse
import json
import sqlite3
import sys
import unicodedata
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / 'vietnam_communication.sqlite3'
KINDS = {'knowledge', 'phrase', 'rule', 'term', 'event', 'metric'}
EVIDENCE = {'cultural_reference', 'practice_hypothesis', 'authored_example'}


def normalize(text):
    text = text.casefold().replace('đ', 'd')
    return ''.join(c for c in unicodedata.normalize('NFD', text)
                   if unicodedata.category(c) != 'Mn')


def load_data():
    return json.loads((ROOT / 'data' / 'database.json').read_text(encoding='utf-8'))


def validate(data):
    category_ids = {x['id'] for x in data['categories']}
    source_ids = {x['id'] for x in data['sources']}
    if len(category_ids) != len(data['categories']) or len(source_ids) != len(data['sources']):
        raise ValueError('Duplicate category or source ID')
    seen = set()
    for r in data['records']:
        if r['id'] in seen:
            raise ValueError('Duplicate record ID: ' + r['id'])
        seen.add(r['id'])
        if r['kind'] not in KINDS or r['evidence_type'] not in EVIDENCE:
            raise ValueError('Invalid record type: ' + r['id'])
        if r['category_id'] not in category_ids:
            raise ValueError('Unknown category: ' + r['id'])
        refs = r.get('sources', [])
        if r['evidence_type'] == 'cultural_reference' and not refs:
            raise ValueError('Cultural reference requires a source: ' + r['id'])
        for ref in refs:
            if ref['source_id'] not in source_ids or not ref['claim_scope'].strip():
                raise ValueError('Invalid scoped citation: ' + r['id'])
        if len({ref['source_id'] for ref in refs}) != len(refs):
            raise ValueError('Duplicate citation: ' + r['id'])
        for key, upper in [('relationship_min', 4), ('privacy_level', 3)]:
            if r.get(key) is not None and (type(r[key]) is not int or not 0 <= r[key] <= upper):
                raise ValueError('Invalid level: ' + r['id'])
        expected = {'phrase':'phrase', 'rule':'rule', 'term':'term', 'event':'event'}.get(r['kind'])
        if expected and expected not in r:
            raise ValueError('Missing details: ' + r['id'])
        if r['kind'] == 'rule':
            rule = r['rule']
            low, high = rule['min_value'], rule['max_value']
            if low is not None and high is not None and low > high:
                raise ValueError('Invalid range: ' + r['id'])
            if r['evidence_type'] != 'practice_hypothesis':
                raise ValueError('Operational thresholds must be labelled practice_hypothesis')
    return True


def build(output=DEFAULT_DB):
    data = load_data()
    validate(data)
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + '.building')
    if temp.exists():
        raise FileExistsError('A build file exists; inspect it before retrying: ' + str(temp))
    conn = sqlite3.connect(temp)
    try:
        conn.executescript((ROOT / 'schema.sql').read_text(encoding='utf-8'))
        with conn:
            conn.executemany('INSERT INTO metadata VALUES (?,?)',
                             [(k, json.dumps(v, ensure_ascii=False)) for k,v in data['metadata'].items()])
            conn.executemany('INSERT INTO categories VALUES (:id,:name_zh)', data['categories'])
            conn.executemany('INSERT INTO sources VALUES (:id,:title,:url,:publisher,:checked_on,:scope,:limitations)', data['sources'])
            for r in data['records']:
                details = json.dumps({k:r[k] for k in ('phrase','rule','term','event') if k in r}, ensure_ascii=False)
                search_text = ' '.join([r['id'], r['title'], r['summary'], r['body'], ' '.join(r['tags']), details])
                conn.execute('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (r['id'],r['kind'],r['category_id'],r['title'],r['summary'],r['body'],r['evidence_type'],r['scope'],r.get('region','cross_region'),r.get('relationship_min'),r.get('privacy_level'),json.dumps(r['tags'],ensure_ascii=False),r['updated_on'],normalize(search_text)))
                for ref in r.get('sources', []):
                    conn.execute('INSERT INTO record_sources VALUES (?,?,?)',(r['id'],ref['source_id'],ref['claim_scope']))
                if r['kind'] == 'phrase':
                    p=r['phrase']; conn.execute('INSERT INTO phrase_details VALUES (?,?,?,?,?,?)',(r['id'],p['english'],p['vietnamese'],p['chinese'],p['register_note'],p['assumptions']))
                if r['kind'] == 'rule':
                    p=r['rule']; conn.execute('INSERT INTO rule_details VALUES (?,?,?,?,?,?,?)',(r['id'],p['min_value'],p['max_value'],p['unit'],p['trigger_condition'],p['action'],p['override_condition']))
                if r['kind'] == 'term':
                    p=r['term']; conn.execute('INSERT INTO term_details VALUES (?,?,?,?,?,?)',(r['id'],p['northern'],p['central'],p['southern'],p['meaning_zh'],p['usage_note']))
                if r['kind'] == 'event':
                    p=r['event']; conn.execute('INSERT INTO event_details VALUES (?,?,?,?,?,?)',(r['id'],p['calendar'],p['month'],p['day'],p['date_note'],p['action_note']))
                conn.execute('INSERT INTO search_index VALUES (?,?,?,?)',(r['id'],r['title'],r['body']+' '+details,' '.join(r['tags'])))
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or conn.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('Database integrity check failed')
    except Exception:
        conn.close()
        temp.unlink(missing_ok=True)
        raise
    conn.close()
    temp.replace(output)
    return output


def connect(path=DEFAULT_DB):
    # Read-only prevents search commands from accidentally creating an empty DB.
    conn=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    conn.row_factory=sqlite3.Row
    return conn


def search(conn, query, category=None, kind=None, evidence=None, limit=20):
    if not query.strip():
        raise ValueError('Search text cannot be empty')
    # Literal substring matching supports Chinese and accent-free Vietnamese.
    clauses=['instr(r.normalized_text,?) > 0']; params=[normalize(query)]
    for column, value in [('category_id',category),('kind',kind),('evidence_type',evidence)]:
        if value:
            clauses.append('r.'+column+'=?'); params.append(value)
    params.append(max(1,min(limit,200)))
    return conn.execute('SELECT r.id,r.kind,r.category_id,r.title,r.summary,r.evidence_type FROM records r WHERE '+' AND '.join(clauses)+' ORDER BY CASE WHEN instr(r.title,?)>0 THEN 0 ELSE 1 END,r.id LIMIT ?',params[:-1]+[query,params[-1]]).fetchall()


def show(conn, record_id):
    row=conn.execute('SELECT * FROM knowledge_with_sources WHERE id=?',(record_id,)).fetchone()
    if not row:
        raise ValueError('Unknown record ID: '+record_id)
    result=dict(row); result.pop('normalized_text',None)
    for table,key in [('phrase_details','phrase'),('rule_details','rule'),('term_details','term'),('event_details','event')]:
        detail=conn.execute('SELECT * FROM '+table+' WHERE record_id=?',(record_id,)).fetchone()
        if detail: result[key]=dict(detail)
    result['sources']=[dict(r) for r in conn.execute('SELECT s.*,rs.claim_scope FROM record_sources rs JOIN sources s ON s.id=rs.source_id WHERE rs.record_id=?',(record_id,))]
    return result


def main():
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description='越南生活与销售沟通知识数据库')
    parser.add_argument('--db',type=Path,default=DEFAULT_DB)
    commands=parser.add_subparsers(dest='command',required=True)
    commands.add_parser('build')
    p=commands.add_parser('search'); p.add_argument('query'); p.add_argument('--category'); p.add_argument('--kind',choices=sorted(KINDS)); p.add_argument('--evidence',choices=sorted(EVIDENCE)); p.add_argument('--limit',type=int,default=20)
    p=commands.add_parser('show'); p.add_argument('id')
    commands.add_parser('stats'); commands.add_parser('verify')
    args=parser.parse_args()
    try:
        if args.command=='build': print(build(args.db)); return
        with connect(args.db) as conn:
            if args.command=='search': output=[dict(r) for r in search(conn,args.query,args.category,args.kind,args.evidence,args.limit)]
            elif args.command=='show': output=show(conn,args.id)
            elif args.command=='stats': output={'records':conn.execute('SELECT count(*) FROM records').fetchone()[0], 'sources':conn.execute('SELECT count(*) FROM sources').fetchone()[0], 'by_kind':dict(conn.execute('SELECT kind,count(*) FROM records GROUP BY kind').fetchall()), 'by_evidence':dict(conn.execute('SELECT evidence_type,count(*) FROM records GROUP BY evidence_type').fetchall())}
            else:
                validate(load_data())
                integrity=conn.execute('PRAGMA integrity_check').fetchone()[0]
                foreign_keys=conn.execute('PRAGMA foreign_key_check').fetchall()
                records=conn.execute('SELECT count(*) FROM records').fetchone()[0]
                indexed=conn.execute('SELECT count(*) FROM search_index').fetchone()[0]
                if integrity!='ok' or foreign_keys or records!=indexed: raise ValueError('Verification failed')
                output={'integrity':integrity,'foreign_key_errors':len(foreign_keys),'records':records,'indexed':indexed}
            print(json.dumps(output,ensure_ascii=False,indent=2))
    except (ValueError,sqlite3.Error,OSError) as e:
        parser.exit(1,str(e)+'\n')


if __name__=='__main__': main()
