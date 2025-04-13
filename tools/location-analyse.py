import pandas as pd
import requests
import json
from tqdm import tqdm
from datetime import datetime
import os
import re

# 配置信息
DEEPSEEK_API_KEY = "sk-4213e1ada059469a861a62160a6af621"
API_URL = "https://api.deepseek.com/v1/chat/completions"
OUTPUT_FILE = "/code/AT-agent/output/output.csv"
RAW_DATA_DIR = "/code/wurenj/output"
LOCATION_DB_PATH = "/code/AT-agent/data-tools/location.csv"

def load_location_db():
    """直接加载外部地理位置数据库"""
    try:
        loc_df = pd.read_csv(LOCATION_DB_PATH)
        # 创建标准化查询键
        loc_df['query_key'] = loc_df['country'].str.lower().str.strip() + '|' + loc_df['city'].str.lower().str.strip()
        return loc_df
    except Exception as e:
        print(f"加载地理位置数据库失败: {str(e)}")
        return None

def match_locations(news_df, loc_db):
    """直接匹配新闻中的地点与数据库"""
    merged_df = pd.merge(
        news_df,
        loc_db,
        how='left',
        left_on=['country1', 'city1'],
        right_on=['country', 'city']
    )
    
    # 重命名并保留需要的列
    merged_df = merged_df.rename(columns={
        'longitude': '经度',
        'latitude': '纬度'
    })
    
    return merged_df[['新闻标题', '内容', 'country1', 'city1', 'location1', 
                     '经度', '纬度', 'location_count']]

def process_raw_data():
    """从output目录读取最新的CSV文件"""
    try:
        csv_files = [f for f in os.listdir(RAW_DATA_DIR) if f.endswith('.csv')]
        if not csv_files:
            raise ValueError("output目录中没有CSV文件")
        
        latest_file = max(csv_files, key=lambda x: os.path.getmtime(os.path.join(RAW_DATA_DIR, x)))
        input_csv = os.path.join(RAW_DATA_DIR, latest_file)
        
        df = pd.read_csv(input_csv, encoding='utf-8')
        required_columns = ['新闻标题', '内容', 'country1', 'city1']
        missing_cols = [col for col in required_columns if col not in df.columns]
        
        if missing_cols:
            raise ValueError(f"CSV文件缺少必要列: {missing_cols}")
        
        print(f"数据加载成功，共 {len(df)} 条记录，文件: {latest_file}")
        return df
    except Exception as e:
        print(f"读取CSV文件失败: {str(e)}")
        return None

def save_results(df):
    """保存结果到CSV文件"""
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    df.to_csv(OUTPUT_FILE, index=False, encoding='utf_8_sig')
    print(f"结果已保存到 {OUTPUT_FILE}")

def main():
    # 加载地理位置数据库
    print("正在加载地理位置数据库...")
    loc_db = load_location_db()
    if loc_db is None:
        print("地理位置数据库加载失败，程序终止")
        return
    
    # 处理原始数据
    print("正在处理新闻数据...")
    news_df = process_raw_data()
    if news_df is None or news_df.empty:
        print("新闻数据处理失败，程序终止")
        return
    
    # 直接匹配地理位置
    print("正在匹配地理位置...")
    result_df = match_locations(news_df, loc_db)
    
    # 保存结果
    save_results(result_df)
    print("地理匹配完成")

if __name__ == "__main__":
    main()