"""Estilos y comportamiento (filtro y orden de las tablas) del informe: en linea, sin dependencias ni red."""

CSS = """
:root{--fondo:#f6f7f9;--tarjeta:#fff;--texto:#1c2430;--suave:#5b6675;--borde:#dfe3e8;--ok:#1a7f4b;--okbg:#e4f5ec;
--aviso:#9a6700;--avisobg:#fff4d6;--error:#b3261e;--errorbg:#fde8e6;--acento:#1f4e78;--barra:#cfe0f1;--barraok:#8fd0ad}
@media (prefers-color-scheme:dark){:root{--fondo:#12161c;--tarjeta:#1b212a;--texto:#e6eaf0;--suave:#9aa6b6;--borde:#2c3541;
--ok:#59d08c;--okbg:#17332a;--aviso:#e8b94a;--avisobg:#3a2f12;--error:#ff8a80;--errorbg:#3b1d1b;--acento:#7fb6ea;--barra:#27415c;--barraok:#2f6b4f}}
*{box-sizing:border-box}body{margin:0;background:var(--fondo);color:var(--texto);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:28px 20px 8px;max-width:1280px;margin:0 auto}h1{margin:0 0 4px;font-size:26px}h2{font-size:19px;margin:34px 0 12px}
h3{font-size:16px;margin:18px 0 8px}main{max-width:1280px;margin:0 auto;padding:0 20px 60px}.suave{color:var(--suave)}
.estado{display:inline-block;padding:4px 12px;border-radius:999px;font-weight:700;font-size:14px}
.ok{background:var(--okbg);color:var(--ok)}.aviso{background:var(--avisobg);color:var(--aviso)}.error{background:var(--errorbg);color:var(--error)}
.tarjetas{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:18px 0}
.tarjeta{background:var(--tarjeta);border:1px solid var(--borde);border-radius:12px;padding:14px 16px}
.tarjeta b{display:block;font-size:26px;line-height:1.1}.tarjeta span{color:var(--suave);font-size:13px}
.tarjeta.error{border-color:var(--error)}.tarjeta.aviso{border-color:var(--aviso)}
.caja{background:var(--tarjeta);border:1px solid var(--borde);border-radius:12px;padding:14px 18px;margin:12px 0}
.alerta{border-left:5px solid;padding:8px 14px;margin:8px 0;border-radius:6px;word-break:break-word}
.alerta.error{border-color:var(--error);background:var(--errorbg);color:var(--texto)}.alerta.aviso{border-color:var(--aviso);background:var(--avisobg);color:var(--texto)}
.alerta.ok{border-color:var(--ok);background:var(--okbg);color:var(--texto)}
.tabla-caja{overflow-x:auto;background:var(--tarjeta);border:1px solid var(--borde);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:7px 10px;text-align:left;border-bottom:1px solid var(--borde);vertical-align:top}
th{position:sticky;top:0;background:var(--tarjeta);font-weight:600;cursor:pointer;white-space:nowrap}th:hover{color:var(--acento)}
tr:last-child td{border-bottom:0}td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:1px 9px;border-radius:999px;font-size:12px;font-weight:600}
.barra{background:var(--barra);border-radius:6px;height:10px;min-width:80px;overflow:hidden}.barra i{display:block;height:100%;background:var(--barraok)}
.barra.baja i{background:var(--aviso)}.barra.mala i{background:var(--error)}
.filtros{display:flex;gap:10px;flex-wrap:wrap;margin:8px 0}.filtros input,.filtros select{padding:7px 10px;border:1px solid var(--borde);
border-radius:8px;background:var(--tarjeta);color:var(--texto);font-size:14px;min-width:200px}
a{color:var(--acento)}details{margin:10px 0}summary{cursor:pointer;font-weight:600}
pre.log{background:var(--tarjeta);border:1px solid var(--borde);border-radius:10px;padding:12px;overflow:auto;max-height:520px;font-size:12.5px;line-height:1.45}
.mono{font-family:ui-monospace,Consolas,monospace;font-size:12.5px}.ruta{color:var(--suave);font-size:12.5px}
nav{position:sticky;top:0;background:var(--fondo);padding:8px 0;z-index:5;display:flex;gap:14px;flex-wrap:wrap;border-bottom:1px solid var(--borde);font-size:14px}
@media print{nav,.filtros{display:none}body{background:#fff}}
"""

JS = """
function normaliza(t){return (t||'').toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g,'')}
function filtra(id){var t=document.getElementById(id),q=normaliza(document.getElementById(id+'-q').value),
 s=document.getElementById(id+'-s'),v=s?s.value:'',n=0;
 for(var i=1;i<t.rows.length;i++){var r=t.rows[i],ok=normaliza(r.innerText).indexOf(q)>=0&&(!v||r.getAttribute('data-f')===v);
  r.style.display=ok?'':'none';if(ok)n++}
 var c=document.getElementById(id+'-n');if(c)c.textContent=n+' de '+(t.rows.length-1)}
function ordena(id,col,num){var t=document.getElementById(id),f=Array.prototype.slice.call(t.rows,1),
 asc=t.getAttribute('data-o')!==String(col);t.setAttribute('data-o',asc?col:'');
 f.sort(function(a,b){var x=a.cells[col].getAttribute('data-v')||a.cells[col].innerText,y=b.cells[col].getAttribute('data-v')||b.cells[col].innerText;
  if(num){x=parseFloat(x)||0;y=parseFloat(y)||0;return asc?x-y:y-x}return asc?x.localeCompare(y,'es'):y.localeCompare(x,'es')});
 f.forEach(function(r){t.tBodies[0].appendChild(r)})}
"""
