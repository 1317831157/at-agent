from flask import Flask, send_from_directory
import os
import shutil
import subprocess

# 创建一个Flask应用的引用，但在导入时不会创建新实例
# 当被导入到app.py时，将使用app.py中的app实例
app = None

def build_frontend():
    """处理前端静态文件"""
    try:
        # 使用全局app引用
        global app
        
        # 检查frontend目录是否存在
        if not os.path.exists('frontend'):
            print("前端项目目录不存在，跳过前端处理")
            return False
            
        # 检查dist目录
        dist_path = os.path.join('frontend', 'dist')
        if not os.path.exists(dist_path) or not os.listdir(dist_path):
            print("dist目录不存在或为空，前端文件可能未构建")
            return False
            
        print("处理前端静态文件...")
        # 设置静态文件目录
        static_dir = os.path.join(app.root_path, 'static')
        
        # 删除现有的static目录（如果存在）
        if os.path.exists(static_dir):
            shutil.rmtree(static_dir)
            
        # 创建新的static目录
        os.makedirs(static_dir)
        
        # 复制构建文件到static目录
        shutil.copytree(dist_path, static_dir, dirs_exist_ok=True)
        
        print("前端文件复制成功")
        return True
    except Exception as e:
        print(f"前端文件处理失败: {str(e)}")
        return False

# 主页路由，使用/作为静态文件根路径
def serve_frontend(path=None):
    """服务前端页面，处理所有前端路由"""
    return send_from_directory('static', 'index.html')

# 初始化函数，在app.py导入时调用
def init_app(flask_app):
    """初始化模块，接收Flask应用实例"""
    global app
    app = flask_app
    return app
