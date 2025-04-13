import pandas as pd
import requests
import json
from tqdm import tqdm
from datetime import datetime
import os

# 配置信息
DEEPSEEK_API_KEY = "sk-4213e1ada059469a861a62160a6af621"  # 请妥善保管您的API密钥
API_URL = "https://api.deepseek.com/v1/chat/completions"
OUTPUT_FILE = "/code/AT-agent/output/output .csv"
RAW_DATA_DIR = "/code/wurenj/output"

def process_raw_data():
    """从output目录读取最新的CSV文件"""
    try:
        csv_files = [f for f in os.listdir(RAW_DATA_DIR) if f.endswith('.csv')]
        if not csv_files:
            raise ValueError("output目录中没有CSV文件")
        
        # 获取最新的CSV文件
        latest_file = max(csv_files, key=lambda x: os.path.getmtime(os.path.join(RAW_DATA_DIR, x)))
        input_csv = os.path.join(RAW_DATA_DIR, latest_file)
        
        df = pd.read_csv(input_csv, encoding='utf-8')
        required_columns = ['新闻标题', '内容']
        missing_cols = [col for col in required_columns if col not in df.columns]
        
        if missing_cols:
            raise ValueError(f"CSV文件缺少必要列: {missing_cols}")
        
        print(f"数据加载成功，共 {len(df)} 条记录，文件: {latest_file}")
        return df
    except Exception as e:
        print(f"读取CSV文件失败: {str(e)}")
        return None

def analyze_social_context(text):
    """分析社会环境相关信息"""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = """请从以下新闻中提取社会环境相关信息，严格按JSON格式返回：
{
  "natural_environment": {
    "terrain": "地形特征（如高原、平原、山地等）",
    "climate": "气候类型",
    "resources": "主要自然资源",
    "ecological_issues": "生态环境问题"
  },
  "religion": {
    "major_religions": "主要宗教信仰",
    "religious_conflicts": "是否存在宗教冲突（是/否/不详）",
    "religious_practices": "突出的宗教习俗"
  },
  "ethnic_groups": {
    "major_ethnicity": "主要民族",
    "ethnic_composition": "民族构成特点",
    "ethnic_conflicts": "是否存在民族冲突（是/否/不详）"
  },
  "social_background": {
    "economic_condition": "经济状况",
    "political_situation": "政治局势",
    "education_level": "教育水平",
    "social_stability": "社会稳定程度（稳定/不稳定/不详）"
  },
  "reason": "分析依据"
}

注意：
1. 所有信息必须基于新闻内容明确提及，不要推测
2. 不确定的信息请标记为'不详'
3. 尽量使用简洁明确的描述"""
    
    prompt += f"\n新闻内容：{text[:2000]}"  # 限制长度避免超长
    
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "response_format": { "type": "json_object" },
        "max_tokens": 2000
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"社会环境分析API请求失败: {str(e)}")
        return None

def process_content(df):
    """处理内容并生成结果DataFrame"""
    results = []
    for index, row in tqdm(df.iterrows(), total=len(df)):
        content = str(row['内容'])
        
        # 分析社会环境信息
        context_json = analyze_social_context(content)
        try:
            context_data = json.loads(context_json) if context_json else {}
        except Exception as e:
            print(f"JSON解析失败: {str(e)}，原始内容: {context_json}")
            context_data = {}
        
        # 设置默认值
        natural_env = context_data.get("natural_environment", {})
        religion = context_data.get("religion", {})
        ethnic = context_data.get("ethnic_groups", {})
        social_bg = context_data.get("social_background", {})
        
        # 构建结果记录
        record = {
            '新闻标题': row['新闻标题'],
            # 自然环境
            '地形特征': natural_env.get("terrain", "不详"),
            '气候类型': natural_env.get("climate", "不详"),
            '主要自然资源': natural_env.get("resources", "不详"),
            '生态环境问题': natural_env.get("ecological_issues", "不详"),
            # 宗教信仰
            '主要宗教信仰': religion.get("major_religions", "不详"),
            '宗教冲突': religion.get("religious_conflicts", "不详"),
            '宗教习俗': religion.get("religious_practices", "不详"),
            # 民族
            '主要民族': ethnic.get("major_ethnicity", "不详"),
            '民族构成': ethnic.get("ethnic_composition", "不详"),
            '民族冲突': ethnic.get("ethnic_conflicts", "不详"),
            # 社会背景
            '经济状况': social_bg.get("economic_condition", "不详"),
            '政治局势': social_bg.get("political_situation", "不详"),
            '教育水平': social_bg.get("education_level", "不详"),
            '社会稳定程度': social_bg.get("social_stability", "不详"),
            '分析依据': context_data.get("reason", "")
        }
        results.append(record)
    
    return pd.DataFrame(results)

def save_results(df):
    """保存结果到CSV文件"""
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    # 如果文件已存在，读取并追加新数据
    if os.path.exists(OUTPUT_FILE):
        existing_df = pd.read_csv(OUTPUT_FILE)
        # 只保留不重复的新闻标题记录
        combined_df = pd.concat([existing_df, df]).drop_duplicates(subset=['新闻标题'], keep='last')
    else:
        combined_df = df
    
    combined_df.to_csv(OUTPUT_FILE, index=False, encoding='utf_8_sig')
    print(f"结果已保存到 {OUTPUT_FILE}")

def main():
    # 处理原始数据
    print("正在处理原始数据...")
    df = process_raw_data()
    if df is None or df.empty:
        print("原始数据处理失败，程序终止")
        return
    
    # 分析内容
    print("正在分析内容...")
    result_df = process_content(df)
    
    # 保存结果
    save_results(result_df)
    print("分析完成")

if __name__ == "__main__":
    main()