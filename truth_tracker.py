# -*- coding: utf-8 -*-
"""
===================================
Truth Social Tracker - Trump 帖子追踪器
===================================

功能：
1. 自动抓取 Trump 的 Truth Social 帖子
2. 存储到本地数据库
3. 检测新帖子并通知
4. 分析帖子内容（情感、关键词、股票提及）
5. 与股票分析系统集成

使用方式：
    python truth_tracker.py                    # 运行一次抓取
    python truth_tracker.py --daemon           # 守护模式，持续监控
    python truth_tracker.py --analyze          # 分析历史帖子
"""

import argparse
import json
import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict
from pathlib import Path

import requests

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# 常量
TRUMP_USERNAME = "realdonaldtrump"
TRUTH_SOCIAL_API = "https://truthsocial.com/api/v1"
DB_PATH = Path(__file__).parent / "data" / "truth_social.db"
DATA_DIR = Path(__file__).parent / "data"

# 股票代码正则（匹配 $TSLA 或 #TSLA 格式）
STOCK_PATTERN = re.compile(r'[\$#]([A-Z]{1,5})')


@dataclass
class TruthPost:
    """Truth Social 帖子数据类"""
    id: str
    created_at: str
    content: str
    url: str
    media_urls: List[str]
    replies_count: int
    reblogs_count: int
    favourites_count: int
    
    # 分析字段
    sentiment_score: float = 0.0  # -1 到 1
    sentiment_label: str = "neutral"  # positive/negative/neutral
    mentioned_stocks: List[str] = None
    keywords: List[str] = None
    
    def __post_init__(self):
        if self.mentioned_stocks is None:
            self.mentioned_stocks = []
        if self.keywords is None:
            self.keywords = []


class TruthSocialTracker:
    """Truth Social 追踪器"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DB_PATH)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
        # 确保数据目录存在
        DATA_DIR.mkdir(exist_ok=True)
        
        # 初始化数据库
        self._init_db()
    
    def _init_db(self):
        """初始化 SQLite 数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posts (
                id TEXT PRIMARY KEY,
                created_at TEXT,
                content TEXT,
                url TEXT,
                media_urls TEXT,
                replies_count INTEGER,
                reblogs_count INTEGER,
                favourites_count INTEGER,
                sentiment_score REAL,
                sentiment_label TEXT,
                mentioned_stocks TEXT,
                keywords TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_created_at ON posts(created_at)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_mentioned_stocks ON posts(mentioned_stocks)
        ''')
        
        conn.commit()
        conn.close()
        logger.info(f"数据库初始化完成: {self.db_path}")
    
    def fetch_posts(self, username: str = TRUMP_USERNAME, limit: int = 40) -> List[TruthPost]:
        """
        从 Truth Social 获取帖子
        
        使用第三方 RSS 服务或 API
        
        Args:
            username: 用户名
            limit: 获取数量
            
        Returns:
            帖子列表
        """
        posts = []
        
        # 尝试多个数据源
        urls_to_try = [
            # 方法1: 使用 nitter 实例 (Twitter/X 镜像，但可能支持 Truth Social)
            # 方法2: 使用 RSSHub
            f"https://rsshub.app/truthsocial/user/{username}",
            # 方法3: 使用 trumpstruth.org (第三方 RSS)
            f"https://trumpstruth.org/feed",
        ]
        
        for url in urls_to_try:
            try:
                logger.info(f"尝试从 {url} 获取...")
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                
                # 解析 RSS
                import xml.etree.ElementTree as ET
                root = ET.fromstring(response.content)
                
                for item in root.findall('.//item'):
                    try:
                        post_id = item.find('guid').text if item.find('guid') is not None else ""
                        title = item.find('title').text if item.find('title') is not None else ""
                        link = item.find('link').text if item.find('link') is not None else ""
                        pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
                        
                        description = item.find('description')
                        content = description.text if description is not None else title
                        
                        post = TruthPost(
                            id=post_id,
                            created_at=pub_date,
                            content=content,
                            url=link,
                            media_urls=[],
                            replies_count=0,
                            reblogs_count=0,
                            favourites_count=0
                        )
                        
                        posts.append(post)
                        
                    except Exception as e:
                        logger.warning(f"解析帖子失败: {e}")
                        continue
                
                if posts:
                    logger.info(f"成功从 {url} 获取 {len(posts)} 条帖子")
                    break
                    
            except Exception as e:
                logger.warning(f"从 {url} 获取失败: {e}")
                continue
        
        if not posts:
            logger.error("所有数据源都失败")
        
        return posts[:limit]
    
    def analyze_post(self, post: TruthPost) -> TruthPost:
        """
        分析帖子内容
        
        Args:
            post: 帖子对象
            
        Returns:
            分析后的帖子对象
        """
        content = post.content
        
        # 1. 简单情感分析（基于关键词）
        positive_words = ['great', 'good', 'excellent', 'amazing', 'fantastic', 'wonderful', 'best', 'win', 'winning', 'success', 'successful', 'love', 'like', 'happy', 'congratulations', 'thank', 'thanks']
        negative_words = ['bad', 'terrible', 'awful', 'worst', 'fail', 'failure', 'hate', 'dislike', 'sad', 'angry', 'disappointed', 'wrong', 'fake', 'lie', 'lies', 'stupid', 'dumb']
        
        content_lower = content.lower()
        pos_count = sum(1 for word in positive_words if word in content_lower)
        neg_count = sum(1 for word in negative_words if word in content_lower)
        
        if pos_count > neg_count:
            post.sentiment_score = min(0.5 + (pos_count - neg_count) * 0.1, 1.0)
            post.sentiment_label = "positive"
        elif neg_count > pos_count:
            post.sentiment_score = max(-0.5 - (neg_count - pos_count) * 0.1, -1.0)
            post.sentiment_label = "negative"
        else:
            post.sentiment_score = 0.0
            post.sentiment_label = "neutral"
        
        # 2. 提取股票代码
        matches = STOCK_PATTERN.findall(content)
        post.mentioned_stocks = list(set(matches))  # 去重
        
        # 3. 提取关键词 (简单版)
        words = content.split()
        post.keywords = [w for w in words if len(w) > 4 and w.isalpha()][:10]
        
        return post
    
    def save_post(self, post: TruthPost) -> bool:
        """
        保存帖子到数据库
        
        Args:
            post: 帖子对象
            
        Returns:
            是否为新帖子
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO posts (
                    id, created_at, content, url, media_urls,
                    replies_count, reblogs_count, favourites_count,
                    sentiment_score, sentiment_label, mentioned_stocks, keywords
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                post.id,
                post.created_at,
                post.content,
                post.url,
                json.dumps(post.media_urls),
                post.replies_count,
                post.reblogs_count,
                post.favourites_count,
                post.sentiment_score,
                post.sentiment_label,
                json.dumps(post.mentioned_stocks),
                json.dumps(post.keywords)
            ))
            
            is_new = cursor.rowcount > 0
            conn.commit()
            
            if is_new:
                logger.info(f"新帖子已保存: {post.id[:20]}...")
            
            return is_new
            
        except Exception as e:
            logger.error(f"保存帖子失败: {e}")
            return False
            
        finally:
            conn.close()
    
    def get_new_posts(self, username: str = TRUMP_USERNAME) -> List[TruthPost]:
        """
        获取新帖子（数据库中不存在的）
        
        Returns:
            新帖子列表
        """
        # 获取最新帖子
        posts = self.fetch_posts(username)
        
        new_posts = []
        for post in posts:
            # 分析帖子
            post = self.analyze_post(post)
            
            # 保存到数据库（如果是新帖子）
            if self.save_post(post):
                new_posts.append(post)
        
        return new_posts
    
    def get_posts_with_stock_mentions(self, stock_code: str = None) -> List[Dict]:
        """
        获取提及股票的帖子
        
        Args:
            stock_code: 股票代码（可选，为空则返回所有提及股票的帖子）
            
        Returns:
            帖子列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            if stock_code:
                cursor.execute('''
                    SELECT * FROM posts 
                    WHERE mentioned_stocks LIKE ?
                    ORDER BY created_at DESC
                ''', (f'%"{stock_code}"%',))
            else:
                cursor.execute('''
                    SELECT * FROM posts 
                    WHERE mentioned_stocks != "[]"
                    ORDER BY created_at DESC
                ''')
            
            rows = cursor.fetchall()
            
            posts = []
            for row in rows:
                post = {
                    'id': row[0],
                    'created_at': row[1],
                    'content': row[2],
                    'url': row[3],
                    'media_urls': json.loads(row[4]) if row[4] else [],
                    'replies_count': row[5],
                    'reblogs_count': row[6],
                    'favourites_count': row[7],
                    'sentiment_score': row[8],
                    'sentiment_label': row[9],
                    'mentioned_stocks': json.loads(row[10]) if row[10] else [],
                    'keywords': json.loads(row[11]) if row[11] else [],
                }
                posts.append(post)
            
            return posts
            
        finally:
            conn.close()
    
    def generate_report(self, hours: int = 24) -> str:
        """
        生成报告
        
        Args:
            hours: 最近多少小时
            
        Returns:
            报告文本
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        since = (datetime.now() - timedelta(hours=hours)).isoformat()
        
        cursor.execute('''
            SELECT * FROM posts 
            WHERE fetched_at > ?
            ORDER BY created_at DESC
        ''', (since,))
        
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            return f"过去 {hours} 小时没有新帖子"
        
        lines = []
        lines.append(f"\n📊 Truth Social 报告 (过去 {hours} 小时)")
        lines.append("=" * 60)
        lines.append(f"新帖子数: {len(rows)}")
        
        # 统计提及股票
        all_stocks = []
        for row in rows:
            stocks = json.loads(row[10]) if row[10] else []
            all_stocks.extend(stocks)
        
        if all_stocks:
            lines.append(f"\n📈 提及股票: {', '.join(set(all_stocks))}")
        
        # 最新帖子
        lines.append("\n📝 最新帖子:")
        for row in rows[:5]:
            content = row[2][:100] + "..." if len(row[2]) > 100 else row[2]
            sentiment = row[9]
            emoji = "😊" if sentiment == "positive" else "😠" if sentiment == "negative" else "😐"
            lines.append(f"\n{emoji} {content}")
            lines.append(f"   🔗 {row[3]}")
        
        return "\n".join(lines)


def run_daemon_mode(tracker: TruthSocialTracker, interval: int = 900):
    """
    守护模式运行
    
    Args:
        tracker: 追踪器实例
        interval: 检查间隔（秒），默认15分钟
    """
    logger.info(f"启动守护模式，检查间隔: {interval}秒")
    
    while True:
        try:
            logger.info("检查新帖子...")
            new_posts = tracker.get_new_posts()
            
            if new_posts:
                logger.info(f"发现 {len(new_posts)} 条新帖子")
                
                # 检查是否有提及股票的帖子
                for post in new_posts:
                    if post.mentioned_stocks:
                        logger.info(f"🚨 帖子提及股票: {post.mentioned_stocks}")
                        logger.info(f"   内容: {post.content[:100]}...")
                        # 这里可以触发股票分析
            else:
                logger.info("没有新帖子")
            
            logger.info(f"下次检查: {interval}秒后")
            time.sleep(interval)
            
        except KeyboardInterrupt:
            logger.info("用户中断，退出守护模式")
            break
        except Exception as e:
            logger.error(f"守护模式错误: {e}")
            time.sleep(60)  # 出错后1分钟再试


def main():
    """主入口函数"""
    parser = argparse.ArgumentParser(
        description='Truth Social Tracker - Trump 帖子追踪器'
    )
    
    parser.add_argument(
        '--daemon', '-d',
        action='store_true',
        help='守护模式，持续监控'
    )
    
    parser.add_argument(
        '--interval',
        type=int,
        default=900,
        help='检查间隔（秒），默认900秒（15分钟）'
    )
    
    parser.add_argument(
        '--report',
        action='store_true',
        help='生成报告'
    )
    
    parser.add_argument(
        '--hours',
        type=int,
        default=24,
        help='报告时间范围（小时），默认24小时'
    )
    
    parser.add_argument(
        '--stock',
        type=str,
        help='查询提及特定股票的帖子'
    )
    
    args = parser.parse_args()
    
    # 初始化追踪器
    tracker = TruthSocialTracker()
    
    if args.daemon:
        # 守护模式
        run_daemon_mode(tracker, args.interval)
        
    elif args.report:
        # 生成报告
        report = tracker.generate_report(args.hours)
        print(report)
        
    elif args.stock:
        # 查询特定股票
        posts = tracker.get_posts_with_stock_mentions(args.stock)
        print(f"\n📈 提及 {args.stock} 的帖子 ({len(posts)}条):")
        for post in posts:
            print(f"\n{post['created_at']}")
            print(f"{post['content'][:200]}...")
            print(f"🔗 {post['url']}")
            
    else:
        # 单次运行
        logger.info("单次运行模式")
        new_posts = tracker.get_new_posts()
        
        if new_posts:
            print(f"\n✅ 获取到 {len(new_posts)} 条新帖子")
            for post in new_posts:
                print(f"\n📅 {post.created_at}")
                print(f"📝 {post.content[:150]}...")
                print(f"😊 情感: {post.sentiment_label} ({post.sentiment_score:+.2f})")
                if post.mentioned_stocks:
                    print(f"📈 提及股票: {', '.join(post.mentioned_stocks)}")
                print(f"🔗 {post.url}")
        else:
            print("\nℹ️ 没有新帖子")


if __name__ == "__main__":
    main()
