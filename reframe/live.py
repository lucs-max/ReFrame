"""Live market signals from free public sources, and the calibration algorithm.

Sources (no API keys needed; each one is optional and failures are tolerated):

* Wikipedia page views: monthly interest in the topic over the last 24
  complete months gives interest level and year-over-year growth.
* Hacker News (Algolia search API): stories about the topic this year vs. last
  year, a second growth signal (strongest for tech topics).
* Apple App Store (iTunes Search API): apps competing for the topic, how
  established they are (rating counts), their prices and their ratings.
* GitHub search: open-source alternatives (supply) for software ideas.

Calibration: every signal proposes a value for one market input, with a
confidence between 0 and 1 based on how much data backs it. The suggested
value is ``current + confidence * (signal - current)``, so thin evidence
nudges your number and strong evidence moves it most of the way. Together
with fixed time windows, medians and a cache, this keeps results consistent
from one run to the next.
"""

from __future__ import annotations

import json
import math
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from .models import Idea

USER_AGENT = "ReFrame/0.1 (idea analysis tool; https://github.com/lucs-max/ReFrame)"
TIMEOUT = 6
CACHE_TTL = 12 * 3600  # seconds: repeat scans within 12h reuse the same data

STOPWORDS = {
    "a", "an", "and", "app", "apps", "about", "based", "best", "business", "businesses", "for",
    "from", "in", "local", "my", "new", "of", "on", "online", "platform", "service", "services",
    "simple", "small", "software", "the", "to", "tool", "tools", "with", "your", "via", "that",
    "who", "people", "connecting", "marketplace", "subscription", "paid", "customer", "customers",
    "done", "you", "&", "-", "–", "—",
}

# Which signals are meaningful for which category.
SOURCES_BY_CATEGORY = {
    "saas": ("wikipedia", "hackernews", "appstore", "github"),
    "api": ("wikipedia", "hackernews", "github"),
    "mobile_app": ("wikipedia", "hackernews", "appstore"),
    "content": ("wikipedia", "hackernews"),
    "ecommerce": ("wikipedia", "hackernews"),
    "physical_product": ("wikipedia", "hackernews"),
    "service": ("wikipedia", "hackernews"),
    "marketplace": ("wikipedia", "hackernews"),
}


class SourceError(Exception):
    pass


def keywords_for(idea: Idea) -> str:
    """The search phrase for an idea: its keywords, or the meaningful words of its title."""
    if idea.keywords.strip():
        return idea.keywords.strip()
    words = [w.strip(".,!?;:()\"'").lower() for w in idea.title.split()]
    kept = [w for w in words if w and w not in STOPWORDS]
    return " ".join(kept[:4]) or idea.title


def _singular(word: str) -> str:
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


# -- HTTP + cache -------------------------------------------------------------

class Fetcher:
    """JSON over HTTPS with a small on-disk cache. Swap ``get_json`` in tests."""

    def __init__(self, cache_path: Path | None = None, ttl: int = CACHE_TTL):
        self.cache_path = cache_path
        self.ttl = ttl
        self._cache: dict = {}
        self._down: dict[str, SourceError] = {}
        if cache_path and cache_path.exists():
            try:
                self._cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._cache = {}

    def get_json(self, url: str, headers: dict | None = None) -> object:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            hint = " (rate limit: try again in a minute)" if e.code in (403, 429) else ""
            raise SourceError(f"HTTP {e.code} from {urllib.parse.urlparse(url).netloc}{hint}") from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise SourceError(f"can't reach {urllib.parse.urlparse(url).netloc} "
                              "(no internet, or blocked by a firewall/proxy)") from e
        except json.JSONDecodeError as e:
            raise SourceError(f"unexpected response from {urllib.parse.urlparse(url).netloc}") from e

    def cached(self, url: str, headers: dict | None = None, refresh: bool = False) -> object:
        hit = self._cache.get(url)
        if hit and not refresh and time.time() - hit["t"] < self.ttl:
            return hit["data"]
        host = urllib.parse.urlparse(url).netloc
        if host in self._down:  # don't wait on a host that already failed in this run
            raise self._down[host]
        try:
            data = self.get_json(url, headers)
        except SourceError as e:
            if "can't reach" in str(e):
                self._down[host] = e
            raise
        self._cache[url] = {"t": time.time(), "data": data}
        return data

    def save(self) -> None:
        if not self.cache_path:
            return
        now = time.time()
        fresh = {k: v for k, v in self._cache.items() if now - v["t"] < self.ttl * 4}
        try:
            self.cache_path.write_text(json.dumps(fresh), encoding="utf-8")
        except OSError:
            pass


# -- sources ------------------------------------------------------------------

def _month_window(today: date, months: int) -> tuple[str, str]:
    """(start, end) covering the last ``months`` complete months, as YYYYMMDD."""
    y, m = today.year, today.month - 1  # last complete month
    if m == 0:
        y, m = y - 1, 12
    end_y, end_m = y, m
    m -= months - 1
    while m <= 0:
        y, m = y - 1, m + 12
    last_day = 28  # any day inside the month works for the monthly API
    return f"{y:04d}{m:02d}01", f"{end_y:04d}{end_m:02d}{last_day:02d}"


def wikipedia(fetch: Fetcher, query: str, refresh: bool, today: date) -> dict:
    words = query.split()
    candidates = [" ".join(_singular(w) for w in words), query, _singular(words[-1]) if words else query]
    title = None
    for q in dict.fromkeys(candidates):
        url = ("https://en.wikipedia.org/w/api.php?action=opensearch&limit=1&namespace=0&format=json"
               "&search=" + urllib.parse.quote(q))
        found = fetch.cached(url, refresh=refresh)
        if isinstance(found, list) and len(found) > 1 and found[1]:
            title = found[1][0]
            break
    if not title:
        raise SourceError("no matching Wikipedia article")
    start, end = _month_window(today, 24)
    article = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/"
           f"{article}/monthly/{start}/{end}")
    items = fetch.cached(url, refresh=refresh).get("items", [])
    views = [int(i["views"]) for i in items]
    if len(views) < 13:
        raise SourceError(f"not enough page-view history for '{title}'")
    recent, prior = views[-12:], views[-24:-12] or views[:-12]
    recent_med, prior_med = statistics.median(recent), statistics.median(prior)
    growth = (recent_med / prior_med - 1) if prior_med > 0 else 0.0
    return {"article": title, "monthly_views": recent_med, "growth": growth,
            "url": f"https://en.wikipedia.org/wiki/{article}"}


def hackernews(fetch: Fetcher, query: str, refresh: bool, now: float) -> dict:
    year = 365 * 24 * 3600
    # Round the window to whole days so repeated scans hit the same cache entry.
    end = int(now // 86400 * 86400)
    counts = []
    for a, b in ((end - year, end), (end - 2 * year, end - year)):
        url = ("https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=1&query="
               + urllib.parse.quote(query)
               + "&numericFilters=" + urllib.parse.quote(f"created_at_i>{a},created_at_i<{b}"))
        counts.append(int(fetch.cached(url, refresh=refresh).get("nbHits", 0)))
    this_year, last_year = counts
    growth = (this_year + 5) / (last_year + 5) - 1  # +5 smooths tiny counts
    return {"stories_this_year": this_year, "stories_last_year": last_year, "growth": growth,
            "url": "https://hn.algolia.com/?q=" + urllib.parse.quote(query)}


def appstore(fetch: Fetcher, query: str, refresh: bool, country: str = "us") -> dict:
    url = ("https://itunes.apple.com/search?entity=software&limit=50&country=" + country
           + "&term=" + urllib.parse.quote(query))
    data = fetch.cached(url, refresh=refresh)
    results = data.get("results", [])
    if not results:
        raise SourceError("no matching apps")
    established = [r for r in results if int(r.get("userRatingCount") or 0) >= 50]
    paid = [float(r["price"]) for r in results if float(r.get("price") or 0) > 0]
    ratings = [float(r["averageUserRating"]) for r in established if r.get("averageUserRating")]
    rating_counts = [int(r.get("userRatingCount") or 0) for r in results]
    top = sorted(results, key=lambda r: int(r.get("userRatingCount") or 0), reverse=True)[:3]
    return {
        "apps_found": len(results), "capped": len(results) >= 50, "established_apps": len(established),
        "paid_apps": len(paid), "median_paid_price": statistics.median(paid) if paid else None,
        "median_rating": statistics.median(ratings) if ratings else None,
        "total_ratings": sum(rating_counts),
        "top_apps": [{"name": r.get("trackName"), "ratings": int(r.get("userRatingCount") or 0),
                      "rating": r.get("averageUserRating"), "price": r.get("price")} for r in top],
        "url": "https://apps.apple.com/us/search?term=" + urllib.parse.quote(query),
    }


def github(fetch: Fetcher, query: str, refresh: bool) -> dict:
    url = "https://api.github.com/search/repositories?per_page=1&q=" + urllib.parse.quote(query)
    data = fetch.cached(url, {"Accept": "application/vnd.github+json"}, refresh=refresh)
    return {"repositories": int(data.get("total_count", 0)),
            "url": "https://github.com/search?type=repositories&q=" + urllib.parse.quote(query)}


# -- calibration ----------------------------------------------------------------

@dataclass
class Suggestion:
    field: str
    current: float
    signal: float
    suggested: float
    confidence: float
    reason: str


@dataclass
class MarketScan:
    query: str
    fetched_at: str
    signals: dict = field(default_factory=dict)
    errors: dict = field(default_factory=dict)
    suggestions: list[Suggestion] = field(default_factory=list)
    pulse: float | None = None  # 0..1 overall live market attractiveness
    pulse_label: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "MarketScan":
        d = dict(d)
        d["suggestions"] = [Suggestion(**s) for s in d.get("suggestions", [])]
        return cls(**d)


def _shrink(current: float, signal: float, confidence: float) -> float:
    return current + confidence * (signal - current)


def calibrate(idea: Idea, signals: dict) -> list[Suggestion]:
    m = idea.market
    out: list[Suggestion] = []

    # Demand growth: blend Wikipedia interest growth and Hacker News trend.
    parts = []
    if "wikipedia" in signals:
        w = signals["wikipedia"]
        conf = min(0.7, max(0.1, math.log10(max(w["monthly_views"], 1)) / 6))
        parts.append((w["growth"], conf, f"Wikipedia interest {w['growth']:+.0%} year over year "
                                         f"({w['monthly_views']:,.0f} views/month)"))
    if "hackernews" in signals:
        h = signals["hackernews"]
        n = h["stories_this_year"] + h["stories_last_year"]
        conf = min(0.5, n / 400)
        if conf >= 0.05:
            parts.append((h["growth"], conf, f"Hacker News stories {h['stories_last_year']} → "
                                             f"{h['stories_this_year']} ({h['growth']:+.0%})"))
    if parts:
        total = sum(c for _, c, _ in parts)
        signal = max(-0.3, min(0.6, sum(g * c for g, c, _ in parts) / total))
        conf = min(0.8, total)
        out.append(Suggestion("demand_growth", m.demand_growth, round(signal, 3),
                              round(_shrink(m.demand_growth, signal, conf), 3), round(conf, 2),
                              "; ".join(r for _, _, r in parts)))

    # Competitors: established apps in the App Store plus open-source alternatives.
    estimate, conf, reasons = None, 0.0, []
    if "appstore" in signals:
        a = signals["appstore"]
        estimate = a["established_apps"] * (1.5 if a["capped"] else 1.0)
        conf = 0.5 if idea.category == "mobile_app" else 0.3
        reasons.append(f"{a['established_apps']} established apps (50+ ratings) among "
                       f"{a['apps_found']}{'+' if a['capped'] else ''} App Store results")
    if "github" in signals and idea.category in ("saas", "api"):
        repos = signals["github"]["repositories"]
        extra = round(math.log10(1 + repos) * 2)
        estimate = (estimate or 0) + extra
        conf = max(conf, 0.3)
        reasons.append(f"{repos:,} GitHub repositories (≈{extra} open-source alternatives)")
    capped = "appstore" in signals and signals["appstore"]["capped"]
    if estimate is not None and capped and estimate < m.competitors:
        estimate = None  # a capped search is only a lower bound: it can't show there are fewer
    if estimate is not None:
        suggested = max(0, round(_shrink(m.competitors, estimate, conf)))
        out.append(Suggestion("competitors", m.competitors, round(estimate, 1), suggested,
                              round(conf, 2), "; ".join(reasons)))

    if "appstore" in signals:
        a = signals["appstore"]
        # Willingness to pay: what paid apps in this space actually charge.
        if idea.category == "mobile_app" and a["paid_apps"] >= 5 and a["median_paid_price"]:
            conf = min(0.6, a["paid_apps"] / 25)
            out.append(Suggestion("willingness_to_pay", m.willingness_to_pay, a["median_paid_price"],
                                  round(_shrink(m.willingness_to_pay, a["median_paid_price"], conf), 2),
                                  round(conf, 2),
                                  f"median price of {a['paid_apps']} paid apps is ${a['median_paid_price']:.2f}"))
        # Differentiation room: weak competitor ratings mean users are unhappy.
        if a["median_rating"] is not None and a["established_apps"] >= 3:
            r = a["median_rating"]
            target = 0.7 if r < 3.8 else 0.6 if r < 4.3 else 0.4 if r < 4.7 else 0.3
            out.append(Suggestion("differentiation", m.differentiation, target,
                                  round(_shrink(m.differentiation, target, 0.3), 2), 0.3,
                                  f"established competitors are rated {r:.1f}/5"
                                  + (": room to do better" if r < 4.3 else ": hard to beat on quality")))
    return [s for s in out if abs(s.suggested - s.current) > 1e-9]


def market_pulse(signals: dict) -> tuple[float | None, str]:
    """A 0..1 summary of live attractiveness: growth up, saturation down."""
    parts = []
    if "wikipedia" in signals:
        parts.append(0.5 + max(-0.5, min(0.5, signals["wikipedia"]["growth"])))
    if "hackernews" in signals:
        parts.append(0.5 + max(-0.5, min(0.5, signals["hackernews"]["growth"] / 2)))
    if "appstore" in signals:
        a = signals["appstore"]
        parts.append(1 - min(1.0, a["established_apps"] / 40))
        if a["median_rating"] is not None:
            parts.append(min(1.0, max(0.0, (4.8 - a["median_rating"]) / 1.5)))
    if not parts:
        return None, "no live data"
    p = sum(parts) / len(parts)
    label = "hot" if p >= 0.65 else "healthy" if p >= 0.5 else "cooling" if p >= 0.35 else "cold or saturated"
    return round(p, 3), label


def scan(idea: Idea, fetch: Fetcher, refresh: bool = False, now: float | None = None) -> MarketScan:
    now = now or time.time()
    today = datetime.fromtimestamp(now, timezone.utc).date()
    query = keywords_for(idea)
    wanted = SOURCES_BY_CATEGORY.get(idea.category, ("wikipedia", "hackernews"))
    jobs = {
        "wikipedia": lambda: wikipedia(fetch, query, refresh, today),
        "hackernews": lambda: hackernews(fetch, query, refresh, now),
        "appstore": lambda: appstore(fetch, query, refresh),
        "github": lambda: github(fetch, query, refresh),
    }
    result = MarketScan(query=query, fetched_at=datetime.fromtimestamp(now, timezone.utc)
                        .isoformat(timespec="seconds"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {name: pool.submit(jobs[name]) for name in wanted}
        for name, fut in futures.items():
            try:
                result.signals[name] = fut.result()
            except SourceError as e:
                result.errors[name] = str(e)
            except Exception as e:  # one odd response must never break the whole scan
                result.errors[name] = f"unexpected response ({e.__class__.__name__})"
    fetch.save()
    result.suggestions = calibrate(idea, result.signals)
    result.pulse, result.pulse_label = market_pulse(result.signals)
    return result


def apply(idea: Idea, market_scan: MarketScan) -> Idea:
    for s in market_scan.suggestions:
        value = s.suggested
        setattr(idea.market, s.field, int(round(value)) if s.field == "competitors" else value)
    return idea


def check(fetch: Fetcher) -> dict[str, str]:
    """Connectivity check for every source (used by `reframe market --check`)."""
    probe = Idea("Invoice reminders for freelancers", category="saas", keywords="invoice")
    s = scan(probe, fetch, refresh=True)
    return {name: ("ok" if name in s.signals else s.errors.get(name, "skipped"))
            for name in ("wikipedia", "hackernews", "appstore", "github")}
