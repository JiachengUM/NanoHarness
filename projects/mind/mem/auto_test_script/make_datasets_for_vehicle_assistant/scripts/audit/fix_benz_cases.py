#!/usr/bin/env python3
"""
环节6：审计修复 - 修复benz_project用例的语义问题
"""
import sys
import json
from pathlib import Path
import re

# 路径配置
PROJECT_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts" / "projects" / "benz_project"
CASES_PATH = PROJECT_DIR / "cases" / "vehicle_assistant_cases.json"
AUDIT_REPORT_PATH = PROJECT_DIR / "audit_results" / "semantic_audit_20250610.json"

def get_expected_response_hint(tag, user_query):
    """根据标签和用户查询生成更具体的助手回应提示"""
    hints = {
        '否定指令': '助手：好的，我停止当前任务。您想要我...',
        '打断取消': '助手：（立即停止当前任务）好的，已停止/已取消。',
        '打断后切换任务': '助手：（停止原任务）好的，我立即为您...（开始新任务）',
        '角色人设继承': '助手：（保持设定人设的语气回应）',
        '自定义人设跨轮保持': '助手：（继续保持人设特征）',
        '方言跨轮保持': '助手：（用指定方言回应，保留方言词汇）',
        '语种跨轮保持': '助手：（用指定语种回应）',
        '多轮方言稳定性': '助手：（持续保持方言/语种）',
        '任务执行中打断': '助手：（立即停止当前执行中的任务）',
    }
    
    for t, hint in hints.items():
        if t in tag:
            return hint
    
    return '助手：（根据用户请求恰当回应）'

def fix_expected_script(original_script, tags):
    """修复expected_script，让助手回应更具体"""
    # 替换笼统的助手回应
    fixed = original_script
    
    vague_patterns = [
        '（根据用户请求正确回应）',
        '（正确回应用户请求）',
        '（根据原始query执行相应动作）',
        '（助手：（正确回应用户请求）',
    ]
    
    for pattern in vague_patterns:
        if pattern in fixed:
            # 根据标签生成更具体的提示
            hint = get_expected_response_hint(tags[0] if tags else '', '')
            fixed = fixed.replace(pattern, hint)
    
    return fixed

def fix_cases():
    """修复用例"""
    # 加载用例
    with open(CASES_PATH, 'r', encoding='utf-8') as f:
        cases = json.load(f)
    
    # 加载审计报告
    with open(AUDIT_REPORT_PATH, 'r', encoding='utf-8') as f:
        audit_report = json.load(f)
    
    issues_by_case = {item['case_id']: item['issues'] for item in audit_report['issues']}
    
    fixed_count = 0
    
    for case in cases:
        case_id = case.get('id', '')
        
        if case_id not in issues_by_case:
            continue
        
        issues = issues_by_case[case_id]
        fixed_issues = []
        
        for issue in issues:
            issue_type = issue['type']
            
            if issue_type == 'vague_expected_script':
                # 修复笼统的expected_script
                original = case.get('expected_script', '')
                tags = case.get('tags', [])
                fixed = fix_expected_script(original, tags)
                case['expected_script'] = fixed
                fixed_issues.append(f'fixed: {issue_type}')
                
            elif issue_type == 'weak_assertion':
                # 增强断言（可选，暂不自动修复）
                pass
                
            elif issue_type == 'backend_visible_assertion':
                # 修正后台可见断言（可选）
                pass
        
        if fixed_issues:
            fixed_count += 1
            # 添加修复标记
            case['_fixed'] = fixed_issues
    
    # 保存修复后的用例
    with open(CASES_PATH, 'w', encoding='utf-8') as f:
        json.dump(cases, f, ensure_ascii=False, indent=2)
    
    print("=" * 60)
    print("环节6：审计修复完成")
    print("=" * 60)
    print(f"\n修复用例数: {fixed_count}")
    print(f"修复后总用例数: {len(cases)}")
    
    # 显示修复示例
    print("\n修复示例（前3条）:")
    for case in cases[:3]:
        if '_fixed' in case:
            print(f"\n[{case['id']}] {case['case_id'][:40]}...")
            print(f"  修复项: {case['_fixed']}")
            # 显示部分修复后的expected_script
            script_lines = case['expected_script'].split('\n')
            for line in script_lines[:5]:
                if '助手' in line:
                    print(f"  助手行: {line[:60]}...")
                    break

if __name__ == "__main__":
    fix_cases()
