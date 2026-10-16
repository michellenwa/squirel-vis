#SPECIFICITY QUERIES

def external_ids_query():

    query = """
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX schema: <http://schema.org/>
        PREFIX wikibase: <http://wikiba.se/ontology#>

        SELECT ?property WHERE {{
          VALUES ?item {{{entity_ids}}} .
          ?item ?p [] .
          ?property wikibase:claim ?p .
          ?property wikibase:propertyType wikibase:ExternalId .  # only external IDs
        }}

        """
    
    return query


def get_all_triples_query():
    
    query = """
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX schema: <http://schema.org/>
        PREFIX wikibase: <http://wikiba.se/ontology#>

        SELECT ?item ?property ?value WHERE {{

          VALUES ?property {{{property_ids}}}
          VALUES ?item {{{entity_ids}}}
          


          ?item ?property ?value .
        }}

        """
    return query

#QUALIFIER QUERIES

def property_uses_qualifiers_query():

    query = """
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX schema: <http://schema.org/>
        PREFIX wikibase: <http://wikiba.se/ontology#>
        PREFIX p: <http://www.wikidata.org/prop/>
        PREFIX ps: <http://www.wikidata.org/prop/statement/>

        PREFIX pq: <http://www.wikidata.org/prop/qualifier/>

        SELECT ?property (COUNT(?allowedQualifier) AS ?allowedQualifierCount) WHERE {{
          VALUES ?property {{{entity_ids}}}

          ?property p:P2302 ?constraintStatement .
          ?constraintStatement ps:P2302 wd:Q21510851 .  # allowed qualifier constraint
          ?constraintStatement pq:P2306 ?allowedQualifier .  # the allowed qualifier(s)
        }}
        GROUP BY ?property
        """
    
    return query
    
def item_qualifiers_query():

    query = """
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX schema: <http://schema.org/>
        PREFIX wikibase: <http://wikiba.se/ontology#>
        PREFIX p: <http://www.wikidata.org/prop/>
        PREFIX ps: <http://www.wikidata.org/prop/statement/>

        SELECT ?item ?property ?statement (COUNT(?qualifierProperty) AS ?qualifierCount) (COUNT(DISTINCT ?qualifierProperty) AS ?qualifierdistinctCount)
        WHERE {{
          VALUES ?item {{{entity_ids}}}
          VALUES ?property {{{property_ids}}}

          ?item ?property ?statement .
          ?statement ?qualifierProperty ?qualifierValue .
          
          # Restricts to real qualifier predicates without a STRSTARTS filter
          [] wikibase:qualifier ?qualifierProperty .
        
        }}
        GROUP BY ?item ?property ?statement
        ORDER BY DESC(?qualifierCount)
        """
    
    return query
    

#REFERENCE QUERIES
    
def reference_count_query():
    query = """
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wikibase: <http://wikiba.se/ontology#>
        PREFIX prov: <http://www.w3.org/ns/prov#>
        PREFIX pr: <http://www.wikidata.org/prop/reference/>

        SELECT ?item ?statementCount (COALESCE(?refCount, 0) AS ?referenceCount) (COALESCE(?distinctRefCount, 0) AS ?distinctreferenceCount)
        WHERE {{
          VALUES ?item {{{entity_ids}}} .
          
          # 1. INDEPENDENT SUBQUERY: Count the statements
          {{
            SELECT ?item (COUNT(DISTINCT ?statement) AS ?statementCount)
            WHERE {{
              VALUES ?item {{{entity_ids}}} .
              ?item ?p ?statement .
              ?statement wikibase:rank [] .
            }}
            GROUP BY ?item
          }}
          
          # 2. INDEPENDENT SUBQUERY: Count the valid references
          OPTIONAL {{
            SELECT ?item (COUNT(?reference) AS ?refCount) (COUNT(DISTINCT ?reference) AS ?distinctRefCount)
            WHERE {{
              VALUES ?item {{{entity_ids}}} .
              ?item ?p ?statement .
              ?statement wikibase:rank [] .
              ?statement prov:wasDerivedFrom ?reference .
              
              MINUS {{ ?reference pr:P143 [] . }}
            }}
            GROUP BY ?item
          }}
        }}
        """
    return query

#INTERNAL QUERIES

def internal_links_query():

    query = """
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX schema: <http://schema.org/>
        PREFIX wikibase: <http://wikiba.se/ontology#>

        SELECT ?value (COUNT(*) AS ?count)
        WHERE {{
          VALUES ?value {{{entity_ids}}} .
            ?subject ?p ?value .
            FILTER(STRSTARTS(STR(?p), STR(wdt:)))
            FILTER(STRSTARTS(STR(?subject), "http://www.wikidata.org/entity/Q"))
        }}
        GROUP BY ?value 
        """
    
    return query
    
    
#EXTERNAL QUERIES

def external_ids_count_query():

    query = """
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX schema: <http://schema.org/>
        PREFIX wikibase: <http://wikiba.se/ontology#>

        SELECT ?property (COUNT(?property) AS ?propertyCount) WHERE {{
          VALUES ?item {{{entity_ids}}} .
          ?item ?p [] .
          ?property wikibase:claim ?p .
          ?property wikibase:propertyType wikibase:ExternalId .  # only external IDs
        }}
        GROUP BY ?property
        ORDER BY DESC(?propertyCount)

        """
    
    return query

def external_ids_counts_query():

    query = """
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX schema: <http://schema.org/>
        PREFIX wikibase: <http://wikiba.se/ontology#>

        SELECT ?item (COUNT(?property) AS ?propertyCount) WHERE {{
          VALUES ?item {{{entity_ids}}} .
          VALUES ?property {{{property_ids}}} .
       	   ?item ?property [] .
          
 
        }}
        GROUP BY ?item
        
        """
    
    return query


#LINGUISTIC QUERIES

def label_language_query():

    query = """
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX schema: <http://schema.org/>
        PREFIX wikibase: <http://wikiba.se/ontology#>

        SELECT DISTINCT ?item ?lang
        WHERE {{
          VALUES ?item {{{entity_ids}}} 
  
          ?item rdfs:label ?label .
          BIND(LANG(?label) AS ?lang)
        }}
        ORDER BY ?item ?lang

        """
    
    return query

def alias_language_query():

    query = """
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX schema: <http://schema.org/>
        PREFIX wikibase: <http://wikiba.se/ontology#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        
        SELECT ?item ?lang (COUNT(?alias) AS ?aliasCount)
        WHERE {{
          VALUES ?item {{{entity_ids}}}
  
          ?item skos:altLabel ?alias .

        }}
        GROUP BY ?item (LANG(?alias) AS ?lang)
        ORDER BY DESC(?aliasCount) 

        """
    
    return query

def description_language_query():

    query = """
        PREFIX wd: <http://www.wikidata.org/entity/>
        PREFIX wdt: <http://www.wikidata.org/prop/direct/>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX schema: <http://schema.org/>
        PREFIX wikibase: <http://wikiba.se/ontology#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        
        SELECT ?item ?lang ?description (STRLEN(?description) AS ?char_count)
        WHERE {{
          VALUES ?item {{{entity_ids}}}
          ?item schema:description ?description .
          BIND(LANG(?description) AS ?lang)
        }}

        """
    
    return query
