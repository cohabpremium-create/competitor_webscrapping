"""
Competitor Scout — Cohab Premium vs Valor Imobiliária
Roda semanalmente via GitHub Actions e envia relatório por e-mail.
"""

import os, json, time, re, unicodedata, smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import anthropic

# ── Configurações ──────────────────────────────────────────────
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]
GMAIL_USER         = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
EMAIL_DESTINO      = os.environ["EMAIL_DESTINO"]

VALOR_URLS = [
    "https://valorimobiliaria.com.br/imoveis-avulsos",
    "https://valorimobiliaria.com.br/imoveis-lancamentos",
    "https://valorimobiliaria.com.br/alugueis-residenciais",
    "https://valorimobiliaria.com.br/alugueis-comerciais",
]
COHAB_URLS = [
    "https://www.cohabpremium.com.br/total-de-imoveis/comprar/Aracaju-5",
    "https://www.cohabpremium.com.br/total-de-imoveis/comprar/Aracaju-5?pag=2",
    "https://www.cohabpremium.com.br/total-de-imoveis/alugar/Aracaju-5",
    "https://www.cohabpremium.com.br/total-de-imoveis/alugar/Aracaju-5?pag=2",
]

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Normalização ───────────────────────────────────────────────
def normalizar(texto: str) -> str:
    if not texto:
        return ""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"\b(cond|condominio|edificio|edf|mansao|residencial|residence|res)\b", "", texto.lower())
    return re.sub(r"\s+", " ", texto).strip()

def levenshtein(a: str, b: str) -> int:
    m, n = len(a), len(b)
    dp = [[max(i, j) if i == 0 or j == 0 else 0 for j in range(n+1)] for i in range(m+1)]
    for i in range(1, m+1):
        for j in range(1, n+1):
            dp[i][j] = dp[i-1][j-1] if a[i-1] == b[j-1] else 1 + min(dp[i-1][j], dp[i][j-1], dp[i-1][j-1])
    return dp[m][n]

def similaridade(a: str, b: str) -> float:
    na, nb = normalizar(a), normalizar(b)
    if not na or not nb:
        return 0.0
    dist = levenshtein(na, nb)
    return 1 - dist / max(len(na), len(nb))

# ── Coleta via Claude ──────────────────────────────────────────
SYSTEM_SCRAPER = """Você é um raspador de dados imobiliários. Dado uma URL de listagem imobiliária,
extraia TODOS os imóveis visíveis nessa página.
Retorne SOMENTE um array JSON com objetos:
{titulo, modalidade, tipo, bairro, condominio, area_m2, quartos, suites, vagas, preco, url, foto}

Regras:
- modalidade: "venda" ou "aluguel"
- tipo: "apartamento", "casa", "comercial", "terreno" ou "outro"
- bairro: minúsculo, sem acento
- condominio: nome do condomínio/edifício (ou "" se não houver)
- area_m2, quartos, suites, vagas: número inteiro (ou null)
- preco: número sem formatação (ou null)
- url: URL completa do imóvel
- foto: URL da primeira imagem (ou "")
Nenhum texto extra, somente o array JSON válido."""

def fetch_imoveis(url: str) -> list[dict]:
    print(f"  → {url}")
    try:
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            system=SYSTEM_SCRAPER,
            messages=[{"role": "user", "content": f"Extraia os imóveis desta página: {url}"}],
        )
        txt = msg.content[0].text.strip()
        txt = re.sub(r"```json|```", "", txt).strip()
        start, end = txt.find("["), txt.rfind("]")
        if start >= 0 and end > start:
            return json.loads(txt[start:end+1])
    except Exception as e:
        print(f"     ⚠ Erro: {e}")
    return []

def coletar(urls: list[str], nome: str) -> list[dict]:
    print(f"\n📡 Coletando {nome}...")
    todos = []
    for url in urls:
        items = fetch_imoveis(url)
        todos.extend(items)
        print(f"     {len(items)} imóveis | total: {len(todos)}")
        time.sleep(1)
    return todos

# ── Comparação ─────────────────────────────────────────────────
def comparar(valor: list[dict], cohab: list[dict]) -> dict:
    matched, uncertain, opportunities = [], [], []

    for v in valor:
        best, best_score, best_level = None, 0, 0

        for c in cohab:
            nv, nc = normalizar(v.get("condominio", "")), normalizar(c.get("condominio", ""))
            if nv and nc and len(nv) > 2 and len(nc) > 2:
                sim = similaridade(nv, nc)
                if sim > 0.75 and v.get("tipo") == c.get("tipo"):
                    if sim > best_score:
                        best_score, best, best_level = sim, c, 1
                    continue

            hits = 0
            if normalizar(v.get("bairro","")) == normalizar(c.get("bairro","")) and v.get("bairro"): hits += 1
            if v.get("modalidade") == c.get("modalidade"): hits += 1
            if v.get("tipo") == c.get("tipo"): hits += 1
            if v.get("area_m2") and c.get("area_m2"):
                if abs(v["area_m2"] - c["area_m2"]) / max(v["area_m2"], c["area_m2"]) <= 0.15:
                    hits += 1
            if v.get("quartos") is not None and v.get("quartos") == c.get("quartos"): hits += 1
            if hits >= 4 and hits > best_score:
                best_score, best, best_level = hits, c, 2

        if best and best_level == 1:
            matched.append({"valor": v, "cohab": best, "confianca": "alta"})
        elif best and best_level == 2:
            uncertain.append({"valor": v, "cohab": best, "confianca": "media", "score": best_score})
        else:
            opportunities.append(v)

    return {"matched": matched, "uncertain": uncertain, "opportunities": opportunities}

# ── Geração do relatório HTML ──────────────────────────────────
def fmt_preco(v) -> str:
    if not v:
        return "—"
    return f"R$ {int(v):,}".replace(",", ".")

def gerar_html(resultado: dict, n_valor: int, n_cohab: int) -> str:
    opps      = resultado["opportunities"]
    matched   = resultado["matched"]
    uncertain = resultado["uncertain"]
    data_hoje = datetime.now().strftime("%d/%m/%Y")

    def card_opp(o):
        foto = f'<img src="{o["foto"]}" style="width:100%;height:140px;object-fit:cover;border-radius:8px 8px 0 0">' if o.get("foto") else '<div style="height:60px;display:flex;align-items:center;justify-content:center;font-size:28px">🏠</div>'
        return f"""
        <div style="background:#fff;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.1);overflow:hidden;break-inside:avoid;margin-bottom:16px">
          {foto}
          <div style="padding:12px">
            <div style="font-size:11px;font-weight:700;color:{'#276749' if o.get('modalidade')=='venda' else '#2c5282'};text-transform:uppercase;margin-bottom:4px">{o.get('modalidade','—')} · {o.get('tipo','—')}</div>
            <div style="font-size:13.5px;font-weight:700;color:#1a202c;margin-bottom:2px">{o.get('titulo') or 'Sem título'}</div>
            <div style="font-size:12px;color:#64748b;margin-bottom:6px">📍 {o.get('bairro','—')}{' · '+o['condominio'] if o.get('condominio') else ''}</div>
            <div style="font-size:12px;color:#64748b;margin-bottom:8px">
              {'📐 '+str(o['area_m2'])+'m²  ' if o.get('area_m2') else ''}
              {'🛏 '+str(o['quartos'])+'q  ' if o.get('quartos') else ''}
              {'🚗 '+str(o['vagas'])+'v' if o.get('vagas') else ''}
            </div>
            <div style="font-size:15px;font-weight:800;color:#1a365d;margin-bottom:8px">{fmt_preco(o.get('preco'))}{'/mês' if o.get('modalidade')=='aluguel' else ''}</div>
            <a href="{o.get('url','#')}" style="display:inline-block;background:#ebf4ff;color:#2b6cb0;padding:6px 12px;border-radius:6px;font-size:12px;font-weight:600;text-decoration:none">🔗 Ver na Valor</a>
          </div>
        </div>"""

    opp_cards = "".join(card_opp(o) for o in opps)

    rows_match = "".join(f"""
        <tr style="border-bottom:1px solid #f0f4f8">
          <td style="padding:10px 12px"><a href="{m['valor'].get('url','#')}" style="color:#2b6cb0;font-weight:600;text-decoration:none">{m['valor'].get('titulo','—')}</a><br><small style="color:#64748b">{m['valor'].get('condominio','')}</small></td>
          <td style="padding:10px 12px"><a href="{m['cohab'].get('url','#')}" style="color:#276749;font-weight:600;text-decoration:none">{m['cohab'].get('titulo','—')}</a></td>
          <td style="padding:10px 12px;color:#64748b">{m['valor'].get('bairro','—')}</td>
          <td style="padding:10px 12px"><span style="background:{'#c6f6d5;color:#276749' if m['confianca']=='alta' else '#feebc8;color:#7b341e'};border-radius:20px;padding:2px 10px;font-size:11px;font-weight:700">{m['confianca'].upper()}</span></td>
        </tr>""" for m in matched)

    rows_uncert = "".join(f"""
        <tr style="border-bottom:1px solid #f0f4f8">
          <td style="padding:10px 12px"><a href="{u['valor'].get('url','#')}" style="color:#2b6cb0;font-weight:600;text-decoration:none">{u['valor'].get('titulo','—')}</a></td>
          <td style="padding:10px 12px"><a href="{u['cohab'].get('url','#')}" style="color:#276749;font-weight:600;text-decoration:none">{u['cohab'].get('titulo','—')}</a></td>
          <td style="padding:10px 12px;color:#64748b">{u['valor'].get('bairro','—')}</td>
          <td style="padding:10px 12px;color:#64748b">{u.get('score',0)}/5 critérios</td>
        </tr>""" for u in uncertain)

    return f"""<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8"><title>Competitor Scout — {data_hoje}</title></head>
<body style="font-family:'Segoe UI',system-ui,sans-serif;background:#f0f4f8;margin:0;padding:20px">
<div style="max-width:900px;margin:0 auto">

  <!-- Header -->
  <div style="background:linear-gradient(135deg,#1a365d,#2b6cb0);color:#fff;border-radius:14px;padding:28px;margin-bottom:24px">
    <h1 style="margin:0 0 6px;font-size:22px">🔍 Competitor Scout — Relatório Semanal</h1>
    <p style="margin:0;opacity:.8;font-size:14px">Gerado em {data_hoje} · Cohab Premium vs Valor Imobiliária</p>
    <div style="display:flex;gap:24px;margin-top:18px;flex-wrap:wrap">
      <div style="text-align:center"><div style="font-size:28px;font-weight:800">{n_valor}</div><div style="font-size:12px;opacity:.8">imóveis na Valor</div></div>
      <div style="text-align:center"><div style="font-size:28px;font-weight:800">{n_cohab}</div><div style="font-size:12px;opacity:.8">imóveis na Cohab</div></div>
      <div style="text-align:center"><div style="font-size:28px;font-weight:800">{len(matched)}</div><div style="font-size:12px;opacity:.8">em ambos os sites</div></div>
      <div style="text-align:center;background:rgba(255,255,255,.2);border-radius:10px;padding:8px 16px"><div style="font-size:28px;font-weight:800">{len(opps)}</div><div style="font-size:12px;opacity:.8">🎯 oportunidades</div></div>
    </div>
  </div>

  <!-- Oportunidades -->
  <h2 style="color:#1a365d;font-size:18px;margin-bottom:14px">🎯 {len(opps)} Oportunidade{'s' if len(opps)!=1 else ''} de Captação</h2>
  <p style="color:#64748b;font-size:13px;margin-bottom:20px">Imóveis encontrados na Valor Imobiliária que <strong>não estão</strong> no portfólio da Cohab Premium.</p>
  <div style="columns:2;column-gap:16px">
    {opp_cards if opp_cards else '<p style="color:#94a3b8;text-align:center;padding:32px">Nenhuma oportunidade encontrada esta semana 🎉</p>'}
  </div>

  <!-- Matches -->
  <h2 style="color:#1a365d;font-size:18px;margin:32px 0 14px">🤝 {len(matched)} Imóvel(is) em Ambos os Sites</h2>
  <div style="background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="background:#f7fafc">
        <th style="padding:10px 12px;text-align:left;color:#475569;font-weight:600">Imóvel (Valor)</th>
        <th style="padding:10px 12px;text-align:left;color:#475569;font-weight:600">Correspondente (Cohab)</th>
        <th style="padding:10px 12px;text-align:left;color:#475569;font-weight:600">Bairro</th>
        <th style="padding:10px 12px;text-align:left;color:#475569;font-weight:600">Confiança</th>
      </tr></thead>
      <tbody>{rows_match or '<tr><td colspan="4" style="text-align:center;padding:24px;color:#94a3b8">Nenhum match confirmado</td></tr>'}</tbody>
    </table>
  </div>

  <!-- Incertos -->
  {"" if not uncertain else f'''
  <h2 style="color:#1a365d;font-size:18px;margin:32px 0 14px">🧐 {len(uncertain)} Par(es) para Revisão Manual</h2>
  <div style="background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead><tr style="background:#f7fafc">
        <th style="padding:10px 12px;text-align:left;color:#475569;font-weight:600">Imóvel (Valor)</th>
        <th style="padding:10px 12px;text-align:left;color:#475569;font-weight:600">Similar (Cohab)</th>
        <th style="padding:10px 12px;text-align:left;color:#475569;font-weight:600">Bairro</th>
        <th style="padding:10px 12px;text-align:left;color:#475569;font-weight:600">Similitude</th>
      </tr></thead>
      <tbody>{rows_uncert}</tbody>
    </table>
  </div>'''}

  <p style="text-align:center;color:#94a3b8;font-size:12px;margin-top:32px">Gerado automaticamente pelo Competitor Scout · GitHub Actions</p>
</div>
</body></html>"""

# ── Envio por e-mail ───────────────────────────────────────────
def enviar_email(html: str, n_opps: int):
    print("\n📧 Enviando e-mail...")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🎯 Competitor Scout — {n_opps} oportunidade{'s' if n_opps!=1 else ''} de captação [{datetime.now().strftime('%d/%m')}]"
    msg["From"]    = GMAIL_USER
    msg["To"]      = EMAIL_DESTINO
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, EMAIL_DESTINO, msg.as_string())
    print("   ✅ E-mail enviado!")

# ── Main ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 Competitor Scout iniciando...\n")

    valor_imoveis = coletar(VALOR_URLS, "Valor Imobiliária")
    cohab_imoveis = coletar(COHAB_URLS, "Cohab Premium")

    print(f"\n🔍 Comparando {len(valor_imoveis)} x {len(cohab_imoveis)} imóveis...")
    resultado = comparar(valor_imoveis, cohab_imoveis)

    n_opps    = len(resultado["opportunities"])
    n_matched = len(resultado["matched"])
    n_uncert  = len(resultado["uncertain"])
    print(f"   ✅ {n_matched} matches | 🧐 {n_uncert} incertos | 🎯 {n_opps} oportunidades")

    html = gerar_html(resultado, len(valor_imoveis), len(cohab_imoveis))

    with open("relatorio.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("📄 relatorio.html salvo.")

    enviar_email(html, n_opps)
    print("\n✅ Tudo pronto!")
