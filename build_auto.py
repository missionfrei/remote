#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Auto-Board Generator (Missionfrei / GoRemote)
--------------------------------------------------
Baut die index.html aus (1) automatischen Job-Feeds und (2) einer
manuellen Schicht (manual-jobs.json), die NIE automatisch geloescht wird.

- Live-Lauf (auf GitHub Actions):   python build_auto.py
- Lokaler Demo-Lauf (Cowork, kein Netz): python build_auto.py --mock

Design: uebernimmt template.html (das aktuelle Board) unveraendert und
ersetzt nur die 7 Bereichs-Sektionen. Login-Gate, Chips, Favoriten-Sterne,
Freelance, Toolbox, Footer bleiben wie sie sind.
"""
import json, re, sys, os, datetime, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "template.html")
MANUAL   = os.path.join(HERE, "manual-jobs.json")
OUT      = os.path.join(HERE, "index.html")
MOCK     = "--mock" in sys.argv
TODAY    = datetime.date.today().strftime("%d.%m.%Y")

# ---------- 7 Bereiche: Reihenfolge, Farbe, Label ----------
BEREICHE = [
    ("service",  "#0e7a52", "🟢 Service"),
    ("buero",    "#b07d10", "🟡 Büro & Orga"),
    ("start",    "#c2610c", "🟠 Schnell-Start"),
    ("sprache",  "#6d3fb0", "🟣 Sprache & Text"),
    ("marketing","#1e57b0", "🔵 Marketing & Kreativ"),
    ("vertrieb", "#b3261e", "🔴 Vertrieb & Sales"),
    ("it",       "#33333b", "⚫ IT & Tech"),
]

# ---------- Bereich-Zuordnung nach Stichwoertern (Titel/Tags) ----------
BEREICH_KW = {
    "service":  ["kundenservice","kundenbetreu","customer support","customer service","customer care","customer success","support agent","service agent","reservation","booking","reise","travel","hospitality","concierge","call center","callcenter","kundenberat","beschwerde"],
    "buero":    ["buchhalt","accounting","accountant","finance","finanzbuch","lohn","payroll","steuerfach","controlling","sachbearbeit","backoffice","back office","back-office","assistenz","assistant","verwaltung","admin","office manager","datenerfassung","data entry","dateneingabe"],
    "start":    [],   # frueher Mikrojobs - jetzt raus (Paul). Sektion zeigt nur noch manuelle Freelance-/Portal-Eintraege.
    "sprache":  ["übersetz","ubersetz","translat","lektor","proofread","texter","content writer","copywriter","redaktion","tutor","nachhilfe","language teacher","sprachlehrer"],
    "marketing":["marketing","social media","seo","content creator","content manager","grafik","design","designer","creative","video","brand","paid ads","performance market","kampagne","community manager"],
    "vertrieb": ["sales","vertrieb","sdr","sales development","setter","closer","business development","account executive","akquise","inside sales"],
    "it":       ["developer","engineer","software","devops","entwickl","programmier","backend","frontend","fullstack","full stack","data scientist","data analyst","qa engineer","it-support","it support","system admin","kotlin","python","javascript","react"],
}
BEREICH_ORDER = [b[0] for b in BEREICHE]

DE_MARKERS = ["deutsch","german","(m/w/d)","m/w/d","mwd","stelle","mitarbeiter","kundenbetreu","buchhalt","vertrieb","home office","homeoffice"]
WORLD_MARKERS = ["worldwide","anywhere","weltweit","global","work from anywhere","location independent","location-independent","anywhere in the world","remote worldwide","international remote","fully remote worldwide",
    "ortsunabhängig","ortsunabhaengig","von überall","von ueberall","standortunabhängig","standortunabhaengig","überall arbeiten","ueberall arbeiten","remote weltweit","weltweit remote","von zuhause aus überall"]
EU_MARKERS = ["europe","eu ","emea","cet","european","europaweit","eu-weit","euweit","innerhalb europas","remote in europa","eu remote","europe remote","remote europe","remote (europe)","eu-remote"]
EINSTEIGER_MARKERS = ["junior","entry","einsteiger","quereinstieg","quereinsteiger","no experience","keine erfahrung","berufseinsteiger","trainee","aushilfe","praktik"]
BLOCK = ["werkstud","working student",   # Paul: keine Werkstudenten
    # Paul: KEINE kleinen Nebenverdienst-/Mikrojobs (Umfragen, Klick-Tasks, Tests, KI-Datenlabeling, Transkription-Gigs)
    "umfrage","survey","paid survey","mikrojob","mikro-job","microtask","micro-task","clickwork","crowdwork","crowdsurf",
    "usability test","usability-test","website test","websites testen","produkttest","playtester","beta-test",
    "data annotation","datenannotation","annotator","data labeling","data labelling","daten labeln","rater","search evaluator","ads rating",
    "transcription","transkription","transkribent","untertitel erstellen",
    "ki-training","ki-daten","ki-sprachdaten","ki-trainer","ki-reviewer","ki-community","ai trainer","ai reviewer","audio evaluation","data evaluation",
    "get-paid","get paid to","paid to click","faucet","cashback","nebenverdienst","praemien sammeln","belohnungen verdienen"]

def esc(s):
    return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").strip()

def clean_text(s, n=170):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:n].rsplit(" ",1)[0] + ("…" if len(s) > n else "")

def detect_bereich(text):
    t = text.lower()
    for ber in BEREICH_ORDER:
        for kw in BEREICH_KW[ber]:
            if kw in t:
                return ber
    return None   # kein Match -> nicht aufnehmen (haelt das Board fokussiert)

def detect(job):
    """Ergaenzt lang/region/level anhand des Textes."""
    t = (job["title"] + " " + job.get("raw_loc","") + " " + job.get("raw_tags","") + " " + job.get("info","") + " " + job.get("raw_desc","")).lower()
    lang = "de" if any(m in t for m in DE_MARKERS) else "en"
    if any(m in t for m in WORLD_MARKERS): region = "world"
    elif any(m in t for m in EU_MARKERS):  region = "eu"
    else: region = "de"   # ohne expliziten Weltweit-/EU-Marker: als Deutschland-nur behandeln (-> wird gefiltert)
    level = "einsteiger" if any(m in t for m in EINSTEIGER_MARKERS) else "erfahren"
    return lang, region, level

# ---------- Feeds ----------
def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (MissionfreiBot)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8","replace"))

def from_arbeitnow(raw):
    out=[]
    for j in raw.get("data", []):
        if not j.get("remote"): continue   # arbeitnow ist gemischt - nur Remote-Jobs aufnehmen
        out.append(dict(title=j.get("title",""), company=j.get("company_name",""),
            url=j.get("url",""), info=clean_text(j.get("description","")),
            raw_tags=" ".join(j.get("tags",[]) or [])+" "+" ".join(j.get("job_types",[]) or []),
            raw_desc=clean_text(j.get("description",""), 1000),
            raw_loc=j.get("location","") + " remote"))
    return out

def from_remotive(raw):
    out=[]
    for j in raw.get("jobs", []):
        out.append(dict(title=j.get("title",""), company=j.get("company_name",""),
            url=j.get("url",""), info=clean_text(j.get("description","")),
            raw_tags=(j.get("category","")+" "+" ".join(j.get("tags",[]) or [])),
            raw_loc=j.get("candidate_required_location","")))
    return out

def _j(x):  # list-oder-string -> string
    if isinstance(x,list): return " ".join(str(i) for i in x)
    return str(x or "")

def from_jobicy(raw):
    out=[]
    for j in raw.get("jobs", []):
        out.append(dict(title=j.get("jobTitle",""), company=j.get("companyName",""),
            url=j.get("url",""), info=clean_text(j.get("jobExcerpt","")),
            raw_tags=_j(j.get("jobIndustry"))+" "+_j(j.get("jobType")),
            raw_loc=_j(j.get("jobGeo"))))
    return out

def from_remoteok(raw):
    out=[]
    for j in (raw if isinstance(raw,list) else []):
        if not isinstance(j,dict) or not j.get("position"): continue
        out.append(dict(title=j.get("position",""), company=j.get("company",""),
            url=j.get("url",""), info=clean_text(j.get("description","")),
            raw_tags=_j(j.get("tags")), raw_loc=(j.get("location") or "remote")))
    return out

def http_text(url):
    req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0 (MissionfreiBot)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8","replace")

# ---------- Link-Check (laeuft auf GitHub mit offenem Netz) ----------
UA_LC={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"}
def link_alive(url):
    """False NUR wenn der Link eindeutig tot ist (404/410). Alles andere (403/405/Timeout/DNS) -> behalten
    (Paul-Regel: nur sicher-tote Links entfernen)."""
    for method in ("HEAD","GET"):
        try:
            req=urllib.request.Request(url, method=method, headers=UA_LC)
            with urllib.request.urlopen(req, timeout=12) as r:
                return True
        except urllib.error.HTTPError as e:
            if e.code in (404,410): return False
            if method=="HEAD" and e.code in (403,405,501): continue  # HEAD verboten -> GET testen
            return True
        except Exception:
            return True   # Timeout/DNS/Verbindung -> im Zweifel behalten
    return True

def prune_dead(jobs, workers=24):
    if MOCK or not jobs: return jobs, 0
    import concurrent.futures as cf
    alive=[True]*len(jobs)
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        futs={ex.submit(link_alive, j["url"]): i for i,j in enumerate(jobs)}
        for f in cf.as_completed(futs):
            i=futs[f]
            try: alive[i]=f.result()
            except Exception: alive[i]=True
    kept=[j for j,a in zip(jobs,alive) if a]
    return kept, len(jobs)-len(kept)

def from_rss_generic(xmltext):
    """RSS ohne 'Firma: Titel'-Konvention (euremotejobs, nodesk, realworkfromanywhere)."""
    import xml.etree.ElementTree as ET
    out=[]
    try: root=ET.fromstring(xmltext)
    except Exception: return out
    for item in root.iter("item"):
        title=(item.findtext("title") or "").strip()
        if not title: continue
        link=(item.findtext("link") or "").strip()
        desc=item.findtext("description") or ""
        comp=""
        for ch in item:
            if ch.tag.endswith("creator") and ch.text: comp=ch.text.strip(); break
        out.append(dict(title=title, company=comp, url=link, info=clean_text(desc),
            raw_tags=(item.findtext("category") or ""), raw_desc=clean_text(desc,1000), raw_loc=""))
    return out

def from_himalayas(raw):
    out=[]
    for j in raw.get("jobs", []):
        loc=_j(j.get("locationRestrictions"))
        out.append(dict(title=j.get("title",""), company=j.get("companyName",""),
            url=j.get("guid") or j.get("applicationLink") or "",
            info=clean_text(j.get("excerpt") or j.get("description","")),
            raw_tags=_j(j.get("categories")),
            raw_loc=loc if loc else "worldwide"))
    return out

def from_workingnomads(raw):
    out=[]
    for j in (raw if isinstance(raw,list) else []):
        if not isinstance(j,dict): continue
        out.append(dict(title=j.get("title",""), company=j.get("company_name",""),
            url=j.get("url",""), info=clean_text(j.get("description","")),
            raw_tags=(j.get("category_name","")+" "+_j(j.get("tags"))),
            raw_loc=j.get("location","")))
    return out

def from_wwr(xmltext):
    import xml.etree.ElementTree as ET
    out=[]
    try: root=ET.fromstring(xmltext)
    except Exception: return out
    for item in root.iter("item"):
        title=(item.findtext("title") or "").strip()
        region=(item.findtext("region") or "")
        comp,pos = (title.split(":",1)+[""])[:2] if ":" in title else ("",title)
        out.append(dict(title=(pos.strip() or title), company=comp.strip(),
            url=(item.findtext("link") or ""), info=clean_text(item.findtext("description") or ""),
            raw_tags=(item.findtext("category") or ""), raw_loc=region))
    return out

# (name, url, normalizer, kind) - kind "json"|"text"
SOURCES = [
    # --- Deutschsprachig-orientiert (fuer die >=50%-Deutsch-Quote) ---
    ("arbeitnow",     "https://www.arbeitnow.com/api/job-board-api",         from_arbeitnow, "json"),
    ("arbeitnow-2",   "https://www.arbeitnow.com/api/job-board-api?page=2",  from_arbeitnow, "json"),
    ("arbeitnow-3",   "https://www.arbeitnow.com/api/job-board-api?page=3",  from_arbeitnow, "json"),
    ("arbeitnow-4",   "https://www.arbeitnow.com/api/job-board-api?page=4",  from_arbeitnow, "json"),
    ("arbeitnow-5",   "https://www.arbeitnow.com/api/job-board-api?page=5",  from_arbeitnow, "json"),
    ("remotive-de",   "https://remotive.com/api/remote-jobs?search=german",  from_remotive, "json"),
    ("remotive-de2",  "https://remotive.com/api/remote-jobs?search=deutsch", from_remotive, "json"),
    ("jobicy-de",     "https://jobicy.com/api/v2/remote-jobs?count=100&tag=german", from_jobicy, "json"),
    ("remoteok-de",   "https://remoteok.com/api?tags=german",         from_remoteok, "json"),
    # --- Weltweit (Volumen fuer die andere Haelfte) ---
    ("remotive",      "https://remotive.com/api/remote-jobs",         from_remotive, "json"),
    ("remotive-cs",   "https://remotive.com/api/remote-jobs?category=customer-support",   from_remotive, "json"),
    ("remotive-sales","https://remotive.com/api/remote-jobs?category=sales",              from_remotive, "json"),
    ("remotive-mkt",  "https://remotive.com/api/remote-jobs?category=marketing",          from_remotive, "json"),
    ("remotive-biz",  "https://remotive.com/api/remote-jobs?category=business",           from_remotive, "json"),
    ("remotive-data", "https://remotive.com/api/remote-jobs?category=data",               from_remotive, "json"),
    ("remotive-write","https://remotive.com/api/remote-jobs?category=writing",            from_remotive, "json"),
    ("remotive-fin",  "https://remotive.com/api/remote-jobs?category=finance-legal",      from_remotive, "json"),
    ("remotive-hr",   "https://remotive.com/api/remote-jobs?category=hr",                 from_remotive, "json"),
    ("remotive-pm",   "https://remotive.com/api/remote-jobs?category=project-management", from_remotive, "json"),
    ("remotive-all",  "https://remotive.com/api/remote-jobs?category=all-others",         from_remotive, "json"),
    ("jobicy",        "https://jobicy.com/api/v2/remote-jobs?count=100",             from_jobicy, "json"),
    ("jobicy-any",    "https://jobicy.com/api/v2/remote-jobs?count=100&geo=anywhere", from_jobicy, "json"),
    ("remoteok",      "https://remoteok.com/api",                     from_remoteok, "json"),
    ("himalayas",     "https://himalayas.app/jobs/api?limit=100",     from_himalayas, "json"),
    ("workingnomads", "https://www.workingnomads.com/api/exposed_jobs/", from_workingnomads, "json"),
    ("wwr",           "https://weworkremotely.com/remote-jobs.rss",   from_wwr, "text"),
    ("wwr-cs",        "https://weworkremotely.com/categories/remote-customer-support-jobs.rss",   from_wwr, "text"),
    ("wwr-salesmkt",  "https://weworkremotely.com/categories/remote-sales-and-marketing-jobs.rss", from_wwr, "text"),
    ("wwr-mgmtfin",   "https://weworkremotely.com/categories/remote-management-and-finance-jobs.rss", from_wwr, "text"),
    ("wwr-product",   "https://weworkremotely.com/categories/remote-product-jobs.rss",  from_wwr, "text"),
    ("wwr-allother",  "https://weworkremotely.com/categories/all-other-remote-jobs.rss", from_wwr, "text"),
    ("wwr-design",    "https://weworkremotely.com/categories/remote-design-jobs.rss",     from_wwr, "text"),
    # --- Neue Quellen (aus dem Hauptboard uebernommen, fuer die Zukunft) ---
    ("realworkfromanywhere","https://www.realworkfromanywhere.com/feed", from_rss_generic, "text"),
    ("euremotejobs",  "https://euremotejobs.com/feed/",                  from_rss_generic, "text"),
    ("nodesk",        "https://nodesk.co/remote-jobs/feed/",             from_rss_generic, "text"),
    ("jobspresso",    "https://jobspresso.co/remote-work/feed/",         from_rss_generic, "text"),
    ("remote3",       "https://remote3.co/feed",                         from_rss_generic, "text"),
]

def gather():
    jobs=[]
    if MOCK:
        for name in ("arbeitnow","remotive"):
            p=os.path.join(HERE,"mock",f"{name}.json")
            if os.path.exists(p):
                raw=json.load(open(p,encoding="utf-8"))
                fn={"arbeitnow":from_arbeitnow,"remotive":from_remotive}[name]
                jobs+=fn(raw); print(f"[mock] {name}: {len(fn(raw))}")
        return jobs
    for name,url,fn,kind in SOURCES:
        try:
            raw = http_text(url) if kind=="text" else http_json(url)
            got=fn(raw); jobs+=got
            print(f"[feed] {name}: {len(got)}")
        except Exception as e:
            print(f"[feed] {name} FEHLER (uebersprungen): {e}")
    return jobs

# ---------- Aufbereiten ----------
def process(raw_jobs):
    seen=set(); result=[]
    for j in raw_jobs:
        if not j.get("url") or not j.get("title"): continue
        blob=(j["title"]+" "+j.get("raw_tags","")+" "+j.get("info","")).lower()
        if any(b in blob for b in BLOCK): continue
        ber=detect_bereich(j["title"]+" "+j.get("raw_tags",""))
        if not ber: continue
        lang,region,level=detect(j)
        # WELTWEIT-FIRST (Paul-Vorgabe): KEINE reinen Deutschland-Stellen aufs Board.
        # Deutschsprachig weltweit/EU-ortsunabhaengig ODER englisch weltweit im Service/Einsteiger-Bereich.
        if region=="de": continue                        # "nur in Deutschland" -> raus
        if lang=="de":
            keep = region in ("world","eu")               # deutschsprachig: weltweit ODER EU-ortsunabhaengig
        else:
            keep = (region=="world" and ber in ("service","start","buero","sprache","marketing"))
        if not keep: continue
        u=j["url"].rstrip("/")
        if u in seen: continue
        seen.add(u)
        result.append(dict(title=j["title"], company=j.get("company",""),
            url=j["url"], info=j.get("info","") or "Remote-Stelle - Details ueber den Link.",
            lang=lang, region=region, level=level, bereich=ber, date=TODAY, fd=False, src="auto"))
    return result

def load_manual():
    if not os.path.exists(MANUAL): return []
    try: data=json.load(open(MANUAL,encoding="utf-8"))
    except Exception as e: print("manual-jobs.json Fehler:",e); return []
    out=[]
    for j in data:
        fd=bool(j.get("fd", True))
        out.append(dict(title=j["title"], company=j.get("company",""), url=j["url"],
            info=j.get("info",""), lang=j.get("lang","de"), region=j.get("region","de"),
            level=j.get("level","einsteiger"), bereich=j.get("bereich","service"),
            date=j.get("date",TODAY), fd=fd, src=j.get("src") or ("customer" if fd else "import")))
    return out

# ---------- Render ----------
def region_tag(r): return {"world":'<span class="tag world">🌍 Weltweit</span>',
    "eu":'<span class="tag eu">🇪🇺 EU</span>',"de":'<span class="tag de">🇩🇪 DE</span>'}.get(r,'')
def level_tag(l): return '<span class="tag lvl">🌱 Einsteiger</span>' if l=="einsteiger" else '<span class="tag">📈 Mit Erfahrung</span>'
def lang_tag(l):  return '<span class="tag delang">Deutsch</span>' if l=="de" else '<span class="tag">Englisch</span>'
def fd_tag(fd):   return '<span class="tag" style="background:#f3ead4;color:#a8842e;font-weight:650">⭐ Für dich</span>' if fd else ''

def card(j):
    return (f'<div class="card" data-bereich="{j["bereich"]}" data-level="{j["level"]}" data-lang="{j["lang"]}">\n'
            f'  <h3>{esc(j["title"])}</h3>\n  <div class="company">{esc(j["company"])}</div>\n'
            f'  <p class="info">{esc(j["info"])}</p>\n'
            f'  <div class="meta">{region_tag(j["region"])}{level_tag(j["level"])}{lang_tag(j["lang"])}{fd_tag(j["fd"])}'
            f'<span class="tag date">📅 {j["date"]}</span></div>\n'
            f'  <div class="go"><a href="{j["url"]}" target="_blank" rel="noopener">Zur Stelle →</a></div>\n</div>')

# Deckel pro Bereich - kippt den Mix Richtung Service/Buero statt IT-Flut
CAP={"service":300,"buero":150,"start":120,"sprache":100,"marketing":40,"vertrieb":40,"it":20}
def build_sections(jobs):
    by={b:[] for b in BEREICH_ORDER}
    for j in jobs: by[j["bereich"]].append(j)
    for b in by:  # Kunden + Importe immer behalten, nur Auto (Feed) deckeln
        keep=[j for j in by[b] if j.get("src")!="auto"]
        keep.sort(key=lambda x:(not x["fd"],))     # Kunden-Picks (Stern) zuerst
        au=[j for j in by[b] if j.get("src")=="auto"]
        by[b]=keep + au[:max(0, CAP.get(b,60)-len(keep))]
    html=[]
    for ber,color,label in BEREICHE:
        cards=by[ber]
        if not cards: continue
        html.append(f'<section data-ber="{ber}"><h2 style="border-left:4px solid {color};padding-left:12px">{label} <span class="cnt">{len(cards)} Stellen</span></h2>\n<div class="grid">\n'
                    + "\n".join(card(c) for c in cards) + "\n</div>\n</div></section>")
    return "\n\n".join(html), by

def main():
    tpl=open(TEMPLATE,encoding="utf-8").read()
    i0=tpl.find('<section data-ber="service"')
    i1=tpl.find('<section id="freelance"')
    assert i0>0 and i1>0, "Template-Grenzen nicht gefunden"
    head, tail = tpl[:i0], tpl[i1:]

    auto=process(gather())
    manual=load_manual()
    # Tote Links in der manuellen/Import-Schicht raus (laeuft auf GitHub mit offenem Netz)
    manual, dead = prune_dead(manual)
    print(f"[linkcheck] manuelle Schicht: {dead} tote Links entfernt -> {len(manual)} bleiben")

    man_urls={m["url"].rstrip("/") for m in manual}
    auto=[a for a in auto if a["url"].rstrip("/") not in man_urls]  # manuell gewinnt

    # --- Paul-Vorgabe: mindestens die Haelfte deutschsprachig (ueber das GANZE Board) ---
    # Kunden-Picks immer behalten; Englisch nur so weit, dass insgesamt Deutsch >= Englisch.
    # Pool-Reihenfolge: Importe (kuratiert) vor Auto (Feed) -> Feed-Englisch wird zuerst gekuerzt.
    cust=[m for m in manual if m["src"]=="customer"]
    pool=[m for m in manual if m["src"]!="customer"] + auto
    cust_de=sum(1 for m in cust if m["lang"]=="de"); cust_en=len(cust)-cust_de
    pool_de=[j for j in pool if j["lang"]=="de"]
    pool_en=[j for j in pool if j["lang"]!="de"]
    max_pool_en=max(0, (cust_de+len(pool_de)) - cust_en)
    pool_en=pool_en[:max_pool_en]
    alljobs=cust+pool_de+pool_en

    sections, by = build_sections(alljobs)
    total=len(alljobs); de=sum(1 for j in alljobs if j["lang"]=="de")
    world=sum(1 for j in alljobs if j["region"]=="world"); einst=sum(1 for j in alljobs if j["level"]=="einsteiger")

    # Stats im Head aktualisieren
    def setstat(label,val):
        nonlocal head
        head=re.sub(r'(<b>)\d+(</b><span>'+re.escape(label)+r')', r'\g<1>'+str(val)+r'\2', head, count=1)
    setstat("Positionen aktuell",total); setstat("weltweit machbar",world)
    setstat("Einsteiger-geeignet",einst); setstat("auf Deutsch",de)

    open(OUT,"w",encoding="utf-8").write(head+sections+"\n\n"+tail)
    pct = round(100*de/total) if total else 0
    n_c=sum(1 for j in alljobs if j.get("src")=="customer")
    n_i=sum(1 for j in alljobs if j.get("src")=="import")
    n_a=sum(1 for j in alljobs if j.get("src")=="auto")
    print(f"\nGEBAUT: {total} Stellen | de={de} ({pct}%) en={total-de} weltweit={world} einsteiger={einst}")
    print(f"   Kunden {n_c} + Import {n_i} + Auto {n_a} | tote Links entfernt: {dead}")
    for b,_,lbl in BEREICHE: print(f"   {lbl}: {len(by[b])}")
    print("->", OUT)

if __name__=="__main__":
    main()
