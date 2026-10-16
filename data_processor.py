import requests
import json
import math
import csv
import numpy as np
import pandas as pd
from collections import Counter, defaultdict
import statistics
from my_functions import get_compare_results, fetch_domain_qids, Run_My_SPARQL_Query, check_response_data_contents, build_domain_query, build_comparison_domain_query, build_comparison_domain_query_2, all_properties_query, count_analysis_query, extract_bindings, chunk_list, Run_My_SPARQL_Query_by_batch, add_missing_scores, basic_plot, calculate_lang_scores, get_compare_results_dynamic, fetch_domain_qids_dynamic, build_comparison_domain_query_dynamic
from my_queries import external_ids_query, get_all_triples_query, property_uses_qualifiers_query, item_qualifiers_query, reference_count_query, internal_links_query, external_ids_count_query, external_ids_counts_query, label_language_query, alias_language_query, description_language_query

SCORE_HEADERS = [
    "Context",
    "QID", 
    "Specificity", 
    "Qualifiers", 
    "References", 
    "Internal", 
    "External", 
    "Linguistic"
]

def fetch_and_process_data(domain_parameters, add_property, add_comparison):
    
    # Match fetch_domain_qids_dynamic: a bare string must become a list before
    # anything iterates it, or "P495" iterates as four separate characters.
    if isinstance(add_property, str):
        add_property = [add_property]
        add_comparison = [add_comparison]
    
    #DEFINE DOMAIN
    
    qid_list, comp = fetch_domain_qids_dynamic(domain_parameters, add_property, add_comparison)
    
    print(f"entities matched: {len(qid_list)}")
    
    if not qid_list:
        # No entities for this context. The UI checks len(results_df) == 0 and
        # shows its own message, so return the empty frame rather than raising.
        return pd.DataFrame(columns=SCORE_HEADERS)
    
    #GET PROPERTY LIST AND RESULTS
    
    all_properties_result = Run_My_SPARQL_Query_by_batch(
        sparql_query_placeholder=all_properties_query(), 
        entity_lst=qid_list, 
        chunk_size=200
    )
    
    entity_property_counts = defaultdict(set)

    entity_properties_ids = defaultdict(list) ##

    for row in all_properties_result:
        entity_id = row["entity_id"]["value"]
        property_id = row["property"]["value"]
        entity_property_counts[entity_id].add(property_id)
        entity_properties_ids[entity_id].append(property_id) ##
    
    entity_properties_ids = dict(entity_properties_ids) ##

    #number of properties per entity
    counts_per_entity = [len(props) for props in entity_property_counts.values()]
    
    entity_to_count = {
        entity_id: len(props)
        for entity_id, props in entity_property_counts.items()
    }
    
    #property percentages
    #flatten all properties into one list
    all_properties = []
    for properties in entity_properties_ids.values():
        all_properties.extend(properties)

    #count occurrences
    property_counts = Counter(all_properties)

    #convert counts to percentages
    total_entities = len(entity_properties_ids)

    property_percentages = [
        (prop, (count / total_entities) * 100)
        for prop, count in property_counts.items()
    ]

    #sort from most used to least used
    property_percentages.sort(key=lambda x: x[1], reverse=True)

    #exclude domain criteria
    excluded_properties = {prop_id for prop_id, _ in domain_parameters}
    for prop in (add_property or []):
        excluded_properties.add(prop)

    excluded_properties = [
        f"http://www.wikidata.org/entity/{property_id}"
        for property_id in excluded_properties
    ]

    filtered_property_percentages = [
        (prop, pct)
        for prop, pct in property_percentages
        if prop not in excluded_properties
    ]
    
    
    ##1. SPECIFICITY
    
    external_ids_result = Run_My_SPARQL_Query_by_batch(external_ids_query(), qid_list, 50)

    identifiers = []
    for row in external_ids_result:
        identifiers.append(row["property"]["value"])

    unique_identifiers = list(set(identifiers))
    
    # Exclude the external-ID properties here rather than inside the batch helper,
    # so an empty result is an expected outcome we can return from, not an error.
    triple_property_list = [
        prop for prop, _ in filtered_property_percentages
        if prop not in set(unique_identifiers)
    ]

    if not triple_property_list:
        print("No non-identifier properties found for these entities - returning an empty frame.")
        return pd.DataFrame(columns=SCORE_HEADERS)

    get_all_triples_result = Run_My_SPARQL_Query_by_batch(
        sparql_query_placeholder=get_all_triples_query(), 
        entity_lst=qid_list, 
        chunk_size=200, 
        property_list=triple_property_list
    )
    
    item = []
    prop = []
    value = []
    unique_values = defaultdict(set)

    for row in get_all_triples_result:
        item.append(row["item"]["value"])
        prop.append(row["property"]["value"])
        value.append(row["value"]["value"])
    
        pro = row['property']['value']
        val = row['value']['value']
        unique_values[pro].add(val)
    
    distinct_counts = {prop: len(vals) for prop, vals in unique_values.items()}

    prop_value = [f"{p}: {v}" for p, v in zip(prop, value)]
    
    counts_pv = Counter(prop_value)
    counts_p = Counter(prop)
    scores_dict = {}
    weighted_scores_dict = {}

    for pv_key, pv_count in counts_pv.items():
        p_key = pv_key.split(": ")[0] 
        p_count = counts_p[p_key]
    
        scores_dict[pv_key] = -math.log2(pv_count / p_count)
        weight = p_count / len(qid_list)
        weighted_scores_dict[pv_key] = weight * scores_dict[pv_key]
    
    triple_dict = defaultdict(list)

    for key, val in zip(item, prop_value):
        triple_dict[key].append(val)

    triple_dict = dict(triple_dict)
    
    m_score = max(weighted_scores_dict.values(), default=0)
    triple_counts = {entity: len(triples) for entity, triples in triple_dict.items()}
    s_score = max(triple_counts.values(), default=0)
    theoretical_max_score = m_score * math.log(1 + s_score)

    top_pv_key = max(weighted_scores_dict, key=weighted_scores_dict.get, default=None)
    #top_score = weighted_scores_dict[top_pv_key]
    top_score = weighted_scores_dict.get(top_pv_key, 0)
    
    sum_scores = {}
    norm_scores = {}

    for key, values in triple_dict.items():
        current_sum = sum(weighted_scores_dict[v] for v in values)
        count_pairs = len(values)
        
        sum_scores[key] = (current_sum / count_pairs) * math.log(1 + count_pairs)
        norm_scores[key] = sum_scores[key] / theoretical_max_score if theoretical_max_score else 0

    add_missing_scores(norm_scores, qid_list)
    
    ##2. QUALIFIERS
    
    # all_properties is the flattened list WITH duplicates, so querying it as-is
    # re-asks about the same property once per entity that uses it.
    unique_properties = list(set(all_properties))

    property_uses_qualifiers_result = Run_My_SPARQL_Query_by_batch(
        sparql_query_placeholder=property_uses_qualifiers_query(), 
        entity_lst=unique_properties, 
        chunk_size=50,
    )

    value_count_connect = Counter()

    for row in property_uses_qualifiers_result:
        p = row["property"]["value"]
        c = row["allowedQualifierCount"]["value"]
        value_count_connect[p] += int(c)

    print("properties with allowed-qualifier constraints:", len(value_count_connect))

    # If the constraint query comes back empty (e.g. the endpoint's index lacks
    # the P2302 statements on property entities), count qualifiers wherever they
    # actually occur rather than sending an empty list and scoring everything 0.
    qualifier_property_list = list(value_count_connect.keys()) or unique_properties
    
    item_qualifiers_result = Run_My_SPARQL_Query_by_batch(
        sparql_query_placeholder=item_qualifiers_query(), 
        entity_lst=qid_list, 
        chunk_size=100,
        property_list=qualifier_property_list,
        prop_prefix="p:",
        prop_sep=" ",            # VALUES is space-separated, not ", "
        prop_chunk_size=100
    )

    print("qualifier rows returned:", len(item_qualifiers_result))

    item_qualifier = []
    prop_qualifier = []
    count_qualifier = []
    item_count_qualifier = Counter()

    for row in item_qualifiers_result:
        i = row["item"]["value"]
        p = row["property"]["value"]
        c = int(row["qualifierdistinctCount"]["value"])
    
        item_qualifier.append(i)
        prop_qualifier.append(p)
        count_qualifier.append(c)
    
        # Count totals simultaneously
        item_count_qualifier[i] += c
    
    item_prop_qualifier = {}

    for i, p in zip(item_qualifier, prop_qualifier):
        item_prop_qualifier.setdefault(i, []).append(p)
    
    item_prop_count = {ent: len(props) for ent, props in item_prop_qualifier.items()}
    
    theoretical_max_score_q = np.percentile(count_qualifier, 99) if count_qualifier else 0
    
    scores_qualifier = {}
    norm_scores_qualifier = {}

    for key, value in item_count_qualifier.items():
        divisor = item_prop_count.get(key, 0)

        if divisor and theoretical_max_score_q:
            scores_qualifier[key] = value / divisor
            norm_scores_qualifier[key] = min(1.0, scores_qualifier[key] / theoretical_max_score_q)
        else:
            scores_qualifier[key] = 0
            norm_scores_qualifier[key] = 0

    filled = add_missing_scores(norm_scores_qualifier, qid_list)

    if qid_list and filled == len(qid_list):
        print("WARNING: no qualifier data for any entity - every score is a placeholder.")
    
    ##3. REFERENCES
    
    reference_count_result = Run_My_SPARQL_Query_by_batch(
        sparql_query_placeholder=reference_count_query(), 
        entity_lst=qid_list, 
        chunk_size=200
    )

    reference_dict = {}

    for row in reference_count_result:
        k = row["item"]["value"]
        v1 = int(row["statementCount"]["value"])
        v2 = int(row["referenceCount"]["value"])
        v3 = int(row["distinctreferenceCount"]["value"])
    
        if k not in reference_dict:
            reference_dict[k] = [v1, v2, v3]
        else:
            reference_dict[k][0] += v1
            reference_dict[k][1] += v2
            reference_dict[k][2] += v3
    
    score_count_reference = {}
    distinct_score_count_reference = {}
    weighted_score_count_reference = {}

    for key, (statements, refs, distinct_refs) in reference_dict.items():
        if statements > 0:
            score_count_reference[key] = refs / statements
            distinct_score_count_reference[key] = distinct_refs / statements
        
            weight_score = min(1.0, ((0.5 * refs) + (0.5 * distinct_refs)) / statements)
            weighted_score_count_reference[key] = weight_score
        else:
            score_count_reference[key] = 0.0
            distinct_score_count_reference[key] = 0.0
            weighted_score_count_reference[key] = 0.0
    
    add_missing_scores(score_count_reference, qid_list)

    add_missing_scores(distinct_score_count_reference, qid_list)

    add_missing_scores(weighted_score_count_reference, qid_list)
    
    ##4. INTERNAL
    
    internal_links_result = Run_My_SPARQL_Query_by_batch(
        sparql_query_placeholder=internal_links_query(), 
        entity_lst=qid_list, 
        chunk_size=100
    )

    value_score_connect = defaultdict(int)

    for row in internal_links_result:
        v = row["value"]["value"]
        c = int(row["count"]["value"])
        value_score_connect[v] += c

    value_score_connect = dict(value_score_connect)
    
    #in_max_value = max(value_score_connect.values())
    in_max_value = max(value_score_connect.values(), default=0)
    
    new_vscore_connect = {}
    total_internal = {}

    for v, total_score in value_score_connect.items():
        if v in triple_dict: 
            score_in = math.log10(1 + total_score) / math.log10(1 + in_max_value)
            new_vscore_connect[v] = min(1.0, score_in)
        
            total_internal[v] = total_score
    
    add_missing_scores(new_vscore_connect, qid_list)
    
    ##5. EXTERNAL
    
    external_ids_count_result = Run_My_SPARQL_Query_by_batch(
        sparql_query_placeholder=external_ids_count_query(), 
        entity_lst=qid_list, 
        chunk_size=400
    )
    prop_count_external = defaultdict(int)

    for row in external_ids_count_result:
        p = row["property"]["value"]
        c = int(row["propertyCount"]["value"])
        prop_count_external[p] += c

    prop_count_external = dict(prop_count_external)
    
    external_ids_counts_result = Run_My_SPARQL_Query_by_batch(
        sparql_query_placeholder=external_ids_counts_query(), 
        entity_lst=qid_list, 
        chunk_size=100,
        property_list=list(prop_count_external.keys()),
        prop_chunk_size=100
    )


    p_count_external = []
    external_links_dict = Counter()

    for row in external_ids_counts_result:
        k = row["item"]["value"]
        v = int(row["propertyCount"]["value"])
    
        p_count_external.append(v)
        external_links_dict[k] += v
    
    #max_value = np.percentile(p_count_external, 99)
    if len(p_count_external) > 0:
        max_value = np.percentile(p_count_external, 99)
    else:
        max_value = 0

    norm_elinks_dict = {}

    for v, total_score in external_links_dict.items():
        if max_value != 0:
            norm_elinks_dict[v] = min(1.0, total_score / max_value)
        else:
            norm_elinks_dict[v] = 0.0
    
    add_missing_scores(norm_elinks_dict, qid_list)
    
    ##6. LINGUISTIC
    
    label_language_result = Run_My_SPARQL_Query_by_batch(
        sparql_query_placeholder=label_language_query(), 
        entity_lst=qid_list, 
        chunk_size=400
    )

    label_languages_dict = defaultdict(list)

    for row in label_language_result:
        k = row["item"]["value"]
        v = row["lang"]["value"]
        label_languages_dict[k].append(v)

    label_languages_dict = dict(label_languages_dict)
    
    alias_language_result = Run_My_SPARQL_Query_by_batch(
        sparql_query_placeholder=alias_language_query(), 
        entity_lst=qid_list, 
        chunk_size=400
    )

    alias_data = []
    alias_counts = []

    for row in alias_language_result:
        ent = row["item"]["value"]
        lang = row["lang"]["value"]
        count = int(row["aliasCount"]["value"])
    
        alias_data.append((ent, lang, count))
        alias_counts.append(count)
    
    #percentile and scoring math
    #percentiles = np.percentile(alias_counts, [90])
    if len(alias_counts) > 0:
        percentiles = np.percentile(alias_counts, [90])
    else:
        percentiles = [0]
        
    alias_max_score = 1.0
    inflection_point = percentiles[0]

    alias_score = defaultdict(dict)

    for ent, lang, count in alias_data:
        if count == 0:
            score = 0.0
        else:
            score = alias_max_score / (1 + math.exp(-(count - inflection_point)))
        
        alias_score[ent][lang] = score
    
    alias_score = dict(alias_score)
    
    description_language_result = Run_My_SPARQL_Query_by_batch(
        sparql_query_placeholder=description_language_query(), 
        entity_lst=qid_list, 
        chunk_size=400
    )

    desc_data = []
    lang_char_counts = defaultdict(list)

    #extraction pass
    for row in description_language_result:
        ent = row["item"]["value"]
        lang = row["lang"]["value"]
        char_count = int(row["char_count"]["value"])
    
        desc_data.append((ent, lang, char_count))
        if char_count > 0: 
            lang_char_counts[lang].append(char_count)

    #calculate medians
    language_medians = {
        lang: statistics.median(counts) 
        for lang, counts in lang_char_counts.items()
    }

    item_language_scores = defaultdict(dict)
    
    #calculate final scores based on thresholds
    for ent, lang, char_count in desc_data:
        m_l = language_medians.get(lang, 0) 
    
        if char_count == 0 or m_l == 0:
            score = 0
        else:
            threshold = max(100, 2 * m_l)
            excess = max(0, char_count - threshold)
            score = max(0, 1 - (excess / threshold))
        
        item_language_scores[ent][lang] = score

    item_language_scores = dict(item_language_scores)
    
    sub_key_scores = {}
    main_key_scores = {}

    max_lang = max((len(langs) for langs in label_languages_dict.values()), default=0)

    for entity, langs in label_languages_dict.items():
        entity_sub_scores = {}
        total_main_score = 0.0
    
        for lang in langs:
            score_alias = alias_score.get(entity, {}).get(lang, 0.0)
            score_desc = item_language_scores.get(entity, {}).get(lang, 0.0)
        
            combined_score = (score_alias * 0.1) + (score_desc * 0.3) + 0.6
        
            entity_sub_scores[lang] = combined_score
            total_main_score += combined_score 
    
        sub_key_scores[entity] = entity_sub_scores
        main_key_scores[entity] = total_main_score / max_lang if max_lang else 0

    add_missing_scores(main_key_scores, qid_list)
    
    # ALL SCORES
    
    dicts = [norm_scores, norm_scores_qualifier, weighted_score_count_reference, new_vscore_connect, norm_elinks_dict, main_key_scores]

    all_keys = set().union(*dicts)

    all_scores_dict = {key: [d.get(key, None) for d in dicts] for key in all_keys}
    
    
    # CREATE DATAFRAME

    qid_to_comparison = {qid: variable for qid, variable in comp}

    rows = []

    for qid, scores in all_scores_dict.items():
        comp_var = qid_to_comparison.get(qid, "Unknown")
    
        row_data = [comp_var, qid] + scores
        rows.append(row_data)

    headers = SCORE_HEADERS
    
    df = pd.DataFrame(rows, columns=headers)

    
    
    
    
    
    
    
#    # Mock dataframe for this example
#    data = {
#        "Category": ["France", "Italy", "Male", "Female"],
#        "Count": [1500, 1200, 3000, 800]
#    }
#    df = pd.DataFrame(data)
    
    return df
    
    
    
