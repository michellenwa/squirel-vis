# SQuIREL-Vis

A Streamlit dashboard for measuring and comparing the **richness** of Wikidata entity profiles across contexts (e.g. artworks by country of origin, or people in an occupation by country of citizenship and gender).

Entities are scored on six SQuIREL dimensions:

| Dimension | What it measures |
|---|---|
| Specificity | Use of rare, tailored statements rather than templated facts |
| Qualifiers | Density of qualifiers (dates, roles, etc.) on statements |
| References | Density and diversity of valid sources |
| Internal | How often other Wikidata items link to the entity |
| External | Number of external identifiers |
| Linguistic | Coverage of labels, descriptions and aliases across languages |

The dashboard then clusters entities into richness profiles (Gaussian Mixture Model), compares score distributions between groups (Kruskal–Wallis), computes Gini inequality per dimension, and lets you export an HTML report following the SQuIREL documentation framework.

Data is fetched live from the [QLever Wikidata SPARQL endpoint](https://qlever.dev/wikidata).

## Files

- `dashboard.py` — the Streamlit app (UI, charts, report)
- `data_processor.py` — computes the six dimension scores for a context
- `my_functions.py` — SPARQL query runner, batching and query builders
- `my_queries.py` — SPARQL queries for each dimension

## Running locally

Requires Python 3.9+.

```bash
pip install -r requirements.txt
streamlit run dashboard.py
```

The app opens in your browser at http://localhost:8501.

## Notes

- Large contexts can take several minutes, since queries are batched and rate-limited against the public endpoint.
- Results depend on the live state of Wikidata, so scores can change over time.
