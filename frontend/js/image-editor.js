// UMI LAB floating image editor. Pixel coordinate selections always refer to source imagery.
export function setupImageEditor({onPick,onCrop,onEdit,getModel=()=>''}) {
  const $=id=>document.getElementById(id);
  const pane=$('imagePreview'), stage=$('previewStage'), canvas=$('previewCanvas'),ctx=canvas.getContext('2d');
  const ratio=$('previewRatio'), toolRect=$('previewRect'),toolMove=$('previewMove'),toolPan=$('previewPan');
  const selectStatus=$('previewSelectionInfo'), crop=$('previewCrop'), edit=$('previewEdit'),confirm=$('previewConfirm'),cancel=$('previewCancel');
  const image=new Image();image.decoding='async';
  let activeAsset=null,idx=0,count=0,drag=null,selection=null,confirmed=false,tool='rect',busy=false,busyTimer=null,busyStarted=0,animFrame=null;
  let zoom=1,panX=0,panY=0,dimensions={w:1,h:1,scale:1,ox:0,oy:0};
  const clamp=(x,a,b)=>Math.max(a,Math.min(b,x));
  const ratios={'free':0,'1:1':1,'3:2':3/2,'3:4':3/4,'4:3':4/3,'16:9':16/9};
  function updateActions(){const valid=!!selection&&selection.w>=8&&selection.h>=8;crop.disabled=busy||!valid;edit.disabled=busy||!valid;confirm.disabled=busy||!valid||confirmed;cancel.disabled=busy||!selection;toolMove.disabled=busy||!valid;selectStatus.textContent=busy?'AI request running · selected pixels are being processed':!selection?'Drag a rectangle · G moves selection · wheel/pinch to zoom':`${Math.round(selection.w)} × ${Math.round(selection.h)} px · ${tool==='move'?'Drag inside to move · R returns to drawing':confirmed?'selected · press G to move':'Enter to confirm · G to move · outside to cancel'}`;}
  function sourcePoint(ev,inside=true){const r=canvas.getBoundingClientRect(),x=ev.clientX-r.left,y=ev.clientY-r.top;
    const nx=(x-dimensions.ox)/dimensions.scale,ny=(y-dimensions.oy)/dimensions.scale;
    return {x:inside?clamp(nx,0,image.naturalWidth):nx,y:inside?clamp(ny,0,image.naturalHeight):ny};}
  function hasImage(){return image.complete&&image.naturalWidth>0;}
  function render(){if(pane.hidden||pane.classList.contains('collapsed'))return;
    const rect=stage.getBoundingClientRect();const w=Math.max(1,rect.width),h=Math.max(1,rect.height),dpr=Math.min(2,window.devicePixelRatio||1);
    canvas.width=Math.round(w*dpr);canvas.height=Math.round(h*dpr);canvas.style.width=w+'px';canvas.style.height=h+'px';
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);ctx.fillStyle='#0d1016';ctx.fillRect(0,0,w,h);
    if(!hasImage()){ctx.fillStyle='#a5adbe';ctx.textAlign='center';ctx.fillText('Loading image…',w/2,h/2);return;}
    const fit=Math.min(w/image.naturalWidth,h/image.naturalHeight);const scale=fit*zoom;
    const ox=(w-image.naturalWidth*scale)/2+panX,oy=(h-image.naturalHeight*scale)/2+panY;
    dimensions={w,h,scale,ox,oy};ctx.imageSmoothingEnabled=true;ctx.imageSmoothingQuality='high';
    ctx.drawImage(image,ox,oy,image.naturalWidth*scale,image.naturalHeight*scale);
    if(selection){const r=selection,sx=ox+r.x*scale,sy=oy+r.y*scale,sw=r.w*scale,sh=r.h*scale;
      ctx.save();
      if(busy){
        // During AI edits the full original image stays visible: animate ONLY the inside edge.
        const phase=performance.now()/1050,dx=Math.cos(phase),dy=Math.sin(phase);
        const glow=ctx.createLinearGradient(sx+sw*(.5-.75*dx),sy+sh*(.5-.75*dy),sx+sw*(.5+.75*dx),sy+sh*(.5+.75*dy));
        glow.addColorStop(0,'#46e9cc');glow.addColorStop(.3,'#8dbdff');glow.addColorStop(.65,'#d897fa');glow.addColorStop(1,'#ffb88e');
        const border=Math.min(4,Math.max(2,Math.min(sw,sh)/55));
        ctx.strokeStyle=glow;ctx.lineWidth=border;ctx.setLineDash([]);
        ctx.strokeRect(sx+border/2,sy+border/2,Math.max(0,sw-border),Math.max(0,sh-border));
      }else{
        ctx.beginPath();ctx.rect(ox,oy,image.naturalWidth*scale,image.naturalHeight*scale);ctx.rect(sx,sy,sw,sh);
        ctx.fillStyle='rgba(5,10,20,.55)';ctx.fill('evenodd');
        ctx.strokeStyle=confirmed?'#59f1c2':'#ffc271';ctx.lineWidth=1.5;ctx.setLineDash([8,5]);ctx.strokeRect(sx,sy,sw,sh);
      }
      ctx.restore();
    }
    $('previewZoomLabel').textContent=Math.round(zoom*100)+'%';
  }
  function clear(){selection=null;confirmed=false;if(tool==='move')setTool('rect');updateActions();render();}
  function setTool(next){if(busy||next==='move'&&!selection)return;tool=next;toolRect.setAttribute('aria-pressed',String(next==='rect'));toolMove.setAttribute('aria-pressed',String(next==='move'));toolPan.setAttribute('aria-pressed',String(next==='pan'));canvas.style.cursor=next==='pan'?'grab':next==='move'?'move':'crosshair';updateActions();}
  function geometry(from,to){const ar=ratios[ratio.value]||0;let w=to.x-from.x,h=to.y-from.y;
    const signX=Math.sign(w)||1,signY=Math.sign(h)||1;w=Math.abs(w);h=Math.abs(h);
    if(ar&&w&&h){if(w/h>ar)w=h*ar;else h=w/ar;}
    const maxW=signX>0?image.naturalWidth-from.x:from.x,maxH=signY>0?image.naturalHeight-from.y:from.y;
    const factor=Math.min(1,maxW/Math.max(.001,w),maxH/Math.max(.001,h));w*=factor;h*=factor;
    return{x:from.x+(signX<0?-w:0),y:from.y+(signY<0?-h:0),w,h};
  }
  function selectionPayload(){if(!selection||selection.w<8||selection.h<8||!hasImage())return null;
    const nw=image.naturalWidth,nh=image.naturalHeight;
    return{x:selection.x/nw,y:selection.y/nh,w:selection.w/nw,h:selection.h/nh};}
  function selectionContains(p){return !!selection&&p.x>=selection.x&&p.y>=selection.y&&p.x<=selection.x+selection.w&&p.y<=selection.y+selection.h;}
  function adjustZoom(next,clientX,clientY){if(!hasImage())return;const bounds=canvas.getBoundingClientRect();
    const cx=(clientX??(bounds.left+bounds.width/2))-bounds.left,cy=(clientY??(bounds.top+bounds.height/2))-bounds.top;
    const beforeX=(cx-dimensions.ox)/dimensions.scale,beforeY=(cy-dimensions.oy)/dimensions.scale;
    zoom=clamp(next,.2,18);const scale=Math.min(dimensions.w/image.naturalWidth,dimensions.h/image.naturalHeight)*zoom;
    panX=cx-(dimensions.w-image.naturalWidth*scale)/2-beforeX*scale;
    panY=cy-(dimensions.h-image.naturalHeight*scale)/2-beforeY*scale;render();
  }
  canvas.addEventListener('pointerdown',ev=>{if(busy||ev.button!==0&&ev.button!==1)return;if(!hasImage())return;
    const p=sourcePoint(ev,false);if(tool==='pan'||ev.button===1||ev.shiftKey||ev.altKey){drag={kind:'pan',x:ev.clientX,y:ev.clientY,px:panX,py:panY};canvas.setPointerCapture(ev.pointerId);return;}
    if(p.x<0||p.y<0||p.x>image.naturalWidth||p.y>image.naturalHeight){clear();return;}
    if(tool==='move'){if(selectionContains(p)){drag={kind:'move',from:p,original:{...selection}};canvas.setPointerCapture(ev.pointerId);}else clear();return;}
    if(selection&&!selectionContains(p)){clear();return;}
    selection=null;confirmed=false;drag={kind:'select',from:sourcePoint(ev)};canvas.setPointerCapture(ev.pointerId);updateActions();});
  canvas.addEventListener('pointermove',ev=>{if(!drag)return;
    if(drag.kind==='pan'){panX=drag.px+ev.clientX-drag.x;panY=drag.py+ev.clientY-drag.y;render();}
    else if(drag.kind==='move'){const pt=sourcePoint(ev);const original=drag.original;selection={...original,x:clamp(original.x+pt.x-drag.from.x,0,image.naturalWidth-original.w),y:clamp(original.y+pt.y-drag.from.y,0,image.naturalHeight-original.h)};render();updateActions();}
    else{selection=geometry(drag.from,sourcePoint(ev));render();updateActions();}});
  function pointerFinish(ev){if(!drag)return;if(drag.kind==='select'){selection=geometry(drag.from,sourcePoint(ev));if(selection.w<8||selection.h<8)selection=null;confirmed=false;updateActions();render();}drag=null;
    if(canvas.hasPointerCapture(ev.pointerId))canvas.releasePointerCapture(ev.pointerId);}
  canvas.addEventListener('pointerup',pointerFinish);canvas.addEventListener('pointercancel',pointerFinish);
  canvas.addEventListener('wheel',ev=>{if(!hasImage())return;ev.preventDefault();adjustZoom(zoom*Math.exp(-ev.deltaY*.002),ev.clientX,ev.clientY);},{passive:false});
  toolRect.onclick=()=>setTool('rect');toolMove.onclick=()=>setTool(tool==='move'?'rect':'move');toolPan.onclick=()=>setTool('pan');ratio.onchange=()=>{clear();setTool('rect');};
  $('previewZoomIn').onclick=()=>adjustZoom(zoom*1.25);$('previewZoomOut').onclick=()=>adjustZoom(zoom/1.25);
  $('previewFit').onclick=()=>{zoom=1;panX=0;panY=0;render();};
  confirm.onclick=()=>{if(selection){confirmed=true;updateActions();render();}};cancel.onclick=clear;
  function busyUpdateLabel(){const s=Math.floor((Date.now()-busyStarted)/1000);$('previewProcessingClock').textContent=String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0');}
  async function runImageAction(operation){if(busy)return;const r=selectionPayload();if(!r||!activeAsset)return;
    const prompt=$('previewEditPrompt').value.trim();if(operation==='edit'&&!prompt){$('previewEditPrompt').focus();return;}
    busy=true;busyStarted=Date.now();const operationAsset=activeAsset;
    $('previewProcessingText').textContent=operation==='crop'?'Cropping selection':'AI editing · '+(getModel()||'image model');
    $('previewProcessing').hidden=false;pane.classList.add('editor-is-processing');
    $('previewEdit').textContent=operation==='crop'?'Edit AI':'Editing…';$('previewCrop').textContent=operation==='crop'?'Cropping…':'Crop';
    $('previewPick').disabled=true;$('previewPrev').disabled=true;$('previewNext').disabled=true;
    busyUpdateLabel();busyTimer=setInterval(busyUpdateLabel,1000);updateActions();
    const animate=()=>{if(!busy)return;render();animFrame=requestAnimationFrame(animate);};animFrame=requestAnimationFrame(animate);
    try{await (operation==='crop'?onCrop(operationAsset,r):onEdit(operationAsset,r,prompt));}
    finally{busy=false;clearInterval(busyTimer);cancelAnimationFrame(animFrame);$('previewProcessing').hidden=true;pane.classList.remove('editor-is-processing');
      $('previewEdit').textContent='Edit AI';$('previewCrop').textContent='Crop';
      $('previewPick').disabled=false;$('previewPrev').disabled=false;$('previewNext').disabled=false;updateActions();render();}
  }
  crop.onclick=()=>runImageAction('crop');
  edit.onclick=()=>runImageAction('edit');
  $('previewPick').onclick=()=>{if(activeAsset)onPick(activeAsset);};
  function saveBounds(){try{const b=pane.getBoundingClientRect();localStorage.setItem('umi.editor.bounds',JSON.stringify({left:b.left,top:b.top,width:b.width,height:b.height}));}catch(e){}}
  function draggable(handle,resizer=false){handle.addEventListener('pointerdown',ev=>{if(ev.button!==0||ev.target.closest('button,input,select,textarea'))return;
    const b=pane.getBoundingClientRect(),start={left:b.left,top:b.top,width:b.width,height:b.height,x:ev.clientX,y:ev.clientY};ev.preventDefault();handle.setPointerCapture(ev.pointerId);
    const move=e=>{const dx=e.clientX-start.x,dy=e.clientY-start.y;
      if(resizer){pane.style.width=clamp(start.width+dx,330,innerWidth-start.left-8)+'px';pane.style.height=clamp(start.height+dy,180,innerHeight-start.top-8)+'px';}
      else{pane.style.left=clamp(start.left+dx,0,Math.max(0,innerWidth-100))+'px';pane.style.top=clamp(start.top+dy,0,Math.max(0,innerHeight-42))+'px';}
      requestAnimationFrame(render);
    };
    const end=()=>{handle.removeEventListener('pointermove',move);handle.removeEventListener('pointerup',end);handle.removeEventListener('pointercancel',end);saveBounds();render();};
    handle.addEventListener('pointermove',move);handle.addEventListener('pointerup',end);handle.addEventListener('pointercancel',end);
  });}
  draggable($('previewHandle'));draggable($('previewResize'),true);
  $('previewCollapse').onclick=()=>{pane.classList.toggle('collapsed');$('previewCollapse').textContent=pane.classList.contains('collapsed')?'□':'−';render();};
  $('closePreview').onclick=close;
  $('previewPrev').onclick=()=>document.dispatchEvent(new CustomEvent('umi-preview-step',{detail:-1}));
  $('previewNext').onclick=()=>document.dispatchEvent(new CustomEvent('umi-preview-step',{detail:1}));
  const observer=new ResizeObserver(()=>{if(!pane.hidden)requestAnimationFrame(render);});observer.observe(stage);
  try{const b=JSON.parse(localStorage.getItem('umi.editor.bounds')||'{}');if(Number.isFinite(+b.width)&&+b.width>=330)pane.style.width=Math.min(innerWidth-16,+b.width)+'px';if(Number.isFinite(+b.height)&&+b.height>=180)pane.style.height=Math.min(innerHeight-16,+b.height)+'px';if(Number.isFinite(+b.left))pane.style.left=clamp(+b.left,0,Math.max(0,innerWidth-100))+'px';if(Number.isFinite(+b.top))pane.style.top=clamp(+b.top,0,Math.max(0,innerHeight-42))+'px';}catch(e){}
  image.onload=()=>{zoom=1;panX=0;panY=0;clear();};image.onerror=()=>{selectStatus.textContent='Unable to load this image';};
  function open(asset,index,total,selected){activeAsset=asset;idx=index;count=total;selection=null;confirmed=false;pane.hidden=false;pane.classList.remove('collapsed');$('previewCollapse').textContent='−';
    $('previewCaption').textContent=`${idx+1} / ${count} · ${(asset.view||'Concept').replaceAll('_',' ')}`;$('previewPick').textContent=selected?'Remove reference':'Select reference';
    $('previewEditPrompt').value='';image.src=asset.url;updateActions();requestAnimationFrame(render);}
  function close(){pane.hidden=true;drag=null;activeAsset=null;selection=null;image.removeAttribute('src');}
  document.addEventListener('keydown',ev=>{if(pane.hidden)return;
    if(ev.key==='Escape'){if(selection){clear();ev.stopImmediatePropagation();}else{close();ev.stopImmediatePropagation();}}
    if(ev.key==='Enter'&&!ev.target.closest('input,textarea,select,button')&&selection){ev.preventDefault();confirmed=true;updateActions();render();}
    if(ev.key.toLowerCase()==='g'&&!ev.metaKey&&!ev.ctrlKey&&!ev.altKey&&!ev.target.closest('input,textarea,select,button')&&selection&&!busy){ev.preventDefault();setTool(tool==='move'?'rect':'move');}
    if(ev.key.toLowerCase()==='r'&&!ev.metaKey&&!ev.ctrlKey&&!ev.altKey&&!ev.target.closest('input,textarea,select,button')&&!busy){ev.preventDefault();setTool('rect');}
    if(ev.code==='Space'&&!ev.repeat&&!ev.target.closest('input,textarea,select,button')){ev.preventDefault();setTool('pan');}
  },true);
  document.addEventListener('keyup',ev=>{if(ev.code==='Space'&&tool==='pan')setTool('rect');});
  window.addEventListener('resize',render);
  updateActions();return{open,close,setSelected:value=>{$('previewPick').textContent=value?'Remove reference':'Select reference';}};
}
