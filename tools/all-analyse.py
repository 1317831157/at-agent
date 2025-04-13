import pandas as pd
import requests
import json
from tqdm import tqdm
import os
import re
from datetime import datetime

DEEPSEEK_API_KEY = "sk-4213e1ada059469a861a62160a6af621"
API_URL = "https://api.deepseek.com/v1/chat/completions"
REPORT_DIR = "/code/AT-agent/analysis_reports"

class EventAnalyzer:
    def __init__(self):
        os.makedirs(REPORT_DIR, exist_ok=True)
        self.today = datetime.now().strftime("%Y%m%d")
        
    def load_data(self, file_path):
        """加载数据文件并预处理"""
        try:
            df = pd.read_csv(file_path, encoding='utf-8')
            df['内容'] = df['内容'].apply(lambda x: re.sub(r'\s+', ' ', str(x)).strip())
            print(f"成功加载数据，共 {len(df)} 条记录")
            return df.dropna(subset=['内容'])
        except Exception as e:
            print(f"数据加载失败: {str(e)}")
            return None

    def generate_analysis_prompt(self, event_data):
        """生成深度分析提示词"""
        return f"""基于以下事件信息，撰写一份专业分析报告：
        
事件标题：{event_data.get('新闻标题','')}
时间：{event_data.get('发生时间','不详')}
地点：{event_data.get('国家','')}/{event_data.get('城市','')}
事件类型：{event_data.get('事件性质','')}

内容摘要：
{event_data.get('内容','')[:1500]}

报告要求：
1. 分析事件背景与直接诱因
2. 评估各方行动策略及效果
3. 统计伤亡数据的潜在含义
4. 预测可能产生的后续影响
5. 适当延伸比较类似历史事件

报告格式要求：
- 采用学术论文的严谨表述
- 段落间自然过渡（避免使用"首先/其次"）
- 包含数据支撑的关键结论
- 允许5%的相关领域延伸"""

    def analyze_event(self, text_data):
        """调用API进行深度分析"""
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{
                "role": "user",
                "content": self.generate_analysis_prompt(text_data)
            }],
            "temperature": 0.7,
            "max_tokens": 2000
        }
        
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            return response.json()['choices'][0]['message']['content']
        except Exception as e:
            print(f"分析请求失败: {str(e)}")
            return None

    def generate_report(self, df):
        """生成完整分析报告"""
        report_content = []
        statistics = {
            '事件类型分布': {},
            '地区分布': {},
            '伤亡统计': {'总死亡':0,'总受伤':0}
        }
        
        for _, row in tqdm(df.iterrows(), total=len(df)):
            analysis = self.analyze_event(row)
            if not analysis:
                continue
                
            # 记录关键数据
            event_type = row.get('事件性质','其他')
            statistics['事件类型分布'][event_type] = statistics['事件类型'].get(event_type,0)+1
            
            location = f"{row.get('国家','未知')}-{row.get('城市','')}"
            statistics['地区分布'][location] = statistics['地区分布'].get(location,0)+1
            
            if isinstance(row.get('死亡人数',0),int):
                statistics['伤亡统计']['总死亡'] += row['死亡人数']
            if isinstance(row.get('受伤人数',0),int):
                statistics['伤亡统计']['总受伤'] += row['受伤人数']
            
            # 构建报告段落
            report_content.append(
                f"## 事件分析报告：{row['新闻标题']}\n"
                f"**时间地点**：{row.get('发生时间','')} | {location}\n"
                f"**事件类型**：{event_type}\n\n"
                f"{analysis}\n\n"
                f"{'='*50}\n"
            )
        
        # 添加统计分析
        stats_section = "\n## 全局统计分析\n"
        stats_section += f"事件总数：{len(df)}\n"
        stats_section += f"涉及地区：{len(statistics['地区分布'])}个\n\n"
        
        stats_section += "### 事件类型分布\n"
        stats_section += "\n".join([f"- {k}: {v}次" for k,v in statistics['事件类型分布'].items()])
        
        stats_section += "\n\n### 伤亡情况\n"
        stats_section += f"- 总死亡人数：{statistics['伤亡统计']['总死亡']}\n"
        stats_section += f"- 总受伤人数：{statistics['伤亡统计']['总受伤']}\n"
        
        report_content.insert(0, stats_section)
        return "\n".join(report_content)

    def save_report(self, content):
        """保存分析报告"""
        report_path = os.path.join(REPORT_DIR, f"event_analysis_{self.today}.md")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"分析报告已保存至：{report_path}")

def main():
    analyzer = EventAnalyzer()
    
    # 示例数据路径 - 实际使用时替换为真实路径
    data_file = "/code/AT-agent/pachong/events_data.csv"
    event_data = analyzer.load_data(data_file)
    
    if event_data is not None:
        report = analyzer.generate_report(event_data)
        analyzer.save_report(report)

if __name__ == "__main__":
    main()