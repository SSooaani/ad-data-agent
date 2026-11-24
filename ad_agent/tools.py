from ad_agent.catalog import schema_search
from ad_agent.sql_policy import sql_validate
from ad_agent.sql_tools import result_analyze, sql_execute


def metric_search(query, top_k=3):
    from rag.retrieve import retrieve
    return retrieve(query, top_k, force_semantic=True)
