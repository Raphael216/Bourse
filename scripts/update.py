import json, os, datetime, urllib.request
import yfinance as yf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "data.json")
WT = {"Tendance": 25, "Fondamentaux": 25, "Solidité": 20, "Actualités": 15, "Risque": 15}
cl = lambda x: max(0.0, min(1.0, x))

def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return float((100 - 100/(1 + up/dn)).iloc[-1])

def crit(s):
    p, m50, m200, r = s["p"], s["m50"], s["m200"], s["rsi"]
    a = cl(.5 + (p/m200 - 1)*2.5); b = .7 if p > m50 else .35
    rs = .75 if r < 30 else 1 if r <= 55 else .6 if r <= 70 else .2
    per, g, d, y, sent, beta = s["per"], s["g"], s["d"], s["y"], s["s"], s["b"]
    pe = .5 if per is None else 0 if per <= 0 else 1 if per < 12 else .8 if per < 18 else .5 if per < 25 else .2
    gr = .5 if g is None else cl(.4 + g/20)
    db = .5 if d is None else 1 if d < 1 else .8 if d < 2 else .5 if d < 3 else .2
    yl = .5 if y is None else cl(y/5)
    nw = .5 if sent is None else (sent + 2)/4
    rk = .5 if beta is None else cl(1 - (beta - .6)/1.2)
    return {"Tendance": .4*a + .2*b + .4*rs, "Fondamentaux": .5*pe + .5*gr,
            "Solidité": .7*db + .3*yl, "Actualités": nw, "Risque": rk}

def score(s):
    c = crit(s); t = round(sum(c[k]*WT[k] for k in WT)); cap = False
    if ((s["d"] or 0) > 3 or (s["b"] or 0) > 1.5) and t > 69:
        t, cap = 69, True
    v = "Acheter" if t >= 70 else "Surveiller" if t >= 45 else "Ne pas acheter"
    return t, v, cap, {k: round(c[k]*100) for k in c}

def fetch(sym, name):
    t = yf.Ticker(sym)
    h = t.history(period="1y")["Close"].dropna()
    try: i = t.info
    except Exception: i = {}
    g = i.get("earningsGrowth"); y = i.get("trailingAnnualDividendYield")
    debt, cash, ebitda = i.get("totalDebt"), i.get("totalCash"), i.get("ebitda")
    rec = i.get("recommendationMean")
    s = {"id": sym, "n": name, "p": round(float(h.iloc[-1]), 2),
         "m50": round(float(h.tail(50).mean()), 2), "m200": round(float(h.tail(200).mean()), 2),
         "rsi": round(rsi(h), 1), "per": i.get("trailingPE"),
         "g": None if g is None else round(g*100, 1),
         "d": round((debt - (cash or 0))/ebitda, 2) if debt and ebitda else None,
         "y": None if y is None else round(y*100, 2),
         "s": None if rec is None else round(3 - rec, 2), "b": i.get("beta"),
         "h": [round(float(x), 2) for x in h.tail(90)]}
    s["score"], s["verdict"], s["cap"], s["crit"] = score(s)
    return s

def notify(msg, urgent):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic: print("ALERTE:", msg); return
    req = urllib.request.Request("https://ntfy.sh/" + topic, data=msg.encode("utf-8"),
        headers={"Title": "Score Bourse", "Priority": "high" if urgent else "default"})
    urllib.request.urlopen(req, timeout=15)

def main():
    cfg = json.load(open(os.path.join(ROOT, "config.json")))["tickers"]
    try: old = {s["id"]: s["verdict"] for s in json.load(open(OUT))["stocks"]}
    except Exception: old = {}
    stocks = []
    for sym, name in cfg.items():
        try: stocks.append(fetch(sym, name))
        except Exception as e: print("Erreur", sym, e)
    for s in stocks:
        o = old.get(s["id"])
        if o and o != s["verdict"]:
            notify(f"{s['n']} : {o} -> {s['verdict']} (score {s['score']}/100, cours {s['p']} EUR)",
                   s["verdict"] != "Surveiller")
    json.dump({"updated": datetime.datetime.utcnow().isoformat() + "Z", "stocks": stocks},
              open(OUT, "w"), ensure_ascii=False)

main()
