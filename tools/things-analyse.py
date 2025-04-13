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

def analyze_military_action(text):
    """分析军事行动相关信息"""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = """请从以下新闻中提取军事行动相关信息，严格按JSON格式返回：
{
  "parties": {
    "attacker": "攻击方（如无则写'不详'）",
    "defender": "防御方（如无则写'不详'）"
  },
  "action_type": "军事行动/恐怖袭击/军事演习/科技创新/政策调整（如无则写'不详'）",
  "purpose": "行动目的（如无则写'不详'）",
  "outcome": "行动结果（如无则写'不详'）",
  "casualties": {
    "deaths": "死亡人数（数字或'不详'）",
    "injuries": "受伤人数（数字或'不详'）",
    "has_women_children": "是否有妇女儿童（是/否/不详）",
    "women_children_deaths": "妇女儿童死亡人数（数字或'不详'）",
    "women_children_injuries": "妇女儿童受伤人数（数字或'不详'）"
  },
  "has_damage": "是否有建筑破坏（是/否/不详）",
  "reason": "分析依据"
}

注意：
1. 必须明确区分攻击方和防御方
2. 数字信息必须尽可能提取具体数值
3. 不确定的信息请标记为'不详'"""
    
    prompt += f"\n新闻内容：{text[:2000]}"  # 限制长度避免超长
    
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "response_format": { "type": "json_object" },
        "max_tokens": 1500
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"军事行动分析API请求失败: {str(e)}")
        return None

def process_content(df):
    """处理内容并生成结果DataFrame"""
    results = []
    for index, row in tqdm(df.iterrows(), total=len(df)):
        content = str(row['内容'])
        
        # 分析军事行动信息
        action_json = analyze_military_action(content)
        try:
            action_data = json.loads(action_json) if action_json else {}
        except Exception as e:
            print(f"JSON解析失败: {str(e)}，原始内容: {action_json}")
            action_data = {}
        
        # 设置默认值
        parties = action_data.get("parties", {})
        casualties = action_data.get("casualties", {})
        
        # 处理数字字段
        def parse_number(value):
            if isinstance(value, int):
                return value
            if str(value).isdigit():
                return int(value)
            return -1  # 用-1表示"不详"
        
        # 构建结果记录
        record = {
            '新闻标题': row['新闻标题'],
            '攻击方': parties.get("attacker", "不详"),
            '防御方': parties.get("defender", "不详"),
            '事件性质': action_data.get("action_type", "不详"),
            '行动目的': action_data.get("purpose", "不详"),
            '行动结果': action_data.get("outcome", "不详"),
            '死亡人数': parse_number(casualties.get("deaths", "不详")),
            '受伤人数': parse_number(casualties.get("injuries", "不详")),
            '是否有妇女儿童': casualties.get("has_women_children", "不详"),
            '妇女儿童死亡人数': parse_number(casualties.get("women_children_deaths", "不详")),
            '妇女儿童受伤人数': parse_number(casualties.get("women_children_injuries", "不详")),
            '是否有建筑破坏': action_data.get("has_damage", "不详"),
            '分析依据': action_data.get("reason", "")
        }
        results.append(record)
    
    return pd.DataFrame(results)

def save_results(df):
    """保存结果到CSV文件"""
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    # 如果文件已存在，读取并追加新数据
    if os.path.exists(OUTPUT_FILE):
        existing_df = pd.read_csv(OUTPUT_FILE)
        combined_df = pd.concat([existing_df, df], ignore_index=True)
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