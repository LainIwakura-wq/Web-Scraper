from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse
import hashlib
import time
import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn

console = Console()

# =====================
# USER INPUT
# =====================
START_URL = input("Enter the URL to crawl: ").strip()
parsed_url = urlparse(START_URL)
if not parsed_url.scheme.startswith("http"):
    console.print("[red]Invalid URL! Must start with http:// or https://[/red]")
    exit(1)

ALLOWED_DOMAIN = parsed_url.netloc
console.print(f"[green]Crawling site:[/green] {START_URL} (domain: {ALLOWED_DOMAIN})")

# =====================
# CONFIG
# =====================
OUTPUT_DIR = Path("data")
PAGES_DIR = OUTPUT_DIR / "pages"
IMAGES_DIR = OUTPUT_DIR / "images"
VIDEOS_DIR = OUTPUT_DIR / "videos"

MAX_PAGES = 50
CRAWL_DELAY = 1.0
TIMEOUT = 15
HEADERS = {"User-Agent": "TerminalCrawler/1.0"}

# =====================
# UTILITIES
# =====================
def normalize_url(url, base):
    if not url:
        return None
    return urljoin(base, url)


def same_domain(url):
    return urlparse(url).netloc == ALLOWED_DOMAIN


def hash_name(text):
    return hashlib.sha256(text.encode()).hexdigest()


# =====================
# FETCH PAGE
# =====================
def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


# =====================
# PARSE HTML
# =====================
def parse(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    links = set(normalize_url(a["href"], base_url) for a in soup.find_all("a", href=True))
    images = set(normalize_url(img["src"], base_url) for img in soup.find_all("img", src=True))
    videos = set()
    for v in soup.find_all("video"):
        if v.get("src"):
            videos.add(normalize_url(v["src"], base_url))
        for s in v.find_all("source", src=True):
            videos.add(normalize_url(s["src"], base_url))
    return links, images, videos


# =====================
# DOWNLOAD MEDIA
# =====================
def download(url, folder):
    folder.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(url)
    name = Path(parsed.path).name or hash_name(url)
    path = folder / name
    if path.exists():
        return False
    try:
        r = requests.get(url, headers=HEADERS, stream=True, timeout=TIMEOUT)
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True
    except Exception:
        return False


# =====================
# SAVE PAGE
# =====================
def save_page(url, html):
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    filename = PAGES_DIR / f"{hash_name(url)}.html"
    filename.write_text(html, encoding="utf-8")


# =====================
# MAIN CRAWLER
# =====================
def crawl():
    visited = set()
    queue = deque([START_URL])
    count = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        console=console,
    ) as progress:
        page_task = progress.add_task("[cyan]Pages Crawled[/cyan]", total=MAX_PAGES)
        media_task = progress.add_task("[magenta]Media Downloaded[/magenta]", total=0)  # dynamic

        while queue and count < MAX_PAGES:
            url = queue.popleft()
            if url in visited or not same_domain(url):
                console.log(f"[yellow][SKIP][/yellow] {url}")
                continue

            visited.add(url)
            console.log(f"[green][PAGE][/green] Crawling: {url}")

            try:
                html = fetch(url)
            except Exception as e:
                console.log(f"[red][ERROR][/red] {url} → {e}")
                continue

            save_page(url, html)
            links, images, videos = parse(html, url)

            # Queue new links
            for link in links:
                if link not in visited:
                    queue.append(link)

            # Download images
            for img in images:
                if download(img, IMAGES_DIR):
                    progress.update(media_task, advance=1)
                    console.log(f"[blue][IMG][/blue] {img}")

            # Download videos
            for vid in videos:
                if download(vid, VIDEOS_DIR):
                    progress.update(media_task, advance=1)
                    console.log(f"[magenta][VID][/magenta] {vid}")

            count += 1
            progress.update(page_task, advance=1)
            time.sleep(CRAWL_DELAY)

    console.log(f"[bold green]Crawling complete![/bold green] Total pages crawled: {count}")


if __name__ == "__main__":
    crawl()
