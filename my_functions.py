import requests
import json
import time
import matplotlib.pyplot as plt

SPARQL_PREFIXES = """
	PREFIX wd: <http://www.wikidata.org/entity/>
	PREFIX wdt: <http://www.wikidata.org/prop/direct/>
	PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
	PREFIX schema: <http://schema.org/>
	PREFIX wikibase: <http://wikiba.se/ontology#>
"""


def Run_My_SPARQL_Query(sparql_query):
    qlever_endpoint = "https://qlever.dev/api/wikidata"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/sparql-results+json",
        "User-Agent": (
            "sqirelproject/1.0 "
            "(contact: michelle.nwachukwu@kcl.ac.uk)"
        ),
    }

    data = {
        "query": sparql_query,
        "format": "json",
    }

    max_retries = 5
    backoff_factor = 2

    for attempt in range(max_retries):
        try:
            response = requests.post(
                qlever_endpoint,
                data=data,
                headers=headers,
                allow_redirects=True,
                timeout=300,
            )

            # Successful request
            if response.status_code == 200:
                return response.json()

            elif response.status_code in (429, 502, 503, 504):
                sleep_time = backoff_factor ** attempt
                print(f"Server error ({response.status_code}). Retrying in {sleep_time}s (Attempt {attempt+1}/{max_retries})...")

                time.sleep(sleep_time)
                continue

            # Other HTTP errors — don't retry
            else:
                print(f"HTTP Error: {response.status_code}")
                print(f"Query:\n{sparql_query}")
                print(f"Server Response:\n{response.text}")

                response.raise_for_status()

        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                sleep_time = backoff_factor ** attempt

                print(
                    f"Request timed out. "
                    f"Retrying in {sleep_time} seconds "
                    f"(Attempt {attempt + 1} of {max_retries})..."
                )

                time.sleep(sleep_time)
                continue

            raise

        except requests.exceptions.ConnectionError:
            if attempt < max_retries - 1:
                sleep_time = backoff_factor ** attempt

                print(
                    f"Connection error. "
                    f"Retrying in {sleep_time} seconds "
                    f"(Attempt {attempt + 1} of {max_retries})..."
                )

                time.sleep(sleep_time)
                continue

            raise

    raise Exception(
        f"Failed to fetch data after {max_retries} attempts."
    )



def check_response_data_contents(response_data):
    print(json.dumps(response_data, indent=2)[:1000])
   
def get_compare_results(results):
    item_list = []
    variable_list = []
    for result in results["results"]["bindings"]:
        item_list.append(result["item"]["value"])
        variable_list.append(result["variableLabel"]["value"])
        
    result_compare = list(zip(item_list, variable_list))
        
    return result_compare
   
def get_compare_results_dynamic(results, num_variables):
    # 1. Figure out ONLY the variable keys (we handle 'item' separately)
    keys = []
    if num_variables == 1:
        keys.append("variableLabel")
    elif num_variables > 1:
        for i in range(1, num_variables + 1):
            keys.append(f"variable{i}Label")

    result_compare = []
    missing = 0

    # 2. Loop through the rows one by one
    for result in results["results"]["bindings"]:
        # Get the main item
        item = result.get("item", {}).get("value")
        
        # 3. Collect all the variables for this specific row
        row_variables = []
        for key in keys:
            val = result.get(key, {}).get("value")
            
            if val is not None:
                row_variables.append(str(val))
            else:
                # Fall back to the QID. A literal "Unknown" here silently merges
                # every row into one group and hides the real fault upstream.
                missing += 1
                row_variables.append(item.split("/")[-1] if item else "Unknown")
                
        # 4. Join the collected variables with an underscore
        combined_variables = "_".join(row_variables)
        
        # 5. Append the tuple (item, combined_string) to our final list
        result_compare.append((item, combined_variables))

    if missing:
        print(f"WARNING: {missing} comparison label(s) missing across "
              f"{len(result_compare)} rows; expected keys {keys}")
        
    return result_compare
   
   
def fetch_domain_qids(domain_parameters, add_property=None, add_comparison=None):
    """
    Fetches QID lists based on whether comparison parameters are provided.
    """
    # Check if both comparison parameters are provided
    if add_property is not None and add_comparison is not None:
        
        # RUN THESE FOR COMPARISON DOMAINS
        query = build_comparison_domain_query(domain_parameters, add_property, add_comparison)
        domain_comp_result = Run_My_SPARQL_Query(query)
        comp = get_compare_results(domain_comp_result)
        
        # Extract qid using a list comprehension for cleaner syntax
        qid_list = [qid for qid, variable in comp]
        
    else:
        
        # RUN THESE FOR NON-COMPARISON DOMAINS
        query = build_domain_query(domain_parameters)
        domain_result = Run_My_SPARQL_Query(query)
        qid_list = get_results(domain_result)
        
    return qid_list, comp
    
def fetch_domain_qids_dynamic(domain_parameters, add_property=None, add_comparison=None):
    """
    Fetches QID lists based on whether comparison parameters are provided.
    """
    # Normalise a bare string into a list BEFORE anything calls len() on it.
    # len("P495") == 4, which is what collapsed the artwork comparison into a
    # single "Unknown" group.
    if isinstance(add_property, str):
        add_property = [add_property]
        add_comparison = [add_comparison]

    # Check if both comparison parameters are provided
    if add_property is not None and add_comparison is not None:
        
        # RUN THESE FOR COMPARISON DOMAINS
        query = build_comparison_domain_query_dynamic(domain_parameters, add_property, add_comparison)
        domain_comp_result = Run_My_SPARQL_Query(query)
        comp = get_compare_results_dynamic(domain_comp_result, len(add_property))
        
        # Grab the first item (the QID) from every tuple, regardless of tuple size
        qid_list = [row[0] for row in comp]
        
    else:
        
        # RUN THESE FOR NON-COMPARISON DOMAINS
        query = build_domain_query(domain_parameters)
        domain_result = Run_My_SPARQL_Query(query)
        
        # was extract_bindings(domain_result, 0) - the integer key never matches a
        # string-keyed binding, so this branch always returned an empty list
        qid_list = extract_bindings(domain_result, "item")
        
        # Set comp to None so the return statement doesn't crash
        comp = None 
    
    # An item with two values for the comparison property yields one row per
    # value, so the same QID can arrive twice and double every += accumulator
    # downstream. comp keeps its duplicates; qid_to_comparison collapses them.
    qid_list = list(dict.fromkeys(qid_list))
        
    return qid_list, comp


#query builder

def build_domain_query(domain_parameters):
    where_clauses = [f"?item wdt:{prop} wd:{value} ." for prop, value in domain_parameters]
    where_block = "\n  ".join(where_clauses)

    query = f"""{SPARQL_PREFIXES}
        SELECT ?item ?itemLabel WHERE {{
          {where_block}
          ?item rdfs:label ?itemLabel .
          FILTER (LANG(?itemLabel) = "en") .
        }}
        ORDER BY ?itemLabel
    """
    return query
    
def build_comparison_domain_query(domain_parameters, add_property, add_comparison):
    where_clauses = [f"?item wdt:{prop} wd:{value} ." for prop, value in domain_parameters]
    where_block = "\n  ".join(where_clauses)
    
    # Updated to generate a VALUES block
    compare_values = f"wd:{add_comparison[0]} wd:{add_comparison[1]}"
    values_block = f"VALUES ?variable {{ {compare_values} }}"
    property_block = f"?item wdt:{add_property} ?variable ."

    query = f"""{SPARQL_PREFIXES}
        SELECT DISTINCT ?item ?itemLabel ?variable ?variableLabel WHERE {{
          {where_block}
          {values_block}
          {property_block}
          ?item rdfs:label ?itemLabel .
          FILTER (LANG(?itemLabel) = "en") .
          ?variable rdfs:label ?variableLabel .
          FILTER (LANG(?variableLabel) = "en") .
        }}
        ORDER BY ?itemLabel
    """
    return query
    
  

def build_comparison_domain_query_2(domain_parameters, add_property, add_comparison):
    where_clauses = [f"?item wdt:{prop} wd:{value} ." for prop, value in domain_parameters]
    where_block = "\n  ".join(where_clauses)
    
    property_clauses = [f"?item wdt:{prop} ?variable{i+1} ." for i, prop in enumerate(add_property)]
    property_block = "\n  ".join(property_clauses)
    
    compare_clauses = [f"VALUES ?variable{i+1} {{ wd:{val1} wd:{val2} }}" for i, (val1, val2) in enumerate(add_comparison)]
    compare_block = "\n  ".join(compare_clauses)

    query = f"""{SPARQL_PREFIXES}
        SELECT ?item ?itemLabel ?variable1 ?variable1Label ?variable2 ?variable2Label WHERE {{
          {compare_block}
          {where_block}
          {property_block}
          
          OPTIONAL {{ 
            ?item rdfs:label ?itemLabel . 
            FILTER(LANG(?itemLabel) = "en") 
          }}
          OPTIONAL {{ 
            ?variable1 rdfs:label ?variable1Label . 
            FILTER(LANG(?variable1Label) = "en") 
          }}
          OPTIONAL {{ 
            ?variable2 rdfs:label ?variable2Label . 
            FILTER(LANG(?variable2Label) = "en") 
          }}
        }}
        ORDER BY ?itemLabel
    """
    return query

def build_comparison_domain_query_dynamic(domain_parameters, add_property, add_comparison):
    # 1. Safeguard inputs to ensure they are lists
    if isinstance(add_property, str):
        add_property = [add_property]
        
    num_vars = len(add_property)
    
    # If 1 variable, add_comparison might be a flat list ["Q1", "Q2"]. We need it to be [["Q1", "Q2"]]
    if num_vars == 1 and not isinstance(add_comparison[0], (list, tuple)):
        add_comparison = [add_comparison]

    # 2. Build the WHERE block for domain parameters
    where_clauses = [f"?item wdt:{prop} wd:{value} ." for prop, value in domain_parameters]
    where_block = "\n  ".join(where_clauses)

    # 3. Dynamically build SELECT, VALUES, PROPERTY, and LABEL blocks
    select_vars = ["?item", "?itemLabel"]
    values_clauses = []
    property_clauses = []
    
    # Start the labels block with the item label
    label_clauses = [
        'OPTIONAL { \n    ?item rdfs:label ?itemLabel . \n    FILTER(LANG(?itemLabel) = "en") \n  }'
    ]

    for i in range(num_vars):
        prop = add_property[i]
        vals = add_comparison[i]
        
        # Determine variable naming (?variable vs ?variable1, ?variable2)
        var_name = "?variable" if num_vars == 1 else f"?variable{i+1}"
        
        # Add to SELECT list
        select_vars.extend([var_name, f"{var_name}Label"])
        
        # Build VALUES string (e.g., wd:Q1 wd:Q2)
        vals_str = " ".join([f"wd:{v}" for v in vals])
        values_clauses.append(f"VALUES {var_name} {{ {vals_str} }}")
        
        # Build property connection
        property_clauses.append(f"?item wdt:{prop} {var_name} .")
        
        # Build OPTIONAL label block for this variable
        label_clauses.append(
            f'OPTIONAL {{ \n    {var_name} rdfs:label {var_name}Label . \n    FILTER(LANG({var_name}Label) = "en") \n  }}'
        )

    # Join the dynamically created clauses
    select_clause = " ".join(select_vars)
    values_block = "\n  ".join(values_clauses)
    property_block = "\n  ".join(property_clauses)
    labels_block = "\n  ".join(label_clauses)

    # 4. Construct final query
    # (Assuming SPARQL_PREFIXES is defined elsewhere in your script)
    query = f"""{SPARQL_PREFIXES}
SELECT DISTINCT {select_clause} WHERE {{
  {values_block}
  
  {where_block}
  
  {property_block}
  
  {labels_block}
}}
ORDER BY ?itemLabel
"""
    return query

def all_properties_query():
    query = SPARQL_PREFIXES + """
        SELECT DISTINCT ?entity_id ?entity_idLabel ?property ?propertyLabel WHERE {{
          VALUES ?entity_id {{{entity_ids}}} .
          ?entity_id ?prop [] .
          ?property wikibase:directClaim ?prop .
          ?property rdfs:label ?propertyLabel .
          FILTER (LANG(?propertyLabel) = "en") .
          ?entity_id rdfs:label ?entity_idLabel .
          FILTER (LANG(?entity_idLabel) = "en") .
        }}
    """
    return query

def count_analysis_query(property):
    query = SPARQL_PREFIXES + """
        SELECT ?item ?itemLabel WHERE {{
          VALUES ?entity_id {{{entity_ids}}} .
          ?entity_id wdt:{property} ?item .
          ?item rdfs:label ?itemLabel .
          FILTER (LANG(?itemLabel) = "en")
        }}
        GROUP BY ?item ?itemLabel
        ORDER BY ?itemLabel
    """
    return query

#new function

def extract_bindings(results_data, *keys):
    """
    Replaces all get_results, get_results_label, get_compare_results, etc.
    Works for both single queries (dictionary) and batched queries (lists).
    Usage: extract_bindings(results, "item") or extract_bindings(results, "item", "variable1Label")
    """
    bindings = results_data.get("results", {}).get("bindings", []) if isinstance(results_data, dict) else results_data
    
    if len(keys) == 1:
        return [b[keys[0]]["value"] for b in bindings if keys[0] in b]
    return [tuple(b[k]["value"] for k in keys if k in b) for b in bindings]

def chunk_list(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

#run sparql query

def Run_My_SPARQL_Query_by_batch(
    sparql_query_placeholder, 
    entity_lst, 
    chunk_size, 
    property_list=None, 
    prop_chunk_size=None, 
    exclude_props=None, 
    entity_prefix="wd:",   # Default is wd:, but can be changed
    prop_prefix="wdt:",    # Default is wdt:, but can be changed
    prop_sep=" "
):
    """
    Handles all batch variations. Handles missing properties, excluded properties, 
    custom prefixes for BOTH entities and properties, custom separators, 
    and handles complex nested chunking safely.
    """
    response_data = []
    
    # 1. Filter excluded properties
    if property_list and exclude_props:
        not_set = set(exclude_props)
        property_list = [prop for prop in property_list if prop not in not_set]

    # 1b. Dedupe, and refuse to run with an empty property list.
    # "FILTER (?property IN ())" and "VALUES ?property { }" are both legal SPARQL
    # that match nothing, so the endpoint returns 200 with zero rows and the
    # failure propagates silently as scores of 0.
    if property_list is not None:
        property_list = list(dict.fromkeys(property_list))

        if not property_list:
            raise ValueError(
                "property_list is empty after filtering - this query would return "
                "zero rows without raising. Check the query that produced it."
            )
        
    # 2. Handle property chunking safely
    if property_list:
        prop_batches = list(chunk_list(property_list, prop_chunk_size)) if prop_chunk_size else [property_list]
    else:
        prop_batches = [[]] # Fallback for no properties

    # 3. Loop through the entities
    for batch in chunk_list(entity_lst, chunk_size):
        # Apply the dynamic entity prefix here
        entity_ids = " ".join(f"{entity_prefix}{l.split('/')[-1]}" for l in batch)
        
        # 4. Loop through property batches
        for prop_batch in prop_batches:
            if prop_batch:
                # Apply the dynamic property prefix here
                property_ids = prop_sep.join(f"{prop_prefix}{l.split('/')[-1]}" for l in prop_batch)
            else:
                property_ids = ""
                
            sparql_query = sparql_query_placeholder.format(entity_ids=entity_ids, property_ids=property_ids)
            batch_data = Run_My_SPARQL_Query(sparql_query)
            time.sleep(1)
        
            # Defensive check
            if batch_data and "results" in batch_data and "bindings" in batch_data["results"]:
                response_data.extend(batch_data["results"]["bindings"])

    return response_data

#scores and plotting

def add_missing_scores(score_dict, qid_list, default=0):
    """
    Fills entities that produced no rows. Returns the number of entities filled,
    so callers can tell "no data at all" apart from a genuine score of zero.
    """
    filled = 0
    for qid in qid_list:
        if qid not in score_dict:
            score_dict[qid] = default
            filled += 1
    return filled
            
def basic_plot(scores):
    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    keys = [item[0] for item in sorted_items]
    values = [item[1] for item in sorted_items]

    plt.figure(figsize=(8, 5))
    plt.bar(keys, values, color='skyblue')
    plt.xlabel('Keys')
    plt.ylabel('Total Score')
    plt.title('Total Scores per Key (Descending)')
    plt.show()
    
def calculate_lang_scores(data, median):
    new_data = {}
    
    for main_key, sub_dict in data.items():
        new_data[main_key] = {}
        
        for sub_key, (description, count) in sub_dict.items():
            words = description.split()
            
            # Condition 1: Count < median AND 2 words or less AND all words < 7 characters
            if count < median and len(words) <= 2 and all(len(word) < 7 for word in words):
                score = 0.8
            # Condition 2: Count is 10 or more above the median
            elif count >= median + 10:
                score = 1.2
            # Condition 3: Neither of the above
            else:
                score = 1.0
                
            new_data[main_key][sub_key] = score
            
    return new_data
