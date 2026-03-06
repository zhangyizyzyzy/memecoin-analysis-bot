#!/usr/bin/env python3
"""
Memecoin Intelligence Collector
Collects data from Twitter, News, DexScreener, OKX, and generates AI analysis reports.
"""

import os
import json
import time
import hmac
import hashlib
import base64
import asyncio
import aiohttp
import requests
from datetime import datetime, timezone
from pathlib import Path

# ─── CONFIG ────────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
TWITTER_BEARER_TOKEN = os.environ.get("TWITTER_BEARER_TOKEN", "")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")
OKX_API_KEY = os.environ.get("OKX_API_KEY", "")
OKX_SECRET = os.environ.get("OKX_SECRET", "")
OKX_PASSPHRASE = os.environ.get("OKX_PASSPHRASE", "")

# Chains to monitor
CHAINS = ["solana", "ethereum", "base", "bsc"]

# DEX Screener chain IDs
DEXSCREENER_CHAINS = {
    "solana": "solana",
    "ethereum": "ethereum",
    "base": "base",
    "bsc": "bsc",
}

# Output directory for GitHub Pages
DOCS_DIR = Path(__file__).parent.parent / "docs"
DATA_DIR = DOCS_DIR / "data"

# ─── DEXSCREENER ───────────────────────────────────────────────────────────────

def fetch_dexscreener_trending(chain: str) -> list:
    """Fetch trending tokens from DexScreener for a given chain."""
    try:
        url = f"https://api.dexscreener.com/token-boosts/top/v1"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        # Filter by chain
        chain_tokens = [t for t in data if t.get("chainId", "").lower() == chain.lower()]
        
        results = []
        for token in chain_tokens[:10]:
            results.append({
                "symbol": token.get("tokenAddress", "")[:8],
                "address": token.get("tokenAddress", ""),
                "chain": chain,
                "url": token.get("url", ""),
                "boostAmount": token.get("totalAmount", 0),
                "source": "dexscreener_boost"
            })
        return results
    except Exception as e:
        print(f"[DEX] Error fetching trending for {chain}: {e}")
        return []

def fetch_dexscreener_token_detail(token_address: str, chain: str) -> dict:
    """Fetch detailed token data from DexScreener."""
    try:
        chain_id = DEXSCREENER_CHAINS.get(chain, chain)
        url = f"https://api.dexscreener.com/tokens/v1/{chain_id}/{token_address}"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        if not data or len(data) == 0:
            return {}
        
        pair = data[0]
        base = pair.get("baseToken", {})
        
        return {
            "symbol": base.get("symbol", "UNKNOWN"),
            "name": base.get("name", ""),
            "address": token_address,
            "chain": chain,
            "price_usd": pair.get("priceUsd", "0"),
            "price_change_5m": pair.get("priceChange", {}).get("m5", 0),
            "price_change_1h": pair.get("priceChange", {}).get("h1", 0),
            "price_change_6h": pair.get("priceChange", {}).get("h6", 0),
            "price_change_24h": pair.get("priceChange", {}).get("h24", 0),
            "volume_24h": pair.get("volume", {}).get("h24", 0),
            "liquidity_usd": pair.get("liquidity", {}).get("usd", 0),
            "market_cap": pair.get("marketCap", 0),
            "fdv": pair.get("fdv", 0),
            "txns_24h_buys": pair.get("txns", {}).get("h24", {}).get("buys", 0),
            "txns_24h_sells": pair.get("txns", {}).get("h24", {}).get("sells", 0),
            "dex_url": pair.get("url", ""),
            "source": "dexscreener"
        }
    except Exception as e:
        print(f"[DEX] Error fetching detail for {token_address}: {e}")
        return {}

def fetch_dexscreener_new_pairs(chain: str) -> list:
    """Fetch latest token pairs from DexScreener."""
    try:
        url = f"https://api.dexscreener.com/token-profiles/latest/v1"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        chain_tokens = [t for t in data if t.get("chainId", "").lower() == chain.lower()]
        
        results = []
        for token in chain_tokens[:5]:
            addr = token.get("tokenAddress", "")
            detail = fetch_dexscreener_token_detail(addr, chain)
            if detail:
                detail["is_new"] = True
                results.append(detail)
            time.sleep(0.3)  # Rate limit
        return results
    except Exception as e:
        print(f"[DEX] Error fetching new pairs for {chain}: {e}")
        return []

# ─── TWITTER / OPENTWITTER-MCP ──────────────────────────────────────────────────

def search_twitter_memecoin(query: str) -> list:
    """Search Twitter for memecoin mentions via bearer token."""
    try:
        headers = {"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"}
        params = {
            "query": f"{query} -is:retweet lang:en",
            "max_results": 20,
            "tweet.fields": "public_metrics,created_at,author_id",
            "expansions": "author_id",
            "user.fields": "username,public_metrics"
        }
        url = "https://api.twitter.com/2/tweets/search/recent"
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        
        if resp.status_code == 200:
            data = resp.json()
            tweets = data.get("data", [])
            users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
            
            results = []
            for tweet in tweets:
                author = users.get(tweet.get("author_id", ""), {})
                metrics = tweet.get("public_metrics", {})
                user_metrics = author.get("public_metrics", {})
                results.append({
                    "text": tweet.get("text", ""),
                    "likes": metrics.get("like_count", 0),
                    "retweets": metrics.get("retweet_count", 0),
                    "replies": metrics.get("reply_count", 0),
                    "author": author.get("username", "unknown"),
                    "author_followers": user_metrics.get("followers_count", 0),
                    "created_at": tweet.get("created_at", ""),
                    "engagement": metrics.get("like_count", 0) + metrics.get("retweet_count", 0) * 3
                })
            # Sort by engagement
            results.sort(key=lambda x: x["engagement"], reverse=True)
            return results
        else:
            print(f"[Twitter] API error {resp.status_code}: {resp.text[:200]}")
            return []
    except Exception as e:
        print(f"[Twitter] Error: {e}")
        return []

def collect_twitter_intelligence(tokens: list) -> dict:
    """Collect Twitter intelligence for token list + general memecoin trends."""
    results = {}
    
    # General memecoin sentiment
    general_queries = [
        "memecoin 100x",
        "new memecoin launch solana",
        "memecoin gem ethereum",
        "BSC memecoin pump",
    ]
    
    general_tweets = []
    for q in general_queries[:2]:  # Limit API calls
        tweets = search_twitter_memecoin(q)
        general_tweets.extend(tweets)
        time.sleep(1)
    
    results["general_sentiment"] = general_tweets[:15]
    
    # Per-token Twitter search
    token_intel = {}
    for token in tokens[:5]:  # Top 5 tokens
        symbol = token.get("symbol", "")
        if not symbol or len(symbol) < 2:
            continue
        tweets = search_twitter_memecoin(f"${symbol} memecoin")
        token_intel[symbol] = {
            "tweets": tweets[:5],
            "total_engagement": sum(t.get("engagement", 0) for t in tweets),
            "tweet_count": len(tweets)
        }
        time.sleep(1.5)
    
    results["token_intel"] = token_intel
    return results

# ─── NEWS / OPENNEWS-MCP ────────────────────────────────────────────────────────

def search_news_memecoin(query: str) -> list:
    """Search news for memecoin via NewsAPI."""
    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "language": "en",
            "sortBy": "publishedAt",
            "pageSize": 10,
            "apiKey": NEWS_API_KEY
        }
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        
        articles = []
        for article in data.get("articles", []):
            articles.append({
                "title": article.get("title", ""),
                "description": article.get("description", ""),
                "source": article.get("source", {}).get("name", ""),
                "url": article.get("url", ""),
                "published_at": article.get("publishedAt", "")
            })
        return articles
    except Exception as e:
        print(f"[News] Error: {e}")
        return []

def collect_news_intelligence() -> dict:
    """Collect news intelligence for memecoins."""
    queries = [
        "memecoin cryptocurrency",
        "solana memecoin",
        "new crypto token launch"
    ]
    
    all_articles = []
    for q in queries:
        articles = search_news_memecoin(q)
        all_articles.extend(articles)
        time.sleep(0.5)
    
    # Deduplicate by title
    seen = set()
    unique_articles = []
    for a in all_articles:
        if a["title"] not in seen:
            seen.add(a["title"])
            unique_articles.append(a)
    
    return {
        "articles": unique_articles[:20],
        "total_count": len(unique_articles)
    }

# ─── OKX API ───────────────────────────────────────────────────────────────────

def okx_sign(timestamp: str, method: str, path: str, body: str = "") -> str:
    """Generate OKX API signature."""
    message = timestamp + method + path + body
    mac = hmac.new(OKX_SECRET.encode(), message.encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()

def okx_headers(method: str, path: str, body: str = "") -> dict:
    """Generate OKX API headers."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    sig = okx_sign(timestamp, method, path, body)
    return {
        "OK-ACCESS-KEY": OKX_API_KEY,
        "OK-ACCESS-SIGN": sig,
        "OK-ACCESS-TIMESTAMP": timestamp,
        "OK-ACCESS-PASSPHRASE": OKX_PASSPHRASE,
        "Content-Type": "application/json"
    }

def fetch_okx_smart_money() -> dict:
    """Fetch OKX on-chain smart money signals."""
    try:
        base_url = "https://www.okx.com"
        
        # Try OKX DEX market data - public endpoint
        path = "/api/v5/market/tickers?instType=SPOT"
        resp = requests.get(f"{base_url}{path}", timeout=15)
        
        if resp.status_code == 200:
            data = resp.json()
            tickers = data.get("data", [])
            
            # Find high-volume small cap tokens (potential smart money targets)
            interesting = []
            for t in tickers:
                try:
                    vol = float(t.get("volCcy24h", 0))
                    last = float(t.get("last", 0))
                    change = float(t.get("sodUtc8", 0)) if t.get("sodUtc8") else 0
                    inst_id = t.get("instId", "")
                    
                    # Filter: USDT pairs, high % change
                    if (inst_id.endswith("-USDT") and 
                        last < 0.01 and  # Low price = potential memecoin
                        vol > 100000 and  # Decent volume
                        abs(change) > 10):  # Significant price movement
                        interesting.append({
                            "symbol": inst_id.replace("-USDT", ""),
                            "price": last,
                            "volume_24h": vol,
                            "price_change": change,
                            "exchange": "OKX"
                        })
                except:
                    pass
            
            # Sort by absolute price change
            interesting.sort(key=lambda x: abs(x.get("price_change", 0)), reverse=True)
            return {
                "smart_money_signals": interesting[:10],
                "source": "okx_market"
            }
        else:
            print(f"[OKX] Error {resp.status_code}")
            return {"smart_money_signals": [], "source": "okx_market"}
    except Exception as e:
        print(f"[OKX] Error: {e}")
        return {"smart_money_signals": [], "source": "okx_market"}

# ─── AI ANALYSIS ───────────────────────────────────────────────────────────────

def generate_ai_report(all_data: dict) -> str:
    """Generate AI analysis report using OpenRouter."""
    try:
        # Prepare summary for AI
        tokens_summary = json.dumps(all_data.get("tokens", [])[:8], indent=2, ensure_ascii=False)
        twitter_summary = json.dumps(all_data.get("twitter", {}).get("general_sentiment", [])[:5], indent=2, ensure_ascii=False)
        news_summary = json.dumps(all_data.get("news", {}).get("articles", [])[:5], indent=2, ensure_ascii=False)
        okx_summary = json.dumps(all_data.get("okx", {}).get("smart_money_signals", [])[:5], indent=2, ensure_ascii=False)
        
        prompt = f"""You are a professional cryptocurrency memecoin analyst. Based on the following real-time data, generate a comprehensive intelligence report in Chinese.

## Chain Data (DexScreener)
{tokens_summary}

## Twitter Intelligence
{twitter_summary}

## News Intelligence
{news_summary}

## OKX Smart Money Signals
{okx_summary}

Generate a report in Chinese with the following sections:
1. 🔥 **市场总览** - Overall market sentiment (2-3 sentences)
2. 🚀 **热门代币分析** - Top 3-5 tokens worth watching with reasons
3. 📱 **社区热度** - Twitter & social sentiment analysis
4. 📰 **新闻动态** - Key news affecting memecoins
5. 🐋 **聪明钱信号** - Smart money/whale movements detected
6. ⚠️ **风险提示** - Key risks to watch
7. 🎯 **操作建议** - Actionable insights (NOT financial advice, educational only)

Format with clear headers, emojis, and be specific about tokens and data points. Keep it concise but data-driven."""

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://zhangyizyzyzy.github.io/memecoin-reports/",
        }
        
        payload = {
            "model": "anthropic/claude-3.5-sonnet",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000,
            "temperature": 0.7
        }
        
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=60
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[AI] Error generating report: {e}")
        return f"⚠️ AI分析生成失败: {str(e)}\n\n请检查OpenRouter API配置。"

# ─── MAIN COLLECTION PIPELINE ──────────────────────────────────────────────────

def collect_all_chain_tokens() -> list:
    """Collect trending tokens across all chains."""
    all_tokens = []
    
    for chain in CHAINS:
        print(f"[DEX] Fetching trending tokens for {chain}...")
        
        # Get trending/boosted tokens
        boosted = fetch_dexscreener_trending(chain)
        
        # Get details for boosted tokens
        for token_stub in boosted[:5]:
            addr = token_stub.get("address", "")
            if addr:
                detail = fetch_dexscreener_token_detail(addr, chain)
                if detail and detail.get("volume_24h", 0) > 1000:
                    all_tokens.append(detail)
                time.sleep(0.5)
        
        # Get new pairs
        print(f"[DEX] Fetching new pairs for {chain}...")
        new_pairs = fetch_dexscreener_new_pairs(chain)
        all_tokens.extend(new_pairs)
        
        time.sleep(1)
    
    # Sort by volume
    all_tokens.sort(key=lambda x: float(x.get("volume_24h", 0)), reverse=True)
    
    # Deduplicate by address
    seen = set()
    unique_tokens = []
    for t in all_tokens:
        addr = t.get("address", "")
        if addr and addr not in seen:
            seen.add(addr)
            unique_tokens.append(t)
    
    return unique_tokens[:30]

def run_collection():
    """Main collection pipeline."""
    print(f"\n{'='*60}")
    print(f"🚀 Memecoin Intelligence Collector")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*60}\n")
    
    timestamp = datetime.now(timezone.utc).isoformat()
    report_data = {
        "timestamp": timestamp,
        "tokens": [],
        "twitter": {},
        "news": {},
        "okx": {},
        "ai_report": ""
    }
    
    # 1. Collect chain tokens
    print("📊 Step 1/5: Collecting chain data from DexScreener...")
    tokens = collect_all_chain_tokens()
    report_data["tokens"] = tokens
    print(f"  ✅ Found {len(tokens)} tokens across {len(CHAINS)} chains")
    
    # 2. Twitter intelligence
    print("\n🐦 Step 2/5: Collecting Twitter intelligence...")
    if TWITTER_BEARER_TOKEN:
        twitter_data = collect_twitter_intelligence(tokens)
        report_data["twitter"] = twitter_data
        tweet_count = len(twitter_data.get("general_sentiment", []))
        print(f"  ✅ Collected {tweet_count} relevant tweets")
    else:
        print("  ⚠️ Twitter token not configured, skipping")
    
    # 3. News intelligence
    print("\n📰 Step 3/5: Collecting news intelligence...")
    if NEWS_API_KEY:
        news_data = collect_news_intelligence()
        report_data["news"] = news_data
        print(f"  ✅ Collected {news_data.get('total_count', 0)} news articles")
    else:
        print("  ⚠️ News API key not configured, skipping")
    
    # 4. OKX smart money
    print("\n🐋 Step 4/5: Fetching OKX smart money signals...")
    if OKX_API_KEY:
        okx_data = fetch_okx_smart_money()
        report_data["okx"] = okx_data
        print(f"  ✅ Found {len(okx_data.get('smart_money_signals', []))} smart money signals")
    else:
        print("  ⚠️ OKX API not configured, skipping")
    
    # 5. Generate AI report
    print("\n🤖 Step 5/5: Generating AI analysis report...")
    if OPENROUTER_API_KEY:
        ai_report = generate_ai_report(report_data)
        report_data["ai_report"] = ai_report
        print(f"  ✅ AI report generated ({len(ai_report)} chars)")
    else:
        print("  ⚠️ OpenRouter API key not configured, skipping AI analysis")
    
    # Save data
    save_report(report_data)
    
    print(f"\n{'='*60}")
    print(f"✅ Collection complete!")
    print(f"{'='*60}\n")
    
    return report_data

def save_report(data: dict):
    """Save report data to docs directory for GitHub Pages."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now(timezone.utc)
    
    # Save latest report
    latest_path = DATA_DIR / "latest.json"
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n💾 Saved: {latest_path}")
    
    # Save timestamped archive
    archive_name = timestamp.strftime("%Y%m%d_%H%M%S") + ".json"
    archive_path = DATA_DIR / "archive" / archive_name
    archive_path.parent.mkdir(exist_ok=True)
    with open(archive_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # Update reports index
    index_path = DATA_DIR / "index.json"
    try:
        with open(index_path) as f:
            index = json.load(f)
    except:
        index = {"reports": []}
    
    index["reports"].insert(0, {
        "filename": archive_name,
        "timestamp": data["timestamp"],
        "token_count": len(data.get("tokens", [])),
    })
    index["reports"] = index["reports"][:48]  # Keep last 48 reports (2 days)
    index["last_updated"] = data["timestamp"]
    
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    
    print(f"💾 Archive saved: {archive_path}")

if __name__ == "__main__":
    run_collection()
