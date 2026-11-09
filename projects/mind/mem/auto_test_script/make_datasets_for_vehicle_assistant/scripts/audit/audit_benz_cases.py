#!/usr/bin/env python3
"""
环节5：质量审计 - 对benz_project用例进行审计
"""
import sys
import json
from pathlib import Path
from collections import defaultdict

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parents[7]))

from projects.mind.mem.auto_test_script.case_schema import TestCase

# 路径配置
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts" / "projects" / "benz_project"
CASES_PATH = PROJECT_DIR / "cases" / "vehicle_assistant_cases.json"
TAG_TREE_PATH = PROJECT_DIR / "tag_tree" / "vehicle_assistant_case_tag_tree.json"
AUDIT_REPORT_PATH = PROJECT_DIR / "audit_results" / "audit_report_20250610.json"

def load_tag_tree():
    """加载标签树，获取所有叶子标签"""
    with open(TAG_TREE_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    def collect_leaves(node):
        if 'children' not in node or not node['children']:
            return [node['name']]
        leaves = []
        for child in node['children']:
            leaves.extend(collect_leaves(child))
        return leaves
    
    return set(collect_leaves(data['root']))

def audit_cases():
    """审计用例"""
    # 加载数据
    with open(CASES_PATH, 'r', encoding='utf-8') as f:
        cases = json.load(f)
    
    valid_leaf_tags = load_tag_tree()
    
    # 审计结果
    issues = []
    stats = {
        'total_cases': len(cases),
        'schema_valid': 0,
        'schema_invalid': 0,
        'tag_issues': 0,
        'format_issues': 0
    }
    
    for i, case in enumerate(cases):
        case_id = case.get('id', f'case_{i}')
        case_issues = []
        
        # 1. Schema 校验
        try:
            TestCase(**case)
            stats['schema_valid'] += 1
        except Exception as e:
            stats['schema_invalid'] += 1
            case_issues.append({
                'type': 'schema_error',
                'severity': 'error',
                'message': str(e)[:200]
            })
        
        # 2. 标签审计
        tags = case.get('tags', [])
        invalid_tags = [t for t in tags if t not in valid_leaf_tags]
        if invalid_tags:
            stats['tag_issues'] += 1
            case_issues.append({
                'type': 'invalid_tags',
                'severity': 'error',
                'message': f'非叶子标签: {invalid_tags}'
            })
        
        # 3. 格式审计 - expected_script
        expected_script = case.get('expected_script', '')
        if '【' in expected_script or '】' in expected_script:
            stats['format_issues'] += 1
            case_issues.append({
                'type': 'format_error',
                'severity': 'warning',
                'message': 'expected_script 包含【】格式，应改为（）'
            })
        
        # 4. 格式审计 - user_query_lists
        user_query_lists = case.get('user_query_lists', [])
        if not user_query_lists:
            case_issues.append({
                'type': 'missing_user_query',
                'severity': 'error',
                'message': 'user_query_lists 为空'
            })
        
        # 5. 断言审计
        nl_assertion = case.get('nl_assertion', [])
        if not nl_assertion:
            case_issues.append({
                'type': 'missing_assertion',
                'severity': 'error',
                'message': 'nl_assertion 为空'
            })
        elif all(not s.strip() for s in nl_assertion if isinstance(s, str)):
            case_issues.append({
                'type': 'empty_assertion',
                'severity': 'error',
                'message': 'nl_assertion 全为空白'
            })
        
        # 收集该case的所有问题
        if case_issues:
            issues.append({
                'case_id': case_id,
                'case_index': i,
                'issues': case_issues
            })
    
    # 生成审计报告
    audit_report = {
        'audit_time': '2026-06-10',
        'project': 'benz_project',
        'summary': {
            'total_cases': stats['total_cases'],
            'schema_valid': stats['schema_valid'],
            'schema_invalid': stats['schema_invalid'],
            'cases_with_issues': len(issues),
            'total_issues': sum(len(c['issues']) for c in issues)
        },
        'stats': stats,
        'issues': issues
    }
    
    # 保存审计报告
    AUDIT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_REPORT_PATH, 'w', encoding='utf-8') as f:
        json.dump(audit_report, f, ensure_ascii=False, indent=2)
    
    # 打印摘要
    print("=" * 60)
    print("环节5：质量审计报告")
    print("=" * 60)
    print(f"\n总用例数: {stats['total_cases']}")
    print(f"Schema通过: {stats['schema_valid']}")
    print(f"Schema失败: {stats['schema_invalid']}")
    print(f"有问题用例: {len(issues)}")
    print(f"总问题数: {sum(len(c['issues']) for c in issues)}")
    
    if issues:
        print("\n问题详情（前5条）:")
        for case_info in issues[:5]:
            print(f"\n[{case_info['case_id']}]")
            for issue in case_info['issues']:
                print(f"  - [{issue['severity']}] {issue['type']}: {issue['message'][:80]}")
    
    print(f"\n审计报告已保存: {AUDIT_REPORT_PATH}")
    
    return audit_report

if __name__ == "__main__":
    audit_cases()
