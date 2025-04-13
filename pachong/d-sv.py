import os
import csv
import re

# 定义输入和输出路径
input_dir = '/code/output'
output_csv = '/code/wurenj/data/output.csv'

# 准备正则表达式匹配文件名模式
pattern = re.compile(r'^(.*?)_(\d{8})_(\d+)$')

# 准备写入CSV文件
with open(output_csv, 'w', newline='', encoding='utf-8') as csvfile:
    writer = csv.writer(csvfile)
    # 写入表头（添加"索引"列）
    writer.writerow(['索引', '新闻标题', '日期', '编号', '内容'])
    
    # 初始化索引
    index = 1
    
    # 遍历输入目录下的所有子目录
    for subdir in os.listdir(input_dir):
        subdir_path = os.path.join(input_dir, subdir)
        if os.path.isdir(subdir_path):
            # 尝试匹配文件名模式
            match = pattern.match(subdir)
            if match:
                title, date, number = match.groups()
            else:
                title, date, number = subdir, '', ''
            
            # 查找并读取content.txt文件
            content_path = os.path.join(subdir_path, 'content.txt')
            content = ''
            if os.path.exists(content_path):
                with open(content_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            
            # 写入CSV行（添加index作为第一列）
            writer.writerow([index, title, date, number, content])
            index += 1  # 索引自增

print(f"CSV文件已生成: {output_csv}")