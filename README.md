# SQuIREL-Vis
[![arXiv](https://img.shields.io/badge/arXiv-2610.24709-b31b1b.svg)](https://arxiv.org/abs/2610.24709)

A Streamlit dashboard for measuring and comparing the **richness** of Wikidata entity profiles across contexts (e.g. artworks by country of origin, or people in an occupation by country of citizenship and gender).

Entities are scored on six SQuIREL dimensions:

| Dimension | What it measures |
|---|---|
| **Semantic Specificity** | Measures if an entity uses rare, tailored information rather than basic, templated facts. |
| **Qualifier Density** | Tracks the use of extra nuances (like start dates or academic degrees) added to basic facts. |
| **Reference Provenance** | Evaluates the density and diversity of valid sources backing up the entity's claims. |
| **Internal Connectivity** | Shows how deeply an entity is linked to by other pages within the database. |
| **External Network** | Counts external identifiers, indicating recognition by outside institutions and databases. |
| **Linguistic Accessibility** | Assesses how well the entity is translated across different languages (labels, descriptions, and aliases). |

The dashboard then clusters entities into richness profiles (Gaussian Mixture Model), compares score distributions between groups (Kruskal–Wallis), computes Gini inequality per dimension, and lets you export an HTML report following the [SQuIREL documentation framework](https://arxiv.org/abs/2610.24709).

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

## Citation

If you use this dashboard or the SQuIREL framework in your research, please cite our paper

'''bibtex
@misc{nwachukwu2026squirelcontextrelativeframeworkmeasuring,
      title={SQuIREL: A Context-Relative Framework for Measuring Entity Richness in Wikidata}, 
      author={Michelle Nwachukwu and Albert Meroño-Peñuela and Martim Brandão},
      year={2026},
      eprint={2610.24709},
      archivePrefix={arXiv},
      primaryClass={cs.AI},
      url={https://arxiv.org/abs/2610.24709}, 
}
