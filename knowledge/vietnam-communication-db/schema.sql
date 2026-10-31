PRAGMA foreign_keys = ON;
CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE categories (id TEXT PRIMARY KEY, name_zh TEXT NOT NULL);
CREATE TABLE sources (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL,
 publisher TEXT NOT NULL, checked_on TEXT NOT NULL,
 scope TEXT NOT NULL, limitations TEXT NOT NULL
);
CREATE TABLE records (
 id TEXT PRIMARY KEY,
 kind TEXT NOT NULL CHECK(kind IN ('knowledge','phrase','rule','term','event','metric')),
 category_id TEXT NOT NULL REFERENCES categories(id),
 title TEXT NOT NULL, summary TEXT NOT NULL, body TEXT NOT NULL,
 evidence_type TEXT NOT NULL CHECK(evidence_type IN ('cultural_reference','practice_hypothesis','authored_example')),
 scope TEXT NOT NULL, region TEXT NOT NULL DEFAULT 'cross_region',
 relationship_min INTEGER CHECK(relationship_min BETWEEN 0 AND 4),
 privacy_level INTEGER CHECK(privacy_level BETWEEN 0 AND 3),
 tags_json TEXT NOT NULL CHECK(json_valid(tags_json)),
 updated_on TEXT NOT NULL, normalized_text TEXT NOT NULL
);
CREATE TABLE record_sources (
 record_id TEXT NOT NULL REFERENCES records(id) ON DELETE CASCADE,
 source_id TEXT NOT NULL REFERENCES sources(id),
 claim_scope TEXT NOT NULL,
 PRIMARY KEY(record_id, source_id)
);
CREATE TABLE phrase_details (
 record_id TEXT PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
 english TEXT NOT NULL, vietnamese TEXT NOT NULL, chinese TEXT NOT NULL,
 register_note TEXT NOT NULL, assumptions TEXT NOT NULL
);
CREATE TABLE rule_details (
 record_id TEXT PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
 min_value REAL, max_value REAL, unit TEXT NOT NULL,
 trigger_condition TEXT NOT NULL, action TEXT NOT NULL,
 override_condition TEXT NOT NULL,
 CHECK(min_value IS NULL OR max_value IS NULL OR min_value <= max_value)
);
CREATE TABLE term_details (
 record_id TEXT PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
 northern TEXT NOT NULL, central TEXT NOT NULL, southern TEXT NOT NULL,
 meaning_zh TEXT NOT NULL, usage_note TEXT NOT NULL
);
CREATE TABLE event_details (
 record_id TEXT PRIMARY KEY REFERENCES records(id) ON DELETE CASCADE,
 calendar TEXT NOT NULL CHECK(calendar IN ('gregorian','lunar','family_specific','variable')),
 month INTEGER CHECK(month BETWEEN 1 AND 12),
 day INTEGER CHECK(day BETWEEN 1 AND 31),
 date_note TEXT NOT NULL, action_note TEXT NOT NULL
);
CREATE VIRTUAL TABLE search_index USING fts5(record_id UNINDEXED,title,body,keywords,tokenize='unicode61 remove_diacritics 2');
CREATE INDEX idx_records_category ON records(category_id,kind,evidence_type);
CREATE INDEX idx_sources_record ON record_sources(source_id);
CREATE VIEW knowledge_with_sources AS
 SELECT r.*, c.name_zh AS category_name,
 (SELECT group_concat(s.url, char(10)) FROM record_sources rs JOIN sources s ON s.id=rs.source_id WHERE rs.record_id=r.id) AS source_urls
 FROM records r JOIN categories c ON c.id=r.category_id;
