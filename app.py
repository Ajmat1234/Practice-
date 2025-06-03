from serpapi import GoogleSearch

params = {
    "engine": "google_trends",
    "trend_type": "daily_searches",
    "geo": "IN",  # India
    "api_key": "70ebdbe547951ef401bb19a971980b9d54a5eb1b3c1be277de68d946c08e9f4d"
}

search = GoogleSearch(params)
results = search.get_dict()

trends = results.get("trending_searches", [])
print("Top Google Trends (India - 24 hours):")
for i, trend in enumerate(trends[:20], 1):
    print(f"{i}. {trend['title']}")
