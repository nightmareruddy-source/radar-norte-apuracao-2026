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
const dom2=new JSDOM(fs.readFileSync(path.join(root,'painel.html'),'utf8'),{runScripts:'dangerously',beforeParse(w){w.fetch=()=>new Promise(()=>{});w.AbortController=AbortController;}});
state.municipios[0].votos=1;state.municipios[1].votos=500;state.municipios[2].votos=null;
dom2.window.render(state);
assert.equal(dom2.window.document.querySelector('#tb tr').children[3].textContent,'500');
assert(dom2.window.document.querySelector('#secoes').textContent.includes('1.250 de 5.000'));
state.resumo.apuracao='NAO_INICIADA';dom2.window.render(state);
assert.equal(dom2.window.document.querySelector('#tb tr').children[3].textContent,'1');
dom2.window.close();console.log('PASS: seções no topo; votos decrescentes apenas após início.');
const realState=JSON.parse(execFileSync(process.env.PYTHON||'python',['-c','import json;from test_simulado2026 import fixture_state;print(json.dumps(fixture_state()))'],{cwd:root,encoding:'utf8'}));
const dom3=new JSDOM(fs.readFileSync(path.join(root,'painel.html'),'utf8'),{runScripts:'dangerously',beforeParse(w){w.fetch=()=>new Promise(()=>{});w.AbortController=AbortController;}});
dom3.window.render(realState);
assert.equal(dom3.window.document.querySelector('#tb tr').children[3].textContent,'330');
assert(dom3.window.document.querySelector('#soma').textContent.includes('431'));
assert(dom3.window.document.querySelector('#apuracao').textContent.startsWith('FINAL'));
assert(!dom3.window.document.querySelector('#apuracao').textContent.includes('preparação'));
assert(dom3.window.document.querySelector('#ambiente').textContent.includes('SIMULADO'));
dom3.window.close();console.log('PASS: três respostas originais simulado TSE 2026 → parser → API → DOM, candidato de teste 68028, 431 votos.');
