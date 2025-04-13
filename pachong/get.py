import json
import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import logging
from datetime import datetime
import imghdr

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('xinhua_crawler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def find_json_files(directory, pattern="无人机袭击_新华网.json"):
    """查找目录中匹配模式的所有JSON文件"""
    json_files = []
    try:
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith('.json') and pattern in file:
                    json_files.append(os.path.join(root, file))
        logger.info(f"找到 {len(json_files)} 个匹配的JSON文件")
        return json_files
    except Exception as e:
        logger.error(f"查找JSON文件时出错: {str(e)}")
        return []

def read_json_file(file_path):
    """读取JSON文件并返回数据"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            return [data]
        else:
            raise ValueError("JSON数据格式不符合预期")
            
    except Exception as e:
        logger.error(f"读取JSON文件 {file_path} 失败: {str(e)}")
        return []

def is_valid_url(url):
    """检查URL是否有效"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def download_image(img_url, save_dir, referer=None):
    """下载图片并保存到指定目录"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        if referer:
            headers['Referer'] = referer

        response = requests.get(img_url, headers=headers, timeout=15, stream=True)
        response.raise_for_status()
        
        # 从URL获取图片扩展名
        img_name = os.path.basename(urlparse(img_url).path)
        if not img_name or '.' not in img_name:
            # 如果没有扩展名，使用内容判断
            ext = imghdr.what(None, response.content)
            img_name = f"{datetime.now().strftime('%Y%m%d%H%M%S')}.{ext}" if ext else "image.jpg"
        
        os.makedirs(save_dir, exist_ok=True)
        img_path = os.path.join(save_dir, img_name)
        
        with open(img_path, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        
        logger.info(f"图片下载成功: {img_path}")
        return img_path
    except Exception as e:
        logger.error(f"下载图片失败 {img_url}: {str(e)}")
        return None

def extract_chinese_text(text):
    """提取中文字符及常见标点"""
    # 匹配中文字符及常见标点：。，、；：？！""''（）《》【】…
    pattern = re.compile(r'[\u4e00-\u9fa5，。、；：？！""\'\'（）《》【】…]+')
    return ' '.join(pattern.findall(text))

def clean_content(content):
    """清理内容，移除【纠错】后的文本"""
    if not content:
        return ""
    
    # 查找【纠错】位置
    correct_pos = content.find("【纠错】")
    if correct_pos != -1:
        content = content[:correct_pos]
    
    # 移除多余空白
    content = re.sub(r'\s+', ' ', content).strip()
    return content

def get_web_content(url, retry=2):
    """获取网页内容，支持重试"""
    if not is_valid_url(url):
        logger.error(f"无效的URL: {url}")
        return None
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
    }
    
    for attempt in range(retry + 1):
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            
            if 'charset' in response.headers.get('content-type', '').lower():
                encoding_match = re.search(r'charset=(.*)', response.headers['content-type'].lower())
                if encoding_match:
                    response.encoding = encoding_match.group(1)
            else:
                response.encoding = 'utf-8'
            
            logger.info(f"成功获取网页内容: {url}")
            return response.text
        except requests.RequestException as e:
            if attempt == retry:
                logger.error(f"获取网页内容失败(尝试{attempt + 1}次): {url} - {str(e)}")
                return None
            logger.warning(f"获取网页内容失败，正在重试({attempt + 1}/{retry}): {url}")
            continue
    return None

def extract_content_and_images(html, base_url):
    """提取正文内容和图片"""
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # 提取正文
        content_selectors = [
            {'name': 'div', 'class': 'article'},
            {'name': 'div', 'class': 'content'},
            {'name': 'div', 'id': 'article'},
            {'name': 'div', 'class': 'article-content'},
        ]
        
        content_div = None
        for selector in content_selectors:
            if 'class' in selector:
                content_div = soup.find(selector['name'], class_=selector['class'])
            elif 'id' in selector:
                content_div = soup.find(selector['name'], id=selector['id'])
            if content_div:
                break
        
        if not content_div:
            divs = soup.find_all('div')
            for div in divs:
                if len(div.find_all('p')) > 5:
                    content_div = div
                    break
        
        # 提取文本内容
        text_content = ""
        if content_div:
            # 移除不需要的元素
            for elem in content_div(['script', 'style', 'iframe', 'nav', 'footer', 'aside', 
                                   'div.ad', 'div.comment', 'div.recommend', 'div.share']):
                elem.decompose()
            
            # 获取纯文本并清理
            raw_text = content_div.get_text(separator='\n', strip=True)
            text_content = clean_content(raw_text)
            chinese_text = extract_chinese_text(text_content)
        else:
            logger.warning("无法定位正文内容区域")
            chinese_text = ""
        
        # 提取图片
        images = []
        if content_div:
            img_tags = content_div.find_all('img', src=True)
            for img in img_tags:
                img_url = urljoin(base_url, img['src'])
                if is_valid_url(img_url):
                    images.append(img_url)
        
        return {
            'raw_text': text_content,
            'chinese_text': chinese_text,
            'images': images
        }
    except Exception as e:
        logger.error(f"提取内容时出错: {str(e)}")
        return {
            'raw_text': "",
            'chinese_text': "",
            'images': []
        }

def save_article_data(title, content_data, output_base_dir='output'):
    """保存文章数据和图片"""
    try:
        # 创建安全标题用于文件名
        safe_title = re.sub(r'[\\/*?:"<>|]', '', title)[:100].strip() or "无标题"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        article_dir = os.path.join(output_base_dir, f"{safe_title}_{timestamp}")
        
        os.makedirs(article_dir, exist_ok=True)
        
        # 保存文本内容
        text_path = os.path.join(article_dir, "content.txt")
        with open(text_path, 'w', encoding='utf-8') as f:
            f.write(f"标题: {title}\n\n")
            f.write("原始文本:\n")
            f.write(content_data['raw_text'])
            f.write("\n\n提取的中文文本:\n")
            f.write(content_data['chinese_text'])
        
        # 下载图片
        img_dir = os.path.join(article_dir, "images")
        img_paths = []
        for img_url in content_data['images']:
            img_path = download_image(img_url, img_dir, referer=content_data.get('url'))
            if img_path:
                img_paths.append(img_path)
        
        logger.info(f"文章数据保存完成: {article_dir}")
        return {
            'article_dir': article_dir,
            'text_path': text_path,
            'image_paths': img_paths
        }
    except Exception as e:
        logger.error(f"保存文章数据失败: {str(e)}")
        return None

def process_article(article):
    """处理单篇文章"""
    if not isinstance(article, dict):
        logger.warning("文章数据不是字典格式")
        return None
    
    link = article.get('link')
    title = article.get('title', '无标题')
    
    if not link:
        logger.warning(f"文章缺少链接: {title}")
        return None
        
    logger.info(f"\n处理文章: {title}")
    logger.info(f"链接: {link}")
    
    # 获取网页内容
    html = get_web_content(link)
    if not html:
        return None
        
    # 提取内容和图片
    content_data = extract_content_and_images(html, link)
    content_data['url'] = link
    
    # 保存数据
    result = save_article_data(title, content_data)
    return {
        'title': title,
        'url': link,
        'result': result
    }

def main():
    data_dir = '/code/wurenj/news'
    output_base_dir = 'output/xinhua_articles'
    
    try:
        json_files = find_json_files(data_dir)
        if not json_files:
            logger.error("没有找到匹配的JSON文件")
            return
            
        logger.info(f"开始处理 {len(json_files)} 个JSON文件...")
        
        total_articles = 0
        success_count = 0
        
        for json_file in json_files:
            logger.info(f"\n{'='*50}")
            logger.info(f"处理文件: {json_file}")
            
            articles = read_json_file(json_file)
            if not articles:
                logger.warning("文件中没有有效文章数据")
                continue
                
            for article in articles:
                total_articles += 1
                result = process_article(article)
                if result and result.get('result'):
                    success_count += 1
        
        logger.info(f"\n{'='*50}")
        logger.info(f"处理完成! 共处理 {total_articles} 篇文章，成功抓取 {success_count} 篇")
    except Exception as e:
        logger.error(f"主程序出错: {str(e)}")

if __name__ == "__main__":
    main()