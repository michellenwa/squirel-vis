import hashlib

import streamlit as st
from SPARQLWrapper import SPARQLWrapper, JSON
from my_functions import Run_My_SPARQL_Query
from data_processor import fetch_and_process_data
import numpy as np
import pandas as pd
from scipy.stats import kruskal
from sklearn.mixture import GaussianMixture
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Dashboard Sketch", layout="wide")

# ==========================================
# 1. INITIALIZE SESSION STATE & TEXT
# ==========================================
if 'main_view' not in st.session_state:
    st.session_state.main_view = 'Distribution of Scores'
if 'report_content_html' not in st.session_state:
    st.session_state.report_content_html = ""

def update_main(chart_name):
    st.session_state.main_view = chart_name

CHART_EXPLANATIONS = {
    'Distribution of Scores': "Shows the spread of richness scores across different groups to highlight representational disparities.",
    'Average Scores Per Profile': "Groups entities into distinct clusters (ranging from basic stubs to highly rich items) based on their overall data depth.",
    'Profile Distribution Across Contexts': "Highlights structural imbalances by showing what percentage of a specific group falls into each richness profile (e.g., if one demographic is mostly low-richness stubs).",
    'Feature Inequality (Gini Scores)': "Measures how unequally data is distributed within a group. A score near 0 means all entities have similar depth; near 1 means a small subset holds most of the detailed data."
}

# ==========================================
# 1b. CANONICAL SQuIREL ORDERING
# ==========================================
SQUIREL_FEATURE_ORDER = [
    "Specificity",
    "Qualifiers",
    "References",
    "Internal",
    "External",
    "Linguistic",
]

def get_ordered_features(numeric_cols):
    """Return numeric_cols arranged in SQuIREL's fixed dimension order."""
    ordered = [c for c in SQUIREL_FEATURE_ORDER if c in numeric_cols]
    leftovers = sorted(c for c in numeric_cols if c not in SQUIREL_FEATURE_ORDER)
    return ordered + leftovers

# ==========================================
# 2. SPARQL DATA FETCHERS (Cached)
# ==========================================
@st.cache_data(ttl=3600)
def get_artwork_types():
    query = """
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?typeofartwork ?typeofartworkLabel WHERE {
      ?typeofartwork wdt:P31 wd:Q116474095 .
      ?typeofartwork rdfs:label ?typeofartworkLabel .
      FILTER (LANG(?typeofartworkLabel) = "en") .
    }
    ORDER BY ?typeofartwork 
    """
    try:
        data = Run_My_SPARQL_Query(query)
        bindings = data.get("results", {}).get("bindings", [])
        return {
            item["typeofartworkLabel"]["value"]: item["typeofartwork"]["value"].split("/")[-1]
            for item in bindings if "typeofartworkLabel" in item and "typeofartwork" in item
        }
    except Exception as e:
        st.error(f"Error fetching artwork types: {e}")
        return {}
        
@st.cache_data(ttl=3600)
def get_occupation_types():
    query = """
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?typeofoccupation ?typeofoccupationLabel WHERE {
      ?typeofoccupation wdt:P31 wd:Q12737077 .
      ?typeofoccupation rdfs:label ?typeofoccupationLabel .
      FILTER (LANG(?typeofoccupationLabel) = "en") .
    }
    ORDER BY ?typeofoccupation 
    """
    try:
        data = Run_My_SPARQL_Query(query)
        bindings = data.get("results", {}).get("bindings", [])
        return {
            item["typeofoccupationLabel"]["value"]: item["typeofoccupation"]["value"].split("/")[-1]
            for item in bindings if "typeofoccupationLabel" in item and "typeofoccupation" in item
        }
    except Exception as e:
        st.error(f"Error fetching occupations types: {e}")
        return {}

@st.cache_data(ttl=3600)
def get_countries():
    query = """
    PREFIX wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT DISTINCT ?country ?countryLabel ?continent ?continentLabel WHERE {
      VALUES ?type { wd:Q3624078 wd:Q6256 }
      ?country wdt:P31 ?type .
      ?country wdt:P30 ?continent .
      
      ?country rdfs:label ?countryLabel .
      FILTER (LANG(?countryLabel) = "en") .
      ?continent rdfs:label ?continentLabel .
      FILTER (LANG(?continentLabel) = "en") .
    }
    ORDER BY ?continentLabel ?countryLabel
    """
    try:
        data = Run_My_SPARQL_Query(query)
        bindings = data.get("results", {}).get("bindings", [])
        
        country_dict = {}
        for item in bindings:
            if "countryLabel" in item and "continentLabel" in item and "country" in item:
                label = f"{item['countryLabel']['value']} ({item['continentLabel']['value']})"
                qid = item["country"]["value"].split("/")[-1]
                country_dict[label] = qid
        return country_dict
    except Exception as e:
        st.error(f"Error fetching countries: {e}")
        return {}

@st.cache_data(ttl=3600)
def get_genders():
    query = """
    PREFIX wd: <http://www.wikidata.org/entity/>
    PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

    SELECT ?gender ?genderLabel WHERE {
      VALUES ?gender { wd:Q6581097 wd:Q6581072 wd:Q1097630 wd:Q2449503 wd:Q1052281 }
      ?gender rdfs:label ?genderLabel .
      FILTER (LANG(?genderLabel) = "en") .
    }
    ORDER BY ?genderLabel
    """
    try:
        data = Run_My_SPARQL_Query(query)
        bindings = data.get("results", {}).get("bindings", [])
        return {
            item["genderLabel"]["value"]: item["gender"]["value"].split("/")[-1]
            for item in bindings if "genderLabel" in item and "gender" in item
        }
    except Exception as e:
        st.error(f"Error fetching genders: {e}")
        return {}

# ==========================================
# 3. CHART GENERATION FUNCTIONS
# ==========================================
def draw_distribution(df, features, contexts, context_color_map, height, render_to_ui=True):
    feature_labels = {}
    for label in features:
        groups = [df[df['Context'] == c][label].dropna().values for c in contexts]
        try:
            _, p_val = kruskal(*groups)
            if p_val < 0.001: star = "***"
            elif p_val < 0.01: star = "**"
            elif p_val < 0.05: star = "*"
            else: star = "(ns)"
            feature_labels[label] = f"{label} {star}"
        except ValueError:
            feature_labels[label] = label
 
    ordered_metric_labels = [feature_labels[f] for f in features]
 
    df_melted = df.melt(id_vars=['Context'], value_vars=features, var_name='Metric', value_name='Score')
    df_melted['Metric'] = df_melted['Metric'].map(feature_labels)
 
    fig = px.box(
        df_melted, x='Metric', y='Score', color='Context',
        color_discrete_map=context_color_map,
        category_orders={'Metric': ordered_metric_labels, 'Context': list(contexts)}
    )
    fig.update_layout(template="plotly_white", xaxis_title=None, boxmode='group', height=height, margin=dict(t=40, b=10, l=10, r=10))
    
    if render_to_ui:
        st.plotly_chart(fig, use_container_width=True)
    return fig
 
def draw_profiles(df_gmm, metric_cols, height, profile_colors, category_order, render_to_ui=True):
    profile_summary = df_gmm.groupby('Profile')[metric_cols].mean().reset_index()
    summary_melted = profile_summary.melt(id_vars='Profile', value_vars=metric_cols)
    
    fig = px.bar(
        summary_melted, x='value', y='variable', facet_row='Profile',
        color='Profile', orientation='h', color_discrete_map=profile_colors,
        category_orders={"Profile": category_order, "variable": metric_cols}
    )
    fig.update_layout(height=height, template="plotly_white", showlegend=False, title="", margin=dict(t=40, b=10, l=10, r=10))
    fig.update_yaxes(matches=None, title=None)
    fig.update_xaxes(title="Score")
    fig.for_each_annotation(lambda a: a.update(text=a.text.split("=")[-1]) if "=" in a.text else a)
    
    if render_to_ui:
        st.plotly_chart(fig, use_container_width=True)
    return fig
 
def draw_bias(df_gmm, height, profile_colors, category_order, contexts, render_to_ui=True):
    # Raw counts per Profile x Context, plus the percentage version — both
    # reindexed identically so they line up row-for-row, column-for-column.
    counts_table = pd.crosstab(df_gmm['Profile'], df_gmm['Context'])
    bias_table = counts_table.div(counts_table.sum(axis=0), axis=1) * 100
 
    ordered_index = [c for c in category_order if c in bias_table.index]
    ordered_cols = [c for c in contexts if c in bias_table.columns]
    counts_table = counts_table.reindex(index=ordered_index, columns=ordered_cols, fill_value=0)
    bias_table = bias_table.reindex(index=ordered_index, columns=ordered_cols, fill_value=0)
    
    fig = go.Figure()
    for profile in category_order:
        if profile in bias_table.index:
            fig.add_trace(go.Bar(
                x=bias_table.columns,
                y=bias_table.loc[profile],
                name=profile,
                marker_color=profile_colors[profile],
                customdata=counts_table.loc[profile].values,
                hovertemplate=(
                    "<b>" + profile + "</b><br>"
                    "%{x}: %{y:.1f}% (%{customdata} entities)"
                    "<extra></extra>"
                )
            ))
 
    fig.update_layout(
        barmode='stack',
        height=height,
        template="plotly_white",
        margin=dict(t=40, b=10, l=10, r=10),
        yaxis_title="% of Entities"
    )
    
    if render_to_ui:
        st.plotly_chart(fig, use_container_width=True)
        
    return fig
 
def calculate_gini(array):
    array = np.sort(np.array(array, dtype=float).flatten())
    array = array[~np.isnan(array)]
    if len(array) == 0: return 0
    if np.amin(array) < 0: array -= np.amin(array)
    array += 0.0000001
    index = np.arange(1, array.shape[0] + 1)
    n = array.shape[0]
    return ((np.sum((2 * index - n  - 1) * array)) / (n * np.sum(array)))
 
def draw_gini(df, features, contexts, height, render_to_ui=True):
    gini_results = []
    for ctx in contexts:
        ctx_data = df[df['Context'] == ctx]
        row = {'Context': ctx}
        for feat in features:
            row[feat] = calculate_gini(ctx_data[feat].values)
        gini_results.append(row)
 
    # Rows: canonical context order. Columns: canonical SQuIREL feature order.
    gini_df = pd.DataFrame(gini_results).set_index('Context')
    gini_df = gini_df.reindex(index=list(contexts), columns=features)
 
    fig = px.imshow(gini_df, text_auto=".3f", aspect="auto", 
                    color_continuous_scale="Sunset")
    fig.update_layout(template="plotly_white", xaxis_title=None, height=height, margin=dict(t=40, b=10, l=10, r=10))
    
    if render_to_ui:
        st.plotly_chart(fig, use_container_width=True)
    return fig


# ==========================================
# 4. STREAMLIT UI & SIDEBAR
# ==========================================
st.title("SQuIREL-Vis")

with st.expander("What is SQuIREL?"):
    st.markdown("""
    **SQuIREL** measures the "richness" or structural depth of an entity profile based on its specific context, rather than just checking basic completeness. 
    It evaluates entities across six dimensions:
    * **Semantic Specificity**: Measures if an entity uses rare, tailored information rather than basic, templated facts.
    * **Qualifier Density**: Tracks the use of extra nuances (like start dates or academic degrees) added to basic facts.
    * **Reference Provenance**: Evaluates the density and diversity of valid sources backing up the entity's claims.
    * **Internal Connectivity**: Shows how deeply an entity is linked to by other pages within the database.
    * **External Network**: Counts external identifiers, indicating recognition by outside institutions and databases.
    * **Linguistic Accessibility**: Assesses how well the entity is translated across different languages (labels, descriptions, and aliases).
    """)

custom_css = """
<style>
    [data-testid="stSidebar"] {
        min-width: 400px !important;
        max-width: 400px !important;
    }
</style>
"""
st.markdown(custom_css, unsafe_allow_html=True)

with st.sidebar:
    st.header("Select Context")
    category_options = ["Artwork", "Occupation"]
    selected_category = st.selectbox("Select a Category", category_options)

    selected_artwork_type = None
    selected_occupation_type = None
    artwork_types = {}
    occupation_types = {}
    
    if selected_category == "Artwork":
        with st.spinner("Querying QLever for artwork types..."):
            artwork_types = get_artwork_types()
            
        if artwork_types:
            selected_artwork_type = st.selectbox("Select Type", list(artwork_types.keys()))
            st.write(f"**Current Selection:** {selected_artwork_type} ({artwork_types[selected_artwork_type]})")
        else:
            st.warning("No artwork types returned.")
            
    if selected_category == "Occupation":
        with st.spinner("Querying QLever for occupation types..."):
            occupation_types = get_occupation_types()
            
        if occupation_types:
            selected_occupation_type = st.selectbox("Select Type", list(occupation_types.keys()))
            st.write(f"**Current Selection:** {selected_occupation_type} ({occupation_types[selected_occupation_type]})")
        else:
            st.warning("No occupation types returned.")

    st.divider()

    st.subheader("Country Selection")
    with st.spinner("Querying QLever for countries..."):
        countries = get_countries()

    selected_countries = []
    if countries:
        selected_countries = st.multiselect("Select one or more countries", list(countries.keys()))
        if selected_countries:
            st.write("**You selected:**")
            for country in selected_countries:
                st.write(f"- {country} ({countries[country]})")
    else:
        st.warning("No countries returned.")
            
    st.subheader("Gender Selection")
    with st.spinner("Querying QLever for genders..."):
        genders = get_genders()

    selected_genders = []
    if genders:
        is_artwork = (selected_category == "Artwork")
        help_text = "Gender selection is not applicable for Artworks." if is_artwork else None
        
        selected_genders = st.multiselect(
            "Select one or more genders", 
            list(genders.keys()),
            disabled=is_artwork, 
            help=help_text       
        )
        
        if selected_genders:
            st.write("**You selected:**")
            for gender in selected_genders:
                st.write(f"- {gender} ({genders[gender]})")
    else:
        st.warning("No genders returned.")
    
    st.divider()
    run_btn = st.button("Run Analysis", type="primary")

# ==========================================
# 5. DATA PROCESSING & DASHBOARD LAYOUT
# ==========================================
st.divider()
 
if run_btn:
    st.session_state.report_content_html = "" # clears old report when new analysis runs
 
    domain_parameters = []
    add_property_list = []
    add_comparison_list = []
 
    country_properties = {
        "Artwork": "P495",  # Country of Origin
        "Occupation": "P27" # Country of Citizenship
    }
 
    if selected_category in country_properties:
        if selected_category == "Artwork" and selected_artwork_type:
            domain_parameters.append(("P31", artwork_types[selected_artwork_type]))
        elif selected_category == "Occupation" and selected_occupation_type:
            domain_parameters.append(("P106", occupation_types[selected_occupation_type]))
            
        if selected_countries:
            country_qids = tuple(countries[c] for c in selected_countries)
            add_property_list.append(country_properties[selected_category]) 
            add_comparison_list.append(country_qids)
            
        if selected_genders:
            gender_qids = tuple(genders[g] for g in selected_genders)
            add_property_list.append("P21")
            add_comparison_list.append(gender_qids)
 
    # Both categories use the same list-based call. fetch_domain_qids_dynamic
    # handles a single-element list correctly; passing a bare string made
    # len(add_property) return the string's length instead of 1.
    add_property = add_property_list if add_property_list else None
    add_comparison = add_comparison_list if add_comparison_list else None
 
    with st.spinner("Processing data, this may take awhile..."):
        results_df = fetch_and_process_data(
            domain_parameters, 
            add_property, 
            add_comparison
        )
 
        if results_df is None or len(results_df) == 0:
            # No entities matched the selected context — clear out any stale
            # results from a previous run so old graphs don't linger, and
            # show a plain message
            for key in ('results_df', 'df_gmm', 'category_order', 'features', 'contexts', 'entity_count'):
                st.session_state.pop(key, None)
            st.session_state.no_entities_found = True
        else:
            st.session_state.no_entities_found = False
 
            # 1. De-duplicate then sort by QID with a STABLE sort, so any
            #    ties (or repeated QIDs from overlapping queries) always land
            #    in the same row order across runs. `sort_values` defaults to
            #    quicksort, which is NOT stable and can silently reshuffle
            #    ties differently each run.
            if 'QID' in results_df.columns:
                results_df = results_df.drop_duplicates(subset='QID')
                results_df = results_df.sort_values('QID', kind='mergesort').reset_index(drop=True)
 
            st.session_state.results_df = results_df
            st.session_state.entity_count = len(results_df)
 
            # 2. Extract features in the fixed SQuIREL dimension order
            numeric_cols = [col for col in results_df.select_dtypes(include=[np.number]).columns if col != 'QID']
            features = get_ordered_features(numeric_cols)
 
            df_gmm = results_df.copy()
            X = df_gmm[features].fillna(0)
 
            # Clustering Logic
            max_k = min(6, len(X))
            if max_k >= 2:
                bics = []
                models = []
                
                with st.spinner("Calculating clusters..."):
                    for k in range(2, max_k + 1):
                        try:
                            gmm = GaussianMixture(
                                n_components=k, 
                                random_state=42, 
                                covariance_type='full', 
                                reg_covar=1e-5,
                                n_init=10, 
                                max_iter=500
                            )
                            gmm.fit(X)
                            bics.append(gmm.bic(X))
                            models.append(gmm)
                        except Exception:
                            bics.append(float('inf'))
                            models.append(None)
                
                if not all(m is None for m in models):
                    best_idx = np.argmin(bics)
                    best_gmm = models[best_idx]
                    best_k = best_idx + 2  
                    
                    
                    df_gmm['Profile_ID'] = best_gmm.predict(X)
 
                    temp_summary = df_gmm.groupby('Profile_ID')[features].mean()
                    sorted_clusters = temp_summary.sum(axis=1).sort_values(kind='mergesort').index
                    
                    mapping = {}
                    for rank, old_id in enumerate(sorted_clusters):
                        if rank == 0:
                            mapping[old_id] = "Stub Entities"
                        elif rank == best_k - 1:
                            mapping[old_id] = "Rich Entities"
                        else:
                            mid_tier_number = (best_k - 1) - rank
                            mapping[old_id] = f"Mid-Range Entities {mid_tier_number}"
                            
                    df_gmm['Profile'] = df_gmm['Profile_ID'].map(mapping)
                    category_order = ["Stub Entities"] + [f"Mid-Range Entities {i}" for i in reversed(range(1, best_k - 1))] + ["Rich Entities"]
                    
                    st.session_state.df_gmm = df_gmm
                    st.session_state.category_order = category_order
                    st.session_state.features = features
                    # 3. Pin context order too — .unique() reflects row order
                    #    from upstream data, which is not guaranteed stable.
                    #    Sort explicitly so charts never silently reshuffle.
                    st.session_state.contexts = sorted(results_df['Context'].unique())
                else:
                    st.error("GMM clustering failed for all cluster sizes.")
            elif len(X) < 2:
                # Fewer than 2 entities means clustering can't run at all —
                # this isn't "no entities" (results_df is non-empty) but
                # there's nothing to profile
                st.warning(f"Only {len(X)} entit{'y' if len(X) == 1 else 'ies'} matched this context — at least 2 are needed to generate profiles.")
 
if st.session_state.get('no_entities_found'):
    st.info("No entities were found for the selected context. Try adjusting your category, type, country, or gender selection and run the analysis again.")
 
if 'results_df' in st.session_state and 'df_gmm' in st.session_state:
    results_df = st.session_state.results_df
    df_gmm = st.session_state.df_gmm
    category_order = st.session_state.category_order
    features = st.session_state.features
    contexts = st.session_state.contexts
 
    # Total, plus a per-group (per-Context) breakdown right next to it.
    context_counts = results_df['Context'].value_counts().reindex(contexts).fillna(0).astype(int)
    count_cols = st.columns(len(contexts) + 1)
    count_cols[0].metric("**Total entities**", st.session_state.get('entity_count', len(results_df)))
    for col, ctx in zip(count_cols[1:], contexts):
        col.metric(ctx, int(context_counts[ctx]))
    
    theme_colors_1 = px.colors.sequential.Sunset
    theme_colors_2 = px.colors.sequential.Plasma
   
    context_color_map = {ctx: theme_colors_1[i % len(theme_colors_1)] for i, ctx in enumerate(contexts)}
    profile_color_map = {prof: theme_colors_2[i % len(theme_colors_2)] for i, prof in enumerate(category_order)}
 
    def render_actual_chart(chart_name, is_main=True):
        h = 550 if is_main else 250 
        
        if chart_name == 'Distribution of Scores':
            return draw_distribution(results_df, features, contexts, context_color_map, h, render_to_ui=True)
        elif chart_name == 'Average Scores Per Profile':
            adjusted_h = max(h, 250 * len(category_order)) if is_main else h
            return draw_profiles(df_gmm, features, adjusted_h, profile_color_map, category_order, render_to_ui=True)
        elif chart_name == 'Profile Distribution Across Contexts':
            return draw_bias(df_gmm, h, profile_color_map, category_order, contexts, render_to_ui=True)
        elif chart_name == 'Feature Inequality (Gini Scores)':
            return draw_gini(results_df, features, contexts, h, render_to_ui=True)
 
    main_col, right_col = st.columns([3, 1])
 
    with main_col:
        st.subheader(f"{st.session_state.main_view}")
        st.caption(CHART_EXPLANATIONS.get(st.session_state.main_view, ""))
        render_actual_chart(st.session_state.main_view, is_main=True)
 
    with right_col:
        st.subheader("Other Graphs")
        all_charts = [
            'Distribution of Scores', 
            'Average Scores Per Profile', 
            'Profile Distribution Across Contexts', 
            'Feature Inequality (Gini Scores)'
        ]
 
        for chart in all_charts:
            if chart != st.session_state.main_view:
                with st.container(border=True):
                    st.markdown(f"**{chart}**")
                    render_actual_chart(chart, is_main=False)
                    st.button(f"Set as Main", key=f"btn_{chart}", on_click=update_main, args=(chart,), use_container_width=True)



# ==========================================
# 6. SQuIREL DOCUMENTATION FRAMEWORK 
# ==========================================
if 'results_df' in st.session_state and 'df_gmm' in st.session_state:
    st.divider()
    st.header("SQuIREL Documentation Framework")
    st.markdown("Record your findings based on the framework outlined in the *SQuIREL* research methodology.")

    with st.expander("📝 Draft New Report Form", expanded=True):
        
        auto_context_str = f"Category: {selected_category}"
        if selected_category == "Artwork" and selected_artwork_type:
            auto_context_str += f" | Type: {selected_artwork_type} ({artwork_types.get(selected_artwork_type, '')})"
        elif selected_category == "Occupation" and selected_occupation_type:
            auto_context_str += f" | Type: {selected_occupation_type} ({occupation_types.get(selected_occupation_type, '')})"
            
        if selected_countries:
            country_str_list = [f"{c} ({countries.get(c, '')})" for c in selected_countries]
            auto_context_str += f"\nCountries: {', '.join(country_str_list)}"
        
        if selected_genders:
            gender_str_list = [f"{g} ({genders.get(g, '')})" for g in selected_genders]
            auto_context_str += f"\nGenders: {', '.join(gender_str_list)}"
            
        with st.form("documentation_form"):
            context_constants = st.text_area("Define Context Constants", value=auto_context_str)
            st.caption("State the constant property-value pairs that were used to gather items to populate the context.")
            
            baseline_target = st.text_area("Baseline Subject and Target Subject")
            st.caption("State the varied property-value pairs that comprise the context dataset for the comparison.")
            
            main_bias = st.text_area("Main Bias Indicator(s)")
            st.caption("From the results of the six richness dimensions, what are the main indicators that there is an issue of bias when comparing the Target subject to the Baseline subject?")
            
            editorial_gap = st.text_area("Editorial Gap")
            st.caption("Is the bias caused by a skew in editor attention or behaviour? Does the Target have a significant deficit in enriched items? Does the Target have higher Gini scores due to a lack of editor attention, community focus, or organised WikiProjects compared to the Baseline?")
            
            source_gap = st.text_area("Source Material Gap")
            st.caption("Is the bias caused by a lack of verifiable references and source material? Does the Target have higher Reference scores and stub items? Is the disparity a reflection of external reality? Do the Baseline items simply have more published, verifiable literature globally available than the Target items?")
            
            data_model_gap = st.text_area("Data Model Gap")
            st.caption("Is the bias caused by the mismatch between the data model and the epistemic reality of the Target? Does the high Qualifier or Internal Link Gini suggest that Wikidata's established schema is poorly suited for the Target Context? Are editors forced to leave items bare because the culturally or contextually correct properties do not exist?")
            
            bias_check = st.text_area("Bias Check")
            st.caption("Does the high inequality indicate actual bias, or a natural structural hierarchy within this specific domain (e.g., a few 'hub' items naturally hoarding links while other valid items have few)?")
            
            targeted_recs = st.text_area("Targeted Recommendation(s)")
            st.caption("Split target recommendations into four categories when applicable: Parity, Floor Raising, Investigation, and No internal action.")
            
            actionable_goals = st.text_area("Actionable Goal(s)")
            st.caption("Here actionable goals can be listed to create an itinerary of interventions for the Wikidata community to potentially tackle.")
            
            submitted = st.form_submit_button("Generate Report with Graphs")
            
            if submitted:
                if 'results_df' in st.session_state and 'df_gmm' in st.session_state:
                    with st.spinner("Generating report and rendering graphs..."):
                        current_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        
                        # Generate identical figures silently for the report
                        fig_dist = draw_distribution(st.session_state.results_df, st.session_state.features, st.session_state.contexts, context_color_map, 400, render_to_ui=False)
                        fig_prof = draw_profiles(st.session_state.df_gmm, st.session_state.features, 400, profile_color_map, st.session_state.category_order, render_to_ui=False)
                        fig_bias = draw_bias(st.session_state.df_gmm, 400, profile_color_map, st.session_state.category_order, st.session_state.contexts, render_to_ui=False)
                        fig_gini = draw_gini(st.session_state.results_df, st.session_state.features, st.session_state.contexts, 400, render_to_ui=False)
                        
                        html_dist = fig_dist.to_html(full_html=False, include_plotlyjs='cdn')
                        html_prof = fig_prof.to_html(full_html=False, include_plotlyjs='cdn')
                        html_bias = fig_bias.to_html(full_html=False, include_plotlyjs='cdn')
                        html_gini = fig_gini.to_html(full_html=False, include_plotlyjs='cdn')

                        html_report = f"""
                        <html>
                        <head>
                            <style>
                                body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 900px; margin: auto; padding: 20px; }}
                                h1 {{ color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
                                h2 {{ color: #34495e; margin-top: 30px; }}
                                .section {{ background: #f9f9f9; padding: 15px; border-radius: 5px; margin-bottom: 20px; border: 1px solid #e1e1e1; }}
                                .graph-container {{ margin: 30px 0; page-break-inside: avoid; }}
                                pre {{ white-space: pre-wrap; font-family: inherit; }}
                            </style>
                        </head>
                        <body>
                            <h1>SQuIREL Bias Analysis Report</h1>
                            <p><strong>Generated on:</strong> {current_date}</p>

                            <div class="section">
                                <h2>1. Context & Baseline</h2>
                                <p><strong>Context Constants:</strong><br> <pre>{context_constants}</pre></p>
                                <p><strong>Baseline & Target Subject:</strong><br> {baseline_target}</p>
                            </div>

                            <div class="section">
                                <h2>2. Bias Indicators & Gaps</h2>
                                <p><strong>Main Bias Indicator(s):</strong><br> {main_bias}</p>
                                <p><strong>Editorial Gap:</strong><br> {editorial_gap}</p>
                                <p><strong>Source Material Gap:</strong><br> {source_gap}</p>
                                <p><strong>Data Model Gap:</strong><br> {data_model_gap}</p>
                            </div>

                            <h2>Data Visualisations</h2>
                            <div class="graph-container">
                                <h3>Distribution of Scores</h3>
                                {html_dist}
                            </div>
                            <div class="graph-container">
                                <h3>Average Scores Per Profile</h3>
                                {html_prof}
                            </div>
                            <div class="graph-container">
                                <h3>Profile Distribution Across Contexts</h3>
                                {html_bias}
                            </div>
                            <div class="graph-container">
                                <h3>Feature Inequality (Gini Scores)</h3>
                                {html_gini}
                            </div>

                            <div class="section">
                                <h2>3. Verification & Action</h2>
                                <p><strong>Bias Check:</strong><br> {bias_check}</p>
                                <p><strong>Targeted Recommendation(s):</strong><br> {targeted_recs}</p>
                                <p><strong>Actionable Goal(s):</strong><br> {actionable_goals}</p>
                            </div>
                        </body>
                        </html>
                        """
                        st.session_state.report_content_html = html_report
                        st.success("Report generated successfully")
                else:
                    st.warning("Please run the analysis first to generate data for the report.")

    if st.session_state.report_content_html:
        st.subheader("Report Preview")
        with st.container(border=True):
            st.components.v1.html(st.session_state.report_content_html, height=600, scrolling=True)
        
        st.download_button(
            label="Download Complete HTML Report (Print to PDF)",
            data=st.session_state.report_content_html,
            file_name=f"SQuIREL_Report_{datetime.now().strftime('%Y%m%d')}.html",
            mime="text/html",
            help="Open this downloaded file in any browser, and use 'Ctrl+P' / 'Cmd+P' to save it as a cleanly formatted PDF."
        )
