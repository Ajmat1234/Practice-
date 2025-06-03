import requests
from bs4 import BeautifulSoup

def get_trending_searches():
    url = "https://trends.google.com/trends/trendingsearches/daily?geo=IN"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print("Failed to fetch data:", response.status_code)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    titles = soup.select("div.feed-item-header > a")

    results = []
    for title in titles:
        results.append(title.text.strip())

    return results

# Run it
top_trends = get_trending_searches()
print("Top Trending Google Searches in India (Last 24 Hours):")
for i, trend in enumerate(top_trends[:20], 1):
    print(f"{i}. {trend}")
