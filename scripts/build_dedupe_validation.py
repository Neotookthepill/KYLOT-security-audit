#!/usr/bin/env python3
"""Construit une page HTML de validation des doublons clients depuis groups.json."""
import html
import json
import sys
from pathlib import Path


def esc(x):
    return html.escape(str(x or ""))


def label(g, i):
    names = g.get("names") or []
    phones = g.get("phones") or []
    name = names[i] if i < len(names) else ""
    phone = phones[i] if i < len(phones) else ""
    return f"{name} — {phone}" if phone else f"{name} (sans téléphone)"


def build(report_dir: Path) -> Path:
    groups = [g for g in json.loads((report_dir / "groups.json").read_text()) if g.get("type") == "client"]
    cards = []
    for g in groups:
        mids = g.get("member_ids") or []
        opts = "".join(
            f'<option value="{esc(m)}" {"selected" if m == g.get("keep_id") else ""}>{esc(label(g, i))}</option>'
            for i, m in enumerate(mids)
        )
        phone = " / ".join(x for x in (g.get("phones") or []) if x)
        postal = " / ".join(x for x in (g.get("postal_codes") or []) if x)
        sales = " / ".join(map(str, g.get("sales_per_member") or []))
        projects = " / ".join(map(str, g.get("projects_per_member") or []))
        warn = '<span class="warn">À vérifier</span>' if g.get("confidence") != "high" else ""
        cards.append(
            f'''<article class="card" data-group="{esc(g['group_id'])}">
  <div class="top"><h3>{esc(' / '.join(g.get('names') or []))}</h3>{warn}</div>
  <div class="facts">
    {f'<div><b>Téléphone</b> {esc(phone)}</div>' if phone else '<div><b>Téléphone</b> <span class="missing">aucun numéro</span></div>'}
    {f'<div><b>Code postal</b> {esc(postal)}</div>' if postal else ''}
    {f'<div><b>Ventes associées</b> {esc(sales)}</div>' if sales else ''}
    {f'<div><b>Chantiers associés</b> {esc(projects)}</div>' if projects else ''}
  </div>
  <div class="choice"><label class="yes"><input type="checkbox" data-approve="{esc(g['group_id'])}"> Oui, c’est le même client</label><span class="muted">Sinon, ne rien cocher.</span></div>
  <label class="keep">Fiche à garder <select data-keep="{esc(g['group_id'])}">{opts}</select></label>
</article>'''
        )
    page = f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Doublons clients — validation</title>
<style>body{{font-family:Inter,system-ui,sans-serif;background:#f6f8fb;color:#101828;margin:0;padding:20px}}main{{max-width:900px;margin:auto}}h1{{font-size:27px;margin:0 0 8px}}.intro{{color:#475467;line-height:1.6;margin:0 0 16px}}.why{{background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:15px;margin:0 0 18px;color:#475467;line-height:1.6}}.why b{{color:#101828}}.bar{{position:sticky;top:0;background:#fff;border:1px solid #e4e7ec;border-radius:12px;padding:12px;display:flex;gap:12px;align-items:center;margin-bottom:16px;z-index:2;flex-wrap:wrap}}button{{background:#101828;color:#fff;border:0;border-radius:8px;padding:11px 15px;font-weight:600;cursor:pointer}}.card{{background:#fff;border:1px solid #e4e7ec;border-radius:14px;padding:16px;margin:0 0 12px}}.top{{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}}h3{{margin:0;font-size:18px}}.warn{{font-size:11px;background:#fffaeb;color:#b54708;padding:4px 8px;border-radius:20px;white-space:nowrap}}.facts{{display:grid;gap:4px;margin:10px 0;padding:10px;background:#f9fafb;border-radius:8px;font-size:13px;color:#475467}}.facts b{{color:#344054}}.missing{{color:#b42318;font-weight:600}}.choice{{margin-top:10px;display:flex;gap:14px;align-items:center;flex-wrap:wrap}}.yes{{font-weight:600;color:#067647;display:flex;gap:8px;align-items:center}}.keep{{display:flex;gap:8px;align-items:center;margin-top:10px;font-size:13px;flex-wrap:wrap}}select{{max-width:100%;padding:8px;border:1px solid #d0d5dd;border-radius:8px;background:#fff;font-size:13px}}.muted{{color:#667085;font-size:12px}}.note{{font-size:13px;color:#475467;background:#eef4ff;border:1px solid #c7d7fe;padding:12px;border-radius:10px;margin-bottom:18px;line-height:1.5}}</style></head><body><main>
<h1>Doublons clients à valider</h1>
<p class="intro">Ces fiches semblent appartenir au même client. Pour chacune, indique si c’est bien le même client, puis choisis la fiche à garder.</p>
<div class="why"><b>Pourquoi y a-t-il des doublons ?</b><br>Les données viennent de plusieurs imports et de saisies faites à des moments différents. Le même nom a parfois été écrit avec des majuscules, des accents ou un espace différent. L’ancien système n’empêchait pas de créer deux fiches pour la même personne. Rien n’est supprimé automatiquement : le client valide d’abord.</div>
<div class="note"><b>Important :</b> la fiche recommandée est celle qui a un téléphone et le plus d’historique. Le bouton « Sélectionner les cas évidents » coche les groupes dont le nom est identique et les coordonnées concordent. Le client peut décocher un cas douteux (ex. deux sociétés homonymes).</div>
<div class="bar"><button id="select-safe">Sélectionner les cas évidents</button><button id="download">Télécharger les validations</button><span id="count" class="muted">0 client validé</span></div>
{''.join(cards)}
</main><script>
const groups={json.dumps(groups, ensure_ascii=False)};
function updateCount(){{document.getElementById('count').textContent=document.querySelectorAll('[data-approve]:checked').length+' client(s) validé(s)';}}
document.querySelectorAll('[data-approve]').forEach(x=>x.addEventListener('change',updateCount));
document.getElementById('select-safe').onclick=()=>{{for(const g of groups){{if(g.confidence==='high'){{const box=document.querySelector('[data-approve="'+g.group_id+'"]');if(box)box.checked=true;}}}}updateCount();}};
document.getElementById('download').onclick=()=>{{const cols=['group_id','type','confidence','company_id','normalized_name','sale_id','keep_id','member_ids','names','phones','postal_codes','sales_per_member','projects_per_member','notes_per_member','statuses','scheduled_dates','amounts','sale_dates','new_name','approve'];const q=v=>'"'+String(v??'').replace(/"/g,'""')+'"';const lines=[cols.join(',')];for(const g of groups){{const box=document.querySelector(`[data-approve="${{g.group_id}}"]`);if(!box||!box.checked)continue;const sel=document.querySelector(`[data-keep="${{g.group_id}}"]`);const row={{...g,keep_id:sel?sel.value:g.keep_id,approve:'yes'}};lines.push(cols.map(c=>q(Array.isArray(row[c])?row[c].join('|'):row[c])).join(','));}}const blob=new Blob([lines.join('\\n')],{{type:'text/csv;charset=utf-8'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='validations-clients.csv';a.click();URL.revokeObjectURL(a.href);}};
</script></body></html>'''
    out = report_dir / "validation-clients.html"
    out.write_text(page, encoding="utf-8")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("Usage: build_dedupe_validation.py <report_dir>")
    print(build(Path(sys.argv[1])))
