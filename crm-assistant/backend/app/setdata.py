"""Official financial data from the Stock Exchange of Thailand (set.or.th).

set.or.th sits behind Imperva/Incapsula bot protection: its JSON API returns a
JavaScript challenge unless the request carries the session cookies that the site
issues when a normal page is loaded. We therefore:
  1. "prime" a session by GETting a set.or.th HTML page (obtains visid_incap / incap_ses),
  2. reuse those cookies (via a stdlib cookie jar) to call the public JSON API.

No third-party dependencies — only the Python standard library.

Public endpoints used (verified working):
  /api/set/stock/list                                  -> all listed symbols (name TH/EN)
  /api/set/stock/{symbol}/profile                      -> company profile
  /api/set/stock/{symbol}/company-highlight/financial-data  -> 5 yrs annual highlights
  /api/set/stock/{symbol}/highlight-data               -> market cap, P/E, yield, ...
"""
import gzip
import json
import re
import time
import threading
import urllib.request
import http.cookiejar

BASE = "https://www.set.or.th"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/120.0.0.0 Safari/537.36")

_lock = threading.Lock()
_opener = None
_primed_at = 0.0
_SESSION_TTL = 20 * 60  # re-prime cookies every 20 min

_symbols_cache = None
_symbols_at = 0.0
_SYMBOLS_TTL = 24 * 60 * 60

# Words to strip when matching a free-text company name to a listed name.
_STOP = {
    "the", "public", "company", "limited", "co", "ltd", "pcl", "plc", "group",
    "corporation", "corp", "inc", "holding", "holdings", "thailand", "and",
    "บริษัท", "จำกัด", "มหาชน", "กลุ่ม",
}


def _new_opener():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def _fetch(url, referer=None, accept="application/json, text/plain, */*", timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9,th;q=0.8",
        "Referer": referer or f"{BASE}/en/home",
    })
    try:
        with _opener.open(req, timeout=timeout) as r:
            raw = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                raw = gzip.decompress(raw)
            return r.status, raw
    except urllib.error.HTTPError as e:
        # Incapsula blocks come back as HTTP errors (e.g. 403) with an HTML body.
        raw = b""
        try:
            raw = e.read()
        except Exception:
            pass
        return e.code, raw


def _ensure_session(force=False):
    """Load a set.or.th HTML page so Incapsula issues session cookies."""
    global _opener, _primed_at
    if _opener is None or force or (time.time() - _primed_at) > _SESSION_TTL:
        _opener = _new_opener()
        # Two hits (home, then a stock page) reliably completes the cookie handshake.
        _fetch(f"{BASE}/en/home", accept="text/html")
        _fetch(f"{BASE}/en/market/product/stock/quote/SCC/factsheet", accept="text/html")
        _primed_at = time.time()


def _looks_blocked(status, raw):
    return status != 200 or (raw[:200].lstrip().startswith(b"<"))


def _get_json(path, referer=None):
    """GET a JSON endpoint, priming/refreshing the Incapsula session as needed."""
    with _lock:
        _ensure_session()
        url = f"{BASE}{path}"
        status, raw = _fetch(url, referer=referer)
        if _looks_blocked(status, raw):
            _ensure_session(force=True)
            status, raw = _fetch(url, referer=referer)
        if _looks_blocked(status, raw):
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None


# ---------------- Symbol resolution ----------------
def _norm_tokens(s):
    s = (s or "").lower()
    s = re.sub(r"[^\w\u0e00-\u0e7f]+", " ", s)  # keep latin + Thai
    return [t for t in s.split() if t and t not in _STOP]


def _load_symbols():
    global _symbols_cache, _symbols_at
    if _symbols_cache is not None and (time.time() - _symbols_at) < _SYMBOLS_TTL:
        return _symbols_cache
    data = _get_json("/api/set/stock/list?lang=en")
    syms = (data or {}).get("securitySymbols", []) if isinstance(data, dict) else []
    _symbols_cache = syms
    _symbols_at = time.time()
    return syms


def resolve_symbol(text, hint_name=None):
    """Resolve a SET ticker from free text and/or a company name.

    Priority:
      1. An explicit ticker token in `text` that exactly matches a listed symbol.
      2. Best fuzzy match (by name-token overlap) of `hint_name` or `text` against
         listed company names. Returns None if no confident match.
    Returns (symbol, listed_name_en) or None.
    """
    syms = _load_symbols()
    if not syms:
        return None
    by_symbol = {}
    for s in syms:
        sym = (s.get("symbol") or "").upper()
        if sym and sym not in by_symbol:
            by_symbol[sym] = s

    # 1) explicit ticker in the text (2-8 uppercase/alnum chars)
    for tok in re.findall(r"\b[A-Z][A-Z0-9]{1,7}\b", text or ""):
        if tok in by_symbol:
            s = by_symbol[tok]
            return tok, s.get("nameEN") or s.get("nameTH") or tok

    # 2) fuzzy match on company name
    q = _norm_tokens(hint_name) or _norm_tokens(text)
    if not q:
        return None
    qset = set(q)
    best, best_score = None, 0.0
    for s in syms:
        for nm in (s.get("nameEN"), s.get("nameTH")):
            toks = set(_norm_tokens(nm))
            if not toks:
                continue
            inter = len(qset & toks)
            if not inter:
                continue
            # overlap relative to the query (how much of the query is covered)
            score = inter / len(qset)
            # prefer names that also cover most of their own tokens (tight match)
            score += 0.3 * (inter / len(toks))
            if score > best_score:
                best, best_score = s, score
    # require a reasonably confident match to avoid picking the wrong company
    if best and best_score >= 0.9:
        return (best.get("symbol") or "").upper(), best.get("nameEN") or best.get("nameTH")
    return None


# ---------------- Financials ----------------
def _m(v):
    """Values from SET are in THOUSAND baht -> convert to MILLION baht."""
    return None if v is None else round(v / 1000.0)


def _fmt_int(v):
    return "-" if v is None else f"{v:,.0f}"


def _fmt_num(v, nd=2):
    return "-" if v is None else f"{v:,.{nd}f}"


def financial_summary(symbol):
    """Return {'symbol','name','text','sources'} with official SET data, or None."""
    symbol = symbol.upper()
    ref = f"{BASE}/en/market/product/stock/quote/{symbol}/factsheet"
    fin = _get_json(f"/api/set/stock/{symbol}/company-highlight/financial-data?lang=en", ref)
    if not isinstance(fin, list) or not fin:
        return None
    profile = _get_json(f"/api/set/stock/{symbol}/profile?lang=en", ref) or {}
    hi = _get_json(f"/api/set/stock/{symbol}/highlight-data?lang=en", ref) or {}

    name = profile.get("name") or symbol
    sector = " / ".join(x for x in [profile.get("industryName"), profile.get("sectorName")] if x)

    lines = [f"SET OFFICIAL FINANCIAL DATA — {name} ({symbol})"
             f"{(' · ' + sector) if sector else ''}",
             "Currency: million THB (annual, consolidated). Source: set.or.th (official)."]
    lines.append("Year | Revenue | NetProfit | NetMargin% | ROE% | EPS | D/E | TotalAssets | Equity")
    for r in sorted(fin, key=lambda x: x.get("year") or 0):
        yr = r.get("year")
        # Q9 = full year; anything else is an interim period (label it)
        period = str(yr) if r.get("quarter") in ("Q9", "9M", None) else f"{yr} {r.get('quarter')}"
        lines.append(
            f"{period} | {_fmt_int(_m(r.get('totalRevenue')))} | {_fmt_int(_m(r.get('netProfit')))} | "
            f"{_fmt_num(r.get('netProfitMargin'))} | {_fmt_num(r.get('roe'))} | {_fmt_num(r.get('eps'))} | "
            f"{_fmt_num(r.get('deRatio'))} | {_fmt_int(_m(r.get('totalAsset')))} | {_fmt_int(_m(r.get('equity')))}")

    if hi:
        mc = hi.get("marketCap")  # marketCap is in BAHT (not thousands) -> to million
        mc_m = None if mc is None else round(mc / 1_000_000.0)
        lines.append(
            "Market snapshot: "
            f"Market cap { _fmt_int(mc_m) } MTHB, P/E {_fmt_num(hi.get('peRatio'))}, "
            f"P/BV {_fmt_num(hi.get('pbRatio'))}, Dividend yield {_fmt_num(hi.get('dividendYield'))}% "
            f"(as of {str(hi.get('asOfDate') or '')[:10]}).")

    text = "\n".join(lines)
    sources = [{
        "title": f"SET Factsheet — {name} ({symbol})",
        "url": ref,
    }]
    return {"symbol": symbol, "name": name, "text": text, "sources": sources}


def lookup(text, hint_name=None):
    """High-level: resolve a symbol from text/name then return its financial summary."""
    try:
        res = resolve_symbol(text, hint_name=hint_name)
        if not res:
            return None
        symbol, _ = res
        return financial_summary(symbol)
    except Exception:
        return None
