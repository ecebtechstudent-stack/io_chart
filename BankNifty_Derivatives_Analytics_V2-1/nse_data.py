
import time
import requests
import pandas as pd


class NSEClient:
    BASE = "https://www.nseindia.com"

    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.nseindia.com/option-chain",
            "Connection": "keep-alive",
        })
        self.warm()

    def warm(self):
        for path in ["/", "/option-chain"]:
            try:
                self.s.get(self.BASE + path, timeout=15)
            except requests.RequestException:
                pass

    def get(self, path, params=None, attempts=3):
        last = None

        for n in range(attempts):
            try:
                r = self.s.get(
                    self.BASE + path,
                    params=params,
                    timeout=25,
                    allow_redirects=True,
                )

                if r.status_code in (401, 403, 429):
                    last = RuntimeError(
                        f"NSE HTTP {r.status_code}: request may be blocked/rate-limited."
                    )
                    self.warm()
                    time.sleep(2 + n * 2)
                    continue

                r.raise_for_status()
                return r.json()

            except Exception as e:
                last = e
                time.sleep(1 + n)

        raise last or RuntimeError("NSE request failed.")

    def get_banknifty_constituents(self):
        data = self.get(
            "/api/equity-stockIndices",
            params={"index": "NIFTY BANK"},
        )

        result = []
        for row in data.get("data", []):
            symbol = row.get("symbol")
            if symbol and symbol.upper() not in ("NIFTY BANK", "BANKNIFTY"):
                if symbol not in result:
                    result.append(symbol)

        return result

    def get_option_chain(self, symbol, is_index=False):
        if is_index:
            return self.get(
                "/api/option-chain-indices",
                params={"symbol": "BANKNIFTY"},
            )

        return self.get(
            "/api/option-chain-equities",
            params={"symbol": symbol},
        )

    def get_derivative_quote(self, symbol):
        return self.get(
            "/api/quote-derivative",
            params={"symbol": symbol},
        )

    def parse_futures(self, payload):
        rows = []

        def walk(x):
            if isinstance(x, dict):
                if x.get("instrumentType") == "FUTIDX" or x.get("instrumentType") == "FUTSTK":
                    rows.append(x)
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)

        walk(payload)

        if not rows:
            return pd.DataFrame()

        wanted = [
            "symbol", "expiryDate", "lastPrice", "change", "pChange",
            "openInterest", "changeinOpenInterest",
            "totalTradedVolume", "underlyingValue", "instrumentType"
        ]

        out = pd.DataFrame(rows)
        for c in wanted:
            if c not in out.columns:
                out[c] = None

        return out[wanted].drop_duplicates().reset_index(drop=True)
