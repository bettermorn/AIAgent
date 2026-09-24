#!/usr/bin/env python3
"""
法律合规助手 API 测试客户端
使用示例: python test_client.py
"""

import requests
import json
import sys
from typing import Dict, Any

# API基础URL
BASE_URL = "http://127.0.0.1:8000"

def test_health_check():
    """测试健康检查端点"""
    print("=== 健康检查 ===")
    try:
        response = requests.get(f"{BASE_URL}/healthz")
        if response.status_code == 200:
            print("✅ 服务器运行正常")
            return True
        else:
            print(f"❌ 健康检查失败: {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到服务器，请确保服务器正在运行")
        return False

def test_qa_api():
    """测试法规问答API"""
    print("\n=== 法规问答测试 ===")
    url = f"{BASE_URL}/api/qa"
    
    questions = [
        {
            "question": "GDPR规定的个人数据处理的法律依据有哪些？",
            "jurisdictions": ["EU"],
            "as_of": "2025-09-01"
        },
        {
            "question": "企业如何履行数据可携带权？",
            "jurisdictions": ["EU"]
        },
        {
            "question": "什么是个人信息销售的选择退出权？",
            "jurisdictions": ["US", "CA"]
        },
        {
            "question": "数据保护官的主要职责是什么？",
            "jurisdictions": ["EU"],
            "as_of": "2025-09-01"
        }
    ]
    
    for i, question in enumerate(questions):
        print(f"\n--- 问题 {i+1} ---")
        print(f"问题: {question['question']}")
        
        try:
            response = requests.post(url, json=question)
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 答案: {result['answer'][:200]}...")
                print(f"📊 置信度: {result['confidence']}")
                print(f"📚 引用数量: {len(result['citations'])}")
                if result['citations']:
                    print(f"🔗 主要引用: {result['citations'][0]['title']}")
            else:
                print(f"❌ 请求失败: {response.status_code}")
                print(f"错误信息: {response.text}")
        except Exception as e:
            print(f"❌ 请求异常: {e}")

def test_compliance_gap():
    """测试合规差距分析"""
    print("\n=== 合规差距分析测试 ===")
    url = f"{BASE_URL}/api/compliance/gap"
    
    # 读取示例数据
    try:
        with open("examples/fact.json", "r", encoding="utf-8") as f:
            fact = json.load(f)
    except FileNotFoundError:
        print("❌ 找不到示例文件 examples/fact.json")
        return
    
    test_cases = [
        {"fact": fact},
        {"fact": fact, "policies": ["gdpr"]},
        {"fact": fact, "policies": ["ccpa"]},
    ]
    
    for i, case in enumerate(test_cases):
        print(f"\n--- 测试案例 {i+1} ---")
        policies = case.get("policies", ["所有政策"])
        print(f"分析政策: {', '.join(policies)}")
        
        try:
            response = requests.post(url, json=case)
            if response.status_code == 200:
                result = response.json()
                print(f"✅ 发现 {len(result['gaps'])} 个潜在合规问题")
                
                # 显示前3个问题
                for j, gap in enumerate(result['gaps'][:3]):
                    print(f"  {j+1}. 控制措施: {gap['control_id']}")
                    print(f"     状态: {gap['status']} | 风险: {gap['risk']}")
                    
                if 'summary' in result:
                    print(f"📋 总结: {result['summary']}")
            else:
                print(f"❌ 请求失败: {response.status_code}")
                print(f"错误信息: {response.text}")
        except Exception as e:
            print(f"❌ 请求异常: {e}")

def test_contract_review():
    """测试合同审查"""
    print("\n=== 合同审查测试 ===")
    url = f"{BASE_URL}/api/contracts/review"
    
    # 测试文件列表
    test_files = [
        "examples/sample_contract.txt",
    ]
    
    for file_path in test_files:
        print(f"\n--- 审查文件: {file_path} ---")
        try:
            with open(file_path, "rb") as f:
                files = {"file": f}
                response = requests.post(url, files=files)
                
            if response.status_code == 200:
                result = response.json()
                print("✅ 合同审查完成")
                print(f"📊 提取的条款: {len(result.get('extracted', {}))}")
                print(f"⚠️  风险项数量: {len(result.get('risks', []))}")
                
                # 显示主要风险
                for i, risk in enumerate(result.get('risks', [])[:3]):
                    print(f"  风险 {i+1}: {risk}")
                    
            else:
                print(f"❌ 请求失败: {response.status_code}")
                print(f"错误信息: {response.text}")
        except FileNotFoundError:
            print(f"❌ 找不到文件: {file_path}")
        except Exception as e:
            print(f"❌ 请求异常: {e}")

def create_sample_files():
    """创建额外的示例文件"""
    print("\n=== 创建示例文件 ===")
    
    # 创建简单合同示例
    simple_contract = """
软件许可协议

甲方：技术公司
乙方：客户公司

第一条 许可范围
甲方同意向乙方提供软件使用权，期限为12个月。

第二条 付款条款  
乙方应在签署本协议后30天内支付许可费用50,000元。

第三条 保密条款
双方应对在履行本协议过程中获得的对方商业秘密承担保密义务。

第四条 责任限制
甲方对因使用软件导致的任何损失不承担赔偿责任。

第五条 争议解决
因本协议产生的争议应通过友好协商解决，协商不成的，提交北京仲裁委员会仲裁。
"""
    
    try:
        with open("examples/simple_contract.txt", "w", encoding="utf-8") as f:
            f.write(simple_contract.strip())
        print("✅ 创建 examples/simple_contract.txt")
    except Exception as e:
        print(f"❌ 创建文件失败: {e}")

def main():
    """主测试函数"""
    print("法律合规助手 API 测试客户端")
    print("=" * 40)
    
    # 健康检查
    if not test_health_check():
        print("\n💡 请确保服务器正在运行:")
        print("   cd /path/to/legal-compliance-agent")
        print("   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")
        sys.exit(1)
    
    # 创建示例文件
    create_sample_files()
    
    # 运行各项测试
    test_qa_api()
    test_compliance_gap() 
    test_contract_review()
    
    print("\n" + "=" * 40)
    print("✅ 所有测试完成")
    print("\n💡 查看完整API文档: http://127.0.0.1:8000/docs")

if __name__ == "__main__":
    main()
