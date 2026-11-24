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
        '回答本项目广告字段、指标和时间规则前使用本服务器检索。'
        '表名、字段名及类型优先调用 schema_search，缺失字段不得猜测。'
        'CTR、归因、时间范围及业务限制调用 metric_search。'
        '查询数据时先调用 sql_validate，再调用 sql_execute；执行端会再次校验。'
        'SQL 必须显式设置最外层 LIMIT 1-1000，只能查询两个项目白名单对象。'
        '拿 sql_execute 返回的 result_id 调用 result_analyze，将 agent_context 交给模型解释并引用来源。'
        'cost/cpo 不是真实货币金额，不能计算真实 ROAS。'
        '最近七天指数据时间轴，不是当前日期。不要为了检索调用外部 LLM。'
    ),
)


READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


@server.tool(annotations=READ_ONLY)
def schema_search(query: str = '', table_name: str | None = None) -> dict:
    """从实时 information_schema 查询表结构和字段；物化视图补查 pg_catalog。query 示例：campaign、click。"""
    return tools.schema_search(query, table_name)


@server.tool(annotations=READ_ONLY)
def metric_search(query: str, top_k: int = 3) -> dict:
    """使用 BGE-M3/Chroma 检索 CTR、转化、归因及业务规则，返回公式、字段和来源；不调用外部模型。"""
    return tools.metric_search(query, top_k)


@server.tool(annotations=READ_ONLY)
def sql_validate(sql: str) -> dict:
    """用 SQLGlot 检查单条 SELECT、表白名单、实时字段、函数与显式 LIMIT 1-1000。返回 valid 和 safe_sql。"""
    return tools.sql_validate(sql)


@server.tool(annotations=READ_ONLY)
def sql_execute(sql: str) -> dict:
    """再次安全检查后以 criteo_reader 执行只读查询，超时 5 秒、最多 1000 行/1MB。返回真实 rows 和 result_id。"""
    return tools.sql_execute(sql)


@server.tool(annotations=READ_ONLY)
def result_analyze(result_id: str, preview_rows: int = 20) -> dict:
    """整理 sql_execute 的真实结果为结构化记录、列摘要和 Agent 上下文；只接收真实 result_id，不接受编造的记录。"""
    return tools.result_analyze(result_id, preview_rows)


if __name__ == '__main__':
    server.run(transport='stdio')
