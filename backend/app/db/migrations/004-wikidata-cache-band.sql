-- Safety: remember whether a cached Wikidata pick is a group of real people (a band today; sports
-- teams later, D-59), whether that group's name is also a common word ("Eagles": "eagle" is an
-- animal), and the label of a group that lost the pick to a kind item ("The Police" for the item
-- "police") (A04 part 3a). A group's block depends on how the name was typed, which the
-- lowercased cache key cannot tell, so the check is redone from these columns on every cache hit.
-- The names are generic so sports teams need no second migration. Older rows default to 0 / NULL;
-- they are from an older classes_version and ignored anyway.

ALTER TABLE wikidata_safety_cache ADD COLUMN grouped INTEGER NOT NULL DEFAULT 0;
ALTER TABLE wikidata_safety_cache ADD COLUMN grouped_common INTEGER NOT NULL DEFAULT 0;
ALTER TABLE wikidata_safety_cache ADD COLUMN grouped_lost_label TEXT;
