"""Growth-market and culture knowledge base; Python standard library only."""
import argparse
import json
import sqlite3
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / 'growth_markets.sqlite3'
EVIDENCE = {'cultural_reference', 'source_attested_phrase', 'authored_example', 'practice_hypothesis'}
KINDS = {'culture', 'phrase', 'language_variety', 'event', 'rule', 'metric', 'market', 'project_signal'}
VARIETIES = {'standard', 'regional_dialect', 'separate_language', 'colloquial_register', 'historical_reference', 'script_variation'}


def normalize(text):
    text = unicodedata.normalize('NFKD', text.casefold())
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return text.translate(str.maketrans({'ʻ': "'", 'ʼ': "'", '‘': "'", '’': "'", 'ё': 'е'}))


def load():
    return json.loads((ROOT / 'data.json').read_text(encoding='utf-8'))


def validate(data):
    countries={x['code'] for x in data['countries']}
    categories={x['id'] for x in data['categories']}
    sources={x['id'] for x in data['sources']}
    for key, ids in [('countries', countries), ('categories', categories), ('sources', sources)]:
        if len(ids) != len(data[key]): raise ValueError('Duplicate '+key)
    seen=set()
    for r in data['records']:
        if r['id'] in seen: raise ValueError('Duplicate ID: '+r['id'])
        seen.add(r['id'])
        if r['country'] not in countries or r['category'] not in categories: raise ValueError('Invalid scope: '+r['id'])
        if r['kind'] not in KINDS or r['evidence'] not in EVIDENCE: raise ValueError('Invalid kind/evidence: '+r['id'])
        if not all(r.get(k) for k in ['title','summary','body','scope']): raise ValueError('Empty required field: '+r['id'])
        if r['evidence'] in {'cultural_reference','source_attested_phrase'} and not r['sources']:
            raise ValueError('Reference has no source: '+r['id'])
        for ref in r['sources']:
            if ref['source'] not in sources or not ref['supports'].strip(): raise ValueError('Invalid citation: '+r['id'])
        if len({ref['source'] for ref in r['sources']}) != len(r['sources']): raise ValueError('Duplicate citation: '+r['id'])
        if r['kind']=='rule' and r['evidence']!='practice_hypothesis': raise ValueError('Numeric rules must be practice hypotheses')
        if r['kind']=='rule':
            p=r['details']; lo,hi=p.get('min'),p.get('max')
            if lo is not None and hi is not None and lo>hi: raise ValueError('Invalid numeric range')
        if r['kind']=='language_variety' and r['details'].get('variety_type') not in VARIETIES: raise ValueError('Invalid language variety')
        if r['kind']=='phrase':
            p=r['details']
            if not p.get('text') or not p.get('meaning_zh') or not p.get('register'): raise ValueError('Incomplete phrase')
            if p.get('native_review_status') not in {'source_attested_not_native_reviewed','authored_not_native_reviewed'}: raise ValueError('Unsubstantiated native review status')
        if r['evidence']=='source_attested_phrase' and r['kind']!='phrase': raise ValueError('Phrase evidence on non-phrase')
    return True


SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE countries(code TEXT PRIMARY KEY,name_zh TEXT NOT NULL,profile_json TEXT NOT NULL CHECK(json_valid(profile_json)));
CREATE TABLE categories(id TEXT PRIMARY KEY,name_zh TEXT NOT NULL);
CREATE TABLE sources(id TEXT PRIMARY KEY,title TEXT NOT NULL,url TEXT NOT NULL,publisher TEXT NOT NULL,access_level TEXT NOT NULL,checked_on TEXT NOT NULL,limitations TEXT NOT NULL);
CREATE TABLE records(id TEXT PRIMARY KEY,country TEXT NOT NULL REFERENCES countries(code),category TEXT NOT NULL REFERENCES categories(id),kind TEXT NOT NULL,evidence TEXT NOT NULL,title TEXT NOT NULL,summary TEXT NOT NULL,body TEXT NOT NULL,scope TEXT NOT NULL,details_json TEXT NOT NULL CHECK(json_valid(details_json)),tags_json TEXT NOT NULL CHECK(json_valid(tags_json)),updated_on TEXT NOT NULL,normalized_text TEXT NOT NULL);
CREATE TABLE citations(record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,source_id TEXT NOT NULL REFERENCES sources(id),supports TEXT NOT NULL,PRIMARY KEY(record_id,source_id));
CREATE VIRTUAL TABLE search_index USING fts5(record_id UNINDEXED,title,body,details,tokenize='unicode61 remove_diacritics 2');
CREATE INDEX records_filters ON records(country,category,kind,evidence);
CREATE INDEX citations_sources ON citations(source_id);
CREATE VIEW records_with_sources AS SELECT r.*,(SELECT group_concat(s.url,char(10)) FROM citations c JOIN sources s ON s.id=c.source_id WHERE c.record_id=r.id) AS source_urls FROM records r;
'''


def build(path=DEFAULT_DB):
    data=load(); validate(data)
    path=Path(path).resolve(); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.building')
    if temp.exists():raise FileExistsError('Inspect existing build file: '+str(temp))
    conn=sqlite3.connect(temp)
    try:
        conn.executescript(SCHEMA)
        with conn:
            conn.executemany('INSERT INTO metadata VALUES (?,?)',[(k,json.dumps(v,ensure_ascii=False)) for k,v in data['metadata'].items()])
            for c in data['countries']:conn.execute('INSERT INTO countries VALUES (?,?,?)',(c['code'],c['name_zh'],json.dumps(c,ensure_ascii=False)))
            conn.executemany('INSERT INTO categories VALUES (:id,:name_zh)',data['categories'])
            conn.executemany('INSERT INTO sources VALUES (:id,:title,:url,:publisher,:access_level,:checked_on,:limitations)',data['sources'])
            for r in data['records']:
                details=json.dumps(r['details'],ensure_ascii=False)
                tags=json.dumps(r['tags'],ensure_ascii=False)
                text=' '.join([r['id'],r['title'],r['summary'],r['body'],r['scope'],details,tags])
                conn.execute('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(r['id'],r['country'],r['category'],r['kind'],r['evidence'],r['title'],r['summary'],r['body'],r['scope'],details,tags,r['updated_on'],normalize(text)))
                conn.executemany('INSERT INTO citations VALUES (?,?,?)',[(r['id'],ref['source'],ref['supports']) for ref in r['sources']])
                conn.execute('INSERT INTO search_index VALUES (?,?,?,?)',(r['id'],r['title'],r['summary']+' '+r['body'],details))
        if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or conn.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('Integrity error')
    except Exception:
        conn.close();temp.unlink(missing_ok=True);raise
    conn.close();temp.replace(path)
    (ROOT/'schema.sql').write_text(SCHEMA,encoding='utf-8')
    return path


class ReadOnlyConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc, traceback):
        try:
            return super().__exit__(exc_type, exc, traceback)
        finally:
            self.close()


def connect(path=DEFAULT_DB):
    conn=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True,factory=ReadOnlyConnection)
    conn.row_factory=sqlite3.Row
    return conn


def search(conn,query,country=None,category=None,kind=None,evidence=None,limit=20,include_shared=True,include_inactive=False):
    if not query.strip():raise ValueError('Empty query')
    where=['instr(normalized_text,?)>0'];values=[normalize(query)]
    if not include_inactive:
        where.append("country IN (SELECT code FROM countries WHERE json_extract(profile_json, '$.market_screen.status') IN ('candidate','shared','linked_not_rescreened'))")
    if country:
        if include_shared and country!='GLOBAL':where.append("country IN (?, 'GLOBAL')")
        else:where.append('country=?')
        values.append(country)
    for key,value in [('category',category),('kind',kind),('evidence',evidence)]:
        if value:where.append(key+'=?');values.append(value)
    values.append(max(1,min(200,limit)))
    return [dict(r) for r in conn.execute('SELECT id,country,category,kind,evidence,title,summary FROM records WHERE '+' AND '.join(where)+' ORDER BY id LIMIT ?',values)]


def show(conn,record_id):
    row=conn.execute('SELECT * FROM records WHERE id=?',(record_id,)).fetchone()
    if not row:raise ValueError('Unknown ID: '+record_id)
    out=dict(row);out.pop('normalized_text',None)
    out['details']=json.loads(out.pop('details_json'));out['tags']=json.loads(out.pop('tags_json'))
    out['sources']=[dict(r) for r in conn.execute('SELECT s.*,c.supports FROM citations c JOIN sources s ON c.source_id=s.id WHERE c.record_id=?',(record_id,))]
    return out


def stats(conn):
    return {'records':conn.execute('SELECT count(*) FROM records').fetchone()[0],'sources':conn.execute('SELECT count(*) FROM sources').fetchone()[0],'by_country':dict(conn.execute('SELECT country,count(*) FROM records GROUP BY country').fetchall()),'by_kind':dict(conn.execute('SELECT kind,count(*) FROM records GROUP BY kind').fetchall()),'by_evidence':dict(conn.execute('SELECT evidence,count(*) FROM records GROUP BY evidence').fetchall())}


def export():
    import export_guides
    export_guides.main()


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    p=argparse.ArgumentParser(description='增长与城建市场文化数据库');p.add_argument('--db',type=Path,default=DEFAULT_DB)
    sub=p.add_subparsers(dest='cmd',required=True)
    for cmd in ['build','export','stats','verify','markets']:sub.add_parser(cmd)
    q=sub.add_parser('search');q.add_argument('query');q.add_argument('--country',choices=[c['code'] for c in load()['countries']]);q.add_argument('--category');q.add_argument('--kind',choices=sorted(KINDS));q.add_argument('--evidence',choices=sorted(EVIDENCE));q.add_argument('--limit',type=int,default=20);q.add_argument('--country-only',action='store_true')
    q.add_argument('--include-inactive',action='store_true',help='显式查看暂停／退出／待核验市场的旧资料；不构成开发推荐')
    q=sub.add_parser('show');q.add_argument('id')
    a=p.parse_args()
    try:
        if a.cmd=='build':print(build(a.db));return
        if a.cmd=='export':
            import export_guides
            export_guides.main();return
        with connect(a.db) as c:
            if a.cmd=='search':out=search(c,a.query,a.country,a.category,a.kind,a.evidence,a.limit,not a.country_only,a.include_inactive)
            elif a.cmd=='markets':out={x['code']:x.get('market_screen') for x in load()['countries']}
            elif a.cmd=='show':out=show(c,a.id)
            elif a.cmd=='stats':out=stats(c)
            else:
                validate(load());n=c.execute('SELECT count(*) FROM records').fetchone()[0]
                if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or c.execute('PRAGMA foreign_key_check').fetchall() or n!=c.execute('SELECT count(*) FROM search_index').fetchone()[0]:raise ValueError('Verification failed')
                out={'integrity':'ok','records':n,'foreign_key_errors':0}
            print(json.dumps(out,ensure_ascii=False,indent=2))
    except (ValueError,OSError,sqlite3.Error) as e:p.exit(1,str(e)+'\n')


if __name__=='__main__':main()
