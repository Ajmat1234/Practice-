from pytrends.request import TrendReq

pytrends = TrendReq(hl='en-US', tz=360)

# Try with supported country
trending_searches_df = pytrends.trending_searches(pn='united_states')

print("Top Trending Topics (US):")
print(trending_searches_df.head(20))
