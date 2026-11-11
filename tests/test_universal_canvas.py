"""Object-agnostic photo-table contracts; no provider keys or network required."""
import json
import pathlib
import subprocess
import unittest

ROOT=pathlib.Path(__file__).resolve().parent.parent


class UniversalCanvasTests(unittest.TestCase):
    def test_subject_catalogues_exist(self):
        data=json.loads((ROOT/'object_catalog.json').read_text())
        for key in ('person','room','product','machine','object'):
            self.assertTrue(data[key]['assemblies'], key)
        parts={part for g in data['person']['assemblies'] for part in g['parts']}
        self.assertTrue({'Sunglasses','Watch','Handbag','Necklace'}.issubset(parts))
        scene={part for g in data['room']['assemblies'] for part in g['parts']}
        self.assertTrue({'Desk','Laptop','Chair'}.issubset(scene))

    def test_new_controls_are_connected(self):
        page=(ROOT/'frontend/index.html').read_text()
        js=(ROOT/'frontend/js/app.js').read_text()
        for name in ('arrangeButton','arrangeMenu','fitLayout','subjectType','sceneKind','customPart','addCustomPart'):
            self.assertIn(f'id="{name}"',page)
        for phrase in ('Layout.nextFreeSpot','Layout.positions','setPackVisibility','pack.hidden','subject_type:state.subjectType','state.customParts'):
            self.assertIn(phrase,js)
        self.assertIn('<script defer src="/static/js/canvas-layouts.js"',page)

    def test_layouts_do_not_overlap_or_move_hidden_packs(self):
        script=r'''
const assert=require('node:assert/strict');
const L=require('./frontend/js/canvas-layouts.js');
const nodes=[{id:'hero',kind:'hero',x:0,y:0},{id:'angle',kind:'angle',parent:'hero',x:540,y:0},{id:'hidden',kind:'component',packId:'p',parent:'hero',x:0,y:700}];
const hidden=[{id:'p',hidden:true}];
const dropped=L.nextFreeSpot(nodes,{x:0,y:0},'hero','hero');
for(const n of nodes){assert.equal(L.collides?false:Math.abs(dropped.x-n.x)<5&&Math.abs(dropped.y-n.y)<5,false)}
for(const mode of ['grid','orbit','fountain']){
 const result=L.positions(nodes,hidden,mode,'hero');
 assert.ok(result.hero&&result.angle,mode);
 assert.equal(result.hidden,undefined,mode);
}
const many=Array.from({length:20},(_,i)=>({id:String(i),x:i*12,y:0,kind:i%2?'component':'angle',parent:i?'0':null}));
for(let i=0;i<20;i++){const found=L.nextFreeSpot(many.slice(0,i),{x:0,y:0},many[i].kind,'0');many[i].x=found.x;many[i].y=found.y;}
for(let i=0;i<many.length;i++)for(let j=0;j<i;j++){
 const a=L.extent(many[i],'0'),b=L.extent(many[j],'0');
 assert.ok(Math.abs(many[i].x-many[j].x)*2>=a.w+b.w+90||Math.abs(many[i].y-many[j].y)*2>=a.h+b.h+90,'overlap '+i+' '+j);
}
console.log('UNIVERSAL LAYOUT CHECK PASSED');
'''
        process=subprocess.run(['node','-e',script],cwd=str(ROOT),capture_output=True,text=True,timeout=30)
        self.assertEqual(process.returncode,0,process.stdout+'\n'+process.stderr)

    def test_backend_uses_subject_type_and_manifest(self):
        app=(ROOT/'backend/app.py').read_text()
        for marker in ("OBJECT_CATALOG=json.loads", "'catalogs':OBJECT_CATALOG", "subject_type=str(body.get('subject_type')", "assemblies=PARTS['assemblies'] if scene_type=='vehicle'"):
            self.assertIn(marker,app)
        self.assertIn('Do not introduce unrelated people',app)

if __name__=='__main__':unittest.main()
