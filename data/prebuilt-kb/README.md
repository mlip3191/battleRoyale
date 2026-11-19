# Prebuilt knowledge base (D-66)

The seed fighters' passages and their vectors, so a fresh setup can skip `npm run ingest`.
In live mode the app loads them at startup into an empty knowledge base, but only when they
were built with the same embedding model as yours (`knowledge-base.json` records a SHA-256
fingerprint of the model name, never the name itself). Otherwise it says so and points to
`npm run ingest`, which also stays the way to rebuild or refresh.

- `knowledge-base.json`: each document's title, URL, license, retrieval date and content hash,
  and its passages (no article HTML).
- `vectors.f16`: one little-endian float16 vector per passage, in the JSON's order (the app
  stores them as float32; half precision halves the file without changing search results).

To export again after a full live ingest (rarely: each export adds about 16 MB to git history):
`uv run --directory backend python -m app.research.kb_prebuilt`

## License

The passages are text from Wikipedia articles, licensed under
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Each document in
`knowledge-base.json` keeps its article title and URL, which is the attribution; see
`docs/research.md` for the sources. Wikidata facts are CC0 and are not in these files.
