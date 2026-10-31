
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
