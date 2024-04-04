import feedparser
from feedgen.feed import FeedGenerator
from datetime import datetime
import pytz
import requests
from bs4 import BeautifulSoup

# 日本時間のタイムゾーンを設定
JST = pytz.timezone("Asia/Tokyo")


def get_rss_links(url, blacklist, max_depth, current_depth=0):
    if current_depth >= max_depth or url in blacklist:
        return []
    try:
        response = requests.get(url)
        soup = BeautifulSoup(response.text, "html.parser")
        rss_links = [
            link.get("href")
            for link in soup.find_all("link", {"type": "application/rss+xml"})
        ]
        return rss_links
    except:
        return []


def add_new_url_to_file(url, file_path):
    with open(file_path, "r+") as file:
        existing_urls = [line.strip() for line in file]
        if url not in existing_urls:
            file.write(url + "\n")


def generate_rss_feed(feed_urls, blacklist):
    # 全てのフィードエントリを保持するリスト
    all_entries = []

    # 各フィードを読み込み、エントリをリストに追加
    for url in feed_urls:
        feed = feedparser.parse(url)
        all_entries.extend(feed.entries)

        # 再帰的に新しいURLを探索し、RSSフィードを追加
        new_urls = get_rss_links(url, blacklist, max_depth=3)
        for new_url in new_urls:
            if new_url not in feed_urls and new_url not in blacklist:
                add_new_url_to_file(new_url, "feed_urls.txt")
                add_new_url_to_file(new_url, "blacklist.txt")

    # エントリを公開日でソート
    # 'published_parsed'がない場合は現在時刻を使用する
    all_entries.sort(
        key=lambda entry: entry.get(
            "published_parsed", datetime.now(tz=JST).timetuple()
        ),
        reverse=True,
    )

    # 新しいRSSフィードを初期化
    fg = FeedGenerator()
    fg.title("Student Entrepreneurs Feed")
    fg.link(href="https://tbshiki.github.io/studententrepreneursfeed/", rel="alternate")
    fg.description(
        "This FEED is a compilation of student entrepreneurship information. We wish you success."
    )
    fg.lastBuildDate(datetime.now(JST))

    # 新しいRSSフィードの項目を追加
    for entry in all_entries:
        # タイトルまたは説明に「学生」というワードが含まれるかチェック
        if "学生" in entry.title or "学生" in entry.description:
            fe = fg.add_entry()
            fe.title(entry.title)
            fe.link(href=entry.link)
            fe.description(entry.description)
            if hasattr(entry, "published"):
                fe.published(entry.published)

    # RSSフィードをファイルに書き出す
    fg.rss_file("feed/index.xml", pretty=True, encoding="utf-8")


def load_urls_from_file(file_path):
    with open(file_path, "r") as file:
        return [line.strip() for line in file]


if __name__ == "__main__":
    feed_urls = load_urls_from_file("feed_urls.txt")
    blacklist = load_urls_from_file("blacklist.txt")
    generate_rss_feed(feed_urls, blacklist)
