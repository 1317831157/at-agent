from flask import Flask, request, jsonify,send_from_directory
import subprocess
import json
import os
import pandas as pd
from flask_caching import Cache
import requests

app = Flask(__name__)

# 配置缓存
cache = Cache(config={'CACHE_TYPE': 'SimpleCache'})
cache.init_app(app)

DEEPSEEK_API_KEY = "sk-4213e1ada059469a861a62160a6af621"
API_URL = "https://api.deepseek.com/v1/chat/completions"

# 存储用户请求的临时目录
REQUEST_DIR = "/code/AT-agent/requests"
os.makedirs(REQUEST_DIR, exist_ok=True)

# 导入build模块
try:
    import build
    build.init_app(app)  # 传递app实例到build模块
    
    # 添加build中的路由
    app.add_url_rule('/', 'serve_frontend', build.serve_frontend)
    # 添加通用路由处理器，捕获所有前端路由
    app.add_url_rule('/<path:path>', 'serve_frontend_routes', build.serve_frontend)
except ImportError:
    print("警告：无法导入build模块，前端页面可能无法正常显示")


# 添加静态资源路由
@app.route('/assets/<path:filename>')
def serve_assets(filename):
    """处理assets目录下的静态资源"""
    return send_from_directory('static/assets', filename)

# 添加favicon路由
@app.route('/favicon.ico')
def favicon():
    """提供favicon图标"""
    return send_from_directory('static', 'favicon.ico')



@app.route('/analyze', methods=['POST'])
def analyze_text():
    """接收前端文本并进行分析"""
    data = request.json
    user_text = data.get('text', '')
    
    if not user_text:
        return jsonify({"error": "No text provided"}), 400
    
    try:
        # 第一步：分析关键词和需求
        analysis_result = analyze_with_deepseek(user_text)
        # print('analysis_result',analysis_result)
        # 第二步：处理关键词
        keywords = analysis_result.get('keywords', ['无人机袭击'])
        # with open('/code/wurenj/pachong/final.py', 'w') as f:
        #     f.write(f"keywords = {json.dumps(keywords, ensure_ascii=False)}")
        
        # 第三步：处理需求并调度
        requirements = analysis_result.get('requirements', {})
        dispatch_requirements(requirements)
        
        # 第四步：运行爬虫和分析脚本
        # run_analysis_scripts()
        
        return jsonify({
            "code": 200,
            'message':'成功',
            'data':{
             "keywords": keywords,
             "requirements": requirements,
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/output', methods=['GET'])
@cache.cached(timeout=60, query_string=True)
def get_output_data():
    """提供CSV文件数据访问接口"""
    try:
        # 检查文件是否存在
        # csv_path = '/code/AT-agent/output/output.csv'
        csv_path = './output/output.csv'
        if not os.path.exists(csv_path):
            return jsonify({"code": 404,
            'message':'输出文件不存在',}), 404
        
        # 获取查询参数
        filters = {
            'country': request.args.get('country'),
            'city': request.args.get('city'),
            'date_from': request.args.get('date_from'),
            'date_to': request.args.get('date_to')
        }
        
        # 读取CSV文件
        df = pd.read_csv(csv_path)
        
        # 应用过滤器
        if filters['country']:
            df = df[df['国家'] == filters['country']]
        if filters['city']:
            df = df[df['城市'] == filters['city']]
        if filters['date_from'] and filters['date_to']:
            df = df[(df['日期'] >= filters['date_from']) & 
                   (df['日期'] <= filters['date_to'])]
        
        # 分页处理
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 100))
        total = len(df)
        start = (page - 1) * per_page
        end = start + per_page
        paginated_data = df.iloc[start:end].to_dict(orient='records')
        
        return jsonify({
            "code": 200,
            'message':'成功',
            "data": paginated_data,
            "filters": {k: v for k, v in filters.items() if v},
            "page": page,
            "per_page": per_page,
            "total": total
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def analyze_with_deepseek(text):
    """调用DeepSeek API分析文本"""
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    prompt = f"""请分析以下文本，提取最多2个关键词（军事相关），并识别用户需求：
{text}

请按以下JSON格式返回：
{{
  "keywords": ["关键词1", "关键词2"],
  "requirements": {{
    "地理定位": true/false,
    "情况分析": true/false,
    "背景环境": true/false,
    "可视化": true/false
  }}
}}"""
    
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "response_format": {"type": "json_object"},
        "max_tokens": 500
    }
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        response_json = response.json()
        
        # 确保获取到的是字典而不是字符串
        content = response_json['choices'][0]['message']['content']
        
        # 如果content是字符串，尝试解析为JSON
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except json.JSONDecodeError:
                raise ValueError("API返回的不是有效的JSON格式")
        
        # 确保返回的是字典
        if not isinstance(content, dict):
            raise ValueError("API返回的数据格式不正确")
            
        return content
    except Exception as e:
        print(f"DeepSeek API请求失败: {str(e)}")
        return {
            "keywords": ["无人机袭击"],
            "requirements": {
                "地理定位": False,
                "情况分析": False,
                "背景环境": False,
                "可视化": False
            }
        }

def dispatch_requirements(requirements):
    """将需求写入调度器"""
    dispatch_content = f"""# 自动生成的调度配置
requirements = {json.dumps(requirements, indent=2, ensure_ascii=False)}

def execute():
    if requirements.get('地理定位'):
        from modules import geolocation
        geolocation.run()
    
    if requirements.get('情况分析'):
        from modules import situation_analysis
        situation_analysis.run()
        
    if requirements.get('背景环境'):
        from modules import background_analysis
        background_analysis.run()
        
    if requirements.get('可视化'):
        from modules import visualization
        visualization.run()
"""
    
    with open('/code/AT-agent/diaoduqi.py', 'w') as f:
        f.write(dispatch_content)

def run_analysis_scripts():
    """运行分析脚本"""
    try:
        # 运行爬虫
        subprocess.run(['python', '/code/AT-agent/pachong/final.py'], check=True)
        # 运行调度器
        subprocess.run(['python', '/code/AT-agent/diaoduqi.py'], check=True)
    except subprocess.CalledProcessError as e:
        raise Exception(f"脚本执行失败: {str(e)}")

if __name__ == '__main__':
     # 处理前端静态文件
    try:
        build.build_frontend()
    except (NameError, AttributeError):
        print("无法处理前端静态文件，请确保build模块已正确导入")
        
    print("服务已启动，访问 http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000)