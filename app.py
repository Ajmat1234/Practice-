import requests
from bs4 import BeautifulSoup

def get_trending_searches_india():
    url = "https://trends.google.com/trends/trendingsearches/daily/rss?geo=IN"
    response = requests.get(url)

    if response.status_code != 200:
        print("Failed to fetch data:", response.status_code)
        return []

    soup = BeautifulSoup(response.content, 'xml')
    items = soup.find_all('item')

    trends = []
    for item in items:
        title = item.title.text
        trends.append(title)

    return trends

# Run function
top_trends = get_trending_searches_india()
print("Top Trending Google Searches in India (Last 24 Hours):")
for i, trend in enumerate(top_trends[:20], 1):
    print(f"{i}. {trend}")
