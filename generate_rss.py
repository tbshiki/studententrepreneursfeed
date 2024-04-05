import feedparser
from feedgen.feed import FeedGenerator
from datetime import datetime, timedelta
import pytz
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urlunparse
import time

# 日本時間のタイムゾーンを設定
JST = pytz.timezone("Asia/Tokyo")


def load_processed_entries(file_path):
    try:
        with open(file_path, "r") as file:
            return set(line.strip() for line in file)
    except FileNotFoundError:
        return set()


def save_processed_entries(file_path, entries):
    with open(file_path, "w") as file:
        for entry in entries:
            file.write(entry + "\n")


def get_rss_links(url, blacklist, max_depth, current_depth=0):
    if current_depth >= max_depth or url in blacklist or url in explored_urls:
        return []
    explored_urls.add(url)

    # 同一ドメインへのアクセス間隔を1秒以上開ける
    domain = urlparse(url).netloc
    if domain in last_access_time:
        elapsed_time = time.time() - last_access_time[domain]
        if elapsed_time < 1:
            time.sleep(1 - elapsed_time)
    last_access_time[domain] = time.time()

    try:
        response = requests.get(url, timeout=10)  # SSL検証を有効化

        # ステータスコードが200 (OK) 以外の場合は空のリストを返す
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")
        rss_links = [
            link.get("href")
            for link in soup.find_all("link", {"type": "application/rss+xml"})
        ]

        # サブディレクトリの場合は上位ディレクトリも含めて検証
        parsed_url = urlparse(url)
        base_url = parsed_url.scheme + "://" + parsed_url.netloc
        for path in parsed_url.path.split("/")[:-1]:
            base_url += path + "/"
            rss_url = base_url + "rss"
            if rss_url not in rss_links:
                response = requests.get(rss_url, timeout=10)
                if response.status_code == 200:
                    rss_links.append(rss_url)
            rss_url = base_url + "feed"
            if rss_url not in rss_links:
                response = requests.get(rss_url, timeout=10)
                if response.status_code == 200:
                    rss_links.append(rss_url)

        return rss_links
    except requests.exceptions.SSLError:
        try:
            response = requests.get(url, timeout=10, verify=False)  # SSL検証を無効化
            soup = BeautifulSoup(response.text, "html.parser")
            rss_links = [
                link.get("href")
                for link in soup.find_all("link", {"type": "application/rss+xml"})
            ]

            # サブディレクトリの場合は上位ディレクトリも含めて検証
            parsed_url = urlparse(url)
            base_url = parsed_url.scheme + "://" + parsed_url.netloc
            for path in parsed_url.path.split("/")[:-1]:
                base_url += path + "/"
                rss_url = base_url + "rss"
                if rss_url not in rss_links:
                    rss_links.append(rss_url)
                rss_url = base_url + "feed"
                if rss_url not in rss_links:
                    rss_links.append(rss_url)

            return rss_links
        except requests.exceptions.RequestException:
            return []
    except requests.exceptions.RequestException:
        return []


def add_new_url_to_file(url, file_path):
    with open(file_path, "r+") as file:
        existing_urls = [line.strip() for line in file]
        if url not in existing_urls:
            file.write(url + "\n")


def normalize_url(url):
    # URLからクエリパラメータを除去
    parsed_url = urlparse(url)
    normalized_url = urlunparse(parsed_url._replace(query=""))
    return normalized_url


def generate_rss_feed(feed_urls, blacklist):
    # 全てのフィードエントリを保持するリスト
    all_entries = []

    # 重複チェック用のセット
    entry_links = set()

    # 過去にチェック済みの記事のURLを取得
    checked_entries = load_processed_entries("processed_entries.txt")

    # 過去にindex.xmlに追加済みの記事のURLを取得
    indexed_entries = load_processed_entries("indexed_entries.txt")

    # 各フィードを読み込み、エントリをリストに追加
    for url in feed_urls:
        feed = feedparser.parse(url)
        entry_count = 0
        for entry in feed.entries:
            # URLを正規化
            normalized_link = normalize_url(entry.link)

            # チェック済みの記事は処理済みリストに追加
            if normalized_link not in checked_entries:
                checked_entries.add(normalized_link)

            # published_parsed属性が存在しない場合は現在の日時を使用
            if hasattr(entry, "published_parsed"):
                published_time = datetime.fromtimestamp(
                    time.mktime(entry.published_parsed)
                )
            else:
                published_time = datetime.now()

            # 3ヶ月以前の記事は無視
            if published_time < datetime.now() - timedelta(days=90):
                break

            # descriptionが存在しない場合は空の文字列を使用
            description = entry.description if hasattr(entry, "description") else ""

            # タイトルまたは説明に「起業」キーワードが含まれるかチェック
            if "起業" in entry.title + description:
                # 重複チェック
                if normalized_link not in entry_links:
                    all_entries.append(entry)
                    entry_links.add(normalized_link)
                    entry_count += 1

                    # index.xmlに追加済みの記事を追加
                    indexed_entries.add(normalized_link)

            # 再帰的に新しいURLを探索し、RSSフィードを追加
            new_urls = get_rss_links(entry.link, blacklist, max_depth=3)
            for new_url in new_urls:
                if new_url not in feed_urls and new_url not in blacklist:
                    if "起業" in entry.title + description:
                        add_new_url_to_file(new_url, "feed_urls.txt")
                        feed_urls.append(new_url)  # 新しいURLをfeed_urlsに追加

            # 記事数が300件に達したら次のフィードに移行
            if entry_count >= 300:
                break

    save_processed_entries("processed_entries.txt", checked_entries)
    save_processed_entries("indexed_entries.txt", indexed_entries)

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
    for entry in all_entries[:100]:  # 最新の100件を出力
        fe = fg.add_entry()
        fe.title(entry.title)
        fe.link(href=entry.link)
        fe.description(entry.description if hasattr(entry, "description") else "")
        if hasattr(entry, "published"):
            fe.published(entry.published)

    # RSSフィードをファイルに書き出す
    fg.rss_file("feed/index.xml", pretty=True, encoding="utf-8")


def load_urls_from_file(file_path):
    with open(file_path, "r") as file:
        return [line.strip() for line in file]


if __name__ == "__main__":
    last_access_time = {}
    explored_urls = set()
    feed_urls = load_urls_from_file("feed_urls.txt")
    blacklist = load_urls_from_file("blacklist.txt")
    generate_rss_feed(feed_urls, blacklist)
