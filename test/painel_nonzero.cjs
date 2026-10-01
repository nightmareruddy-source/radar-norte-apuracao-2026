// Synthetic integration check. NOT a regression against real 2022 results.
const {execFileSync}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {JSDOM}=require('jsdom');const root=path.resolve(__dirname,'..');
const state=JSON.parse(execFileSync(process.env.PYTHON||'python',['-c',`
import json,tempfile
from pathlib import Path
import radar_norte as r
with tempfile.TemporaryDirectory() as tmp:
 r.MOCK_DATA=Path(tmp);r.cycle(True);print(json.dumps(r.api_state()))
`],{cwd:root,encoding:'utf8'}));
const dom=new JSDOM(fs.readFileSync(path.join(root,'painel.html'),'utf8'),{runScripts:'dangerously',beforeParse(w){w.fetch=()=>new Promise(()=>{});w.AbortController=AbortController;}});
dom.window.render(state);const doc=dom.window.document;
assert.equal(state.resumo.soma_ultimos_dados,6150);
assert.equal(doc.querySelector('#tb tr').children[3].textContent,'123');
assert.equal(doc.querySelector('#apuracao').textContent,'PARCIAL');
assert(!doc.querySelector('#apuracao').textContent.includes('preparação'));
assert(doc.querySelector('#ambiente').textContent.includes('FICTÍCIOS'));
dom.window.close();console.log('PASS: mock Python → parser → API → DOM: 123 votos/cidade, PARCIAL, demonstração explícita. Não valida 2022.');
