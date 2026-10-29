#!/usr/bin/env python3
"""poh marketing · constrói o ficheiro cifrado da Área de Cliente (clientes.json).

Uso:  python3 build_portal.py <pasta_raw> <saida.json>
A pasta_raw tem 6 ficheiros JSON, cada um com a lista "results" de uma consulta SQL ao Notion:
  clientes.json publicacoes.json gravacoes.json ideias.json guioes.json relatorios.json
Cada cliente com "Código do portal" preenchido recebe um bloco cifrado (AES-GCM, chave PBKDF2 do código).
Só quem tem o código consegue ler o seu bloco.
"""
import json, os, sys, re, base64, hashlib, datetime
from zoneinfo import ZoneInfo
try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    os.system(f"{sys.executable} -m pip install -q --break-system-packages cryptography")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ITER = 150000
TZ = ZoneInfo("Europe/Lisbon")

def norm(code): return re.sub(r"[^A-Z0-9]", "", (code or "").upper())
def cid(code): return hashlib.sha256(("poh|" + norm(code)).encode()).hexdigest()[:16]
def pid(url): return re.sub(r"[^0-9a-f]", "", (url or "").split("/")[-1].split("?")[0])[-32:]

def rels(v):
    if not v: return []
    try: return [pid(u) for u in json.loads(v)]
    except Exception: return []

def lst(v):
    if not v: return []
    try: return json.loads(v)
    except Exception: return [v]

def load(raw, name):
    p = os.path.join(raw, name)
    if not os.path.exists(p): return []
    d = json.load(open(p, encoding="utf-8"))
    return d.get("results", d) if isinstance(d, dict) else d

def dt(v):
    """Data do Notion -> (ISO local, tem_hora)"""
    if not v: return None, False
    v = v.strip()
    if len(v) <= 10: return v, False
    try:
        d = datetime.datetime.fromisoformat(v.replace("Z", "+00:00"))
        if d.tzinfo is None: d = d.replace(tzinfo=datetime.timezone.utc)
        return d.astimezone(TZ).strftime("%Y-%m-%dT%H:%M"), True
    except Exception:
        return v[:10], False

def enc(code, obj):
    key_src = norm(code).encode()
    salt = os.urandom(16); iv = os.urandom(12)
    key = hashlib.pbkdf2_hmac("sha256", key_src, salt, ITER, 32)
    ct = AESGCM(key).encrypt(iv, json.dumps(obj, ensure_ascii=False).encode(), None)
    b = lambda x: base64.b64encode(x).decode()
    return {"s": b(salt), "i": b(iv), "d": b(ct)}

def main(raw, out):
    now = datetime.datetime.now(TZ)
    ym = now.strftime("%Y-%m")
    clientes = load(raw, "clientes.json")
    pubs = load(raw, "publicacoes.json"); grav = load(raw, "gravacoes.json")
    ideias = load(raw, "ideias.json"); guioes = load(raw, "guioes.json"); rels_ = load(raw, "relatorios.json")
    blobs = {}
    for c in clientes:
        code = c.get("Código do portal")
        if not norm(code) or len(norm(code)) < 12: continue
        me = pid(c.get("url"))
        mine = lambda rows: [r for r in rows if me in rels(r.get("Cliente"))]
        P = []
        for r in mine(pubs):
            d, h = dt(r.get("date:Data de publicação:start"))
            P.append({"t": r.get("Publicação") or "Publicação", "e": r.get("Estado") or "", "f": r.get("Formato") or "",
                      "pl": lst(r.get("Plataforma")), "d": d, "h": h, "leg": r.get("Legenda") or "", "hs": r.get("Hashtags") or "",
                      "lk": r.get("Link do post") or "", "ap": r.get("Aprovação do cliente") or "", "id": pid(r.get("url"))[-6:]})
        G = []
        for r in mine(grav):
            if (r.get("Estado") or "") == "Cancelada": continue
            d, h = dt(r.get("date:Data:start"))
            G.append({"t": r.get("Sessão") or "Gravação", "e": r.get("Estado") or "", "tp": lst(r.get("Tipo")), "loc": r.get("Local") or "", "d": d, "h": h})
        I = [{"t": r.get("Ideia"), "e": r.get("Estado") or "", "f": r.get("Formato") or "", "pi": r.get("Pilar") or "",
              "hk": r.get("Hook") or "", "ds": r.get("Descrição") or ""}
             for r in mine(ideias) if r.get("Ideia") and (r.get("Estado") or "") != "Descartada"]
        S = [{"t": r.get("Guião"), "e": r.get("Estado") or "", "f": r.get("Formato") or "", "g": r.get("Gancho (0–3s)") or "",
              "tx": r.get("Texto no ecrã") or "", "pr": r.get("Preparar antes") or "", "au": r.get("Áudio") or "",
              "leg": r.get("Legenda") or "", "dur": r.get("Duração (s)"), "d": dt(r.get("date:Data de gravação:start"))[0]}
             for r in mine(guioes) if r.get("Guião")]
        R = []
        for r in mine(rels_):
            if (r.get("Estado") or "") != "Enviado": continue
            R.append({"t": r.get("Relatório"), "m": (r.get("date:Mês:start") or "")[:7], "al": r.get("Alcance"), "vi": r.get("Visualizações"),
                      "in": r.get("Interações"), "si": r.get("Seguidores início"), "sf": r.get("Seguidores fim"), "pf": r.get("Publicações feitas"),
                      "ok": r.get("O que funcionou") or "", "mel": r.get("A melhorar no próximo mês") or "", "best": r.get("Melhor publicação") or ""})
        R.sort(key=lambda x: x["m"], reverse=True)
        inm = lambda d: bool(d) and d[:7] == ym
        meta_p = c.get("Publicações por mês") or 0; meta_g = c.get("Gravações por mês") or 0
        prog = {
            "gravado": [sum(1 for g in G if g["e"] in ("Gravada", "Editada") and inm(g["d"])), meta_g],
            "editado": [sum(1 for p in P if p["e"] in ("Para aprovação", "Aprovado", "Agendado", "Publicado") and inm(p["d"])), meta_p],
            "publicado": [sum(1 for p in P if p["e"] == "Publicado" and inm(p["d"])), meta_p],
        }
        data = {"nome": c.get("Cliente"), "setor": c.get("Setor") or "", "mod": c.get("Modalidade") or "", "pac": c.get("Pacote") or "",
                "valor": c.get("Valor mensal"), "redes": lst(c.get("Redes geridas")), "metaP": meta_p, "metaG": meta_g,
                "inicio": c.get("date:Início do contrato:start"), "contacto": c.get("Pessoa de contacto") or "",
                "prog": prog, "pubs": sorted(P, key=lambda x: x["d"] or "9999"), "grav": sorted(G, key=lambda x: x["d"] or "9999"),
                "ideias": I, "guioes": S, "rel": R, "mes": ym}
        blobs[cid(code)] = enc(code, data)
    json.dump({"v": 1, "it": ITER, "updated": now.strftime("%Y-%m-%dT%H:%M"), "c": blobs}, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"ok: {len(blobs)} clientes cifrados -> {out}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
