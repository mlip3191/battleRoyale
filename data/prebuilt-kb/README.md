# Prebuilt knowledge base (D-66)

The seed fighters' passages and their vectors, so a fresh setup can skip `npm run ingest`.
In live mode the app loads them at startup into an empty knowledge base, but only when they
were built with the same embedding model as yours (`knowledge-base.json` records a SHA-256
fingerprint of the model name, never the name itself). Otherwise it says so and points to
`npm run ingest`, which also stays the way to rebuild or refresh.

- `knowledge-base.json`: each document's title, URL, license, retrieval date and content hash,
  and its passages (no article HTML).
- `vectors-1.f16`, `vectors-2.f16`, `vectors-3.f16`: one little-endian float16 vector per
  passage, in the JSON's order, cut into parts under 4.5 MiB so each fits the pre-commit hook's
  5 MB limit. The app joins them in the order `knowledge-base.json` lists them and checks the
  SHA-256 of the joined bytes (it stores the vectors as float32; half precision halves the size
  without changing search results).

The files never overwrite a knowledge base that already has passages. They hold passages and
vectors only: the Wikidata facts a full `npm run ingest` also stores are not included, and stored
facts are preferred over facts read from passages, so a few stat sheets can differ slightly from
a fully ingested setup until you run `npm run ingest`.

To export again (rarely: each export adds about 16 MB to git history), first re-parse every seed
article with `uv run --directory backend python -m scripts.ingest_seed --refresh` in live mode,
then run `uv run --directory backend python -m app.research.kb_prebuilt`. The export stops if any
seed fighter has no passages, so a partial knowledge base is never committed.

## License

The passages are text from Wikipedia articles, licensed under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Each document in
`knowledge-base.json` keeps its article title and URL, which is the attribution; see
`docs/research.md` for the sources. Wikidata facts are CC0 and are not in these files.
