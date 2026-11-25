-- The words a fact was read from (#522): an infobox row such as "Weight: 25–34 kg (55–75 lb)".
-- Empty for facts whose quote is just their field, value and unit (Wikidata, trait databases).

ALTER TABLE facts ADD COLUMN quote TEXT NOT NULL DEFAULT '';
