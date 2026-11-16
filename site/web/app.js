import {roles,conditions,conditionRounds,validate,toml,checkRun} from './contracts.mjs';
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let contract;
try{contract=await fetchJSON('contract.json',undefined,'Could not load the configuration contract. Reload the page to retry.');}
catch(e){message(e.message,true);}
let config=contract?structuredClone(contract.defaults):null,tab='scenario',run=null,session=null,approved=null,busy=false,admissionSeq=0,navigationSeq=0;
const titles={scenario:['Match configuration','Configure the actual Python engine and provider adapters.'],offline:['Offline execution','Run Split Span through the project CLI or inspect its recorded fixture.'],live:['Live test preparation','Export a bounded, explicitly approved configuration for the local CLI.'],evaluation:['Recorded-run evaluation','Inspect native schema-version-2 results, calls, phases, and observations.']};
const notes={communication_rounds:'0 commits only; 1 skips negotiation; 2 includes both communication phases.',max_turns:'Experiment stop limit; the room itself has a 12-turn deadline.',max_calls:'Every attempt counts. A full team phase reserves retry capacity.',max_attempts:'Includes the initial attempt.',max_output_tokens:'Per request, including provider reasoning where applicable.',history_turns:'Role-local history; zero keeps only the latest explicit note.',image_token_reserve:'Image allowance in the local cost estimate, not an input-token cap.',max_estimated_cost_usd:'Optional local estimate guard. Required here for a live-plan approval.'};
function message(v,error=false){$('status').textContent=v;$('status').classList.toggle('warn',error);}
function numeric(v){return Number.isFinite(v)?v:'';}
function sourceInfo(){
 const revision=contract.commit??'unavailable',state=contract.source_status??'unknown';
 const label='Build source revision · '+esc(revision.slice(0,7))+' · '+esc(state);
 return /^[0-9a-f]{40,64}$/.test(revision)?'<a href="https://github.com/dhar174/Parallax-Relay-AI-Game/tree/'+revision+'" target="_blank" rel="noopener">'+label+'</a>':label;
}
function input(label,attr,value,hint=''){if(attr.includes('type="number"'))value=numeric(value);return '<label>'+esc(label)+'<input '+attr+' value="'+esc(value)+'">'+(hint?'<small style="display:block;margin-top:5px;letter-spacing:0">'+esc(hint)+'</small>':'')+'</label>';}
function metric(label,value,hint=''){return '<div class="slot metric"><small>'+esc(label)+'</small><strong>'+esc(value)+'</strong><p>'+esc(hint)+'</p></div>';}
function download(name,text,type='application/json'){const url=URL.createObjectURL(new Blob([text],{type}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function configuration(){return '<div class="toolbar row"><button id="export-config" class="primary">Download relay-workbench.toml</button><button id="defaults">Restore repository defaults</button><button id="smoke">Use one-turn smoke limits</button><button id="live-smoke">Use named live-smoke preset</button></div><section class="card"><h2>The Split Span</h2><p>Coordinate cooling, bridge power, shard recovery, and team extraction within a fixed 13-tile room. The engine owns the rules, starting resources, objectives, and role-specific observations.</p><div class="cards">'+roles.map(r=>'<article class="slot"><h3>'+r+'</h3><p>'+esc(contract.goals[r])+'</p></article>').join('')+'</div></section><section class="card"><h2>Match settings</h2><div class="grid">'+Object.entries(contract.schema.$defs.MatchSettings.properties).map(([k,s])=>k==='condition'?'<label>Evaluation condition<select data-match="condition"><option value=""'+(config.match.condition==null?' selected':'')+'>From communication rounds</option>'+conditions.map(c=>'<option value="'+c+'"'+(config.match.condition===c?' selected':'')+'>'+c+'</option>').join('')+'</select></label>':input(k,'type="number" step="'+(s.type==='integer'?'1':'any')+'" data-match="'+k+'"',config.match[k]??'',notes[k]||'')).join('')+'</div></section><section class="card"><h2>Provider assignments</h2><p>Model IDs and credentials are resolved from your local environment. Rates are USD per million tokens for your selected model.</p><div class="cards">'+roles.map(r=>{const p=config.players[r];return '<article class="slot"><h3>'+r+'</h3><label>Provider<select data-role="'+r+'" data-player="provider">'+contract.schema.$defs.PlayerSettings.properties.provider.enum.map(v=>'<option'+(v===p.provider?' selected':'')+'>'+v+'</option>').join('')+'</select></label>'+['model_env','api_key_env'].map(k=>input(k,'data-role="'+r+'" data-player="'+k+'"',p[k])).join('')+['input_per_million','output_per_million'].map(k=>input(k,'type="number" step="any" data-role="'+r+'" data-rate="'+k+'"',p.pricing?.[k]??'')).join('')+'</article>';}).join('')+'</div></section><section class="card"><h2>Milestone 2 capabilities</h2><p>'+sourceInfo()+'</p><p>Active roles are fixed at three. Input is the engine-generated private HUD plus current PNG. The current adapter set is OpenAI, Anthropic, and Gemini. Custom rooms, competing goal editors, 2/4-player rosters, other providers, and uploaded observations require future project changes.</p><p>There is no global token cap or random seed in the current configuration. Engine outcomes are deterministic given the submitted actions.</p></section>';}
function setup(){return '<section class="card"><h2>Connect the local project</h2><p>Download and extract the companion outside your repository. Activate the repository’s Python environment, change to the repository root, then run the companion by its full path.</p><a href="relay-workbench.zip" download>Download local companion</a><pre>python /path/to/relay-workbench/relay_workbench.py</pre><p>Open the localhost URL it prints. The companion serves this interface and executes the checked-out project’s actual --mock CLI. It checks that your engine and default configuration match this build. Provider credentials stay in your local environment.</p></section>';}
function offline(){return '<section class="card"><small>'+ (session?'LOCAL PROJECT CONNECTED':'HOSTED WORKBENCH')+'</small><h2>Run the actual scripted fixture</h2><p>PYRA vents, FLUX powers the bridge, and SPECTRA retrieves the shard. The known full solution ends after seven turns with five energy and scores of 100.</p><div class="row"><button id="mock" class="primary" '+(!session||busy?'disabled':'')+'>'+(busy?'Running…':'Run offline through Python')+'</button><button id="fixture" '+(busy?'disabled':'')+'>Load repository fixture</button><a href="example_run/index.html" target="_blank" rel="noopener">Open original visual replay</a></div><p>Fixture playback loads the repository’s existing recorded result. A local run uses the settings currently entered above and creates new native records.</p><pre>python -m parallax_relay.play --mock --config relay-workbench.toml</pre></section>'+(!session?setup():'');}
function canonical(value){return JSON.stringify(value,(_key,v)=>v&&typeof v==='object'&&!Array.isArray(v)?Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b))):v);}
function matchesSmoke(){const normalized=c=>({...c,match:{condition:null,...c.match}});return contract.live_smoke&&canonical(normalized(config))===canonical(normalized(contract.live_smoke.config));}
function sourceLink(url,label){try{if(new URL(url).protocol!=='https:')return '';return '<a href="'+esc(url)+'" target="_blank" rel="noopener">'+esc(label)+'</a>';}catch{return '';}}
function smokeRoster(){
 if(!matchesSmoke())return '';
 const profile=contract.live_smoke;
 return '<section class="card"><h2>Named live-smoke roster</h2><p>Source-checked '+esc(profile.verified_date)+'. Nine requests without retries; at most 18 attempts for one turn. This preset is not standing spending authorization. Recheck model access and rates before execution.</p><div class="cards">'+roles.map(role=>{
  const p=profile.config.players[role],source=profile.sources[role];
  return '<article class="slot"><h3>'+role+'</h3><p>'+esc(profile.models[role])+'</p><p>'+esc(p.provider)+' · $'+esc(p.pricing.input_per_million)+' input / $'+esc(p.pricing.output_per_million)+' output per million tokens</p><p>Local model variable: '+esc(p.model_env)+'<br>Local key variable: '+esc(p.api_key_env)+'</p><p>'+sourceLink(source.model_url,'Model reference')+' · '+sourceLink(source.pricing_url,'Pricing reference')+'</p><p>'+esc(source.notes)+'</p></article>';
 }).join('')+'</div><p>PYRA keeps its character, thermal view, abilities and objective. Its OpenAI agent is independent of SPECTRA and shares only the API key. Anthropic live validation remains deferred.</p></section>';
}
function live(){
 const m=config.match,operands=[m.max_calls,m.max_turns,m.communication_rounds,m.max_attempts];
 const ceiling=operands.every(Number.isFinite)?Math.min(m.max_calls,m.max_turns*roles.length*(m.communication_rounds+1)*m.max_attempts):'—';
 const named=matchesSmoke();
 const check=named?'python scripts/live_smoke.py --check --config relay-workbench.toml':'python -m parallax_relay.play --check --config relay-workbench.toml --env-file .env';
 const execute=named?'python scripts/live_smoke.py --live --config relay-workbench.toml':'python -m parallax_relay.play --live --config relay-workbench.toml --env-file .env';
 return smokeRoster()+'<section class="card"><h2>Review the bounded plan</h2><p>The current release exposes a local CLI. This page prepares its TOML and command. The local companion executes offline runs only.</p><div class="cards">'+metric('Estimated spending guard',m.max_estimated_cost_usd===null?'Unset':Number.isFinite(m.max_estimated_cost_usd)?'$'+m.max_estimated_cost_usd:'—','Maximum configured local estimate; actual billing may differ.')+metric('Request attempt ceiling',ceiling)+metric('Per-request output cap',Number.isFinite(m.max_output_tokens)?m.max_output_tokens:'—','Tokens')+'</div><p>The engine reserves UTF-8 text bytes + image_token_reserve (omitted for no_images) + 2,048 input units per attempt, plus the output cap, priced separately for each role. It reserves all players’ retry budgets before a phase begins. Future text sizes depend on actual model output, so a full-match price cannot be calculated exactly in advance.</p><p>Approval applies to the current settings and entered pricing. Check each local model ID and its current rate before approving. A local --check validates configuration without contacting a provider.</p><pre>'+esc(check)+'</pre><button id="approve" class="primary">Approve estimate and prepare live command</button>'+(approved?'<div><p>Approved locally for this configuration. Download the TOML beside your checkout. Configure keys locally; the smoke helper uses process keys or ignored .env.smoke and pins the named models. Execute only after explicit spending authorization. Each additional live invocation needs its own authorization.</p><pre>'+esc(execute)+'</pre><button id="approved-download">Download approved TOML</button></div>':'')+'</section>';
}
function recordedMode(manifest){
 const mode=manifest.mode??manifest.provenance?.execution?.value?.mode;
 return ['mock','live','programmatic'].includes(mode)?mode:'unknown';
}
function evaluate(candidate=run){if(!candidate)return '<section class="card"><h2>Load a native run</h2><p>Import a run directory containing manifest.json, result.json, final_state.json, calls.jsonl, phases.jsonl, and replay.jsonl.</p>'+imports()+'</section>';
 const r=candidate.result,calls=candidate.calls,failed=calls.filter(c=>c.status!=='ok'),chat=candidate.replay.flatMap(t=>t.communications),successful=calls.filter(c=>c.status==='ok').length;
 return '<section class="card"><div class="row between"><h2>'+esc(candidate.manifest.room??'Room unspecified')+' · '+esc(recordedMode(candidate.manifest))+'</h2><button id="export-run">Export complete JSON</button></div>'+imports()+'<p>Condition: '+esc(candidate.manifest.provenance?.execution?.value?.conditions?.arm??'Historical / unspecified')+' · recorded communications may be spectator-only.</p><div class="cards">'+metric('Team outcome',r.win?'Victory':r.loss?'Defeat':'Incomplete',r.stop_reason)+metric('Resolved turns',r.turns)+metric('Successful attempts',calls.length?Math.round(successful/calls.length*100)+'%':'—','Transport/protocol proxy, not gameplay-rule compliance')+metric('Failed attempts',failed.length)+metric('Reported tokens',(r.budget.reported_input_tokens??0)+(r.budget.reported_output_tokens??0),r.budget.unknown_usage_calls+' calls with unknown usage')+metric('Estimated cost',r.budget.estimated_cost_usd==null?'Unpriced':'$'+r.budget.estimated_cost_usd)+'</div><p>Communication quality requires human review. '+chat.length+' public messages are available below. Success percentages describe attempts, including retries. Engine events provide evidence for illegal actions.</p></section><section class="card"><h2>Engine scores</h2><div class="cards">'+roles.map(role=>metric(role,r.scores?.[role]??'Unscored',contract.goals[role])).join('')+'</div><p>These are the engine’s composite scores. Terminal scores remain absent for incomplete runs.</p></section><section class="card"><h2>Failure evidence and partial phases</h2><pre>'+esc(JSON.stringify(failed,null,2))+'</pre><details><summary>All phase records, including unfinished rounds</summary><pre>'+esc(JSON.stringify(candidate.phases,null,2))+'</pre></details></section><section class="card"><h2>Privileged spectator records</h2><p>Private HUDs, objectives and notes are included. Player adapters receive their own allowlisted projection.</p>'+candidate.replay.map(t=>'<details><summary>Resolved turn '+t.turn+' · energy '+esc(t.state_after.energy)+'</summary><div class="cards">'+roles.map(role=>{const name=t.observations[role]?.image;const src=candidate.images?.[name];return src&&/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(src)?'<div><h3>'+role+'</h3><img alt="'+role+' sensor observation" src="'+src+'"></div>':'';}).join('')+'</div><h3>Public communication</h3>'+t.communications.map(c=>'<p><b>'+esc(c.role)+' / '+esc(c.phase)+'</b> '+esc(c.text)+'</p>').join('')+'<h3>Events</h3><pre>'+esc(JSON.stringify(t.events,null,2))+'</pre><h3>Observations, actions and state</h3><pre>'+esc(JSON.stringify(t,null,2))+'</pre></details>').join('')+'</section>';}
function imports(){return '<div class="row toolbar"><button id="import-directory">Import run folder</button><button id="import-json">Import exported JSON</button><input id="directory" type="file" webkitdirectory multiple hidden><input id="json" type="file" accept=".json" hidden></div>';}
function render(prepared){
 const [title,intro]=titles[tab];
 $('title').textContent=title;
 $('intro').textContent=intro;
 document.querySelectorAll('[data-tab]').forEach(b=>{
  const active=b.dataset.tab===tab;
  b.classList.toggle('active',active);
  if(active)b.setAttribute('aria-current','page');else b.removeAttribute('aria-current');
 });
 $('panel').innerHTML=prepared??({scenario:configuration,offline,live,evaluation:evaluate})[tab]();
}
function admitRun(data,openEvaluation=false){
 const candidate=checkRun(data);
 const evaluation=evaluate(candidate);
 run=candidate;
 if(openEvaluation)tab='evaluation';
 if(tab==='evaluation')render(evaluation);
}
async function fetchJSON(url,options,failure='Could not load the recording.'){
 let response;
 try{response=await fetch(url,options);}catch{throw Error(failure);}
 if(!response.ok){
  if(url==='/api/mock'){
   let data;try{data=await response.json();}catch{}
   if(typeof data?.error==='string')throw Error(data.error);
  }
  throw Error(failure);
 }
 try{return await response.json();}catch{throw Error(failure);}
}
async function loadRun(loader,openEvaluation=false,success=''){
 const seq=++admissionSeq,nav=navigationSeq;
 message('');
 try{
  const data=await loader();
  if(seq!==admissionSeq)return;
  admitRun(data,openEvaluation&&nav===navigationSeq);
  if(nav===navigationSeq||tab==='evaluation')message(success);
 }catch(e){
  if(seq===admissionSeq&&nav===navigationSeq)message(e.message,true);
 }
}
function parseJSON(text,where){
 try{return JSON.parse(text);}
 catch{throw Error('Invalid '+where+': expected valid JSON.');}
}
async function readRunDirectory(files){
 const images=files.filter(f=>/^(turn_\d+_(spectra|pyra|flux|spectator)|final_spectator)\.png$/.test(f.name));
 const names=new Set();
 for(const file of images){
  if(names.has(file.name))throw Error('Duplicate image filename: '+file.name);
  names.add(file.name);
 }
 const data={};
 for(const name of ['manifest','result','final_state','calls','phases','replay']){
  const ext=['calls','phases','replay'].includes(name)?'jsonl':'json';
  const filename=name+'.'+ext;
  const matches=files.filter(f=>f.name===filename);
  if(matches.length!==1)throw Error('Select one run directory with '+filename);
  const text=await matches[0].text();
  data[name]=ext==='jsonl'
   ?text.split(/\r?\n/).flatMap((line,i)=>line.trim()?[parseJSON(line,filename+' line '+(i+1))]:[])
   :parseJSON(text,filename);
 }
 data.images={};
 for(const file of images){
  const bytes=new Uint8Array(await file.arrayBuffer());
  const signature=[137,80,78,71,13,10,26,10];
  if(!signature.every((value,i)=>bytes[i]===value))throw Error('Invalid PNG image: expected a PNG signature.');
  const chunks=[];
  for(let offset=0;offset<bytes.length;offset+=32768)chunks.push(String.fromCharCode(...bytes.subarray(offset,offset+32768)));
  data.images[file.name]='data:image/png;base64,'+btoa(chunks.join(''));
 }
 return data;
}
document.addEventListener('input',({target:t})=>{
 if(!config)return;
 if(t.dataset.match){
  if(t.dataset.match==='condition'){config.match.condition=t.value||null;if(t.value)config.match.communication_rounds=conditionRounds(t.value);render();}
  else config.match[t.dataset.match]=t.value===''&&!t.validity?.badInput&&t.dataset.match==='max_estimated_cost_usd'?null:t.valueAsNumber;
  approved=null;
 }
 if(t.dataset.player){config.players[t.dataset.role][t.dataset.player]=t.value;approved=null;}
 if(t.dataset.rate){
  const p=config.players[t.dataset.role];
  p.pricing??={input_per_million:null,output_per_million:null};
  p.pricing[t.dataset.rate]=t.value===''&&!t.validity?.badInput?null:t.valueAsNumber;
  if(Object.values(p.pricing).every(v=>v===null))p.pricing=null;
  approved=null;
 }
});
document.addEventListener('click',async({target})=>{
 const b=target.closest('button');
 if(!b||b.disabled||!contract)return;
 try{
  if(b.dataset.tab){navigationSeq++;tab=b.dataset.tab;render();message('');return;}
  switch(b.id){
   case 'defaults':config=structuredClone(contract.defaults);approved=null;render();break;
   case 'live-smoke':config=structuredClone(contract.live_smoke.config);approved=null;render();break;
   case 'smoke':
    for(const [key,value] of Object.entries(contract.defaults.match)){
     if(!['max_estimated_cost_usd','condition'].includes(key)&&!Number.isFinite(config.match[key]))config.match[key]=value;
    }
    config.match.max_turns=1;
    config.match.max_calls=roles.length*(config.match.communication_rounds+1)*config.match.max_attempts;
    approved=null;render();break;
   case 'export-config':download('relay-workbench.toml',toml(validate(config,contract)),'application/toml');break;
   case 'approve':validate(config,contract,true);approved=JSON.stringify(config);render();break;
   case 'approved-download':if(approved===JSON.stringify(config))download('relay-workbench.toml',toml(validate(config,contract,true)),'application/toml');break;
   case 'fixture':
    if(busy)return;
    await loadRun(()=>fetchJSON('fixture.json',undefined,'Could not load the repository fixture.'),true,'Loaded the repository’s scripted example_run fixture.');
    break;
   case 'mock':{
    if(busy)return;
    const validated=validate(config,contract);
    busy=true;
    render();
    try{
     await loadRun(()=>fetchJSON('/api/mock',{method:'POST',headers:{'Content-Type':'application/json','X-Relay-Token':session.token},body:JSON.stringify(validated)},'Offline execution failed. Check the local companion.'),true);
    }finally{busy=false;if(tab==='offline')render();}
    break;
   }
   case 'import-directory':$('directory').click();break;
   case 'import-json':$('json').click();break;
   case 'export-run':download('parallax-native-run.json',JSON.stringify(run,null,2));break;
  }
 }catch(e){message(e.message,true);}
});
document.addEventListener('change',async({target:t})=>{
 if(!['directory','json'].includes(t.id)||!contract)return;
 try{
  const files=Array.from(t.files);
  if(!files.length)return;
  await loadRun(async()=>{
   if(files.reduce((sum,f)=>sum+f.size,0)>50000000)throw Error('Choose a run under 50 MB.');
   return t.id==='json'?parseJSON(await files[0].text(),'run JSON'):readRunDirectory(files);
  },false,'Imported native run records.');
 }finally{t.value='';}
});
if(contract){
 if(location.hostname==='127.0.0.1')try{
  const s=await fetchJSON('/api/status');
  if(s.commit===contract.commit)session=s;
 }catch{}
 render();
 const footer=document.querySelector('.sidefoot');
 footer.textContent='REPO '+(contract.commit??'unavailable').slice(0,7)+' · '+(contract.source_status??'unknown')+' · MILESTONE 2';
}else{
 document.querySelectorAll('[data-tab]').forEach(button=>button.disabled=true);
}
