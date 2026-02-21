#!/usr/bin/env python3
"""
===================================
Nitter Twitter Search - Trump 推文搜索
===================================

功能：
1. 使用 Nitter 搜索 Trump 的推文
2. 无需 Twitter API Key
3. 返回推文内容、时间、点赞/转发数

使用方式：
    python nitter_search.py                    # 搜索 Trump 最新推文
    python nitter_search.py --query "tariff"   # 搜索特定关键词
    python nitter_search.py --limit 20         # 获取20条推文
"""

import argparse
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Nitter 实例列表（按可靠性排序）
NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.it",
    "https://nitter.cz",
    "https://nitter.privacydev.net",
    "https://nitter.projectsegfault.com",
]


@dataclass
class Tweet:
    """推文数据类"""
    id: str
    content: str
    created_at: str
    likes: int
    retweets: int
    replies: int
    url: str
    media_urls: List[str]
    is_reply: bool = False
    is_retweet: bool = False


class NitterClient:
    """Nitter 客户端"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.base_url = None
        self._find_working_instance()
    
    def _find_working_instance(self):
        """找到可用的 Nitter 实例"""
        for instance in NITTER_INSTANCES:
            try:
                logger.info(f"测试 Nitter 实例: {instance}")
                response = self.session.get(instance, timeout=10)
                if response.status_code == 200:
                    self.base_url = instance
                    logger.info(f"✅ 使用 Nitter 实例: {instance}")
                    return
            except Exception as e:
                logger.warning(f"❌ {instance} 不可用: {e}")
                continue
        
        raise Exception("没有可用的 Nitter 实例")
    
    def get_user_tweets(self, username: str = "realDonaldTrump", limit: int = 20) -> List[Tweet]:
        """
        获取用户的推文
        
        Args:
            username: Twitter 用户名
            limit: 获取数量
            
        Returns:
            推文列表
        """
        tweets = []
        cursor = ""
        
        while len(tweets) < limit:
            try:
                url = f"{self.base_url}/{username}"
                if cursor:
                    url += f"?cursor={cursor}"
                
                logger.info(f"获取 {username} 的推文...")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                # 解析 HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 查找推文
                tweet_elements = soup.find_all('div', class_='timeline-item')
                
                if not tweet_elements:
                    logger.warning("没有找到推文")
                    break
                
                for element in tweet_elements:
                    try:
                        tweet = self._parse_tweet_element(element, username)
                        if tweet:
                            tweets.append(tweet)
                            
                            if len(tweets) >= limit:
                                break
                    except Exception as e:
                        logger.warning(f"解析推文失败: {e}")
                        continue
                
                # 查找下一页 cursor
                show_more = soup.find('div', class_='show-more')
                if show_more and show_more.find('a'):
                    href = show_more.find('a')['href']
                    match = re.search(r'cursor=([^&]+)', href)
                    if match:
                        cursor = match.group(1)
                    else:
                        break
                else:
                    break
                
                # 防封禁延迟
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"获取推文失败: {e}")
                break
        
        return tweets[:limit]
    
    def search_tweets(self, query: str, limit: int = 20) -> List[Tweet]:
        """
        搜索推文
        
        Args:
            query: 搜索关键词
            limit: 获取数量
            
        Returns:
            推文列表
        """
        tweets = []
        cursor = ""
        
        # URL 编码查询词
        encoded_query = quote(query)
        
        while len(tweets) < limit:
            try:
                url = f"{self.base_url}/search?f=tweets&q={encoded_query}"
                if cursor:
                    url += f"&cursor={cursor}"
                
                logger.info(f"搜索: {query}")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                # 解析 HTML
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # 查找推文
                tweet_elements = soup.find_all('div', class_='timeline-item')
                
                if not tweet_elements:
                    logger.warning("没有找到推文")
                    break
                
                for element in tweet_elements:
                    try:
                        tweet = self._parse_tweet_element(element)
                        if tweet:
                            tweets.append(tweet)
                            
                            if len(tweets) >= limit:
                                break
                    except Exception as e:
                        logger.warning(f"解析推文失败: {e}")
                        continue
                
                # 查找下一页 cursor
                show_more = soup.find('div', class_='show-more')
                if show_more and show_more.find('a'):
                    href = show_more.find('a')['href']
                    match = re.search(r'cursor=([^&]+)', href)
                    if match:
                        cursor = match.group(1)
                    else:
                        break
                else:
                    break
                
                # 防封禁延迟
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"搜索推文失败: {e}")
                break
        
        return tweets[:limit]
    
    def _parse_tweet_element(self, element, default_username: str = "") -> Optional[Tweet]:
        """
        解析推文元素
        
        Args:
            element: BeautifulSoup 元素
            default_username: 默认用户名
            
        Returns:
            Tweet 对象或 None
        """
        try:
            # 检查是否是广告或其他内容
            if element.find('div', class_='ad'):
                return None
            
            # 获取推文链接和ID
            link_element = element.find('a', class_='tweet-link')
            if not link_element:
                return None
            
            tweet_url = link_element['href']
            if not tweet_url.startswith('http'):
                tweet_url = self.base_url + tweet_url
            
            # 提取推文ID
            tweet_id = ""
            match = re.search(r'/status/(\d+)', tweet_url)
            if match:
                tweet_id = match.group(1)
            
            # 获取用户名
            username_element = element.find('a', class_='username')
            username = username_element.text.strip() if username_element else default_username
            
            # 获取内容
            content_element = element.find('div', class_='tweet-content')
            if not content_element:
                return None
            
            # 提取文本
            text_element = content_element.find('div', class_='tweet-text')
            content = ""
            if text_element:
                # 清理 HTML 标签
                for br in text_element.find_all('br'):
                    br.replace_with('\n')
                content = text_element.get_text(separator=' ', strip=True)
            
            # 获取时间
            time_element = element.find('span', class_='tweet-date')
            created_at = ""
            if time_element and time_element.find('a'):
                # 从 title 属性获取完整时间
                time_link = time_element.find('a')
                created_at = time_link.get('title', time_link.text.strip())
            
            # 获取统计数据
            stats = element.find('div', class_='tweet-stats')
            likes = 0
            retweets = 0
            replies = 0
            
            if stats:
                # 回复数
                reply_stat = stats.find('div', class_='icon-reply')
                if reply_stat:
                    reply_text = reply_stat.get_text(strip=True)
                    replies = self._parse_number(reply_text)
                
                # 转发数
                retweet_stat = stats.find('div', class_='icon-retweet')
                if retweet_stat:
                    retweet_text = retweet_stat.get_text(strip=True)
                    retweets = self._parse_number(retweet_text)
                
                # 点赞数
                like_stat = stats.find('div', class_='icon-heart')
                if like_stat:
                    like_text = like_stat.get_text(strip=True)
                    likes = self._parse_number(like_text)
            
            # 获取媒体
            media_urls = []
            attachments = element.find('div', class_='attachments')
            if attachments:
                for img in attachments.find_all('img'):
                    if img.get('src'):
                        media_urls.append(img['src'])
            
            # 检查是否是回复
            is_reply = bool(element.find('div', class_='replying-to'))
            
            # 检查是否是转发
            is_retweet = bool(element.find('div', class_='retweet-header'))
            
            return Tweet(
                id=tweet_id,
                content=content,
                created_at=created_at,
                likes=likes,
                retweets=retweets,
                replies=replies,
                url=tweet_url,
                media_urls=media_urls,
                is_reply=is_reply,
                is_retweet=is_retweet
            )
            
        except Exception as e:
            logger.warning(f"解析推文元素失败: {e}")
            return None
    
    def _parse_number(self, text: str) -> int:
        """解析数字（支持 K/M 后缀）"""
        text = text.strip().replace(',', '')
        
        if not text:
            return 0
        
        try:
            if text.endswith('K'):
                return int(float(text[:-1]) * 1000)
            elif text.endswith('M'):
                return int(float(text[:-1]) * 1000000)
            else:
                return int(text)
        except:
            return 0


def main():
    """主入口函数"""
    parser = argparse.ArgumentParser(
        description='Nitter Twitter 搜索工具'
    )
    
    parser.add_argument(
        '--username', '-u',
        type=str,
        default='realDonaldTrump',
        help='Twitter 用户名，默认 realDonaldTrump'
    )
    
    parser.add_argument(
        '--query', '-q',
        type=str,
        help='搜索关键词'
    )
    
    parser.add_argument(
        '--limit', '-l',
        type=int,
        default=10,
        help='获取数量，默认10条'
    )
    
    args = parser.parse_args()
    
    try:
        # 初始化客户端
        client = NitterClient()
        
        # 获取推文
        if args.query:
            # 搜索模式
            search_query = f"from:{args.username} {args.query}"
            tweets = client.search_tweets(search_query, args.limit)
        else:
            # 用户推文模式
            tweets = client.get_user_tweets(args.username, args.limit)
        
        # 显示结果
        print(f"\n📊 找到 {len(tweets)} 条推文\n")
        print("=" * 80)
        
        for i, tweet in enumerate(tweets, 1):
            print(f"\n{i}. ", end="")
            if tweet.is_retweet:
                print("[转发] ", end="")
            if tweet.is_reply:
                print("[回复] ", end="")
            print(f"{tweet.created_at}")
            
            print(f"   📝 {tweet.content[:150]}{'...' if len(tweet.content) > 150 else ''}")
            print(f"   ❤️ {tweet.likes}  💬 {tweet.replies}  🔄 {tweet.retweets}")
            print(f"   🔗 {tweet.url}")
            
            if tweet.media_urls:
                print(f"   📷 媒体: {len(tweet.media_urls)} 张")
        
        print("\n" + "=" * 80)
        
    except Exception as e:
        logger.error(f"运行失败: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
