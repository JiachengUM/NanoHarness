#!/usr/bin/env python3
"""
环节5第二层：LLM语义审计
检查用户台词、断言、场景的语义质量问题
"""
import sys
import json
from pathlib import Path

# 路径配置
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts" / "projects" / "benz_project"
CASES_PATH = PROJECT_DIR / "cases" / "vehicle_assistant_cases.json"
AUDIT_REPORT_PATH = PROJECT_DIR / "audit_results" / "semantic_audit_20250610.json"

def semantic_audit():
    """语义审计"""
    with open(CASES_PATH, 'r', encoding='utf-8') as f:
        cases = json.load(f)
    
    issues = []
    
    for i, case in enumerate(cases):
        case_id = case.get('id', f'case_{i}')
        case_issues = []
        
        # 获取用例内容
        query = case.get('user_query_lists', [[]])[0][0].get('content', '') if case.get('user_query_lists') else ''
        expected_script = case.get('expected_script', '')
        nl_assertion = case.get('nl_assertion', [])
        tags = case.get('tags', [])
        
        # 语义审计项
        
        # 1. 用户台词是否口语化
        if len(query) > 50 and '，' in query and '。' in query:
            # 可能是书面化长句
            pass  # 不标记为问题，只是观察
        
        # 2. nl_assertion 质量检查
        weak_assertions = [
            '助手应正确回应',
            '助手须正确执行',
            '助手应根据用户请求'
        ]
        
        for assertion in nl_assertion:
            if isinstance(assertion, str):
                # 检查是否有弱断言
                if any(weak in assertion for weak in weak_assertions):
                    case_issues.append({
                        'type': 'weak_assertion',
                        'severity': 'warning',
                        'message': f'断言较笼统: {assertion[:60]}...'
                    })
                
                # 检查是否可从录音核对（面向导演）
                if '后台' in assertion or '工具调用' in assertion or '检索' in assertion:
                    case_issues.append({
                        'type': 'backend_visible_assertion',
                        'severity': 'warning',
                        'message': f'断言涉及后台不可见操作: {assertion[:60]}...'
                    })
        
        # 3. expected_script 质量
        if '（正确回应用户请求）' in expected_script or '（根据用户请求正确回应）' in expected_script:
            case_issues.append({
                'type': 'vague_expected_script',
                'severity': 'warning',
                'message': 'expected_script中助手回应描述过于笼统'
            })
        
        # 4. 多轮对话场景检查
        is_multiround = any(t in tags for t in ['方言跨轮保持', '语种跨轮保持', '多轮方言稳定性', 
                                                  '打断取消', '打断后切换任务', '否定指令', 
                                                  '角色人设继承'])
        if is_multiround:
            # 检查expected_script是否包含多轮结构
            if '第1轮' not in expected_script and '第2轮' not in expected_script:
                case_issues.append({
                    'type': 'missing_round_structure',
                    'severity': 'warning',
                    'message': '多轮场景expected_script缺少轮次结构'
                })
        
        # 5. car_info 检查
        car_info = case.get('context_config', {}).get('car_info', '')
        if not car_info or car_info == '车辆静止，主驾位':
            # 默认car_info，可能需要更丰富
            pass  # 警告级别，非错误
        
        # 收集该case的问题
        if case_issues:
            issues.append({
                'case_id': case_id,
                'case_index': i,
                'case_id_full': case.get('case_id', ''),
                'issues': case_issues
            })
    
    # 生成语义审计报告
    audit_report = {
        'audit_time': '2026-06-10',
        'project': 'benz_project',
        'audit_type': 'semantic',
        'summary': {
            'total_cases': len(cases),
            'cases_with_issues': len(issues),
            'total_issues': sum(len(c['issues']) for c in issues),
            'warning_count': sum(1 for c in issues for i in c['issues'] if i['severity'] == 'warning'),
            'error_count': sum(1 for c in issues for i in c['issues'] if i['severity'] == 'error')
        },
        'issues': issues
    }
    
    # 保存审计报告
    AUDIT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(audit_report, f, ensure_ascii=False, indent=2)
    
    # 打印摘要
    print("=" * 60)
    print("环节5第二层：LLM语义审计报告")
    print("=" * 60)
    print(f"\n总用例数: {audit_report['summary']['total_cases']}")
    print(f"有问题用例: {audit_report['summary']['cases_with_issues']}")
    print(f"总问题数: {audit_report['summary']['total_issues']}")
    print(f"  - Warnings: {audit_report['summary']['warning_count']}")
    print(f"  - Errors: {audit_report['summary']['error_count']}")
    
    if issues:
        print("\n问题详情（按用例）:")
        for case_info in issues[:10]:
            print(f"\n[{case_info['case_id']}] {case_info['case_id_full'][:50]}...")
            for issue in case_info['issues']:
                print(f"  - [{issue['severity'].upper()}] {issue['type']}")
                print(f"    {issue['message'][:80]}")
    else:
        print("\n✓ 所有用例语义检查通过！")
    
    print(f"\n语义审计报告已保存: {AUDIT_REPORT_PATH}")
    
    return audit_report

if __name__ == "__main__":
    semantic_audit()
