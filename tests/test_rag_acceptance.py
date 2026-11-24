"""Local protocol + retrieval acceptance; no Harness UI or external LLM calls."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from rag.settings import configure_environment
configure_environment()

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def unpack(result):
    assert not result.is_error, result
    structured = result.structured_content
    if structured:
        return structured
    return json.loads(''.join(item.text for item in result.content if item.type == 'text'))


async def main():
    params = StdioServerParameters(command=str(ROOT / '.venv/Scripts/python.exe'),
                                   args=['-u', str(ROOT / 'ad_agent/mcp_server.py')],
                                   cwd=str(ROOT), env={**os.environ, 'PYTHONUTF8': '1',
                                                       'PYTHONIOENCODING': 'utf-8'})
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as client:
            await client.initialize()
            tools = await client.list_tools()
            assert {tool.name for tool in tools.tools} == {'schema_search', 'metric_search', 'sql_validate', 'sql_execute', 'result_analyze'}
            schema = unpack(await client.call_tool('schema_search',
                {'table_name': 'raw_criteo_impression'}))
            assert len(schema['tables']['raw_criteo_impression']) == 23
            assert {'click', 'campaign'} <= {row['column_name'] for row in schema['tables']['raw_criteo_impression']}
            missing = unpack(await client.call_tool('schema_search',
                {'table_name': 'raw_criteo_impression', 'query': 'ad_id'}))
            assert missing['found'] is False and missing['missing_fields']==['ad_id']
            print('PASS: MCP handshake, tools, actual metadata, absent field and metadata routing', flush=True)
            question = 'CTR 是什么？使用哪个字段计算？'
            answer = unpack(await client.call_tool('metric_search', {'query': question}))
            assert answer['route'] == 'bge_m3_chroma_with_live_metadata'
            ctr_hits = [hit for hit in answer['knowledge']
                        if hit['source'] == 'knowledge/metric_definitions.md' and 'CTR' in hit['heading']]
            assert ctr_hits, 'CTR definition not present in top 3 semantic results'
            context = answer['agent_context']
            assert all(term in context for term in ('click', 'campaign', 'SUM(click)', 'COUNT(*)', '曝光'))
            assert {'click', 'campaign'} <= {row['field_name'] for row in answer['database_metadata']['columns']}
            print('PASS: CTR retrieves click, campaign, exposure count and formula', flush=True)
            time_answer = unpack(await client.call_tool('metric_search',
                {'query': '最近七天按什么时间范围查询，能用当前日期吗？'}))
            assert any(hit['source'] == 'knowledge/business_rules.md'
                       and '时间' in hit['heading'] for hit in time_answer['knowledge'])
            print('PASS: relative-time business rule retrieved', flush=True)
            query='SELECT campaign_id,impressions,clicks,ctr FROM ads_campaign_daily ORDER BY campaign_id LIMIT 5'
            validation=unpack(await client.call_tool('sql_validate',{'sql':query}))
            assert validation['valid']
            executed=unpack(await client.call_tool('sql_execute',{'sql':query}))
            assert executed['ok'] and executed['returned_rows']==5
            analysis=unpack(await client.call_tool('result_analyze',{'result_id':executed['result_id']}))
            assert analysis['records']==executed['rows']
            print('PASS: five-tool MCP chain returns and analyzes real read-only SQL results',flush=True)
            report = {
                'verified_at': datetime.now(timezone.utc).isoformat(), 'passed': True,
                'external_llm_calls': 0, 'harness_ui_opened': False,
                'tools': [tool.name for tool in tools.tools],
                'question': question, 'ctr_result': answer,
                'relative_time_sources': [{'source': h['source'], 'heading': h['heading']}
                                          for h in time_answer['knowledge']],
                'sql_result':executed,'analysis_result':analysis,
            }
            (ROOT / 'rag/acceptance_report.json').write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    asyncio.run(main())
