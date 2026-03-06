#!/usr/bin/env python3
"""
Memecoin Intelligence Collector v3
热门币数据源:
  - Binance Skills Hub: meme-rush (新发/迁移 meme 榜) + crypto-market-rank (聪明钱/社交热度)
  - OKX OnchainOS: Token Ranking API (链上热度榜)
  - DexScreener: 补充安全验证 (流动性/买卖压)
  - Twitter / NewsAPI: 社区 & 新闻情报
  - OpenRouter AI: 综合分析报告
"""

import os, json, time, hmac, hashlib, base64, requests
from datetime import datetime, timezone
from pathlib import Path

# ─── 环境变量 ──────────────────────────────────────────────────────────────────
OPENROUTER_API_KEY   = os.environ.get("OPENROUTER_API_KEY", "")
TWITTER_BEARER_TOKEN = os.environ.get("TWITTER_BEARER_TOKEN", "")
NEWS_API_KEY         = os.environ.get("NEWS_API_KEY", "")
OKX_API_KEY          = os.environ.get("OKX_API_KEY", "")
OKX_SECRET           = os.environ.get("OKX_SECRET", "")
OKX_PASSPHRASE       = os.environ.get("OKX_PASSPHRASE", "")

DOCS_DIR = Path(__file__).parent.parent / "docs"
DATA_DIR = DOCS_DIR / "data"

WEB3_HEADERS = {
    "Accept-Encoding": "identity",
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0",
}

# ══════════════════════════════════════════════════════════════════════════════
# BINANCE SKILLS HUB — meme-rush skill
# Ref: github.com/binance/binance-skills-hub/skills/binance-web3/meme-rush
# ══════════════════════════════════════════════════════════════════════════════

MEME_RUSH_URL  = "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/market/token/pulse/rank/list"
TOPIC_RUSH_URL = "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/market/token/social-rush/rank/list"

def fetch_meme_rush(chain_id: str, rank_type: int, limit: int = 30) -> list:
    """
    Binance meme-rush 发射台代币榜
    rank_type: 10=新建, 20=即将毕业(bonding curve快满), 30=已迁移到DEX
    chain_id:  "56"=BSC, "CT_501"=Solana
    """
    chain_name = {"56": "bsc", "CT_501": "solana"}.get(chain_id, chain_id)
    stage_name = {10: "新建", 20: "即将毕业", 30: "已迁移"}.get(rank_type, "")
    try:
        payload = {
            "chainId": chain_id,
            "rankType": rank_type,
            "limit": limit,
            "liquidityMin": "1000",       # 过滤零流动性垃圾
            "excludeDevWashTrading": 1,   # 排除dev洗盘
        }
        resp = requests.post(MEME_RUSH_URL, json=payload, headers=WEB3_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "000000":
            print(f"  [MemeRush] API error: {data.get('message','')}")
            return []

        tokens = (data.get("data") or {}).get("tokens", [])
        results = []
        for t in tokens:
            buy   = int(t.get("countBuy",  0) or 0)
            sell  = int(t.get("countSell", 0) or 0)
            total = buy + sell
            results.append({
                "symbol":            t.get("symbol", ""),
                "name":              t.get("name", ""),
                "address":           t.get("contractAddress", ""),
                "chain":             chain_name,
                "price_usd":         t.get("price", "0"),
                "price_change_24h":  float(t.get("priceChange", 0) or 0),
                "market_cap":        float(t.get("marketCap", 0) or 0),
                "liquidity_usd":     float(t.get("liquidity", 0) or 0),
                "volume_24h":        float(t.get("volume", 0) or 0),
                "holders":           int(t.get("holders", 0) or 0),
                "buys_24h":          buy,
                "sells_24h":         sell,
                "buy_pct":           round(buy / total * 100, 1) if total else 0,
                "bonding_progress":  t.get("progress", ""),
                "stage":             stage_name,
                "dev_sell_pct":      t.get("devSellPercent", "0"),
                "top10_holder_pct":  t.get("holdersTop10Percent", ""),
                "kol_holders":       int(t.get("kolHolders", 0) or 0),
                "narrative_cn":      (t.get("narrativeText") or {}).get("cn", ""),
                "has_twitter":       "twitter" in str(t.get("socials", {})),
                "risk_dev_wash":     bool(t.get("tagDevWashTrading")),
                "risk_insider_wash": bool(t.get("tagInsiderWashTrading")),
                "source":            f"binance_meme_rush_r{rank_type}",
            })
        return results
    except Exception as e:
        print(f"  [MemeRush] chain={chain_id} rank={rank_type} error: {e}")
        return []


def fetch_topic_rush(chain_id: str, rank_type: int = 30) -> list:
    """
    Binance topic-rush: AI 生成的热门叙事话题 + 关联代币净流入
    rank_type=30 (Viral, 净流入最高)
    """
    chain_name = {"56": "bsc", "CT_501": "solana"}.get(chain_id, chain_id)
    try:
        params = {"chainId": chain_id, "rankType": rank_type, "sort": 30, "asc": "false"}
        resp = requests.get(TOPIC_RUSH_URL, params=params, headers=WEB3_HEADERS, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "000000":
            return []

        results = []
        for topic in (data.get("data") or [])[:10]:
            topic_name = ((topic.get("name") or {}).get("topicNameCn") or
                          (topic.get("name") or {}).get("topicNameEn", ""))
            for token in (topic.get("tokenList") or [])[:3]:
                results.append({
                    "symbol":           token.get("symbol", ""),
                    "address":          token.get("contractAddress", ""),
                    "chain":            chain_name,
                    "price_change_24h": float(str(token.get("priceChange24h","0")).replace("%","") or 0),
                    "market_cap":       float(token.get("marketCap", 0) or 0),
                    "liquidity_usd":    float(token.get("liquidity", 0) or 0),
                    "net_inflow_1h":    float(token.get("netInflow1h", 0) or 0),
                    "net_inflow_total": float(token.get("netInflow", 0) or 0),
                    "kol_holders":      int(token.get("kolHolders", 0) or 0),
                    "smart_money_holders": int(token.get("smartMoneyHolders", 0) or 0),
                    "holders":          int(token.get("holders", 0) or 0),
                    "topic_name":       topic_name,
                    "topic_inflow_1h":  topic.get("topicNetInflow1h", "0"),
                    "source":           "binance_topic_rush",
                })
        return results
    except Exception as e:
        print(f"  [TopicRush] chain={chain_id} error: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# BINANCE SKILLS HUB — crypto-market-rank skill
# Ref: github.com/binance/binance-skills-hub/skills/binance-web3/crypto-market-rank
# ══════════════════════════════════════════════════════════════════════════════

UNIFIED_RANK_URL = "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/market/token/pulse/unified/rank/list"
SMART_MONEY_URL  = "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/tracker/wallet/token/inflow/rank/query"
SOCIAL_HYPE_URL  = "https://web3.binance.com/bapi/defi/v1/public/wallet-direct/buw/wallet/market/token/pulse/social/hype/rank/leaderboard"

CHAIN_NAME = {"1": "ethereum", "56": "bsc", "8453": "base", "CT_501": "solana"}

def fetch_unified_rank(chain_id: str) -> list:
    """Binance 综合排行榜 — 交易量/流动性/社区综合评分 Top20"""
    try:
        payload = {
            "rankType": 10, "chainId": chain_id,
            "period": 50, "sortBy": 70,
            "orderAsc": False, "page": 1, "size": 20,
        }
        resp = requests.post(UNIFIED_RANK_URL, json=payload, headers=WEB3_HEADERS, timeout=15)
        data = resp.json()
        if data.get("code") != "000000":
            return []
        results = []
        for t in ((data.get("data") or {}).get("tokens") or []):
            results.append({
                "symbol":           t.get("symbol", ""),
                "name":             t.get("name", ""),
                "address":          t.get("contractAddress", ""),
                "chain":            CHAIN_NAME.get(chain_id, chain_id),
                "price_usd":        t.get("price", "0"),
                "price_change_24h": float(t.get("priceChange24h", 0) or 0),
                "price_change_1h":  float(t.get("priceChange1h", 0) or 0),
                "market_cap":       float(t.get("marketCap", 0) or 0),
                "liquidity_usd":    float(t.get("liquidity", 0) or 0),
                "volume_24h":       float(t.get("volume24h", 0) or 0),
                "holders":          int(t.get("holders", 0) or 0),
                "source":           "binance_unified_rank",
            })
        return results
    except Exception as e:
        print(f"  [UnifiedRank] chain={chain_id} error: {e}")
        return []


def fetch_smart_money_inflow(chain_id: str) -> list:
    """Binance 聪明钱流入排名 — tagType=2 (smart money)"""
    try:
        resp = requests.post(
            SMART_MONEY_URL,
            json={"chainId": chain_id, "period": "24h", "tagType": 2},
            headers=WEB3_HEADERS, timeout=15
        )
        data = resp.json()
        if data.get("code") != "000000":
            return []
        results = []
        for t in (data.get("data") or [])[:15]:
            results.append({
                "symbol":                  t.get("symbol", ""),
                "address":                 t.get("contractAddress", ""),
                "chain":                   CHAIN_NAME.get(chain_id, chain_id),
                "smart_money_inflow_24h":  float(t.get("netInflow", 0) or 0),
                "smart_money_buyers":      int(t.get("buyerCount", 0) or 0),
                "price_change_24h":        float(t.get("priceChange24h", 0) or 0),
                "source":                  "binance_smart_money",
            })
        return results
    except Exception as e:
        print(f"  [SmartMoney] chain={chain_id} error: {e}")
        return []


def fetch_social_hype(chain_id: str) -> list:
    """Binance 社交热度排行 — KOL/社区情绪 1小时维度"""
    try:
        resp = requests.get(
            SOCIAL_HYPE_URL,
            params={"chainId": chain_id, "sentiment": "All",
                    "socialLanguage": "ALL", "targetLanguage": "en", "timeRange": 1},
            headers=WEB3_HEADERS, timeout=15
        )
        data = resp.json()
        if data.get("code") != "000000":
            return []
        results = []
        for t in ((data.get("data") or {}).get("leaderboard") or [])[:15]:
            results.append({
                "symbol":        t.get("symbol", ""),
                "address":       t.get("contractAddress", ""),
                "chain":         CHAIN_NAME.get(chain_id, chain_id),
                "social_score":  float(t.get("hypeScore", 0) or 0),
                "sentiment":     t.get("sentiment", ""),
                "mention_count": int(t.get("mentionCount", 0) or 0),
                "source":        "binance_social_hype",
            })
        return results
    except Exception as e:
        print(f"  [SocialHype] chain={chain_id} error: {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
# OKX OnchainOS — Token Ranking + Price Info
# Ref: web3.okx.com/onchainos/dev-docs/market/market-token-reference
# ══════════════════════════════════════════════════════════════════════════════

OKX_CHAIN_INDEX = {"ethereum": "1", "bsc": "56", "base": "8453", "solana": "501"}

def _okx_sign(ts, method, path, body=""):
    msg = ts + method + path + body
    return base64.b64encode(hmac.new(OKX_SECRET.encode(), msg.encode(), hashlib.sha256).digest()).decode()

def _okx_headers(method, path, body=""):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    return {
        "OK-ACCESS-KEY": OKX_API_KEY,
        "OK-ACCESS-SIGN": _okx_sign(ts, method, path, body),
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": OKX_PASSPHRASE,
        "Content-Type": "application/json",
    }

def fetch_okx_token_ranking(chain: str) -> list:
    """OKX OnchainOS 链上代币排行榜"""
    chain_index = OKX_CHAIN_INDEX.get(chain, "1")
    path = f"/api/v6/dex/market/token/ranking-list?chainIndex={chain_index}&limit=20&page=1"
    try:
        resp = requests.get(f"https://www.okx.com{path}", headers=_okx_headers("GET", path), timeout=15)
        data = resp.json()
        if data.get("code") != "0":
            print(f"  [OKX Ranking] {chain}: {data.get('msg','')}")
            return []
        results = []
        for t in ((data.get("data") or {}).get("tokenList") or []):
            results.append({
                "symbol":           t.get("symbol", ""),
                "name":             t.get("tokenName", ""),
                "address":          t.get("tokenContractAddress", ""),
                "chain":            chain,
                "price_usd":        t.get("price", "0"),
                "price_change_24h": float(t.get("priceChange24h", 0) or 0),
                "price_change_1h":  float(t.get("priceChange1h", 0) or 0),
                "market_cap":       float(t.get("marketCap", 0) or 0),
                "liquidity_usd":    float(t.get("liquidity", 0) or 0),
                "volume_24h":       float(t.get("volume24h", 0) or 0),
                "holders":          int(t.get("holderCount", 0) or 0),
                "source":           "okx_onchainos_ranking",
            })
        return results
    except Exception as e:
        print(f"  [OKX Ranking] {chain} error: {e}")
        return []


def fetch_okx_price_info(tokens: list) -> dict:
    """OKX 批量价格详情: 5m/1h/4h/24h 变化 + 交易笔数"""
    if not tokens or not OKX_API_KEY:
        return {}
    path = "/api/v6/dex/market/price-info"
    by_chain: dict[str, list] = {}
    for t in tokens:
        ci   = OKX_CHAIN_INDEX.get(t.get("chain",""), "1")
        addr = t.get("address","")
        if addr:
            by_chain.setdefault(ci, []).append(addr)
    enriched = {}
    for ci, addrs in by_chain.items():
        for i in range(0, min(len(addrs), 100), 50):
            batch = addrs[i:i+50]
            body  = json.dumps({"chainIndex": ci, "tokenContractAddresses": batch})
            try:
                resp = requests.post(f"https://www.okx.com{path}", data=body,
                                     headers=_okx_headers("POST", path, body), timeout=15)
                d = resp.json()
                if d.get("code") == "0":
                    for item in (d.get("data") or []):
                        addr_key = (item.get("tokenContractAddress","")).lower()
                        enriched[addr_key] = {
                            "price_change_5m":  float(item.get("priceChange5m", 0) or 0),
                            "price_change_1h":  float(item.get("priceChange1h", 0) or 0),
                            "price_change_4h":  float(item.get("priceChange4h", 0) or 0),
                            "price_change_24h": float(item.get("priceChange24h", 0) or 0),
                            "volume_24h":       float(item.get("volume24h", 0) or 0),
                            "tx_count_24h":     int(item.get("txCount24h", 0) or 0),
                            "liquidity_usd":    float(item.get("liquidity", 0) or 0),
                            "holders":          int(item.get("holderCount", 0) or 0),
                        }
            except Exception as e:
                print(f"  [OKX PriceInfo] error: {e}")
            time.sleep(0.3)
    return enriched


# ══════════════════════════════════════════════════════════════════════════════
# DexScreener — 安全验证层
# ══════════════════════════════════════════════════════════════════════════════

def dex_verify(symbol: str) -> dict:
    try:
        resp = requests.get(f"https://api.dexscreener.com/latest/dex/search?q={symbol}", timeout=12)
        pairs = resp.json().get("pairs", [])
        if not pairs:
            return {}
        pairs.sort(key=lambda p: float((p.get("liquidity") or {}).get("usd", 0)), reverse=True)
        best  = pairs[0]
        txns  = best.get("txns", {}).get("h24", {})
        buys  = int(txns.get("buys", 0))
        sells = int(txns.get("sells", 0))
        total = buys + sells
        liq   = float((best.get("liquidity") or {}).get("usd", 0))
        mcap  = float(best.get("marketCap") or 0)
        return {
            "dex_url":       best.get("url", ""),
            "liquidity_usd": liq,
            "buy_pct":       round(buys / total * 100, 1) if total else 0,
            "liq_ratio":     round(mcap / liq, 1) if liq else 999,
        }
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# 综合评分 (100分制)
# ══════════════════════════════════════════════════════════════════════════════

def compute_score(t: dict) -> float:
    score = 0.0
    ch1h  = float(t.get("price_change_1h", 0) or 0)
    ch24h = float(t.get("price_change_24h", 0) or 0)
    vol   = float(t.get("volume_24h", 0) or 0)
    liq   = float(t.get("liquidity_usd", 0) or 0)

    # 1. 价格动能 (35分)
    score += min(ch1h / 15 * 20, 20) if ch1h > 0 else 0
    score += min(ch24h / 80 * 15, 15) if ch24h > 0 else max(ch24h / 40 * 5, -8)

    # 2. 成交量 (20分)
    if   vol >= 5_000_000: score += 20
    elif vol >= 1_000_000: score += 15
    elif vol >= 200_000:   score += 10
    elif vol >= 50_000:    score += 5

    # 3. 买压 (15分)
    bp = float(t.get("buy_pct", 50) or 50)
    if   bp >= 70: score += 15
    elif bp >= 60: score += 10
    elif bp >= 50: score += 5
    elif bp < 35:  score -= 10

    # 4. 净流入信号 (15分)
    inflow_1h = float(t.get("net_inflow_1h", 0) or 0)
    sm_inflow = float(t.get("smart_money_inflow_24h", 0) or 0)
    if inflow_1h > 50_000:   score += 10
    elif inflow_1h > 10_000: score += 5
    if sm_inflow > 20_000:   score += 5

    # 5. 聪明钱/KOL持仓 (10分)
    kol = int(t.get("kol_holders", 0) or 0)
    sm  = int(t.get("smart_money_holders", 0) or 0)
    if kol + sm >= 5:  score += 10
    elif kol + sm >= 2: score += 5

    # 6. 社交热度 (5分)
    if t.get("social_score") or t.get("mention_count"):
        score += 5

    # 加分: 多信号源交叉验证
    nsrc = len(set(t.get("sources", [])))
    score += 8 if nsrc >= 3 else (4 if nsrc >= 2 else 0)

    # 加分: 已迁移到DEX (更成熟)
    if t.get("stage") == "已迁移":
        score += 5

    # 风险扣分
    if liq < 10_000:              score -= 25
    elif liq < 50_000:            score -= 10
    liq_ratio = float(t.get("liq_ratio", 10) or 10)
    if liq_ratio > 100:           score -= 15
    if t.get("risk_dev_wash"):    score -= 10
    if t.get("risk_insider_wash"): score -= 8

    return round(max(score, 0), 1)


def score_label(s: float) -> str:
    if s >= 70: return "🔥🔥🔥 极热"
    if s >= 50: return "🔥🔥 热门"
    if s >= 30: return "🔥 关注"
    return "❄️ 冷淡"


# ══════════════════════════════════════════════════════════════════════════════
# 主数据整合流水线
# ══════════════════════════════════════════════════════════════════════════════

def collect_all_tokens() -> list:
    # ── Binance meme-rush ────────────────────────────────────────────────────
    print("\n  [1/4] Binance meme-rush...")
    raw = []
    for chain_id, label in [("CT_501","SOL"), ("56","BSC")]:
        for rank_type, stage in [(10,"新建"),(30,"迁移")]:
            r = fetch_meme_rush(chain_id, rank_type, 25)
            raw += r
            print(f"    {label} {stage}: {len(r)}")
            time.sleep(0.3)

    # ── Binance market-rank ──────────────────────────────────────────────────
    print("  [2/4] Binance market-rank...")
    for cid in ["1","56","8453","CT_501"]:
        r = fetch_unified_rank(cid)
        raw += r
        time.sleep(0.2)
    for cid in ["CT_501","56"]:
        raw += fetch_smart_money_inflow(cid)
        raw += fetch_social_hype(cid)
        raw += fetch_topic_rush(cid, 30)
        time.sleep(0.3)
    print(f"    合计 market-rank 数据: {len(raw)} 条")

    # ── OKX OnchainOS ────────────────────────────────────────────────────────
    print("  [3/4] OKX OnchainOS ranking...")
    if OKX_API_KEY:
        for chain in ["solana","ethereum","bsc","base"]:
            r = fetch_okx_token_ranking(chain)
            raw += r
            print(f"    OKX {chain}: {len(r)}")
            time.sleep(0.3)
    else:
        print("    ⚠️ OKX_API_KEY 未配置，跳过")

    # ── 合并去重 ─────────────────────────────────────────────────────────────
    merged: dict[str, dict] = {}
    for t in raw:
        sym = (t.get("symbol") or "").upper().strip()
        if not sym or len(sym) < 2 or len(sym) > 12:
            continue
        if sym not in merged:
            merged[sym] = {**t, "sources": [t.get("source","")]}
        else:
            e = merged[sym]
            e["sources"].append(t.get("source",""))
            for f in ["volume_24h","liquidity_usd","holders","kol_holders",
                      "smart_money_holders","net_inflow_1h","smart_money_inflow_24h",
                      "social_score","mention_count"]:
                if float(t.get(f,0) or 0) > float(e.get(f,0) or 0):
                    e[f] = t[f]
            for f in ["price_usd","price_change_1h","price_change_24h","market_cap",
                      "buy_pct","stage","narrative_cn","topic_name","dex_url","address","chain"]:
                if not e.get(f) and t.get(f):
                    e[f] = t[f]

    # ── OKX 批量价格补充 ─────────────────────────────────────────────────────
    if OKX_API_KEY:
        print("  [3b] OKX price-info 补充...")
        price_map = fetch_okx_price_info(list(merged.values()))
        for sym, entry in merged.items():
            key = (entry.get("address") or "").lower()
            if key in price_map:
                for k, v in price_map[key].items():
                    if not entry.get(k):
                        entry[k] = v

    # ── 评分 ─────────────────────────────────────────────────────────────────
    candidates = []
    for sym, entry in merged.items():
        entry["sources"]     = list(set(entry.get("sources",[])))
        entry["score"]       = compute_score(entry)
        entry["score_label"] = score_label(entry["score"])
        candidates.append(entry)
    candidates.sort(key=lambda x: x["score"], reverse=True)
    print(f"\n  合并去重: {len(candidates)} 个候选币")

    # ── DexScreener 安全验证 Top20 ───────────────────────────────────────────
    print("  [4/4] DexScreener 安全验证 Top20...")
    final = []
    for token in candidates[:20]:
        sym = token.get("symbol","")
        if sym:
            dex = dex_verify(sym)
            if dex:
                for k,v in dex.items():
                    if not token.get(k):
                        token[k] = v
                liq = float(dex.get("liquidity_usd",0))
                bp  = float(dex.get("buy_pct",50))
                if liq < 10_000: token["score"] = max(token["score"] - 25, 0)
                if bp >= 65:     token["score"] = min(token["score"] + 8, 100)
                elif bp < 35:    token["score"] = max(token["score"] - 8, 0)
                token["score_label"] = score_label(token["score"])
            time.sleep(0.4)
        final.append(token)

    final.sort(key=lambda x: x["score"], reverse=True)
    return final + candidates[20:30]


# ══════════════════════════════════════════════════════════════════════════════
# Twitter
# ══════════════════════════════════════════════════════════════════════════════

def search_twitter(query: str) -> list:
    try:
        resp = requests.post(
            "https://ai.6551.io/open/twitter_search",
            headers={"Authorization": f"Bearer {TWITTER_BEARER_TOKEN}"},
            json={"query": f"{query} -is:retweet lang:en", "max_results": 15},
            timeout=30
        )
        if resp.status_code != 200:
            return []
        data = resp.json().get("data", [])
        if isinstance(data, str):
            try: data = json.loads(data)
            except: data = []
        if isinstance(data, dict):
            # Sometimes data comes wrapped in another object structure
            if "data" in data and isinstance(data["data"], list):
                # Try to map inner data with includes/users if MCP mimics raw API
                users = {u["id"]: u for u in data.get("includes",{}).get("users",[])}
                out = []
                for tw in data.get("data",[]):
                    m = tw.get("public_metrics",{})
                    au = users.get(tw.get("author_id",""),{})
                    out.append({
                        "text": tw.get("text",""),
                        "likes": m.get("like_count",0),
                        "retweets": m.get("retweet_count",0),
                        "author": au.get("username", tw.get("author_id", "unknown")),
                        "author_followers": au.get("public_metrics",{}).get("followers_count",0),
                        "engagement": m.get("like_count",0) + m.get("retweet_count",0) * 3,
                    })
                return sorted(out, key=lambda x: x["engagement"], reverse=True)
            return []

        if not isinstance(data, list):
            return []
            
        out = []
        for tw in data:
            if isinstance(tw, dict):
                likes = tw.get("likes", tw.get("like_count", 0))
                retweets = tw.get("retweets", tw.get("retweet_count", 0))
                out.append({
                    "text":             tw.get("text",""),
                    "likes":            likes,
                    "retweets":         retweets,
                    "author":           tw.get("author","unknown"),
                    "author_followers": tw.get("author_followers", 0),
                    "engagement":       likes + retweets * 3,
                })
        return sorted(out, key=lambda x: x["engagement"], reverse=True)
    except Exception as e:
        print(f"  [Twitter MCP] {e}")
        return []

def collect_twitter_intel(tokens: list) -> dict:
    general = []
    for q in ["memecoin 100x solana", "new memecoin launch"]:
        general += search_twitter(q); time.sleep(1.2)
    token_intel = {}
    for t in tokens[:5]:
        sym = t.get("symbol","")
        if not sym: continue
        tweets = search_twitter(f"${sym} crypto")
        token_intel[sym] = {"tweets": tweets[:4],
                             "total_engagement": sum(tw["engagement"] for tw in tweets)}
        time.sleep(1.5)
    return {"general_sentiment": general[:12], "token_intel": token_intel}


# ══════════════════════════════════════════════════════════════════════════════
# News
# ══════════════════════════════════════════════════════════════════════════════

def search_news(query: str) -> list:
    try:
        resp = requests.post(
            "https://ai.6551.io/open/news_search",
            headers={"Authorization": f"Bearer {NEWS_API_KEY}"},
            json={"query": query},
            timeout=30
        )
        if resp.status_code != 200:
            return []
        
        data = resp.json().get("data", [])
        if isinstance(data, str):
            try: data = json.loads(data)
            except: data = []
        if isinstance(data, dict):
            data = data.get("articles", [])
        if not isinstance(data, list):
            return []
            
        articles = []
        for a in data:
            if isinstance(a, dict):
                src = a.get("source", {})
                if isinstance(src, dict):
                    source_name = src.get("name", "Unknown")
                else:
                    source_name = str(src)
                articles.append({
                    "title": a.get("title", ""),
                    "source": source_name,
                    "url": a.get("url", ""),
                    "published_at": a.get("publishedAt", a.get("published_at", ""))
                })
        return articles
    except Exception as e:
        print(f"  [News MCP] {e}")
        return []

def collect_news_intel() -> dict:
    articles = []
    for q in ["memecoin cryptocurrency", "solana memecoin", "new crypto token launch"]:
        articles += search_news(q)
        time.sleep(0.5)
    seen, unique = set(), []
    for a in articles:
        if a["title"] not in seen:
            seen.add(a["title"]); unique.append(a)
    return {"articles": unique[:20], "total_count": len(unique)}


# ══════════════════════════════════════════════════════════════════════════════
# AI 报告
# ══════════════════════════════════════════════════════════════════════════════

def generate_token_ai_analysis(token: dict, twitter_tweets: list, news_articles: list) -> str:
    if not OPENROUTER_API_KEY:
        return ""

    try:
        ca_address = token.get("address", "")
        symbol = token.get("symbol", "")
        twitter_str = json.dumps(twitter_tweets[:8], indent=2, ensure_ascii=False)
        news_str = json.dumps(news_articles[:5], indent=2, ensure_ascii=False)
        
        prompt = f"""以下是通过 6551 MCP 底座搜集到的针对 CA: [{ca_address}] ({symbol}) 的全网推特和媒体新闻原始数据：

【Twitter 讨论流】
{twitter_str}

【加密媒体通稿】
{news_str}

----------------------------------------

⚠️ 防幻觉铁律（最高优先级）：
1. 你只能基于上面传入的【Twitter 讨论流】和【加密媒体通稿】中的实际数据进行分析。
2. 如果某项数据为空或不足，你必须在对应的分析板块明确写出"数据不足，无法判断"。
3. 不要假装自己能独立访问链上数据或推特，信息来源仅限于上方数据。

执行如下指令分析：作为 6551 Memecoin 分析师，为中国受众深度解码 CA 的起源和叙事（尽量简练）。

输出格式：
1. 起源与硬核证据
2. 叙事深度剖析&文化破壁
3. 影响力地图
4. 风险预警

综合评分：叙事新鲜度 / 跨文化爆发力 / 叙事天花板
"""
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://zhangyizyzyzy.github.io/memecoin-analysis-bot/",
            },
            json={
                "model": "anthropic/claude-3.5-sonnet",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 800,
                "temperature": 0.5
            },
            timeout=120
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  [AI Token] Error for {symbol}: {e}")
        return ""

def generate_ai_report(data: dict) -> str:
    try:
        top = data.get("tokens",[])[:8]
        prompt = f"""你是专业的 Memecoin 链上情报分析师。基于以下实时数据生成简洁有力的中文情报报告。

## 热门代币 Top8
{json.dumps(top, indent=2, ensure_ascii=False)}

## Twitter 动态（前5条）
{json.dumps(data.get("twitter",{}).get("general_sentiment",[])[:5], indent=2, ensure_ascii=False)}

## 新闻（前5条）
{json.dumps(data.get("news",{}).get("articles",[])[:5], indent=2, ensure_ascii=False)}

报告结构（言简意赅，数字具体）：
1. 🔥 **市场总览** — 整体 memecoin 情绪
2. 🚀 **Top 热门币** — 评分最高3-5个：为什么上榜？
3. ⚡ **1小时异动** — 资金流入及价格信号
4. 🐋 **聪明钱动向** — smart_money_holders 等动向
5. 🎯 **热门叙事** — 当下的话题梗
6. ⚠️ **风险警告** — 异常点名
7. 💡 **操作思路** — 仅供参考"""

        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}",
                     "Content-Type": "application/json",
                     "HTTP-Referer": "https://zhangyizyzyzy.github.io/memecoin-analysis-bot/"},
            json={"model": "anthropic/claude-3.5-sonnet",
                  "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 1200},
            timeout=60
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"⚠️ AI报告生成失败: {e}"


# ══════════════════════════════════════════════════════════════════════════════
# 保存报告
# ══════════════════════════════════════════════════════════════════════════════

def save_report(data: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(DATA_DIR / "latest.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    ts  = datetime.now(timezone.utc)
    arc = DATA_DIR / "archive" / (ts.strftime("%Y%m%d_%H%M%S") + ".json")
    arc.parent.mkdir(exist_ok=True)
    with open(arc, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    idx_path = DATA_DIR / "index.json"
    try:    idx = json.loads(idx_path.read_text())
    except: idx = {"reports": []}
    idx["reports"].insert(0, {"filename": arc.name, "timestamp": data["timestamp"],
                               "token_count": len(data.get("tokens",[]))})
    idx["reports"]      = idx["reports"][:48]
    idx["last_updated"] = data["timestamp"]
    idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2))
    print(f"\n💾 Saved: latest.json + {arc.name}")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def run():
    print(f"\n{'='*65}")
    print(f"🚀 Memecoin Intelligence Collector v3")
    print(f"   数据源: Binance Skills Hub (meme-rush + market-rank)")
    print(f"           OKX OnchainOS | DexScreener | Twitter | News")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"{'='*65}\n")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tokens": [], "twitter": {}, "news": {}, "ai_report": "",
        "data_sources": {
            "binance_meme_rush":   True,
            "binance_market_rank": True,
            "okx_onchainos":       bool(OKX_API_KEY),
            "dexscreener":         True,
            "twitter":             bool(TWITTER_BEARER_TOKEN),
            "news":                bool(NEWS_API_KEY),
        }
    }

    print("📡 收集链上数据...")
    tokens = collect_all_tokens()
    report["tokens"] = tokens
    top1 = tokens[0].get("symbol","?") if tokens else "无"
    print(f"\n✅ 最终 {len(tokens)} 个候选币  Top1={top1} ({tokens[0].get('score',0) if tokens else 0}分)")

    if TWITTER_BEARER_TOKEN:
        print("\n🐦 Twitter 情报...")
        report["twitter"] = collect_twitter_intel(tokens)
        print(f"  ✅ {len(report['twitter'].get('general_sentiment',[]))} tweets")

    if NEWS_API_KEY:
        print("\n📰 新闻情报...")
        report["news"] = collect_news_intel()
        print(f"  ✅ {report['news']['total_count']} articles")

    if OPENROUTER_API_KEY:
        print("\n🤖 单币分析与总报告生成...")
        if TWITTER_BEARER_TOKEN:
            for t in tokens[:3]:
                sym = t.get("symbol", "")
                ca = t.get("address", "")
                if not sym or not ca: continue
                print(f"  ⚡ 生成单币深度分析: {sym}")
                t_tweets = search_twitter(f"{ca} OR {sym}")
                t_news = search_news(f"{ca} OR {sym}") if NEWS_API_KEY else []
                t["ai_analysis"] = generate_token_ai_analysis(t, t_tweets, t_news)
                time.sleep(2)
        else:
            print("  ⚠️ 缺少 Twitter Token，跳过单币 AI 分析。")

        report["ai_report"] = generate_ai_report(report)
        print(f"  ✅ 总报告生成 ({len(report['ai_report'])} chars)")

    save_report(report)
    print(f"\n{'='*65}\n✅ 全部完成！\n{'='*65}\n")
    return report

if __name__ == "__main__":
    run()
