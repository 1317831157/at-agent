import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import time
from urllib.parse import quote, urljoin
import re
import random
from fake_useragent import UserAgent
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import os
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('news_crawler.log'),
        logging.StreamHandler()
    ]
)

class NewsCrawler:
    def __init__(self, keywords=None, max_results=100, max_workers=5):
        # 从命令行参数获取关键词
        if keywords is None:
            if len(sys.argv) > 1:
                self.keywords = sys.argv[1].split(',')
            else:
                self.keywords = ["无人机袭击"]
        else:
            self.keywords = keywords if isinstance(keywords, list) else [keywords]
            
        self.max_results = max_results
        self.max_workers = max_workers
        self.ua = UserAgent()
        self.session = requests.Session()
        
        # 初始化请求头
        self.default_headers = {
            'User-Agent': self.ua.random,
            'Referer': 'http://so.news.cn/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        # 新华网特定的请求头
        self.site_specific_headers = {
            '新华网': {
                'Referer': 'http://so.news.cn/',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36'
            }
        }
        
        self.session.headers.update(self.default_headers)
        self.results = []
        self.visited_urls = set()
        
        # 仅保留新华网作为新闻源
        self.news_sources = {
            '新华网': self.search_xinhua
        }
        
        # 代理配置（如果需要）
        self.proxies = None
        
        # 确保输出目录存在
        self.output_dir = '/code/wurenj/news'
        os.makedirs(self.output_dir, exist_ok=True)
    
    def random_delay(self):
        """随机延迟以避免被检测为爬虫"""
        time.sleep(random.uniform(1, 3))
    
    def make_request(self, url, method='GET', source_name=None, **kwargs):
        """封装请求方法，添加错误处理和重试机制"""
        max_retries = 3
        retry_delay = 2
        
        # 合并请求头：默认头 + 特定网站头 + 用户自定义头
        headers = self.default_headers.copy()
        if source_name and source_name in self.site_specific_headers:
            headers.update(self.site_specific_headers[source_name])
        
        # 添加或覆盖用户自定义的请求头
        if 'headers' in kwargs:
            headers.update(kwargs['headers'])
            del kwargs['headers']
        
        for attempt in range(max_retries):
            try:
                # 更新User-Agent和Referer
                headers['User-Agent'] = self.ua.random
                
                # 如果是特定网站，更新Referer
                if source_name and source_name in self.site_specific_headers:
                    headers['Referer'] = self.site_specific_headers[source_name].get('Referer', headers['Referer'])
                
                response = self.session.request(
                    method, 
                    url, 
                    proxies=self.proxies,
                    timeout=10,
                    headers=headers,
                    **kwargs
                )
                response.raise_for_status()
                
                # 检查是否被重定向到验证页面
                if "验证" in response.text or "verification" in response.text.lower():
                    raise requests.exceptions.RequestException("Encountered verification page")
                
                return response
            except requests.exceptions.RequestException as e:
                logging.warning(f"Attempt {attempt + 1} failed for {url}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                logging.error(f"Failed to fetch {url} after {max_retries} attempts")
                return None
    
    def search_xinhua(self, keyword):
        """搜索新华网新闻，使用xinhua.py的翻页逻辑"""
        results = []
        current_page = 1
        processed_count = 0
        
        while len(results) < self.max_results:
            logging.info(f"正在爬取新华网第 {current_page} 页，关键词: {keyword}")
            
            # 获取新闻列表
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
                logging.debug(f"API返回数据: {json.dumps(news_data, ensure_ascii=False, indent=2)}")
                
                # 检查数据结构是否符合预期
                if not isinstance(news_data, dict):
                    logging.warning(f"第 {current_page} 页返回数据不是字典格式")
                    current_page += 1
                    continue
                    
                # 新版新华网API可能返回的格式
                if 'content' in news_data and 'results' in news_data['content']:
                    news_items = news_data['content']['results']
                # 旧版格式
                elif 'content' in news_data and isinstance(news_data['content'], list):
                    news_items = news_data['content']
                else:
                    logging.warning(f"第 {current_page} 页数据格式不符合预期: {news_data.keys()}")
                    current_page += 1
                    continue
                
                # 处理当前页的新闻
                page_processed = 0
                
                for item in news_items:
                    if len(results) >= self.max_results:
                        break
                    
                    if not isinstance(item, dict) or not item.get('url'):
                        continue
                    
                    # 补全URL
                    news_url = urljoin("https://so.news.cn/", item['url'])
                    
                    if news_url in self.visited_urls:
                        continue
                    
                    # 获取新闻详情
                    try:
                        news_detail = {
                            'title': item.get('title', '无标题'),
                            'link': news_url,
                            'source': '新华网',
                            'published': item.get('pubtime', '未知时间'),
                            'keyword': keyword,
                            'source_site': '新华网'
                        }
                        
                        # 获取详情页内容
                        detail_response = self.make_request(news_url, source_name='新华网')
                        if detail_response:
                            soup = BeautifulSoup(detail_response.text, 'html.parser')
                            
                            # 提取标题（优先使用详情页的标题）
                            detail_title = soup.find('h1')
                            if detail_title:
                                news_detail['title'] = detail_title.get_text(strip=True)
                            
                            # 提取发布时间和来源
                            source_info = soup.find('span', class_='source')
                            if source_info:
                                source_text = source_info.get_text(strip=True)
                                parts = [p.strip() for p in source_text.split('|')]
                                if len(parts) > 1:
                                    news_detail['published'] = parts[1].strip()
                            
                            # 提取正文内容
                            content_div = soup.find('div', class_='content')
                            if content_div:
                                for elem in content_div(['script', 'style', 'iframe', 'img', 'video']):
                                    elem.decompose()
                                news_detail['content'] = ' '.join(p.get_text(strip=True) for p in content_div.find_all('p'))
                        
                        results.append(news_detail)
                        self.visited_urls.add(news_url)
                        page_processed += 1
                        
                        # 每页最多处理7条
                        if page_processed >= 10:
                            break
                        
                        # 礼貌性延迟
                        time.sleep(1)
                    
                    except Exception as e:
                        logging.error(f"处理新闻条目失败: {str(e)}")
                        continue
                
                # 翻页
                current_page += 1
                
                # 如果当前页没有处理任何新闻，可能已经到达末尾
                if page_processed == 0:
                    break
                
                # 延迟防止被封
                time.sleep(2)
            
            except ValueError as e:
                logging.error(f"解析新华网JSON失败: {str(e)}")
                break
            except Exception as e:
                logging.error(f"处理第 {current_page} 页时发生未知错误: {str(e)}")
                break
        
        return results
    
    def get_news_from_source(self, source_name, keyword):
        """从单个新闻源获取新闻"""
        try:
            search_func = self.news_sources.get(source_name)
            if search_func:
                results = search_func(keyword)
                # 为每个关键词和来源单独保存文件
                filename = f"{keyword}_{source_name}.json"
                filepath = os.path.join(self.output_dir, filename)
                self._save_results(results, filepath)
                return results
            return []
        except Exception as e:
            logging.error(f"Error getting news from {source_name} for {keyword}: {str(e)}")
            return []
    
    def _save_results(self, results, filepath):
        """内部方法：保存结果到指定文件"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logging.info(f"Results saved to {filepath}")
        except Exception as e:
            logging.error(f"Error saving to JSON: {str(e)}")
    
    def get_all_news(self):
        """从所有新闻源获取新闻（使用多线程）"""
        start_time = datetime.now()
        logging.info(f"Starting news crawl for keywords: {', '.join(self.keywords)}")
        
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
                    logging.error(f"Error in future: {str(e)}")
        
        # 去重
        unique_results = []
        seen_links = set()
        
        for item in self.results:
            clean_link = re.sub(r'[?#].*$', '', item['link'])
            if clean_link not in seen_links:
                seen_links.add(clean_link)
                unique_results.append(item)
        
        self.results = unique_results
        elapsed = datetime.now() - start_time
        logging.info(f"Finished crawl. Found {len(self.results)} articles in {elapsed.total_seconds():.2f} seconds")
        return self.results
    
    def print_summary(self):
        """打印摘要统计信息"""
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
        """打印样本结果"""
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


if __name__ == "__main__":
    # 创建爬虫实例
    # 关键词可以从命令行参数获取，格式为: python script.py 关键词1,关键词2
    crawler = NewsCrawler(
        max_results=100,  # 设置单次爬取100条新闻
        max_workers=4     # 并发线程数
    )
    
    # 执行爬取
    news_items = crawler.get_all_news()
    
    # 输出摘要和样本结果
    crawler.print_summary()
    crawler.print_sample_results()