#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
import json
import logging
from typing import Dict, List

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 脚本路径配置
SCRIPT_PATHS = {
    "地理定位": "/code/AT-agent/tools/location-analyse.py",
    "情况分析": "/code/AT-agent/tools/things-analyse.py",
    "背景环境": "/code/AT-agent/tools/background-analyse.py",
    "可视化": "/code/wurenj/tools/visualization.py"
}

class TaskScheduler:
    def __init__(self, requirements: Dict[str, bool]):
        self.requirements = requirements
        self.execution_order = self._determine_execution_order()
        
    def _determine_execution_order(self) -> List[str]:
        """确定脚本执行顺序"""
        order = []
        
        # 优先处理非可视化需求
        non_viz_reqs = [req for req in self.requirements 
                       if req != "可视化" and self.requirements[req]]
        
        # 如果有非可视化需求
        if non_viz_reqs:
            order.extend(non_viz_reqs)
            if self.requirements.get("可视化", False):
                order.append("可视化")
        # 如果只有可视化需求
        elif self.requirements.get("可视化", False):
            # 默认执行全部三个分析再可视化
            order.extend(["地理定位", "情况分析", "背景环境", "可视化"])
        
        return order
    
    def _validate_scripts(self) -> bool:
        """验证所有需要的脚本是否存在"""
        missing_scripts = []
        for req in self.execution_order:
            if not os.path.exists(SCRIPT_PATHS[req]):
                missing_scripts.append(SCRIPT_PATHS[req])
        
        if missing_scripts:
            logger.error(f"以下脚本不存在: {missing_scripts}")
            return False
        return True
    
    def execute_scripts(self) -> bool:
        """按顺序执行脚本"""
        if not self._validate_scripts():
            return False
        
        logger.info(f"开始执行任务，顺序为: {self.execution_order}")
        
        for script_name in self.execution_order:
            script_path = SCRIPT_PATHS[script_name]
            logger.info(f"正在执行: {script_name} ({script_path})")
            
            try:
                result = subprocess.run(
                    ['python3', script_path],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                logger.info(f"{script_name} 执行成功")
                logger.debug(f"输出:\n{result.stdout}")
            except subprocess.CalledProcessError as e:
                logger.error(f"{script_name} 执行失败: {e.stderr}")
                return False
            except Exception as e:
                logger.error(f"执行 {script_name} 时发生意外错误: {str(e)}")
                return False
        
        logger.info("所有任务执行完成")
        return True

def load_requirements() -> Dict[str, bool]:
    """加载需求配置"""
    try:
        if len(sys.argv) > 1:
            # 从命令行参数读取
            req_json = sys.argv[1]
            return json.loads(req_json)
        else:
            # 默认配置（仅用于测试）
            return {
                "地理定位": True,
                "情况分析": True,
                "背景环境": False,
                "可视化": True
            }
    except Exception as e:
        logger.error(f"加载需求配置失败: {str(e)}")
        return {}

def main():
    requirements = load_requirements()
    if not requirements:
        logger.error("无法获取有效的需求配置")
        return
    
    logger.info(f"接收到的需求配置: {json.dumps(requirements, indent=2, ensure_ascii=False)}")
    
    scheduler = TaskScheduler(requirements)
    if not scheduler.execution_order:
        logger.info("没有需要执行的任务")
        return
    
    if not scheduler.execute_scripts():
        logger.error("任务执行过程中出现错误")
        sys.exit(1)

if __name__ == "__main__":
    main()