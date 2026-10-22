import json, os, time, statistics, datetime, urllib.request
from zoneinfo import ZoneInfo
import numpy as np, pandas as pd, yfinance as yf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = lambda n: os.path.join(ROOT, "docs", n)
DATA, HIST, FUND, DAILY, INTRA = D("data.json"), D("history.json"), D("fund.json"), D("daily.json"), D("intraday.json")
CATS = [(80, "Achat fort"), (65, "Acheter"), (50, "Surveiller"), (35, "Alléger"), (0, "Éviter")]
K = ["Tendance", "Fondamentaux", "Solidité", "Analystes/actus", "Risque"]
WT = dict(zip(K, [20, 25, 20, 10, 25]))
EEA = {"France", "Germany", "Netherlands", "Belgium", "Italy", "Spain", "Portugal", "Ireland", "Luxembourg", "Austria", "Finland", "Greece", "Denmark", "Sweden", "Norway", "Iceland", "Poland", "Liechtenstein"}
POS = set("beats surge surges record upgrade upgraded raises raised soars rally strong growth profit jumps gains outperform hausse bondit relève dépasse".split())
NEG = set("miss misses plunge plunges probe investigation downgrade downgraded cuts warning lawsuit fraud loss losses falls slump recall strike slashes chute baisse enquête avertissement".split())
SENS = {"investigation", "probe", "fraud", "lawsuit", "warning", "recall", "enquête", "avertissement"}
cl = lambda x: max(0.0, min(1.0, x))
cat_of = lambda t: next(i for i, (m, _) in enumerate(CATS) if t >= m)
rd = lambda x, n=1: None if x is None else round(float(x), n)

def band(x, t, v, d=.5):
    if x is None: return d
    for a, b in zip(t, v):
        if x < a: return b
    return v[-1]

def hist(sym, per="1y"):
    df = yf.Ticker(sym).history(period=per).dropna(subset=["Close"])
    df.index = df.index.tz_localize(None).normalize()
    return df

def intra(sym, per, itv):
    df = yf.Ticker(sym).history(period=per, interval=itv).dropna(subset=["Close"])
    return [[x.strftime("%d/%m %H:%M"), round(float(v), 2)] for x, v in zip(df.index.tz_convert("Europe/Paris"), df["Close"])]

def rsi_s(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    return 100 - 100/(1 + up/dn)

def macd_pos(c):
    m = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    return bool((m - m.ewm(span=9, adjust=False).mean()).iloc[-1] > 0)

def atr(df, n=14):
    pc = df["Close"].shift()
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return float(tr.tail(n).mean())

def beta(c, m):
    j = pd.concat([c.pct_change(), m.pct_change()], axis=1, join="inner").dropna().tail(250)
    return None if len(j) < 100 else round(float(j.iloc[:, 0].cov(j.iloc[:, 1]) / j.iloc[:, 1].var()), 2)

def backtest(c, h=20):
    ma50, ma200 = c.rolling(50).mean(), c.rolling(200).mean()
    a = (.5 + (c/ma200 - 1)*2.5).clip(0, 1); b = (c > ma50)*.35 + .35
    r = rsi_s(c); rs = pd.Series(np.where(r < 30, .75, np.where(r <= 55, 1, np.where(r <= 70, .6, .2))), index=c.index)
    m = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean()
    mp = pd.Series(np.where(m - m.ewm(span=9, adjust=False).mean() > 0, 1, .3), index=c.index)
    ts = .3*a + .15*b + .3*rs + .25*mp
    fw = (c.shift(-h)/c - 1).dropna(); ts = ts.loc[fw.index].dropna(); fw = fw.loc[ts.index]; sg = fw[ts >= .75]
    return [len(sg), float(sg.sum()), int((sg > 0).sum()), len(fw), float(fw.sum()), int((fw > 0).sum())]

def stooq_price(sym):
    for k, v in {".PA": ".fr", ".AS": ".nl", ".DE": ".de"}.items():
        if sym.endswith(k):
            try:
                url = f"https://stooq.com/q/l/?s={sym[:-len(k)].lower()}{v}&f=sc&h&e=csv"
                t = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=10).read().decode()
                return float(t.strip().splitlines()[1].split(",")[1])
            except Exception: return None

def news_info(t):
    try: items = t.news or []
    except Exception: return [], None
    out, p, n = [], 0, 0
    for it in items[:10]:
        ti = (it.get("content") or it).get("title") or ""
        w = set(ti.lower().replace(",", " ").replace(".", " ").split())
        pp, nn = len(w & POS), len(w & NEG); p += pp; n += nn
        if ti: out.append({"t": ti, "s": 1 if pp > nn else -1 if nn > pp else 0, "x": bool(w & SENS)})
    return out[:4], (None if not out else ((p - n)/(p + n) if p + n else 0.0))

def fundamentals(sym, today):
    t = yf.Ticker(sym)
    try: i = t.info
    except Exception: i = {}
    sec = i.get("sector") or "Autre"
    debt, cash, eb, mc, fcf = i.get("totalDebt"), i.get("totalCash"), i.get("ebitda"), i.get("marketCap"), i.get("freeCashflow")
    pc = lambda k: None if i.get(k) is None else round(i[k]*100, 1)
    g = gr = None
    try:
        f = t.income_stmt
        def gv(row):
            r = f.loc[row].dropna()
            return round((r.iloc[0]/r.iloc[1] - 1)*100, 1) if len(r) >= 2 and r.iloc[1] > 0 else None
        g, gr = gv("Net Income"), gv("Total Revenue")
    except Exception: pass
    earn = None
    try:
        cal = t.calendar; e = cal.get("Earnings Date") if isinstance(cal, dict) else None
        if e: earn = str(e[0])[:10]
    except Exception: pass
    nw, ns = news_info(t)
    bt = None
    try: bt = backtest(hist(sym, "3y")["Close"])
    except Exception: pass
    y = i.get("trailingAnnualDividendYield"); rec = i.get("recommendationMean")
    return {"date": today, "sector": sec, "kind": "Finance" if sec == "Financial Services" else "Immobilier" if sec == "Real Estate" else "Standard",
        "country": i.get("country"), "per": rd(i.get("trailingPE")), "fpe": rd(i.get("forwardPE")),
        "peg": rd(i.get("trailingPegRatio") or i.get("pegRatio"), 2), "ev": rd(i.get("enterpriseToEbitda")), "pb": rd(i.get("priceToBook"), 2),
        "fcfy": round(fcf/mc*100, 1) if fcf and mc else None, "g": g if g is not None else pc("earningsGrowth"), "grev": gr,
        "roe": pc("returnOnEquity"), "pm": pc("profitMargins"), "d": round((debt - (cash or 0))/eb, 2) if debt and eb else None,
        "y": None if y is None else round(y*100, 2), "s": None if rec is None else round(3 - rec, 2),
        "earn": earn, "news": nw, "nsent": ns, "bt": bt}

def live(sym, name, F, mk):
    df = hist(sym); c = df["Close"]; a = atr(df); p = round(float(c.iloc[-1]), 2)
    ret = lambda x, n: float(x.iloc[-1]/x.iloc[-n-1] - 1)*100
    rel = lambda n: None if mk is None or len(mk) <= n or len(c) <= n else round(ret(c, n) - ret(mk, n), 1)
    v = df["Volume"]; v60 = float(v.tail(60).mean())
    s = {k: F[k] for k in F if k not in ("date", "bt")}
    s.update({"id": sym, "n": name, "p": p, "m50": round(float(c.tail(50).mean()), 2), "m200": round(float(c.tail(200).mean()), 2),
        "rsi": round(float(rsi_s(c).iloc[-1]), 1), "macd": macd_pos(c), "b": beta(c, mk) if mk is not None else None,
        "vol": round(float(c.pct_change().std()*(252**.5)*100), 1), "mdd": round(float(((c/c.cummax()) - 1).min()*100), 1),
        "atr": round(a, 2), "stop": round(p - 2*a, 2), "target": round(p + 3*a, 2), "rel3": rel(63), "rel6": rel(126),
        "volr": round(float(v.tail(5).mean())/v60, 2) if v60 > 0 else None, "r5": round(ret(c, 5), 1),
        "last": str(c.index[-1].date()), "pea": F.get("country") in EEA})
    p2 = stooq_price(sym)
    s["xchk"] = None if not p2 else round((p2/p - 1)*100, 1)
    daily = {"t": [str(x.date()) for x in c.index], "v": [round(float(x), 2) for x in c]}
    try: it = {"j": intra(sym, "1d", "15m"), "w": intra(sym, "7d", "1h")}
    except Exception: it = None
    return s, daily, it

def score(s, med, mkt_ok):
    p, per, flags, why, kind = s["p"], s["per"], [], [], s["kind"]
    if s["xchk"] is not None and abs(s["xchk"]) > 5: flags.append(f"Écart de cours de {s['xchk']} % entre Yahoo et Stooq")
    a = cl(.5 + (p/s["m200"] - 1)*2.5); b = .7 if p > s["m50"] else .35
    r = s["rsi"]; rs = .75 if r < 30 else 1 if r <= 55 else .6 if r <= 70 else .2
    rl = .5 if s["rel6"] is None else cl(.5 + s["rel6"]/40)
    vc = .5 if not s["volr"] or s["volr"] <= 1.5 else (1 if s["r5"] > 0 else .1)
    tend = .24*a + .12*b + .24*rs + .2*(1 if s["macd"] else .3) + .12*rl + .08*vc
    if per is None: pe = .5
    elif per <= 0: pe = 0
    else:
        x = per/med if med else 1
        pe = 1 if x < .7 else .8 if x < .9 else .6 if x < 1.1 else .35 if x < 1.4 else .15
        if per > 80: flags.append("PER aberrant (supérieur à 80)")
    g, grv = s["g"], s["grev"]
    if g is not None and abs(g) > 30: flags.append(f"Croissance extrême ({g} %) plafonnée à ±30 % dans le calcul")
    gu = None if g is None else max(-30, min(30, g))
    gs = .5 if gu is None else cl(.5 + gu/60)
    if grv is not None: gs = .6*gs + .4*cl(.5 + max(-30, min(30, grv))/60)
    ro = .5 if s["roe"] is None else cl(s["roe"]/20); mg = .5 if s["pm"] is None else cl(s["pm"]/20)
    yl = .5 if s["y"] is None else cl(s["y"]/5)
    fw = .1 if s["fpe"] is not None and s["fpe"] <= 0 else band(s["fpe"], [12, 18, 25], [1, .8, .5, .25])
    pb = band(s["pb"], [1, 1.5, 2.5], [1, .7, .4, .2])
    if kind == "Standard":
        fond = .3*pe + .1*fw + .15*band(s["ev"], [7, 11, 16], [1, .8, .5, .25]) + .1*(.5 if s["fcfy"] is None else cl(s["fcfy"]/6)) + .15*gs + .1*ro + .1*mg
        sol = .7*band(s["d"], [1, 2, 3], [1, .8, .5, .2]) + .3*yl
    else:
        fond = .35*pe + .25*pb + .25*ro + .15*gs
        sol = .5*cl((s["roe"] or 0)/12) + .5*yl
    an = .5 if s["s"] is None else (s["s"] + 2)/4
    ns = .5 if s["nsent"] is None else (s["nsent"] + 1)/2
    if any(n["x"] for n in s["news"]): flags.append("Actualité sensible détectée (enquête, avertissement, litige…)")
    bt = s["b"]
    if bt is not None and (bt < .2 or bt > 2.5): flags.append(f"Bêta suspect ({bt})")
    rk = .4*(.5 if bt is None else cl(1 - (bt - .6)/1.2)) + .3*cl(1 - (s["vol"] - 15)/35) + .3*cl(1 + s["mdd"]/40)
    c = dict(zip(K, [tend, fond, sol, .6*an + .4*ns, rk]))
    t = round(sum(c[k]*WT[k] for k in K))
    if not mkt_ok: t -= 5; why.append("CAC 40 sous sa moyenne 200 jours : -5 points (profil prudent)")
    caprisk = bool((s["d"] or 0) > 3 and kind == "Standard" or (bt or 0) > 1.5)
    if caprisk and t > 79: t = 79; why.append("Plafonné à 79 : dette ou volatilité élevée (profil prudent)")
    ed = None
    if s["earn"]:
        try:
            ed = (datetime.date.fromisoformat(s["earn"]) - datetime.date.today()).days
            if 0 <= ed <= 5: flags.append(f"Résultats dans {ed} jour(s)"); why.append("Résultats imminents : plafonné à Surveiller (profil prudent)"); t = min(t, 64)
        except Exception: ed = None
    why.insert(0, "Cours sous la moyenne 200 jours : tendance de fond baissière" if p < s["m200"] else "Cours au-dessus de ses moyennes 50 et 200 jours" if p > s["m50"] else "Cours sous sa moyenne 50 jours")
    if r > 70: why.append("RSI élevé : action possiblement surchauffée")
    if r < 30: why.append("RSI bas : action survendue")
    if med and per and per > 0: why.append(f"PER {per} contre {round(med, 1)} (médiane du secteur)")
    if s["rel6"] is not None: why.append(f"{'Surperforme' if s['rel6'] >= 0 else 'Sous-performe'} le CAC 40 de {abs(s['rel6'])} points sur 6 mois")
    if s["volr"] and s["volr"] > 1.5: why.append(f"Volumes {s['volr']} fois supérieurs à la normale")
    if s["vol"] > 35: why.append("Volatilité élevée")
    if kind != "Standard": why.append(f"Entreprise de type {kind} : la dette/EBITDA est remplacée par le P/B et le ROE")
    miss = sum(v is None for v in (per, g, s["y"], s["roe"], s["s"], s["d"] if kind == "Standard" else s["pb"]))
    stale = (datetime.date.today() - datetime.date.fromisoformat(s["last"])).days > 5
    if stale: flags.append("Cours ancien (plus de 5 jours)")
    if miss >= 4: flags.append("Données insuffisantes : verdict suspendu")
    conf = 100 - 10*miss - (25 if any("Écart" in f for f in flags) else 0) - (30 if stale else 0) - (10 if s["xchk"] is None else 0) - 8*sum(("aberrant" in f or "suspect" in f or "extrême" in f) for f in flags)
    t = max(0, min(100, t)); k = None if miss >= 4 else cat_of(t)
    return {"score": t, "cat": k, "verdict": "Données insuffisantes" if k is None else CATS[k][1], "crit": {x: round(c[x]*100) for x in c},
            "why": why, "flags": flags, "med": rd(med), "conf": max(5, min(100, conf)), "caprisk": caprisk, "earn_days": ed, "miss": miss}

def notify(msg, urgent):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic: print("ALERTE:", msg); return
    req = urllib.request.Request("https://ntfy.sh/" + topic, data=msg.encode("utf-8"), headers={"Title": "Score Bourse", "Priority": "high" if urgent else "default"})
    urllib.request.urlopen(req, timeout=15)

def load(path, default):
    try: return json.load(open(path))
    except Exception: return default

def dump(path, obj): json.dump(obj, open(path, "w"), ensure_ascii=False, separators=(",", ":"))

def main():
    full = json.load(open(os.path.join(ROOT, "config.json")))
    cfg, alerts = full["tickers"], full.get("alerts", [])
    prev = load(DATA, {"stocks": []}); old = {s["id"]: s["verdict"] for s in prev["stocks"]}
    now = datetime.datetime.now(ZoneInfo("Europe/Paris")); today = now.strftime("%Y-%m-%d")
    fc = load(FUND, {}); daily_prev = load(DAILY, {})
    mk, cac_ok, cac_p, cacd = None, True, None, None
    try:
        mdf = hist("^FCHI"); mk = mdf["Close"]; cac_ok = float(mk.iloc[-1]) > float(mk.tail(200).mean()); cac_p = round(float(mk.iloc[-1]), 1)
        cacd = {"t": [str(x.date()) for x in mk.index], "v": [round(float(x), 1) for x in mk]}
    except Exception as e: print("CAC indisponible", e)
    raw, dl, it, bt = [], {"^FCHI": cacd} if cacd else {}, {}, [0]*6
    for sym, name in cfg.items():
        try:
            F = fc.get(sym)
            if not F or F.get("date") != today:
                try: F = fundamentals(sym, today); fc[sym] = F
                except Exception as e:
                    print("Fondamentaux KO", sym, e)
                    if not F: continue
            s, d, i = live(sym, name, F, mk); raw.append(s); dl[sym] = d
            if i: it[sym] = i
            if F.get("bt"): bt = [x + y for x, y in zip(bt, F["bt"])]
        except Exception as e: print("Erreur", sym, e)
        time.sleep(.3)
    stats = {"h": 20, "n": bt[0], "avg_sig": round(bt[1]/bt[0]*100, 2), "hit_sig": round(bt[2]/bt[0]*100), "avg_all": round(bt[4]/bt[3]*100, 2), "hit_all": round(bt[5]/bt[3]*100)} if bt[0] and bt[3] else prev.get("backtest")
    allp = [s["per"] for s in raw if s["per"] and 0 < s["per"] <= 80]; gmed = statistics.median(allp) if allp else None
    hist_log, stocks = load(HIST, []), []
    for s in raw:
        sp = [x["per"] for x in raw if x["sector"] == s["sector"] and x["per"] and 0 < x["per"] <= 80]
        s.update(score(s, statistics.median(sp) if len(sp) >= 3 else gmed, cac_ok)); stocks.append(s)
        o = old.get(s["id"])
        if o and o != s["verdict"] and s["cat"] is not None and o != "Données insuffisantes":
            notify(f"{s['n']} : {o} -> {s['verdict']} (score {s['score']}/100, cours {s['p']} EUR)", s["cat"] in (0, 4))
            hist_log.append({"t": now.strftime("%d/%m %H:%M"), "n": s["n"], "de": o, "a": s["verdict"], "score": s["score"]})
    fired = set(prev.get("fired", []))
    for al in alerts:
        s = next((x for x in stocks if x["id"] == al.get("id")), None)
        for kind in ("above", "below"):
            if s and kind in al:
                key = f"{al['id']}:{kind}:{al[kind]}"; hit = s["p"] >= al[kind] if kind == "above" else s["p"] <= al[kind]
                if hit and key not in fired: notify(f"Alerte prix : {s['n']} {'au-dessus' if kind == 'above' else 'sous'} {al[kind]} EUR (cours {s['p']} EUR)", True); fired.add(key)
                elif not hit: fired.discard(key)
    summ = prev.get("summary"); mn = now.hour*60 + now.minute
    if now.weekday() < 5 and mn >= 1020 and summ != today and len(stocks) > 5:
        top = sorted(stocks, key=lambda x: -x["score"])
        notify("Résumé de 17h. Meilleurs : " + ", ".join(f"{x['n']} {x['score']}" for x in top[:3]) + " | Plus faibles : " + ", ".join(f"{x['n']} {x['score']}" for x in top[-3:]), False); summ = today
    opn = now.weekday() < 5 and 540 <= mn <= 1055
    dump(DATA, {"updated": datetime.datetime.utcnow().isoformat() + "Z", "market": {"open": opn, "cac_ok": cac_ok, "cac": cac_p},
                "backtest": stats, "fired": sorted(fired), "summary": summ, "stocks": stocks})
    dump(INTRA, {"d": it}); dump(HIST, hist_log[-300:]); dump(FUND, fc)
    if daily_prev.get("date") != today and dl: dump(DAILY, {"date": today, "d": dl})

if __name__ == "__main__":
    main()
