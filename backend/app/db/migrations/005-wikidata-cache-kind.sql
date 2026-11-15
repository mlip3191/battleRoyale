-- Safety: remember the first kind item among a name's exact Wikidata matches when the top pick is
-- not a kind (A04 part 3b). A name typed as a common noun ("a wolverine") is judged by it (the
-- animal), a proper name ("Wolverine") by the top pick, and the lowercased cache key cannot tell
-- which was typed, so both are stored. Older rows default to NULL; they are from an older
-- classes_version and ignored anyway.

ALTER TABLE wikidata_safety_cache ADD COLUMN kind_qid TEXT;
ALTER TABLE wikidata_safety_cache ADD COLUMN kind_label TEXT;
ALTER TABLE wikidata_safety_cache ADD COLUMN kind_reason TEXT;
