"""Harness MCP bridge. Imports the embedding model lazily, only for semantic search."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.settings import configure_environment
configure_environment()

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from ad_agent import tools

server = MCPServer(
    'ads_knowledge',
    instructions=(
        '�ش���Ŀ����ֶΡ�ָ���ʱ�����ǰʹ�ñ�������������'
        '�������ֶ������������ȵ��� schema_search��ȱʧ�ֶβ��ò²⡣'
        'CTR������ʱ�䷶Χ��ҵ�����Ƶ��� metric_search��'
        '��ѯ����ʱ�ȵ��� sql_validate���ٵ��� sql_execute��ִ�ж˻��ٴ�У�顣'
        'SQL ������ʽ��������� LIMIT 1-1000��ֻ�ܲ�ѯ������Ŀ����������'
        '�� sql_execute ���ص� result_id ���� result_analyze���� agent_context ����ģ�ͽ��Ͳ�������Դ��'
        'cost/cpo ������ʵ���ҽ����ܼ�����ʵ ROAS��'
        '�������ָ����ʱ���ᣬ���ǵ�ǰ���ڡ���ҪΪ�˼��������ⲿ LLM��'
    ),
)


READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


@server.tool(annotations=READ_ONLY)
def schema_search(query: str = '', table_name: str | None = None) -> dict:
    """��ʵʱ information_schema ��ѯ���ṹ���ֶΣ��ﻯ��ͼ���� pg_catalog��query ʾ����campaign��click��"""
    return tools.schema_search(query, table_name)


@server.tool(annotations=READ_ONLY)
def metric_search(query: str, top_k: int = 3) -> dict:
    """ʹ�� BGE-M3/Chroma ���� CTR��ת��������ҵ����򣬷��ع�ʽ���ֶκ���Դ���������ⲿģ�͡�"""
    return tools.metric_search(query, top_k)


@server.tool(annotations=READ_ONLY)
def sql_validate(sql: str) -> dict:
    """�� SQLGlot ��鵥�� SELECT������������ʵʱ�ֶΡ���������ʽ LIMIT 1-1000������ valid �� safe_sql��"""
    return tools.sql_validate(sql)


@server.tool(annotations=READ_ONLY)
def sql_execute(sql: str) -> dict:
    """�ٴΰ�ȫ������ criteo_reader ִ��ֻ����ѯ����ʱ 5 �롢��� 1000 ��/1MB��������ʵ rows �� result_id��"""
    return tools.sql_execute(sql)


@server.tool(annotations=READ_ONLY)
def result_analyze(result_id: str, preview_rows: int = 20) -> dict:
    """���� sql_execute ����ʵ���Ϊ�ṹ����¼����ժҪ�� Agent �����ģ�ֻ������ʵ result_id�������ܱ���ļ�¼��"""
    return tools.result_analyze(result_id, preview_rows)


if __name__ == '__main__':
    server.run(transport='stdio')
