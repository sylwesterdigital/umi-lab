/* UMI LAB deterministic, dependency-free layout helpers.
   Image coordinates denote centres; visual placement is independent of pan/zoom. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;root.UMILayouts=api;})(typeof window==='object'?window:globalThis,function(){
'use strict';
function extent(node,hero){if(node.kind==='note')return{w:350,h:310};return node.id===hero||node.kind==='hero'?{w:446,h:346}:node.kind==='component'?{w:204,h:184}:{w:252,h:215};}
function packHidden(node,packs){return !!(node.packId&&packs.some(p=>p.id===node.packId&&p.hidden));}
function visible(nodes,packs){return nodes.filter(n=>!n.archived&&!packHidden(n,packs||[]));}
function collides(a,ae,b,be,padding=45){return Math.abs(a.x-b.x)*2<(ae.w+be.w+padding*2)&&Math.abs(a.y-b.y)*2<(ae.h+be.h+padding*2);}
function nextFreeSpot(nodes,wanted,kind,hero,padding=45){
  const source=Array.isArray(nodes)?nodes:[];
  const candidateNode={id:'new',kind:kind||'hero'};const size=extent(candidateNode,hero);
  const anchor={x:Math.round(wanted?.x||0),y:Math.round(wanted?.y||0)};
  function free(p){return source.every(n=>!collides(p,size,n,extent(n,hero),padding));}
  if(free(anchor))return anchor;
  const sx=530,sy=395;
  for(let radius=1;radius<45;radius++){
    const ring=[];
    for(let dx=-radius;dx<=radius;dx++)for(let dy=-radius;dy<=radius;dy++)if(Math.max(Math.abs(dx),Math.abs(dy))===radius)ring.push({x:anchor.x+dx*sx,y:anchor.y+dy*sy,weight:Math.hypot(dx,dy)+Math.abs(dy)*.18});
    ring.sort((a,b)=>a.weight-b.weight||Math.abs(a.y-anchor.y)-Math.abs(b.y-anchor.y));
    for(const c of ring)if(free(c))return{x:c.x,y:c.y};
  }
  const end=Math.max(0,...source.map(n=>n.x+extent(n,hero).w/2));return{x:end+550,y:anchor.y};
}
function groups(nodes){
  const roots=nodes.filter(n=>!n.parent||!nodes.some(v=>v.id===n.parent));
  const grouped=roots.map(r=>({root:r,children:nodes.filter(n=>n.parent===r.id).sort((a,b)=>(a.kind==='angle'?0:1)-(b.kind==='angle'?0:1)||String(a.label).localeCompare(String(b.label)))}));
  return grouped;
}
function positions(nodes,packs,mode,hero){
 const items=visible(nodes,packs),output={};if(!items.length)return output;
 if(mode==='grid'){
   const cols=Math.max(1,Math.ceil(Math.sqrt(items.length*1.4)));
   const sx=495,sy=365;
   items.forEach((n,i)=>{output[n.id]={x:(i%cols-(cols-1)/2)*sx,y:(Math.floor(i/cols)-(Math.ceil(items.length/cols)-1)/2)*sy};});return output;
 }
 if(mode==='orbit'){
   let currentX=0;
   for(const g of groups(items)){
     const maxRing=Math.max(0,Math.ceil(g.children.length/12)-1);
     const farthest=600+maxRing*295;
     output[g.root.id]={x:currentX,y:0};
     g.children.forEach((n,i)=>{const ring=Math.floor(i/12),inRing=i%12,remaining=Math.min(12,g.children.length-ring*12),angle=-Math.PI/2+2*Math.PI*inRing/remaining;const r=600+ring*295;output[n.id]={x:Math.round(currentX+r*Math.cos(angle)),y:Math.round(r*Math.sin(angle))};});
     currentX+=farthest*2+600;
   }
   const xs=Object.values(output).map(p=>p.x),centre=(Math.min(...xs)+Math.max(...xs))/2;for(const p of Object.values(output))p.x-=centre;
   return output;
 }
 if(mode==='fountain'){
   let y=0;
   for(const g of groups(items)){
     const cols=5,rows=Math.ceil(g.children.length/cols);const height=Math.max(520,rows*238+130);
     output[g.root.id]={x:-500,y:y+height/2-230};
     g.children.forEach((n,i)=>{output[n.id]={x:20+(i%cols)*270,y:y+(Math.floor(i/cols)+.5)*238};});
     y+=height+270;
   }
   const vals=Object.values(output);const lo=Math.min(...vals.map(p=>p.y)),hi=Math.max(...vals.map(p=>p.y));for(const p of vals)p.y-=(lo+hi)/2;
   return output;
 }
 throw Error('Unknown layout');
}
return{extent,packHidden,visible,nextFreeSpot,positions};
});
