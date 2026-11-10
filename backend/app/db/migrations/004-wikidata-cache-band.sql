-- Safety: remember whether a cached Wikidata pick is a band, and whether that band's name is also
-- a common word ("Eagles": "eagle" is an animal) (A04 part 3a). A band's block depends on how the
-- name was typed, which the lowercased cache key cannot tell, so the check is redone from these
-- flags on every cache hit. Older rows default to 0; they are from an older classes_version and
-- ignored anyway.

ALTER TABLE wikidata_safety_cache ADD COLUMN band INTEGER NOT NULL DEFAULT 0;
ALTER TABLE wikidata_safety_cache ADD COLUMN band_common INTEGER NOT NULL DEFAULT 0;
