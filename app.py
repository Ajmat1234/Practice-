from pytrends.request import TrendReq

# Pytrends object bana rahe hain
pytrends = TrendReq(hl='en-IN', tz=330)

# Top trending searches in India (realtime)
trending_searches_df = pytrends.trending_searches(pn='india')

# Print top 20 trending topics
print("Top Trending Topics in India:")
print(trending_searches_df.head(20))
