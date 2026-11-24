CREATE TABLE sources (
            source_slug TEXT PRIMARY KEY,
            langs TEXT NOT NULL,
            unit_count INTEGER NOT NULL DEFAULT 0,
            translation_count INTEGER NOT NULL DEFAULT 0,
            dict_entry_count INTEGER NOT NULL DEFAULT 0,
            sample_title TEXT,
            sample_url TEXT,
            license TEXT
        );

CREATE TABLE dict_entries (
            id INTEGER PRIMARY KEY,
            entry_id TEXT NOT NULL,
            lang TEXT NOT NULL,
            headword TEXT NOT NULL,
            lookup_key TEXT NOT NULL,
            homonym TEXT,
            pos TEXT,
            inflection_type TEXT,
            variants TEXT,
            localities TEXT,
            cross_references TEXT,
            notes TEXT,
            source_slug TEXT NOT NULL,
            source_url TEXT,
            raw_entry TEXT
        );

CREATE TABLE dict_inflection_types (
            type_key TEXT PRIMARY KEY,
            lang TEXT NOT NULL,
            source_slug TEXT NOT NULL,
            type_id TEXT NOT NULL,
            pos_group TEXT NOT NULL,
            examples_json TEXT NOT NULL,
            source_url TEXT
        );

CREATE TABLE dict_definitions (
            id INTEGER PRIMARY KEY,
            entry_rowid INTEGER NOT NULL,
            lang TEXT NOT NULL,
            target_lang TEXT NOT NULL,
            definition_text TEXT NOT NULL,
            norm_def TEXT NOT NULL,
            sense TEXT,
            def_vec F8_BLOB(512)
        , source_evidence TEXT);

CREATE TABLE dict_inflections (
            id INTEGER PRIMARY KEY,
            entry_rowid INTEGER NOT NULL,
            lang TEXT NOT NULL,
            form TEXT NOT NULL,
            lookup_key TEXT NOT NULL,
            grammatical_tag TEXT,
            notation TEXT,
            raw_text TEXT,
            metadata_json TEXT
        );

CREATE TABLE dict_examples (
            id INTEGER PRIMARY KEY,
            entry_rowid INTEGER NOT NULL,
            lang TEXT NOT NULL,
            source_text TEXT NOT NULL,
            target_text TEXT,
            target_lang TEXT,
            locality TEXT
        );

CREATE TABLE dict_cognates (
            id INTEGER PRIMARY KEY,
            concept_key TEXT NOT NULL,
            concept_lang TEXT NOT NULL,
            lang TEXT NOT NULL,
            entry_rowid INTEGER NOT NULL,
            headword TEXT NOT NULL,
            pos TEXT,
            definition_text TEXT NOT NULL
        );

CREATE VIRTUAL TABLE dict_fts USING fts5(
            headword,
            definition_text,
            lang UNINDEXED,
            entry_rowid UNINDEXED,
            tokenize='unicode61 remove_diacritics 0'
        );

CREATE TABLE corpus_units (
            id INTEGER PRIMARY KEY,
            unit_id TEXT NOT NULL UNIQUE,
            lang TEXT NOT NULL,
            unit_level TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            unit_idx INTEGER NOT NULL,
            source_slug TEXT NOT NULL,
            text TEXT NOT NULL,
            lid_lang TEXT NOT NULL,
            lid_conf INTEGER NOT NULL,
            orig_vec F8_BLOB(512)
        );

CREATE VIRTUAL TABLE corpus_fts USING fts5(
            text,
            content='corpus_units',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 0'
        );

CREATE TABLE corpus_translations (
            id INTEGER PRIMARY KEY,
            unit_rowid INTEGER NOT NULL,
            lang TEXT NOT NULL,
            target_lang TEXT NOT NULL,
            translated_text TEXT NOT NULL,
            origin TEXT NOT NULL,
            engine TEXT,
            reliability INTEGER NOT NULL,
            q_overall INTEGER,
            q_meaning INTEGER,
            q_omission INTEGER,
            q_addition INTEGER,
            q_facts INTEGER,
            q_naturalness INTEGER,
            q_repetition INTEGER,
            q_artifacts INTEGER,
            q_intrusion INTEGER,
            q_integrity INTEGER,
            q_uncertain INTEGER,
            tr_vec F8_BLOB(512)
        );

CREATE VIRTUAL TABLE corpus_translations_fts USING fts5(
            translated_text,
            content='corpus_translations',
            content_rowid='id',
            tokenize='unicode61 remove_diacritics 0'
        );

CREATE TABLE word_frequencies (
            id INTEGER PRIMARY KEY,
            lang TEXT NOT NULL,
            lookup_key TEXT NOT NULL,
            form TEXT NOT NULL,
            freq INTEGER NOT NULL,
            lemma_et TEXT,
            pos TEXT,
            morph TEXT,
            example_unit_id TEXT,
            sources_json TEXT,
            UNIQUE(lang, lookup_key, form)
        );

CREATE INDEX idx_dict_entries_lang_key ON dict_entries(lang, lookup_key);

CREATE INDEX idx_dict_entries_key ON dict_entries(lookup_key);

CREATE INDEX idx_dict_defs_entry ON dict_definitions(entry_rowid);

CREATE INDEX idx_dict_defs_norm ON dict_definitions(norm_def, target_lang);

CREATE INDEX idx_dict_infl_lang_key ON dict_inflections(lang, lookup_key);

CREATE INDEX idx_dict_infl_key ON dict_inflections(lookup_key);

CREATE INDEX idx_dict_infl_entry ON dict_inflections(entry_rowid);

CREATE INDEX idx_dict_ex_entry ON dict_examples(entry_rowid);

CREATE INDEX idx_dict_cog_key ON dict_cognates(concept_key, concept_lang);

CREATE INDEX idx_dict_cog_entry ON dict_cognates(entry_rowid);

CREATE INDEX idx_corpus_units_lang_src ON corpus_units(lang, source_slug);

CREATE INDEX idx_corpus_units_doc_idx ON corpus_units(doc_id, unit_idx);

CREATE INDEX idx_corpus_units_lid ON corpus_units(lang, lid_lang);

CREATE INDEX idx_corpus_tr_unit ON corpus_translations(unit_rowid);

CREATE INDEX idx_corpus_tr_lang_tgt_rel ON corpus_translations(lang, target_lang, origin, reliability DESC);

CREATE INDEX idx_wf_key ON word_frequencies(lookup_key);

CREATE TABLE corpus_documents (doc_id TEXT PRIMARY KEY, title TEXT, author TEXT, source_url TEXT NOT NULL);
