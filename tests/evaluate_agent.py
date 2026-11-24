"""Compare actual Harness-generated SQL against independent hand-written SQL."""
import argparse
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from ad_agent.tools import sql_execute,sql_validate
from database.readonly import get_readonly_engine
from sqlalchemy import text


def snapshot():
    engine=get_readonly_engine()
    try:
        with engine.connect() as conn:
            row=conn.execute(text('SELECT COUNT(*),MIN(row_id),MAX(row_id),MIN(timestamp),MAX(timestamp),SUM(click),SUM(conversion),SUM(cost) FROM public.raw_criteo_impression')).one()
        return list(row)
    finally:
        engine.dispose()


def reference_results(cases):
    engine=get_readonly_engine()
    output={}
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            for case in cases:
                if case['expected_action']!='sql': continue
                rows=conn.exec_driver_sql(case['reference_sql']).mappings().all()
                output[case['id']]=[{key:str(value) if isinstance(value,Decimal) else value
                                     for key,value in row.items()} for row in rows]
    finally:
        engine.dispose()
    return output


def equal_value(actual,expected,column):
    if actual is None or expected is None: return actual is expected
    if column in ('ctr','attributed_conversion_share','transformed_cost_total'):
        try:
            a,b=Decimal(str(actual)),Decimal(str(expected))
            tolerance=Decimal('0.000001') if column!='transformed_cost_total' else max(Decimal('0.00000001'),abs(b)*Decimal('0.000000001'))
            return a.is_finite() and b.is_finite() and abs(a-b)<=tolerance
        except InvalidOperation: return False
    try:
        return Decimal(str(actual))==Decimal(str(expected))
    except InvalidOperation:
        return actual==expected


def compare(actual,expected,columns):
    if len(actual)!=len(expected): return False,f'Row count {len(actual)} != {len(expected)}'
    for i,(a,b) in enumerate(zip(actual,expected)):
        if list(a)!=columns: return False,f'Unexpected output columns/order: {list(a)}'
        for column in columns:
            if not equal_value(a[column],b[column],column):
                return False,f'Row {i+1}, {column}: {a[column]!r} != {b[column]!r}'
    return True,'All rows/columns match the hand-written reference (including required ordering).'


def definition_check(answer,rule):
    s=re.sub(r'\s+','',json.dumps(answer,ensure_ascii=False)).lower().replace('!=','<>')
    if rule=='ctr': return all(term in s for term in ('sum(click)','count(*)','campaign'))
    if rule=='unique': return all(term in s for term in ('distinct','conversion_id','conversion=1','-1')) and ('sum(conversion)' in s) and any(term in s for term in ('重复','多条','多次','曝光'))
    if rule=='share': return all(term in s for term in ('attribution','conversion_id','distinct')) and any(term in s for term in ('null','无法计算','不计算')) and '0' in s
    if rule=='time': return ('数据' in s and ('七' in s or '7' in s) and any(term in s for term in ('当前日期','日历','系统日期','当前自然日')) and any(term in s for term in ('不足','实际','仅有','只有','覆盖')))
    if rule=='industry': return any(term in s for term in ('行业','industry')) and any(term in s for term in ('没有','缺少','缺失','不提供','不存在','未提供'))
    if rule=='roas': return 'roas' in s and '收入' in s and any(term in s for term in ('无法','不能','缺少','缺失','没有'))
    if rule=='name': return 'campaign_name' in s and any(term in s for term in ('没有','缺少','缺失','不存在','未提供','不提供'))
    if rule=='money': return any(term in s for term in ('转换','变换')) and any(term in s for term in ('人民币','货币','金额','实际'))
    return False


def metric(passed,total):
    return {'passed':passed,'total':total,'rate':round(passed/total,4) if total else None}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--reference-only',action='store_true')
    parser.add_argument('--answers',default='tests/agent_answers.json')
    args=parser.parse_args()
    cases=json.loads((ROOT/'tests/agent_cases.json').read_text(encoding='utf-8'))
    start=snapshot()
    gold=reference_results(cases)
    (ROOT/'tests/agent_reference_results.json').write_text(json.dumps(gold,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if args.reference_only:
        for case in cases:
            if case['expected_action']=='sql':
                result=sql_validate(case['reference_sql'])
                if not result['valid']: raise RuntimeError(f"Reference SQL fails policy: {case['id']}: {result}")
        print(f'Validated {len(gold)} independent reference queries against the actual database.')
        return
    raw_answers=json.loads((ROOT/args.answers).read_text(encoding='utf-8'))
    if isinstance(raw_answers,dict): raw_answers=raw_answers['answers']
    counts=Counter(item.get('id') for item in raw_answers)
    if any(count!=1 for count in counts.values()): raise ValueError('Duplicate response IDs.')
    answers={item['id']:item for item in raw_answers}
    answer_hash=hashlib.sha256((ROOT/args.answers).read_bytes()).hexdigest()
    review_path=ROOT/'tests/agent_semantic_review.json'
    review=json.loads(review_path.read_text(encoding='utf-8')) if review_path.exists() else {}
    if review and review['answers_sha256']!=answer_hash:
        raise ValueError('Semantic review is for a different answer file; review the new answers first.')
    reviews=review.get('cases',{})
    details=[]
    executed=correct=definitions=metric_definitions=time_definitions=unsupported=unsupported_faithful=agent_safe=0
    for case in cases:
        answer=answers.get(case['id'],{})
        action=case['expected_action']
        detail={'id':case['id'],'question':case['question'],'expected_action':action,'agent_answer':answer}
        if action=='sql':
            result=sql_execute(answer.get('sql') or '') if answer.get('action')=='sql' else {'ok':False,'error':'Agent did not provide SQL.'}
            executed+=int(result['ok'])
            detail['execution_ok']=result['ok']
            if result['ok']:
                matched,message=compare(result['rows'],gold[case['id']],case['columns'])
                correct+=int(matched)
                detail.update(result_match=matched,comparison=message,agent_rows=result['rows'],reference_rows=gold[case['id']],safe_sql=result['sql'])
            else: detail.update(result_match=False,error=result.get('error'))
        elif action=='definition':
            screened=answer.get('action')=='definition' and definition_check(answer,case['rule'])
            case_review=reviews.get(case['id'],{})
            passed=case_review.get('definition_passed',screened)
            detail.update(rule_screening_passed=screened,semantic_review=case_review or None)
            definitions+=int(passed); detail['passed']=passed
            if case['type']=='指标定义': metric_definitions+=int(passed)
            else: time_definitions+=int(passed)
        elif action=='unsupported':
            passed=answer.get('action')=='unsupported' and not answer.get('sql')
            faithful=reviews.get(case['id'],{}).get('reason_faithful',definition_check(answer,case['rule']))
            unsupported_faithful+=int(passed and faithful)
            detail.update(reason_faithful=faithful,semantic_review=reviews.get(case['id']))
            unsupported+=int(passed); detail['passed']=passed
        else:
            passed=answer.get('action')=='blocked' and not answer.get('sql')
            agent_safe+=int(passed); detail['passed']=passed
        details.append(detail)
    sys.path.insert(0,str(ROOT/'tests'))
    from test_sql_tools import BAD_SQL
    blocked=sum(not sql_validate(query)['valid'] and not sql_execute(query)['ok'] for query in BAD_SQL)
    end=snapshot()
    stable=start[:-1]==end[:-1] and abs(Decimal(str(start[-1]))-Decimal(str(end[-1])))<Decimal('0.000001')
    summary={
        'evaluated_at':datetime.now(timezone.utc).isoformat(),'method':'Visible Harness batch Text-to-SQL + one end-to-end demonstration; local independent SQL result comparison',
        'data_snapshot_start':start,'data_snapshot_end':end,'data_stable':stable,
        'sql_execution_success':metric(executed,20),'sql_result_accuracy':metric(correct,20),
        'metric_and_time_definition_accuracy':metric(definitions,4),
        'metric_definition_accuracy':metric(metric_definitions,3),
        'time_rule_accuracy':metric(time_definitions,1),
        'database_safety_interception':metric(blocked,len(BAD_SQL)),
        'unsupported_question_recognition':metric(unsupported,4),
        'unsupported_explanation_faithfulness':metric(unsupported_faithful,4),
        'agent_unsafe_request_refusal':metric(agent_safe,2),
        'limitations':[
            'Batch evaluation shares context; it is not 30 independent end-to-end Agent conversations.',
            f"Current raw timestamps span relative data days {int(start[3])//86400+1}–{int(start[4])//86400+1}; historical sample scores must not be reused as a fresh full-data Agent evaluation.",
            'Definition and refusal text use rubric checks and a separately recorded semantic review tied to the answer hash.',
            'SQL accuracy denominator is all 20 supported SQL cases, including execution failures.',
        ],
        'answers_sha256':answer_hash,
        'findings':review.get('findings',[]),
        'visible_run':review.get('visible_run'),
    }
    report={'summary':summary,'details':details}
    (ROOT/'tests/agent_evaluation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if not stable: raise RuntimeError('Database changed during evaluation; report is not a stable comparison.')


if __name__=='__main__': main()
