import json
import os
import re
import subprocess
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
import logging
from datetime import datetime
import imghdr
import time
import random
from fake_useragent import UserAgent
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys

# ==================== 通用配置 ====================
# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('news_processor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== 工具函数 ====================
def is_valid_url(url):
    """检查URL是否有效"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def extract_chinese_text(text):
    """提取中文字符及常见标点"""
    pattern = re.compile(r'[\u4e00-\u9fa5，。、；：？！""\'\'（）《》【】…]+')
    return ' '.join(pattern.findall(text))

def clean_content(content):
    """清理内容，移除【纠错】后的文本"""
    if not content:
        return ""
    
    correct_pos = content.find("【纠错】")
    if correct_pos != -1:
        content = content[:correct_pos]
    
    return re.sub(r'\s+', ' ', content).strip()

# ==================== 内容获取模块 ====================
class ContentFetcher:
    @staticmethod
    def get_web_content(url, retry=2):
        """获取网页内容，支持重试"""
        if not is_valid_url(url):
            logger.error(f"无效的URL: {url}")
            return None
        
        headers = {
            'User-Agent': UserAgent().random,
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

    @staticmethod
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
                for elem in content_div(['script', 'style', 'iframe', 'nav', 'footer', 'aside', 
                                       'div.ad', 'div.comment', 'div.recommend', 'div.share']):
                    elem.decompose()
                
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

# ==================== 数据处理模块 ====================
class DataProcessor:
    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def download_image(img_url, save_dir, referer=None):
        """下载图片并保存到指定目录"""
        try:
            headers = {
                'User-Agent': UserAgent().random
            }
            if referer:
                headers['Referer'] = referer

            response = requests.get(img_url, headers=headers, timeout=15, stream=True)
            response.raise_for_status()
            
            img_name = os.path.basename(urlparse(img_url).path)
            if not img_name or '.' not in img_name:
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

    @staticmethod
    def save_article_data(title, content_data, output_base_dir='output'):
        """保存文章数据和图片"""
        try:
            safe_title = re.sub(r'[\\/*?:"<>|]', '', title)[:100].strip() or "无标题"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            article_dir = os.path.join(output_base_dir, f"{safe_title}_{timestamp}")
            
            os.makedirs(article_dir, exist_ok=True)
            
            text_path = os.path.join(article_dir, "content.txt")
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(f"标题: {title}\n\n")
                f.write("原始文本:\n")
                f.write(content_data['raw_text'])
                f.write("\n\n提取的中文文本:\n")
                f.write(content_data['chinese_text'])
            
            img_dir = os.path.join(article_dir, "images")
            img_paths = []
            for img_url in content_data['images']:
                img_path = DataProcessor.download_image(img_url, img_dir, referer=content_data.get('url'))
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

    @staticmethod
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
        
        html = ContentFetcher.get_web_content(link)
        if not html:
            return None
            
        content_data = ContentFetcher.extract_content_and_images(html, link)
        content_data['url'] = link
        
        result = DataProcessor.save_article_data(title, content_data)
        return {
            'title': title,
            'url': link,
            'result': result
        }

# ==================== 新闻爬虫模块 ====================
class NewsCrawler:
    def __init__(self, keywords=None, max_results=100, max_workers=5):
        # 从命令行参数获取关键词，如果没有则使用默认值
        if keywords is None:
            if len(sys.argv) > 1:
                self.keywords = sys.argv[1].split(',')
            else:
                self.keywords = ["无人机袭击"]  # 默认关键词
        else:
            self.keywords = keywords if isinstance(keywords, list) else [keywords]
            
        self.max_results = max_results
        self.max_workers = max_workers
        self.ua = UserAgent()
        self.session = requests.Session()
        
        self.default_headers = {
            'User-Agent': self.ua.random,
            'Referer': 'http://so.news.cn/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
        }
        
        self.site_specific_headers = {
            '新华网': {
                'Referer': 'http://so.news.cn/',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
            }
        }
        
        self.session.headers.update(self.default_headers)
        self.results = []
        self.visited_urls = set()
        self.news_sources = {
            '新华网': self.search_xinhua
        }
        self.output_dir = '/code/AT-agent/news'
        os.makedirs(self.output_dir, exist_ok=True)

        
    
    def random_delay(self):
        time.sleep(random.uniform(1, 3))
    
    def make_request(self, url, method='GET', source_name=None, **kwargs):
        max_retries = 3
        retry_delay = 2
        
        headers = self.default_headers.copy()
        if source_name and source_name in self.site_specific_headers:
            headers.update(self.site_specific_headers[source_name])
        
        if 'headers' in kwargs:
            headers.update(kwargs['headers'])
            del kwargs['headers']
        
        for attempt in range(max_retries):
            try:
                headers['User-Agent'] = self.ua.random
                
                if source_name and source_name in self.site_specific_headers:
                    headers['Referer'] = self.site_specific_headers[source_name].get('Referer', headers['Referer'])
                
                response = self.session.request(
                    method, 
                    url, 
                    timeout=10,
                    headers=headers,
                    **kwargs
                )
                response.raise_for_status()
                
                if "验证" in response.text or "verification" in response.text.lower():
                    raise requests.exceptions.RequestException("Encountered verification page")
                
                return response
            except requests.exceptions.RequestException as e:
                logger.warning(f"Attempt {attempt + 1} failed for {url}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                logger.error(f"Failed to fetch {url} after {max_retries} attempts")
                return None
    
    def search_xinhua(self, keyword):
        results = []
        current_page = 1
        processed_count = 0
        
        while len(results) < self.max_results:
            logger.info(f"正在爬取新华网第 {current_page} 页，关键词: {keyword}")
            
            params = {
                "keyword": keyword,
                "curPage": current_page,
                "sortField": "0",
                "searchFields": "1"
            }
            
            response = self.make_request(
                "https://so.news.cn/getNews",
                params=params,
                source_name='新华网'
            )
            
            if not response:
                break
            
            try:
                news_data = response.json()
                
                if not isinstance(news_data, dict):
                    logger.warning(f"第 {current_page} 页返回数据不是字典格式")
                    current_page += 1
                    continue
                    
                if 'content' in news_data and 'results' in news_data['content']:
                    news_items = news_data['content']['results']
                elif 'content' in news_data and isinstance(news_data['content'], list):
                    news_items = news_data['content']
                else:
                    logger.warning(f"第 {current_page} 页数据格式不符合预期: {news_data.keys()}")
                    current_page += 1
                    continue
                
                page_processed = 0
                
                for item in news_items:
                    if len(results) >= self.max_results:
                        break
                    
                    if not isinstance(item, dict) or not item.get('url'):
                        continue
                    
                    news_url = urljoin("https://so.news.cn/", item['url'])
                    
                    if news_url in self.visited_urls:
                        continue
                    
                    try:
                        news_detail = {
                            'title': item.get('title', '无标题'),
                            'link': news_url,
                            'source': '新华网',
                            'published': item.get('pubtime', '未知时间'),
                            'keyword': keyword,
                            'source_site': '新华网'
                        }
                        
                        detail_response = self.make_request(news_url, source_name='新华网')
                        if detail_response:
                            soup = BeautifulSoup(detail_response.text, 'html.parser')
                            
                            detail_title = soup.find('h1')
                            if detail_title:
                                news_detail['title'] = detail_title.get_text(strip=True)
                            
                            source_info = soup.find('span', class_='source')
                            if source_info:
                                source_text = source_info.get_text(strip=True)
                                parts = [p.strip() for p in source_text.split('|')]
                                if len(parts) > 1:
                                    news_detail['published'] = parts[1].strip()
                            
                            content_div = soup.find('div', class_='content')
                            if content_div:
                                for elem in content_div(['script', 'style', 'iframe', 'img', 'video']):
                                    elem.decompose()
                                news_detail['content'] = ' '.join(p.get_text(strip=True) for p in content_div.find_all('p'))
                        
                        results.append(news_detail)
                        self.visited_urls.add(news_url)
                        page_processed += 1
                        
                        if page_processed >= 10:
                            break
                        
                        time.sleep(1)
                    
                    except Exception as e:
                        logger.error(f"处理新闻条目失败: {str(e)}")
                        continue
                
                current_page += 1
                
                if page_processed == 0:
                    break
                
                time.sleep(2)
            
            except ValueError as e:
                logger.error(f"解析新华网JSON失败: {str(e)}")
                break
            except Exception as e:
                logger.error(f"处理第 {current_page} 页时发生未知错误: {str(e)}")
                break
        
        return results
    
    def get_news_from_source(self, source_name, keyword):
        try:
            search_func = self.news_sources.get(source_name)
            if search_func:
                results = search_func(keyword)
                filename = f"{keyword}_{source_name}.json"
                filepath = os.path.join(self.output_dir, filename)
                self._save_results(results, filepath)
                return results
            return []
        except Exception as e:
            logger.error(f"Error getting news from {source_name} for {keyword}: {str(e)}")
            return []
    
    def _save_results(self, results, filepath):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"Results saved to {filepath}")
        except Exception as e:
            logger.error(f"Error saving to JSON: {str(e)}")
    
    def get_all_news(self):
        start_time = datetime.now()
        logger.info(f"Starting news crawl for keywords: {', '.join(self.keywords)}")
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            
            for keyword in self.keywords:
                for source_name in self.news_sources:
                    futures.append(executor.submit(
                        self.get_news_from_source, 
                        source_name, 
                        keyword
                    ))
            
            for future in as_completed(futures):
                try:
                    results = future.result()
                    self.results.extend(results)
                except Exception as e:
                    logger.error(f"Error in future: {str(e)}")
        
        unique_results = []
        seen_links = set()
        
        for item in self.results:
            clean_link = re.sub(r'[?#].*$', '', item['link'])
            if clean_link not in seen_links:
                seen_links.add(clean_link)
                unique_results.append(item)
        
        self.results = unique_results
        elapsed = datetime.now() - start_time
        logger.info(f"Finished crawl. Found {len(self.results)} articles in {elapsed.total_seconds():.2f} seconds")
        return self.results
    
    def print_summary(self):
        print("\n=== 新闻爬取摘要 ===")
        print(f"关键词: {', '.join(self.keywords)}")
        print(f"共找到文章: {len(self.results)}篇")
        
        source_counts = {}
        keyword_counts = {}
        
        for item in self.results:
            source_counts[item['source_site']] = source_counts.get(item['source_site'], 0) + 1
            keyword_counts[item['keyword']] = keyword_counts.get(item['keyword'], 0) + 1
        
        print("\n按来源统计:")
        for source, count in source_counts.items():
            print(f"{source}: {count}篇")
        
        print("\n按关键词统计:")
        for keyword, count in keyword_counts.items():
            print(f"{keyword}: {count}篇")
    
    def print_sample_results(self, num=5):
        print(f"\n=== 样本结果 (显示{min(num, len(self.results))}条) ===")
        for i, item in enumerate(self.results[:num], 1):
            print(f"\n结果 {i}:")
            print(f"标题: {item['title']}")
            print(f"来源: {item['source']} ({item['source_site']})")
            print(f"发布时间: {item['published']}")
            print(f"关键词: {item['keyword']}")
            print(f"链接: {item['link']}")
            if 'content' in item:
                print(f"内容预览: {item['content'][:100]}...")

# ==================== 主程序 ====================
def main():
    # 获取当前时间戳用于日志记录
    start_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 运行新闻爬虫
    crawler = NewsCrawler(
        keywords=None,  # 从命令行参数获取
        max_results=100,
        max_workers=4
    )
    news_items = crawler.get_all_news()
    crawler.print_summary()
    crawler.print_sample_results()
    
    # 处理JSON文件中的文章
    data_dir = '/code/wurenj/news'
    output_base_dir = 'output/xinhua_articles'
    
    json_files = DataProcessor.find_json_files(data_dir)
    if not json_files:
        logger.error("没有找到匹配的JSON文件")
    else:
        logger.info(f"开始处理 {len(json_files)} 个JSON文件...")
        
        total_articles = 0
        success_count = 0
        
        for json_file in json_files:
            logger.info(f"\n{'='*50}")
            logger.info(f"处理文件: {json_file}")
            
            articles = DataProcessor.read_json_file(json_file)
            if not articles:
                logger.warning("文件中没有有效文章数据")
                continue
                
            for article in articles:
                total_articles += 1
                result = DataProcessor.process_article(article)
                if result and result.get('result'):
                    success_count += 1
        
        logger.info(f"\n{'='*50}")
        logger.info(f"处理完成! 共处理 {total_articles} 篇文章，成功抓取 {success_count} 篇")
    
    # 运行d-sv.py脚本
    try:
        logger.info("正在启动数据分析和可视化脚本...")
        dsv_script = "/code/wurenj/pachong/d-sv.py"
        
        # 传递关键词给d-sv.py
        keywords_arg = ','.join(crawler.keywords)
        
        # 使用subprocess运行脚本
        subprocess.run(
            ['python', dsv_script, keywords_arg],
            check=True,
            cwd=os.path.dirname(dsv_script)
        )
        logger.info("数据分析和可视化脚本执行完成")
    except subprocess.CalledProcessError as e:
        logger.error(f"执行d-sv.py失败: {str(e)}")
    except Exception as e:
        logger.error(f"运行数据分析脚本时发生错误: {str(e)}")

if __name__ == "__main__":
    main()