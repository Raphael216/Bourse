import json, os, time, statistics, datetime, urllib.request
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np
import yfinance as yf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA, HIST = os.path.join(ROOT, "docs", "data.json"), os.path.join(ROOT, "docs", "history.json")
CATS = [(80, "Achat fort"), (65, "Acheter"), (50, "Surveiller"), (35, "Alléger"), (0, "Éviter")]
WT = {"Tendance": 20, "Fondamentaux": 25, "Solidité": 20, "Analystes": 10, "Risque": 25}
EEA = {"France","Germany","Netherlands","Belgium","Italy","Spain","Portugal","Ireland","Luxembourg","Austria","Finland","Greece","Denmark","Sweden","Norway","Iceland","Poland","Liechtenstein"}
cl = lambda x: max(0.0, min(1.0, x))
cat_of = lambda t: next(i for i, (m, _) in enumerate(CATS) if t >= m)

def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return float((100 - 100/(1 + up/dn)).iloc[-1])

def macd_pos(c):
    m = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    return bool((m - m.ewm(span=9, adjust=False).mean()).iloc[-1] > 0)

def atr(df, n=14):
    pc = df["Close"].shift()
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return float(tr.tail(n).mean())

def beta(c, m):
    j = pd.concat([c.pct_change(), m.pct_change()], axis=1, join="inner").dropna().tail(250)
    if len(j) < 100: return None
    return round(float(j.iloc[:, 0].cov(j.iloc[:, 1]) / j.iloc[:, 1].var()), 2)

def hist1y(sym, per="1y"):
    df = yf.Ticker(sym).history(period=per).dropna(subset=["Close"])
    df.index = df.index.tz_localize(None).normalize()
    return df

def rsi_s(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + up/dn)

def backtest(c, h=20):
    ma50, ma200 = c.rolling(50).mean(), c.rolling(200).mean()
    a = (.5 + (c/ma200 - 1)*2.5).clip(0, 1); b = (c > ma50)*.35 + .35
    r = rsi_s(c); rs = pd.Series(np.where(r < 30, .75, np.where(r <= 55, 1, np.where(r <= 70, .6, .2))), index=c.index)
    m = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    mp = pd.Series(np.where(m - m.ewm(span=9, adjust=False).mean() > 0, 1, .3), index=c.index)
    ts = (.3*a + .15*b + .3*rs + .25*mp)
    fw = (c.shift(-h)/c - 1).dropna(); ts = ts.loc[fw.index].dropna(); fw = fw.loc[ts.index]
    sg = fw[ts >= .75]
    return [len(sg), float(sg.sum()), int((sg > 0).sum()), len(fw), float(fw.sum()), int((fw > 0).sum())]

def stooq_price(sym):
    for k, v in {".PA": ".fr", ".AS": ".nl", ".DE": ".de"}.items():
        if sym.endswith(k):
            try:
                url = f"https://stooq.com/q/l/?s={sym[:-len(k)].lower()}{v}&f=sc&h&e=csv"
                t = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read().decode()
                return float(t.strip().splitlines()[1].split(",")[1])
            except Exception: return None
    return None

def fetch(sym, name, mk):
    t = yf.Ticker(sym)
    df3 = hist1y(sym, "3y"); df = df3.tail(252); c = df["Close"]
    try: i = t.info
    except Exception: i = {}
    debt, cash, ebitda = i.get("totalDebt"), i.get("totalCash"), i.get("ebitda")
    pc = lambda k: None if i.get(k) is None else round(i[k]*100, 1)
    earn = None
    try:
        cal = t.calendar
        e = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if e: earn = str(e[0])[:10]
    except Exception: pass
    a = atr(df); p = round(float(c.iloc[-1]), 2)
    rec = i.get("recommendationMean")
    y = i.get("trailingAnnualDividendYield")
    s = {"id": sym, "n": name, "sector": i.get("sector") or "Autre", "p": p,
        "m50": round(float(c.tail(50).mean()), 2), "m200": round(float(c.tail(200).mean()), 2),
        "rsi": round(rsi(c), 1), "macd": macd_pos(c), "per": i.get("trailingPE"),
        "g": pc("earningsGrowth"), "roe": pc("returnOnEquity"), "pm": pc("profitMargins"),
        "d": round((debt - (cash or 0))/ebitda, 2) if debt and ebitda else None,
        "y": None if y is None else round(y*100, 2), "s": None if rec is None else round(3 - rec, 2),
        "b": beta(c, mk) if mk is not None else None,
        "vol": round(float(c.pct_change().std()*(252**.5)*100), 1),
        "mdd": round(float(((c/c.cummax()) - 1).min()*100), 1),
        "atr": round(a, 2), "stop": round(p - 2*a, 2), "target": round(p + 3*a, 2),
        "earn": earn, "last": str(c.index[-1].date()), "h": [round(float(x), 2) for x in c.tail(90)]}
    s["country"] = i.get("country"); s["pea"] = i.get("country") in EEA
    p2 = stooq_price(sym)
    if p2 and abs(p2/p - 1) > .05: s["xflag"] = f"Écart entre sources : Yahoo {p} € / Stooq {p2} €"
    try: s["_bt"] = backtest(df3["Close"])
    except Exception: pass
    return s

def score(s, med, mkt_ok):
    p, per, flags, why = s["p"], s["per"], [], []
    if s.get("xflag"): flags.append(s["xflag"])
    a = cl(.5 + (p/s["m200"] - 1)*2.5); b = .7 if p > s["m50"] else .35
    r = s["rsi"]; rs = .75 if r < 30 else 1 if r <= 55 else .6 if r <= 70 else .2
    tend = .3*a + .15*b + .3*rs + .25*(1 if s["macd"] else .3)
    if per is None: pe = .5
    elif per <= 0: pe = 0
    else:
        x = per/med if med else 1
        pe = 1 if x < .7 else .8 if x < .9 else .6 if x < 1.1 else .35 if x < 1.4 else .15
        if per > 80: flags.append("PER aberrant (>80)")
    g = s["g"]
    if g is not None and abs(g) > 30: flags.append(f"Croissance extrême ({g}%) plafonnée à ±30%")
    gu = None if g is None else max(-30, min(30, g))
    gr = .5 if gu is None else cl(.5 + gu/60)
    ro = .5 if s["roe"] is None else cl(s["roe"]/20)
    mg = .5 if s["pm"] is None else cl(s["pm"]/20)
    fond = .4*pe + .2*gr + .2*ro + .2*mg
    d = s["d"]; db = .5 if d is None else 1 if d < 1 else .8 if d < 2 else .5 if d < 3 else .2
    sol = .7*db + .3*(.5 if s["y"] is None else cl(s["y"]/5))
    an = .5 if s["s"] is None else (s["s"] + 2)/4
    bt = s["b"]
    if bt is not None and (bt < .2 or bt > 2.5): flags.append(f"Bêta suspect ({bt})")
    rk = .4*(.5 if bt is None else cl(1 - (bt - .6)/1.2)) + .3*cl(1 - (s["vol"] - 15)/35) + .3*cl(1 + s["mdd"]/40)
    c = {"Tendance": tend, "Fondamentaux": fond, "Solidité": sol, "Analystes": an, "Risque": rk}
    t = round(sum(c[k]*WT[k] for k in WT))
    if not mkt_ok: t -= 5; why.append("CAC 40 sous sa moyenne 200 jours : -5 points")
    if ((d or 0) > 3 or (bt or 0) > 1.5) and t > 79:
        t = 79; why.append("Plafonné (dette ou volatilité élevée, profil prudent)")
    if s["earn"]:
        try:
            n = (datetime.date.fromisoformat(s["earn"]) - datetime.date.today()).days
            if 0 <= n <= 5:
                flags.append(f"Résultats dans {n} j"); why.append("Résultats imminents : plafonné à Surveiller")
                t = min(t, 64)
        except Exception: pass
    if p < s["m200"]: why.insert(0, "Cours sous la moyenne 200 jours : tendance de fond baissière")
    elif p > s["m50"]: why.insert(0, "Cours au-dessus de ses moyennes 50 et 200 jours")
    if r > 70: why.append("RSI élevé : action possiblement surchauffée")
    if r < 30: why.append("RSI bas : action survendue")
    if med and per and per > 0: why.append(f"PER {round(per, 1)} contre {round(med, 1)} (médiane du secteur)")
    if s["vol"] > 35: why.append("Volatilité élevée")
    miss = sum(v is None for v in (per, g, d, s["y"], s["roe"], s["s"]))
    t = max(0, min(100, t))
    if miss >= 4: flags.append("Données insuffisantes : verdict suspendu")
    if (datetime.date.today() - datetime.date.fromisoformat(s["last"])).days > 5: flags.append("Cours ancien")
    k = None if miss >= 4 else cat_of(t)
    return {"score": t, "cat": k, "verdict": "Données insuffisantes" if k is None else CATS[k][1],
            "crit": {x: round(c[x]*100) for x in c}, "why": why, "flags": flags, "med": None if not med else round(med, 1)}

def notify(msg, urgent):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic: print("ALERTE:", msg); return
    req = urllib.request.Request("https://ntfy.sh/" + topic, data=msg.encode("utf-8"),
        headers={"Title": "Score Bourse", "Priority": "high" if urgent else "default"})
    urllib.request.urlopen(req, timeout=15)

def load(path, default):
    try: return json.load(open(path))
    except Exception: return default

def main():
    full = json.load(open(os.path.join(ROOT, "config.json")))
    cfg, alerts = full["tickers"], full.get("alerts", [])
    prev = load(DATA, {"stocks": []})
    old = {s["id"]: s["verdict"] for s in prev["stocks"]}
    mk, cac_ok, cac_p = None, True, None
    try:
        mk = hist1y("^FCHI")["Close"]
        cac_ok = float(mk.iloc[-1]) > float(mk.tail(200).mean()); cac_p = round(float(mk.iloc[-1]), 1)
    except Exception as e: print("CAC indisponible", e)
    raw = []
    for sym, name in cfg.items():
        try: raw.append(fetch(sym, name, mk))
        except Exception as e: print("Erreur", sym, e)
        time.sleep(.4)
    bt = [0]*6
    for s in raw:
        b = s.pop("_bt", None)
        if b: bt = [x + y for x, y in zip(bt, b)]
    stats = {"h": 20, "n": bt[0], "avg_sig": round(bt[1]/bt[0]*100, 2), "hit_sig": round(bt[2]/bt[0]*100),
             "avg_all": round(bt[4]/bt[3]*100, 2), "hit_all": round(bt[5]/bt[3]*100)} if bt[0] and bt[3] else prev.get("backtest")
    allp = [s["per"] for s in raw if s["per"] and 0 < s["per"] <= 80]
    gmed = statistics.median(allp) if allp else None
    hist, stocks = load(HIST, []), []
    now = datetime.datetime.now(ZoneInfo("Europe/Paris"))
    for s in raw:
        sp = [x["per"] for x in raw if x["sector"] == s["sector"] and x["per"] and 0 < x["per"] <= 80]
        s.update(score(s, statistics.median(sp) if len(sp) >= 3 else gmed, cac_ok)); stocks.append(s)
        o = old.get(s["id"])
        if o and o != s["verdict"] and s["cat"] is not None and o != "Données insuffisantes":
            notify(f"{s['n']} : {o} -> {s['verdict']} (score {s['score']}/100, cours {s['p']} EUR)", s["cat"] in (0, 4))
            hist.append({"t": now.strftime("%d/%m %H:%M"), "n": s["n"], "de": o, "a": s["verdict"], "score": s["score"]})
    fired = set(prev.get("fired", []))
    for al in alerts:
        s = next((x for x in stocks if x["id"] == al.get("id")), None)
        for kind in ("above", "below"):
            if s and kind in al:
                key = f"{al['id']}:{kind}:{al[kind]}"
                hit = s["p"] >= al[kind] if kind == "above" else s["p"] <= al[kind]
                if hit and key not in fired:
                    notify(f"Alerte prix : {s['n']} {'au-dessus' if kind == 'above' else 'sous'} {al[kind]} EUR (cours {s['p']} EUR)", True); fired.add(key)
                elif not hit: fired.discard(key)
    today = now.strftime("%Y-%m-%d"); summ = prev.get("summary")
    opn = now.weekday() < 5 and 540 <= now.hour*60 + now.minute <= 1055
    if now.weekday() < 5 and now.hour*60 + now.minute >= 1020 and summ != today and len(stocks) > 5:
        top = sorted(stocks, key=lambda x: -x["score"])
        notify("Résumé de 17h. Meilleurs : " + ", ".join(f"{x['n']} {x['score']}" for x in top[:3]) +
               " | Plus faibles : " + ", ".join(f"{x['n']} {x['score']}" for x in top[-3:]), False); summ = today
    json.dump({"updated": datetime.datetime.utcnow().isoformat() + "Z", "market": {"open": opn, "cac_ok": cac_ok, "cac": cac_p},
               "backtest": stats, "fired": sorted(fired), "summary": summ, "stocks": stocks}, open(DATA, "w"), ensure_ascii=False)
    json.dump(hist[-300:], open(HIST, "w"), ensure_ascii=False)

if __name__ == "__main__":
    main()
