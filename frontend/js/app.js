const $=selector=>document.querySelector(selector);
const $$=selector=>[...document.querySelectorAll(selector)];
const state={csrf:'',user:null,projects:[],project:null,assets:[],messages:[],providers:[],parts:null,viewer:null,drive:false,settings:'models',pending:null,filter:'all',logSize:12,logText:'',logTimer:null,appearance:{},tempProviders:{},selectedProvider:'',generating:false,activityTimer:null,activityHide:null,activityStart:0,previewIndex:-1,resumed:false,initialWorkspace:true};
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let toastTimer;
function toast(message,error=false){const target=$('#toast');target.textContent=message;target.className='toast show'+(error?' error':'');clearTimeout(toastTimer);toastTimer=setTimeout(()=>target.className='toast',4200);}
async function api(path,options={}){
  const opts={credentials:'same-origin',...options};opts.headers={...(opts.headers||{})};
  if(Object.hasOwn(opts,'json')){opts.headers['Content-Type']='application/json';opts.body=JSON.stringify(opts.json);delete opts.json;}
  if(opts.method && !['GET','HEAD'].includes(opts.method))opts.headers['X-CSRF-Token']=state.csrf;
  const res=await fetch('/api/'+path,opts);const data=await res.json().catch(()=>({error:'Unexpected server response'}));
  if(!res.ok)throw new Error(data.error||`HTTP ${res.status}`);return data;
}
function setBusy(button,busy,label='Working…'){if(busy){button.dataset.label=button.textContent;button.textContent=label;}else button.textContent=button.dataset.label||button.textContent;button.disabled=busy;}
function withSession(action){if(state.user)return Promise.resolve().then(action);state.pending=action;showAuth('guest');return Promise.resolve();}
const resumeProjectKey=()=>`umi-lab.last-project.${state.user?.id||'visitor'}`;
const draftKey=()=>`umi-lab.draft.${state.user?.id||'visitor'}.${state.project?.id||'new'}`;
function keepDraft(){try{localStorage.setItem(draftKey(),$('#promptInput').value);}catch(e){}}
function restoreDraft(){try{$('#promptInput').value=localStorage.getItem(draftKey())||'';}catch(e){}}
function activity(stage,model='',complete=false,error=false){
 const hud=$('#aiActivity');clearTimeout(state.activityHide);
 if(!state.activityTimer){state.activityStart=Date.now();state.activityTimer=setInterval(()=>{const sec=Math.floor((Date.now()-state.activityStart)/1000);$('#aiActivityTime').textContent=`${String(Math.floor(sec/60)).padStart(2,'0')}:${String(sec%60).padStart(2,'0')}`;},1000);$('#aiActivityTime').textContent='00:00';}
 hud.hidden=false;$('#aiActivityText').textContent=(error?'Failed · ':complete?'Done · ':'AI · ')+(model?model+' · ':'')+stage;
 if(complete||error){clearInterval(state.activityTimer);state.activityTimer=null;state.activityHide=setTimeout(()=>hud.hidden=true,error?9000:5500);}
}
async function copyContent(text){try{await navigator.clipboard.writeText(text);toast('Copied');}catch(e){const box=document.createElement('textarea');box.value=text;box.style.position='fixed';box.style.opacity='0';document.body.append(box);box.select();const ok=document.execCommand('copy');box.remove();toast(ok?'Copied':'Clipboard unavailable',!ok);}}
function addResumeHint(){
 if(state.resumed||!state.project||state.assets.length||!state.messages.length)return;
 state.resumed=true;const chatID=$('#modelSelect').value;
 const model=state.providers.find(p=>p.id===chatID);
 if(model&&!state.project.settings?.resume_asked){
  const projectID=state.project.id;
  activity('Asking how to continue your unfinished vehicle',model.name+' / '+model.model);
  api('projects/'+projectID+'/continue',{method:'POST',json:{provider_id:chatID,temp_provider:tempConfig(chatID)}})
    .then(async result=>{if(result.skipped){activity('Project restored',model.name,true);return;}
      if(state.project?.id===projectID)await openProject(projectID);activity('Follow-up ready',model.name,true);})
    .catch(e=>{activity('Could not ask provider: '+e.message,model.name,false,true);showResumeSuggestion();});
  return;
 }
 showResumeSuggestion();
}
function showResumeSuggestion(){
 if(state.assets.length)return;const feed=$('#chatFeed');if(feed.querySelector('.resume-hint'))return;
 const hint=document.createElement('div');hint.className='bubble assistant resume-hint';
 const text=document.createElement('div');text.className='bubble-text';text.textContent='Project restored. No images generated yet. What should the next image show, or would you like to add a reference?';
 const actions=document.createElement('div');actions.className='bubble-actions';const copy=document.createElement('button');copy.textContent='Copy';copy.onclick=()=>copyContent(text.textContent);actions.append(copy);hint.append(text,actions);feed.append(hint);$('#conversation').hidden=false;
}
async function refreshSession(){const data=await api('session');state.csrf=data.csrf;state.user=data.user;refreshAccount();if(state.user)await loadWorkspace();}
function refreshAccount(){const name=state.user?.display_name||'Profile';$('#accountButton').title=name;$('#avatarFallback').textContent=name.slice(0,1).toUpperCase();const hasPic=!!state.user?.avatar_url;$('#avatarSmall').hidden=!hasPic;$('#avatarFallback').hidden=hasPic;if(hasPic)$('#avatarSmall').src=state.user.avatar_url+'?t='+Date.now();
  const scope=$('#logScope');const server=scope.querySelector('option[value=server]');if(server)server.remove();if(state.user?.role==='admin')scope.add(new Option('App server','server'));$('#logoutButton').hidden=!state.user;$('#accountAction').textContent=state.user?.role==='guest'?'Protect guest account':state.user?'Sign out / change account':'Create private account';}
async function loadWorkspace(){const [projects,parts,providers]=await Promise.all([api('projects'),api('parts'),api('providers')]);state.projects=projects.projects;state.parts=parts;state.providers=providers.providers;renderProjects();renderParts();renderProviders();renderModelSelect();
 if(state.projects.length){let last='';try{last=localStorage.getItem(resumeProjectKey())||'';}catch(e){}const saved=state.projects.find(p=>p.id===last);await openProject(saved?.id||state.projects[0].id);if(state.initialWorkspace)addResumeHint();}
 else {state.project=null;state.assets=[];state.messages=[];renderGallery();restoreDraft();}state.initialWorkspace=false;
}
async function openProject(id){const old=state.project?.id;if(old&&old!==id)keepDraft();const data=await api('projects/'+id);state.project=data.project;state.assets=data.assets;state.messages=data.messages;
 try{localStorage.setItem(resumeProjectKey(),id);}catch(e){}if(old!==id)restoreDraft();restoreImageOptions();renderProjects();renderGallery();renderChat();
 $('#welcome').hidden=state.messages.length>0||state.assets.length>0||!!state.project.prompt;$('#showGallery').hidden=false;
  const settings=state.project.settings||{};$('#bodyColor').value=settings.color||'#8f6bff';$('#rideHeight').value=settings.rideHeight??50;$('#wheelSize').value=settings.wheelSize??100;$('#explodeToggle').checked=!!settings.exploded;state.viewer?.updateCar(settings);}
async function createProject(prompt=''){const result=await api('projects',{method:'POST',json:{name:prompt.slice(0,60)||'New vehicle',prompt,kind:'car'}});state.projects=(await api('projects')).projects;await openProject(result.id);return result.id;}
function renderProjects(){const wrap=$('#projectList');wrap.replaceChildren();for(const item of state.projects){const button=document.createElement('button');button.className='project-item';button.innerHTML=`${esc(item.name)}<small>${esc(item.kind)} · ${new Date(item.updated_at*1000).toLocaleDateString()}</small>`;button.onclick=()=>openProject(item.id).then(()=>hideSidePanels()).catch(e=>toast(e.message,true));wrap.append(button);}}
function renderParts(){const wrap=$('#partsContainer');wrap.replaceChildren();if(!state.parts)return;const q=$('#partSearch').value.toLowerCase().trim();for(const group of state.parts.assemblies){const names=group.parts.filter(n=>!q||n.toLowerCase().includes(q)||group.name.toLowerCase().includes(q));if(!names.length)continue;const div=document.createElement('section');div.className='parts-group';div.innerHTML=`<h3>${esc(group.name)} · ${names.length}</h3><div class="part-tags">${names.map(n=>`<span>${esc(n)}</span>`).join('')}</div>`;wrap.append(div);}}
function renderChat(){
 const wrap=$('#chatFeed');wrap.replaceChildren();
 for(const m of state.messages){
  const item=document.createElement('div');item.className='bubble '+(m.role==='user'?'user':'assistant');
  const body=document.createElement('div');body.className='bubble-text';
  const md=/!\[([^\]]*)\]\((\/api\/media\/[a-f0-9-]+)\)/g;let index=0,hit;
  while((hit=md.exec(m.content))){if(hit.index>index)body.append(document.createTextNode(m.content.slice(index,hit.index)));const im=document.createElement('img');im.src=hit[2];im.alt=hit[1]||'Generated vehicle';im.loading='lazy';body.append(im);index=md.lastIndex;}
  if(index<m.content.length)body.append(document.createTextNode(m.content.slice(index)));
  const controls=document.createElement('div');controls.className='bubble-actions';
  const copy=document.createElement('button');copy.type='button';copy.textContent='Copy';copy.title='Copy entire message';copy.onclick=()=>copyContent(m.content);controls.append(copy);
  if(m.content.length>490){const expand=document.createElement('button');expand.type='button';expand.textContent='More';expand.onclick=()=>{const open=item.classList.toggle('expanded');expand.textContent=open?'Less':'More';};controls.append(expand);}
  item.append(body,controls);wrap.append(item);
 }
 $('#conversation').hidden=state.messages.length===0;if(state.messages.length)wrap.scrollTop=wrap.scrollHeight;
}
function selectedReferenceIds(){const all=new Set((state.assets||[]).map(a=>a.id));const saved=state.project?.settings?.reference_assets;
 if(Array.isArray(saved))return saved.filter(id=>all.has(id)).slice(0,5);
 return state.project?.selected_asset&&all.has(state.project.selected_asset)?[state.project.selected_asset]:[];
}
async function toggleReference(id){if(!state.project)return;const chosen=selectedReferenceIds();const exists=chosen.includes(id);if(!exists&&chosen.length>=5){toast('Maximum five reference images',true);return;}
 const refs=exists?chosen.filter(x=>x!==id):[...chosen,id];const settings={...(state.project.settings||{}),reference_assets:refs};
 const data=await api('projects/'+state.project.id,{method:'PATCH',json:{settings}});state.project=data.project;renderGallery();
}
function renderGallery(){const wrap=$('#galleryGrid');wrap.replaceChildren();const assets=state.assets||[],chosen=selectedReferenceIds();$('#galleryCount').textContent=chosen.length+' selected';
 const result=state.project?.settings?.last_generation;
 $('#galleryLastRun').textContent=result?`Last: ${result.mode==='sheet'?'Six-view sheet':result.mode.replaceAll('_',' ')} · ${result.images_created} image · ${result.reference_count} reference(s) · ${Math.round(result.duration_ms/1000)}s · ${result.provider}/${result.model}`:'No generation yet';
 if(!assets.length){wrap.innerHTML='<div class="empty-gallery">No concepts yet. Describe a vehicle or add an image reference.</div>';return;}
 for(const [idx,asset] of assets.entries()){
  const item=document.createElement('div');item.className='gallery-card'+(chosen.includes(asset.id)?' reference-selected':'');
  const image=document.createElement('button');image.type='button';image.className='gallery-open';image.title='Open full-size image';image.setAttribute('aria-label','Preview '+(asset.view||'image'));
  const img=document.createElement('img');img.src=asset.url;img.alt=asset.view?.replaceAll('_',' ')||'Vehicle reference';img.loading='lazy';image.append(img);
  image.onclick=()=>openPreview(idx);
  const pick=document.createElement('button');pick.type='button';pick.className='gallery-pick';pick.textContent=chosen.includes(asset.id)?'✓':'+';pick.title='Use as visual reference';pick.setAttribute('aria-pressed',String(chosen.includes(asset.id)));
  pick.onclick=()=>toggleReference(asset.id).catch(e=>toast(e.message,true));
  const label=document.createElement('span');label.textContent=(asset.view==='reference'?'Reference':(asset.view||'Image').replaceAll('_',' '));
  item.append(image,pick,label);wrap.append(item);
 }
 $('#showGallery').hidden=false;
}
function openPreview(index){if(!state.assets.length)return;state.previewIndex=(index+state.assets.length)%state.assets.length;const asset=state.assets[state.previewIndex];
 $('#previewImage').src=asset.url;$('#previewImage').alt=(asset.view||'Concept').replaceAll('_',' ');$('#previewCaption').textContent=`${state.previewIndex+1} / ${state.assets.length} · ${$('#previewImage').alt}`;
 $('#previewPick').textContent=selectedReferenceIds().includes(asset.id)?'Remove reference':'Select reference';$('#imagePreview').hidden=false;
}
function closePreview(){$('#imagePreview').hidden=true;$('#previewImage').removeAttribute('src');}
function restoreImageOptions(){try{const key='umi.image-options.'+state.project?.id;const options=JSON.parse(localStorage.getItem(key)||'{}');$('#galleryAction').value=options.mode||'sheet';$('#galleryInstructions').value=options.instructions||'';$('#gallerySystem').value=options.system_id||'';$('#galleryPart').value=options.part_name||'';}catch(e){$('#galleryAction').value='sheet';$('#galleryInstructions').value='';$('#gallerySystem').value='';$('#galleryPart').value='';}updateGalleryModeUI();}
function saveImageOptions(){if(!state.project)return;try{localStorage.setItem('umi.image-options.'+state.project.id,JSON.stringify({mode:$('#galleryAction').value,instructions:$('#galleryInstructions').value,system_id:$('#gallerySystem').value,part_name:$('#galleryPart').value.trim()}));}catch(e){}}
function updateGalleryModeUI(){const mode=$('#galleryAction').value;const system=mode==='system';const part=mode==='part';$('#gallerySystem').hidden=!system;$('#galleryPart').hidden=!part;$('#galleryInstructions').placeholder=mode==='annotate'?'Label visible systems and major parts (optional)':mode==='system'?'Focus instructions for the chosen system (optional)':mode==='part'?'Construction notes for the isolated part (optional)':'Refine style or details (optional)';$('#galleryBody').classList.toggle('compact-parts',system||part);}
function enableGalleryDrag(){const box=$('#galleryPane'),handle=$('#galleryHandle'),corner=$('#galleryResize');
 function begin(ev,resizing){if(ev.button!==0||ev.target.closest('button,select,input'))return;ev.preventDefault();const bounds=box.getBoundingClientRect();const pointer=resizing?corner:handle;
 const snapshot={x:ev.clientX,y:ev.clientY,left:bounds.left,top:bounds.top,width:bounds.width,height:bounds.height};pointer.setPointerCapture(ev.pointerId);
 const move=e=>{if(resizing){box.style.width=Math.max(300,Math.min(innerWidth-snapshot.left-6,snapshot.width+e.clientX-snapshot.x))+'px';box.style.height=Math.max(120,Math.min(innerHeight-snapshot.top-6,snapshot.height+e.clientY-snapshot.y))+'px';}
 else{box.style.left=Math.max(0,Math.min(innerWidth-80,snapshot.left+e.clientX-snapshot.x))+'px';box.style.top=Math.max(0,Math.min(innerHeight-52,snapshot.top+e.clientY-snapshot.y))+'px';}};
 const end=()=>{pointer.removeEventListener('pointermove',move);pointer.removeEventListener('pointerup',end);pointer.removeEventListener('pointercancel',end);try{localStorage.setItem('umi.gallery.bounds',JSON.stringify({left:box.style.left,top:box.style.top,width:box.style.width,height:box.style.height}));}catch(e){}};
 pointer.addEventListener('pointermove',move);pointer.addEventListener('pointerup',end);pointer.addEventListener('pointercancel',end);
 }
 handle.addEventListener('pointerdown',e=>begin(e,false));corner.addEventListener('pointerdown',e=>begin(e,true));
 try{const bounds=JSON.parse(localStorage.getItem('umi.gallery.bounds')||'{}');const x=parseFloat(bounds.left),y=parseFloat(bounds.top),w=parseFloat(bounds.width),h=parseFloat(bounds.height);
 if(Number.isFinite(x))box.style.left=Math.max(0,Math.min(innerWidth-80,x))+'px';if(Number.isFinite(y))box.style.top=Math.max(0,Math.min(innerHeight-55,y))+'px';if(Number.isFinite(w))box.style.width=Math.min(innerWidth-12,Math.max(300,w))+'px';if(Number.isFinite(h))box.style.height=Math.min(innerHeight-12,Math.max(120,h))+'px';}catch(e){}
}
function toggleGallery(show){if(show && !state.project){toast('Describe a vehicle first');return;}$('#galleryPane').hidden=!show;if(show)renderGallery();}
function closeTools(){$('#toolsMenu').hidden=true;$('#toolsButton').setAttribute('aria-expanded','false');}
function hideSidePanels(){for(const id of ['partsPane','garagePane','editPane'])$('#'+id).hidden=true;}
function togglePanel(id){const show=$('#'+id).hidden;hideSidePanels();$('#'+id).hidden=!show;}
async function sendPrompt(event){
 event.preventDefault();const textarea=$('#promptInput');const message=textarea.value.trim();if(!message)return;
 return withSession(async()=>{
  const btn=$('#sendButton');setBusy(btn,true,'…');let chatOK=false;
  try{
   if(!state.project)await createProject(message);
   else await api('projects/'+state.project.id,{method:'PATCH',json:{prompt:message}});
   const chatID=$('#modelSelect').value,imageID=$('#imageProviderSelect').value;
   const chatProvider=state.providers.find(p=>p.id===chatID);const imageProvider=state.providers.find(p=>p.id===imageID);
   const imageRequested=$('#autoImages').checked&&!!imageID;
   if(chatProvider)activity('Connecting for design discussion',chatProvider.name+' / '+(tempConfig(chatID)?.model||chatProvider.model));
   const chatResult=await api('chat',{method:'POST',json:{project_id:state.project.id,message,provider_id:chatID,temp_provider:tempConfig(chatID)}});
   chatOK=true;
   if(!imageRequested && chatProvider)activity('Response received',chatProvider.name,true);
   textarea.value='';keepDraft();$('#welcome').hidden=true;await openProject(state.project.id);
   if(imageRequested){await generateConcepts({automatic:true,prompt:message});}
   else if(!chatProvider)activity('Brief saved · choose a model for AI images','',true);
  }catch(err){activity(err.message,'',false,true);toast(err.message,true);if(chatOK){textarea.value='';keepDraft();await openProject(state.project.id);}}
  finally{setBusy(btn,false);}
 });
}
async function uploadFile(file){if(!file)return;if(!['image/png','image/jpeg','image/webp'].includes(file.type))throw new Error('Use JPG, PNG or WebP');if(file.size>9_000_000)throw new Error('Image exceeds 9 MB');return withSession(async()=>{if(!state.project)await createProject();const data=new FormData();data.append('project_id',state.project.id);data.append('image',file);const response=await api('assets/upload',{method:'POST',body:data});await openProject(state.project.id);
 // An uploaded file is an explicit reference and should remain selected for generation.
 if(response.id&&!selectedReferenceIds().includes(response.id))await toggleReference(response.id);
 toggleGallery(true);$('#welcome').hidden=true;toast('Reference uploaded');});}
async function generateConcepts(options={}){
 const automatic=!!options.automatic;
 return withSession(async()=>{
  if(!state.project)await createProject($('#promptInput').value);
  const choices=state.providers.filter(p=>p.images&&isConfigured(p));const select=automatic?$('#imageProviderSelect'):$('#galleryImageModel');
  const preferred=choices.find(p=>p.id===select.value)||choices[0];
  if(!preferred){openSettings('models');toast('Connect an image provider first',true);return false;}
  if(state.generating)return false;state.generating=true;
  const button=$('#generateButton'),mode=automatic?'front_3q':$('#galleryAction').value;
  const refs=selectedReferenceIds();const instructions=automatic?'':$('#galleryInstructions').value.trim();const systemID=$('#gallerySystem').value;const partName=$('#galleryPart').value.trim();
  if(!automatic&&mode==='system'&&!systemID){toast('Choose a system first',true);return false;}
  if(!automatic&&mode==='part'&&partName.length<2){toast('Enter a part name first',true);return false;}
  setBusy(button,true,'Generating…');activity(refs.length?`Editing from ${refs.length} selected reference(s)`:'Generating from brief',preferred.name+' / '+(tempConfig(preferred.id)?.image_model||preferred.image_model));
  try{
   activity(mode==='sheet'?'Creating a single six-view sheet':mode==='annotate'?'Creating annotated parts map':mode==='system'?'Creating '+systemID+' system sheet':mode==='part'?'Creating isolated part sheet for '+partName:'Creating '+mode.replaceAll('_',' ')+' image',preferred.name+' / '+(tempConfig(preferred.id)?.image_model||preferred.image_model));
   const res=await api('concepts/generate',{method:'POST',json:{project_id:state.project.id,provider_id:preferred.id,prompt:options.prompt||state.project.prompt||$('#promptInput').value,mode,reference_ids:refs,instructions,system_id:systemID,part_name:partName,temp_provider:tempConfig(preferred.id)}});
   await openProject(state.project.id);toggleGallery(true);
   activity(`Saved ${res.images_created} image · ${res.views_completed} view(s) · ${res.reference_count} reference(s)`,preferred.name,true);
   if(res.warnings?.length)toast(res.warnings.join(' · '),true);
   return true;
  }catch(e){activity(e.message,preferred.name,false,true);toast('Image generation: '+e.message,true);return false;}
  finally{setBusy(button,false);state.generating=false;}
 });
}
const tempStorage='umi-lab.temp-providers.v1',preferenceStorage='umi-lab.model-preferences.v1';
function loadTempProviders(){try{const value=JSON.parse(sessionStorage.getItem(tempStorage)||'{}');state.tempProviders=(value&&typeof value==='object')?value:{};}catch(e){state.tempProviders={};}}
function storeTempProviders(){try{sessionStorage.setItem(tempStorage,JSON.stringify(state.tempProviders));}catch(e){toast('Browser session storage unavailable',true);}}
function tempConfig(id){return state.tempProviders[id]||null;}
function isConfigured(p){return !!(state.tempProviders[p.id]?.enabled || p.enabled && (p.has_key || p.local));}
function saveChoices(){try{localStorage.setItem(preferenceStorage,JSON.stringify({chat:$('#modelSelect').value,image:$('#imageProviderSelect').value}));}catch(e){}}
function getChoices(){try{return JSON.parse(localStorage.getItem(preferenceStorage)||'{}');}catch(e){return {};}}
function renderModelSelect(){
 const prefs=getChoices(),chat=$('#modelSelect'),images=$('#imageProviderSelect'),gallery=$('#galleryImageModel');
 const oldChat=chat.value||prefs.chat,oldImage=images.value||prefs.image;
 chat.replaceChildren(new Option('No chat model',''));
 for(const p of state.providers.filter(p=>p.protocol!=='meshy'&&p.protocol!=='tripo'&&p.protocol!=='aholo'&&isConfigured(p)))chat.add(new Option(p.name+' / '+(tempConfig(p.id)?.model||p.model),p.id));
 if([...chat.options].some(o=>o.value===oldChat))chat.value=oldChat;
 images.replaceChildren();gallery.replaceChildren();
 for(const p of state.providers.filter(p=>p.images&&isConfigured(p))){const name=p.name+' / '+(tempConfig(p.id)?.image_model||p.image_model);images.add(new Option(name,p.id));gallery.add(new Option(name,p.id));}
 if([...images.options].some(o=>o.value===oldImage)){images.value=oldImage;gallery.value=oldImage;}
 const enabled=images.options.length>0;chat.hidden=chat.options.length<=1;images.hidden=!enabled;gallery.hidden=!enabled;$('#autoImageLabel').hidden=!enabled;
 saveChoices();
}
function renderProviders(){
 const filter=$('#providerFilter').value,selected=$('#providerSelect'),prior=selected.value||state.selectedProvider;
 selected.replaceChildren();
 const valid=state.providers.filter(p=>filter==='all'||filter==='configured'&&isConfigured(p)||filter==='images'&&p.images||filter==='mesh3d'&&p.mesh3d||filter==='chat'&&!p.mesh3d);
 for(const p of valid)selected.add(new Option(p.name+(isConfigured(p)?' · connected':''),p.id));
 if([...selected.options].some(o=>o.value===prior))selected.value=prior;
 state.selectedProvider=selected.value;renderProviderEditor();
}
function renderProviderEditor(){
 const host=$('#providerEditor'),p=state.providers.find(p=>p.id===$('#providerSelect').value);
 host.replaceChildren();if(!p){host.textContent='No providers in this category';return;}
 const tmp=tempConfig(p.id)||{},connected=isConfigured(p);
 const form=document.createElement('form');form.className='provider-fields-compact';form.autocomplete='off';
 const mesh=p.mesh3d;form.innerHTML=`<div class="provider-title"><strong>${esc(p.name)}</strong><button type="button" role="switch" class="switch ${connected?'on':''}" aria-checked="${connected}" title="Enable or disable this provider"><i></i></button></div>
 <div class="provider-status">${connected?(tmp.enabled?'Temporary · this tab':'Saved on server'):'Not connected'} · ${mesh?'3D':p.images?'Chat / images':'Chat'}</div>
 <label>${mesh?'3D model':'Chat model'}<input class="provider-model" value="${esc(tmp.model??p.model??'')}" maxlength="180"></label>
 ${p.images?`<label>Image model<input class="provider-image" value="${esc(tmp.image_model??p.image_model??'')}" maxlength="180"></label>`:''}
 <label>API endpoint<input class="provider-url" value="${esc(tmp.base_url??p.base_url??'')}" maxlength="300"></label>
 <label>API key<input class="provider-key" type="password" autocomplete="new-password" placeholder="${tmp.api_key?'Temporary key loaded':p.has_key?'Encrypted key stored':'Paste key (not shown)'}"></label>
 <div class="provider-controls"><button type="button" class="test-provider">Test API / balance</button><button type="button" class="temp-provider">Keep in tab</button><button type="submit" class="save-provider">Save on server</button><button type="button" class="clear-provider">Clear</button></div>
 <div class="provider-note" aria-live="polite">Temporary keys stay in this browser tab. Saved keys are encrypted on the server. Balance is displayed only when the provider supports a non-billable check.</div>`;
 const field=key=>form.querySelector('.provider-'+key);
 const config=()=>({enabled:true,model:field('model').value.trim(),image_model:field('image')?.value.trim()||'',base_url:field('url').value.trim(),api_key:field('key').value||tmp.api_key||''});
 const status=message=>form.querySelector('.provider-note').textContent=message;
 form.querySelector('.test-provider').onclick=async()=>{const button=form.querySelector('.test-provider');setBusy(button,true,'Checking…');try{const result=await api('providers/'+p.id+'/check',{method:'POST',json:config()});status(`${result.status}${result.balance!=null?' · Balance: '+result.balance:''}${result.detail?' · '+result.detail:''}`);}catch(e){status('Check failed: '+e.message);}finally{setBusy(button,false);}};
 form.querySelector('.temp-provider').onclick=()=>{state.tempProviders[p.id]=config();storeTempProviders();renderProviders();renderModelSelect();toast(p.name+' available in this tab');};
 form.onsubmit=async e=>{e.preventDefault();try{await api('providers/'+p.id,{method:'PUT',json:config()});delete state.tempProviders[p.id];storeTempProviders();await refreshProviders();toast(p.name+' saved');}catch(e){status('Save failed: '+e.message);}};
 form.querySelector('.clear-provider').onclick=async()=>{if(!confirm('Clear temporary and saved API keys for '+p.name+'?'))return;try{await api('providers/'+p.id,{method:'PUT',json:{...config(),api_key:'',clear_key:true,enabled:false}});delete state.tempProviders[p.id];storeTempProviders();await refreshProviders();toast('Key cleared');}catch(e){status('Clear failed: '+e.message);}};
 form.querySelector('.switch').onclick=async()=>{if(connected){if(tmp.enabled){delete state.tempProviders[p.id];storeTempProviders();renderProviders();renderModelSelect();}else{try{await api('providers/'+p.id,{method:'PUT',json:{...config(),api_key:'',enabled:false}});await refreshProviders();}catch(e){status(e.message);}}}else{if(!config().api_key&&!p.has_key&&!p.local){status('Enter a key then choose temporary or server storage');return;}state.tempProviders[p.id]=config();storeTempProviders();renderProviders();renderModelSelect();}};
 host.append(form);
}
async function refreshProviders(){state.providers=(await api('providers')).providers;renderProviders();renderModelSelect();}

function openSettings(section='models'){if(!state.user && section==='models')section='appearance';$('#drawerBackdrop').hidden=false;$('#settingsDrawer').classList.add('open');$('#settingsDrawer').setAttribute('aria-hidden','false');selectSettings(section);}
function closeSettings(){$('#drawerBackdrop').hidden=true;$('#settingsDrawer').classList.remove('open');$('#settingsDrawer').setAttribute('aria-hidden','true');}
function selectSettings(section){if(section==='models'&&!state.user){closeSettings();withSession(()=>openSettings('models'));return;}state.settings=section;$$('.drawer-tabs button').forEach(b=>b.classList.toggle('selected',b.dataset.settings===section));for(const name of ['models','appearance','profile'])$('#'+name+'Settings').hidden=name!==section;if(section==='profile')loadProfile();}
async function loadProfile(){if(!state.user){closeSettings();showAuth('guest');return;}try{const user=(await api('profile')).user;state.user=user;refreshAccount();$('#profileName').value=user.display_name;$('#profileBio').value=user.bio||'';$('#profileFocus').value=user.focus||'';$('#profilePrivate').hidden=user.role==='guest';$('#profileEmail').value=user.email||'';$('#profilePhone').value=user.phone||'';$('#avatarLarge').hidden=!user.avatar_url;$('#avatarLargeFallback').hidden=!!user.avatar_url;if(user.avatar_url)$('#avatarLarge').src=user.avatar_url+'?t='+Date.now();$('#avatarLargeFallback').textContent=user.display_name.slice(0,1).toUpperCase();}catch(e){toast(e.message,true);}}
async function saveProfile(event){event.preventDefault();try{const res=await api('profile',{method:'PUT',json:{display_name:$('#profileName').value,bio:$('#profileBio').value,focus:$('#profileFocus').value}});state.user=res.user;refreshAccount();toast('Profile saved');}catch(e){toast(e.message,true);}}
async function saveAvatar(file){if(!file)return;const form=new FormData();form.append('image',file);try{await api('profile/avatar',{method:'POST',body:form});await loadProfile();toast('Profile picture saved');}catch(e){toast(e.message,true);}}
const appearanceKey='umi-lab.appearance.v1';
function loadAppearance(){try{state.appearance=JSON.parse(localStorage.getItem(appearanceKey)||'{}');}catch(e){state.appearance={};}applyAppearance();}
function saveAppearance(){const a={theme:$('#themeSelect').value,accent:$('#accentColor').value,surface:$('#surfaceColor').value,text:$('#textColor').value,font:$('#fontSelect').value,customFont:$('#fontCustom').value,scale:Number($('#uiScale').value)};state.appearance=a;try{localStorage.setItem(appearanceKey,JSON.stringify(a));}catch(e){}applyAppearance();}
function applyAppearance(){const a=state.appearance;document.body.dataset.theme=a.theme||'graphite';const root=document.documentElement;root.style.setProperty('--scale',String(Math.max(.8,Math.min(1.35,(a.scale||100)/100))));$('#uiScaleValue').textContent=(a.scale||100)+'%';if(a.theme==='custom'){root.style.setProperty('--accent',a.accent||'#84a4ff');root.style.setProperty('--surface',a.surface||'#111318');root.style.setProperty('--text',a.text||'#f3f5f8');}else for(const v of ['--accent','--surface','--text'])root.style.removeProperty(v);
 let font=a.font||'system-ui';if(font==='custom')font=(a.customFont||'system-ui').replace(/[^a-zA-Z0-9_\- ]/g,'').slice(0,90)||'system-ui';root.style.setProperty('--ui-font',font==='UMI-Uploaded'?'"UMI-Uploaded",system-ui':`"${font}",system-ui`);$('#themeSelect').value=a.theme||'graphite';$('#accentColor').value=a.accent||'#84a4ff';$('#surfaceColor').value=a.surface||'#111318';$('#textColor').value=a.text||'#f3f5f8';$('#fontSelect').value=['system-ui','Inter','Arial','Helvetica Neue','Georgia','monospace','custom'].includes(a.font)?a.font:'system-ui';$('#fontCustom').value=a.customFont||'';$('#uiScale').value=a.scale||100;}
function openFontDb(){return new Promise((resolve,reject)=>{const req=indexedDB.open('umi-lab.localfonts',1);req.onupgradeneeded=()=>req.result.createObjectStore('fonts');req.onsuccess=()=>resolve(req.result);req.onerror=()=>reject(req.error);});}
async function setUploadedFont(buffer){const font=new FontFace('UMI-Uploaded',buffer);await font.load();document.fonts.add(font);document.documentElement.style.setProperty('--ui-font','"UMI-Uploaded",system-ui');}
async function restoreLocalFont(){try{const db=await openFontDb();const stored=await new Promise((ok,fail)=>{const r=db.transaction('fonts').objectStore('fonts').get('selected');r.onsuccess=()=>ok(r.result);r.onerror=()=>fail(r.error);});db.close();if(stored){await setUploadedFont(stored);if(state.appearance.font==='UMI-Uploaded')document.documentElement.style.setProperty('--ui-font','"UMI-Uploaded",system-ui');}}catch(e){/* local font optional */}}
async function uploadFont(file){if(!file)return;if(!/\.(woff2?|ttf|otf)$/i.test(file.name)||file.size>2_000_000){toast('Choose a WOFF, WOFF2, TTF or OTF file under 2 MB',true);return;}try{const bytes=await file.arrayBuffer();await setUploadedFont(bytes);const db=await openFontDb();await new Promise((ok,fail)=>{const tr=db.transaction('fonts','readwrite');tr.objectStore('fonts').put(bytes,'selected');tr.oncomplete=ok;tr.onerror=()=>fail(tr.error);});db.close();state.appearance.font='UMI-Uploaded';localStorage.setItem(appearanceKey,JSON.stringify(state.appearance));toast('Font installed for this browser');}catch(e){toast('Could not load this font',true);}}
function resetAppearance(){state.appearance={};try{localStorage.removeItem(appearanceKey);}catch(e){}applyAppearance();}
const auth={mode:'guest'};
function showAuth(mode='guest'){auth.mode=mode;$('#authOverlay').hidden=false;selectAuthMode(mode);}
function selectAuthMode(mode){auth.mode=mode;$$('.auth-tabs button').forEach(b=>b.classList.toggle('selected',b.id===(mode==='guest'?'guestMode':mode==='login'?'loginMode':'registerMode')));$('#guestMode').hidden=!!state.user;$('#loginMode').hidden=false;$('#registerMode').textContent=mode==='upgrade'?'Protect this account':'Create account';$('#authHeading').textContent=mode==='upgrade'?'Protect your guest profile':mode==='login'?'Sign in':mode==='register'?'Create an account':'Continue as guest';$('#authNameWrap').hidden=mode==='login'||mode==='upgrade';$('#authUserWrap').hidden=mode==='guest';$('#authEmailWrap').hidden=mode!=='register'&&mode!=='upgrade';$('#authPhoneWrap').hidden=mode!=='register'&&mode!=='upgrade';$('#authPasswordWrap').hidden=mode==='guest';$('#authSubmit').textContent=mode==='guest'?'Continue as guest':mode==='login'?'Sign in':mode==='upgrade'?'Protect profile':'Create account';$('#authPassword').autocomplete=mode==='login'?'current-password':'new-password';$('#authPassword').required=mode!=='guest';$('#authUser').required=mode!=='guest';$('#authName').required=mode==='guest'||mode==='register';$('#authError').textContent='';}
async function submitAuth(event){event.preventDefault();const mode=auth.mode;const payload={name:$('#authName').value.trim(),username:$('#authUser').value.trim(),password:$('#authPassword').value,email:$('#authEmail').value,phone:$('#authPhone').value};const uri=mode==='guest'?'guest':mode==='login'?'login':mode==='upgrade'?'account/upgrade':'register';const btn=$('#authSubmit');setBusy(btn,true);try{const res=await api(uri,{method:'POST',json:payload});if(res.csrf)state.csrf=res.csrf;$('#authPassword').value='';$('#authOverlay').hidden=true;await refreshSession();if(state.pending){const pending=state.pending;state.pending=null;await pending();}}catch(e){$('#authError').textContent=e.message;}finally{setBusy(btn,false);}}
async function logout(){if(!state.user){showAuth('login');return;}if(!confirm('Sign out of this workspace?'))return;try{await api('logout',{method:'POST'});state.user=null;state.project=null;state.assets=[];state.messages=[];state.projects=[];state.providers=[];refreshAccount();hideSidePanels();closeSettings();$('#galleryPane').hidden=true;$('#conversation').hidden=true;closeLogs();$('#welcome').hidden=false;$('#promptInput').value='';toast('Signed out');}catch(e){toast(e.message,true);}}
function logLine(entry){if(entry.time||entry.event)return `${entry.time||''} [${entry.level||'INFO'}] ${entry.event||entry.action||''}${entry.status?' · '+entry.status:''}`;return `${entry.ts||''} [${entry.level||'INFO'}] ${entry.action||''} ${entry.status||''}`;}
async function refreshLogs(){if($('#logWindow').hidden||!state.user)return;try{const scope=$('#logScope').value;const data=await api('logs?scope='+scope+'&limit=220');state.logText=data.entries.map(logLine).join('\n')||'No activity yet.';$('#logOutput').textContent=state.logText;}catch(e){$('#logOutput').textContent='Log unavailable: '+e.message;}}
function startLogPolling(){clearInterval(state.logTimer);state.logTimer=setInterval(()=>{if(!$('#logWindow').hidden&&!$('#logWindow').classList.contains('collapsed'))refreshLogs();},8000);}
function showLogs(){withSession(async()=>{$('#logWindow').hidden=false;refreshLogs();startLogPolling();});}
function closeLogs(){$('#logWindow').hidden=true;clearInterval(state.logTimer);}
function changeLogSize(delta){state.logSize=Math.min(23,Math.max(9,state.logSize+delta));$('#logOutput').style.fontSize=state.logSize+'px';try{localStorage.setItem('umi-lab.log-font',String(state.logSize));}catch(e){}}
function enableLogDrag(){const windowEl=$('#logWindow'),handle=$('#logHandle'),resize=$('#logResize');function start(ev,resizeMode){if(ev.button!==0||ev.target.closest('button'))return;ev.preventDefault();const bounds=windowEl.getBoundingClientRect();const x=ev.clientX,y=ev.clientY;const origin={left:bounds.left,top:bounds.top,width:bounds.width,height:bounds.height};const target=resizeMode?resize:handle;target.setPointerCapture(ev.pointerId);const move=e=>{if(resizeMode){windowEl.style.width=Math.max(285,Math.min(innerWidth-origin.left-8,origin.width+e.clientX-x))+'px';windowEl.style.height=Math.max(125,Math.min(innerHeight-origin.top-8,origin.height+e.clientY-y))+'px';}else{windowEl.style.left=Math.max(0,Math.min(innerWidth-bounds.width,origin.left+e.clientX-x))+'px';windowEl.style.top=Math.max(0,Math.min(innerHeight-45,origin.top+e.clientY-y))+'px';}};const end=()=>{target.removeEventListener('pointermove',move);target.removeEventListener('pointerup',end);target.removeEventListener('pointercancel',end);};target.addEventListener('pointermove',move);target.addEventListener('pointerup',end);target.addEventListener('pointercancel',end);}
 handle.addEventListener('pointerdown',e=>start(e,false));resize.addEventListener('pointerdown',e=>start(e,true));}
function applyModelSettings(){state.viewer?.updateCar({color:$('#bodyColor').value,rideHeight:Number($('#rideHeight').value),wheelSize:Number($('#wheelSize').value),exploded:$('#explodeToggle').checked});}
async function saveModel(){return withSession(async()=>{if(!state.project)await createProject();const settings={color:$('#bodyColor').value,rideHeight:Number($('#rideHeight').value),wheelSize:Number($('#wheelSize').value),exploded:$('#explodeToggle').checked};const res=await api('projects/'+state.project.id,{method:'PATCH',json:{settings}});state.project=res.project;toast('3D settings saved');});}
async function toggleDrive(){if(!state.viewer){toast('3D engine is unavailable',true);return;}if(state.drive){state.viewer.setDriving(false);state.drive=false;}else{if($('#explodeToggle').checked){$('#explodeToggle').checked=false;applyModelSettings();}state.drive=state.viewer.setDriving(true);if(!state.drive){toast('Physics engine unavailable',true);return;}}$('#driveButton').textContent=state.drive?'Park':'Drive';$('#driveButton').classList.toggle('active',state.drive);$('#resetDriveButton').hidden=!state.drive;$('#driveHelp').hidden=!state.drive;for(const id of ['rideHeight','wheelSize','explodeToggle'])$('#'+id).disabled=state.drive;}
async function initializeViewer(){try{state.viewer=await import('./viewer.js');await state.viewer.startViewer($('#vehicleCanvas'));$('#sceneHelp').hidden=false;}catch(e){toast('3D scene unavailable. Check CDN access.',true);console.error('Viewer unavailable',e);}}
function downloadJSON(obj,name){const href=URL.createObjectURL(new Blob([JSON.stringify(obj,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=href;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(href),2000);}
function bind(){
 $('#providerFilter').onchange=renderProviders;$('#providerSelect').onchange=()=>{state.selectedProvider=$('#providerSelect').value;renderProviderEditor();};$('#imageProviderSelect').onchange=()=>{$('#galleryImageModel').value=$('#imageProviderSelect').value;saveChoices();};$('#modelSelect').onchange=saveChoices;$('#galleryImageModel').onchange=()=>{$('#imageProviderSelect').value=$('#galleryImageModel').value;saveChoices();};$('#promptForm').addEventListener('submit',sendPrompt);$('#promptInput').addEventListener('input',keepDraft);$('#promptInput').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();$('#promptForm').requestSubmit();}});
 $('#homeButton').onclick=()=>{keepDraft();state.project=null;state.assets=[];state.messages=[];state.resumed=false;try{localStorage.removeItem(resumeProjectKey());}catch(e){}$('#welcome').hidden=false;$('#conversation').hidden=true;$('#galleryPane').hidden=true;$('#showGallery').hidden=true;restoreDraft();$('#promptInput').focus();};$('#toolsButton').onclick=()=>{const willShow=$('#toolsMenu').hidden;$('#toolsMenu').hidden=!willShow;$('#toolsButton').setAttribute('aria-expanded',String(willShow));};$$('#toolsMenu .tool').forEach(b=>b.addEventListener('click',closeTools));$('#settingsButton').onclick=()=>openSettings('models');$('#closeSettings').onclick=closeSettings;$('#drawerBackdrop').onclick=closeSettings;
 $$('.drawer-tabs button').forEach(b=>b.onclick=()=>selectSettings(b.dataset.settings));$('#accountButton').onclick=()=>state.user?openSettings('profile'):showAuth('guest');$('#accountAction').onclick=()=>{if(state.user?.role==='guest'){closeSettings();showAuth('upgrade');}else if(state.user){logout();}else{closeSettings();showAuth('register');}};
 $('#logoutButton').onclick=logout;$('#profileForm').onsubmit=saveProfile;$('#profileAvatar').onchange=e=>saveAvatar(e.target.files[0]);
 for(const id of ['themeSelect','accentColor','surfaceColor','textColor','fontSelect','fontCustom','uiScale'])$('#'+id).addEventListener('input',saveAppearance);$('#resetAppearance').onclick=resetAppearance;$('#fontUpload').onchange=e=>uploadFont(e.target.files[0]);
 $('#authForm').onsubmit=submitAuth;$('#closeAuth').onclick=()=>{$('#authOverlay').hidden=true;state.pending=null;};$('#guestMode').onclick=()=>selectAuthMode('guest');$('#loginMode').onclick=()=>selectAuthMode('login');$('#registerMode').onclick=()=>selectAuthMode(state.user?.role==='guest'?'upgrade':'register');
 $('#partsButton').onclick=()=>withSession(async()=>togglePanel('partsPane'));$('#garageButton').onclick=()=>withSession(async()=>togglePanel('garagePane'));$('#editButton').onclick=()=>togglePanel('editPane');$('#closeParts').onclick=()=>$('#partsPane').hidden=true;$('#closeGarage').onclick=()=>$('#garagePane').hidden=true;$('#closeEdit').onclick=()=>$('#editPane').hidden=true;
 $('#partSearch').oninput=renderParts;$('#newProject').onclick=()=>withSession(async()=>{await createProject();hideSidePanels();$('#welcome').hidden=false;$('#promptInput').focus();});$('#manifestButton').onclick=()=>withSession(async()=>{if(!state.project){toast('Create a project first');return;}const manifest=await api('projects/'+state.project.id+'/manifest');downloadJSON(manifest,'UMI_'+state.project.id.slice(0,8)+'_manifest.json');});
 $('#galleryAction').onchange=()=>{updateGalleryModeUI();saveImageOptions();};$('#gallerySystem').onchange=saveImageOptions;$('#galleryPart').oninput=saveImageOptions;$('#galleryInstructions').oninput=saveImageOptions;$('#collapseGallery').onclick=()=>{const collapsed=$('#galleryPane').classList.toggle('collapsed');$('#collapseGallery').textContent=collapsed?'□':'−';};enableGalleryDrag();
 $('#previewPrev').onclick=()=>openPreview(state.previewIndex-1);$('#previewNext').onclick=()=>openPreview(state.previewIndex+1);$('#closePreview').onclick=closePreview;$('#previewPick').onclick=async()=>{try{await toggleReference(state.assets[state.previewIndex].id);openPreview(state.previewIndex);}catch(e){toast(e.message,true);}};$('#imagePreview').onclick=e=>{if(e.target===$('#imagePreview'))closePreview();};
 $('#attachButton').onclick=()=>$('#uploadInput').click();$('#uploadInput').onchange=e=>{uploadFile(e.target.files[0]).catch(err=>toast(err.message,true));e.target.value='';};$('#showGallery').onclick=()=>toggleGallery(true);$('#closeGallery').onclick=()=>toggleGallery(false);$('#generateButton').onclick=generateConcepts;$('#exportButton').onclick=()=>withSession(async()=>{if(!state.project){toast('Create a project first');return;}window.location.href='/api/projects/'+state.project.id+'/export';});
 $('#clearChatView').onclick=()=>$('#conversation').hidden=true;for(const id of ['bodyColor','rideHeight','wheelSize','explodeToggle'])$('#'+id).oninput=applyModelSettings;$('#saveDesign').onclick=()=>saveModel().catch(e=>toast(e.message,true));$('#driveButton').onclick=toggleDrive;$('#resetDriveButton').onclick=()=>state.viewer?.resetDriving();
 $('#logsButton').onclick=showLogs;$('#closeLogs').onclick=closeLogs;$('#collapseLogs').onclick=()=>{const collapsed=$('#logWindow').classList.toggle('collapsed');$('#collapseLogs').textContent=collapsed?'□':'−';};$('#logSmaller').onclick=()=>changeLogSize(-1);$('#logLarger').onclick=()=>changeLogSize(1);$('#logScope').onchange=refreshLogs;$('#refreshLogs').onclick=refreshLogs;$('#copyLogs').onclick=async()=>{try{await navigator.clipboard.writeText(state.logText);toast('Session log copied');}catch(e){toast('Clipboard unavailable',true);}};enableLogDrag();
 let depth=0;document.addEventListener('dragenter',e=>{if(![...(e.dataTransfer?.types||[])].includes('Files'))return;depth++;$('#dropOverlay').hidden=false;});document.addEventListener('dragover',e=>{if([...(e.dataTransfer?.types||[])].includes('Files'))e.preventDefault();});document.addEventListener('dragleave',e=>{if(![...(e.dataTransfer?.types||[])].includes('Files'))return;depth=Math.max(0,depth-1);if(!depth)$('#dropOverlay').hidden=true;});document.addEventListener('drop',e=>{e.preventDefault();depth=0;$('#dropOverlay').hidden=true;const file=[...(e.dataTransfer?.files||[])].find(f=>f.type.startsWith('image/'));if(file)uploadFile(file).catch(err=>toast(err.message,true));});
 document.addEventListener('click',e=>{if(!e.target.closest('.header-right'))closeTools();});document.addEventListener('keydown',e=>{if(e.key==='Escape'){closePreview();closeTools();$('#authOverlay').hidden=true;closeSettings();hideSidePanels();$('#galleryPane').hidden=true;}});
}
loadTempProviders();bind();updateGalleryModeUI();loadAppearance();restoreLocalFont();try{state.logSize=Math.min(23,Math.max(9,Number(localStorage.getItem('umi-lab.log-font')||12)));}catch(e){}$('#logOutput').style.fontSize=state.logSize+'px';initializeViewer();refreshSession().catch(err=>toast('Server connection unavailable: '+err.message,true));
