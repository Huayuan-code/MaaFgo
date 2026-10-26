import test from 'node:test';
import assert from 'node:assert/strict';
import {clipboardImage,imageMime,MAX_IMAGE_BYTES,readScreenshotResult,screenshotTeam} from './screenshotImportModel';
import type {ScreenshotSlot} from './screenshotImportModel';
import type {Catalog} from './model';
const catalog:Catalog={servants:[{id:1,name:'甲'}],equips:[{id:2,name:'乙',recognizable:true},{id:3,name:'不可识别'}],mysticCodes:[]};
const slots=():ScreenshotSlot[]=>Array.from({length:6},(_,slot)=>({slot,servantId:slot===0?1:null,status:slot===0?'identified':'empty',support:slot===0,equipStatus:'empty'}));
test('screenshot formats and size are explicit; empty MIME may use filename extension',()=>{
 for(const type of ['image/png','image/jpeg','image/webp'])assert.equal(imageMime({type,size:10}),type);
 assert.equal(imageMime({type:'',name:'中文.JPEG',size:1}),'image/jpeg');
 for(const file of [{type:'image/gif',size:10},{type:'text/plain',name:'a.png',size:10},{type:'image/png',size:0},{type:'image/png',size:MAX_IMAGE_BYTES+1}])assert.throws(()=>imageMime(file));
});
test('clipboard image routing ignores ordinary text and rejects multiple images',()=>{
 const fake={} as File;
 assert.equal(clipboardImage([{kind:'string',type:'text/plain',getAsFile:()=>fake}]),null);
 assert.equal(clipboardImage([{kind:'file',type:'image/png',getAsFile:()=>fake}]),fake);
 assert.throws(()=>clipboardImage(Array.from({length:2},()=>({kind:'file',type:'image/png',getAsFile:()=>fake}))));
});
test('screenshot preview must contain all six ordered slots and strict identities',()=>{
 const original={slots:slots(),warnings:['请核对',null]};const read=readScreenshotResult(original);
 assert.deepEqual(read.warnings,['请核对']);assert.notEqual(read.slots[0],original.slots[0]);
 for(const bad of [slots().slice(1),[...slots().slice(0,5),slots()[0]],slots().map(s=>({...s,servantId:true})),slots().map(s=>({...s,support:'false'}))])assert.throws(()=>readScreenshotResult({slots:bad}));
});
test('screenshot import writes only observed requirements, without invented skill levels or master outfit',()=>{
 const rows=slots();rows[0].equipId=2;const before=structuredClone(rows);
 const data=screenshotTeam(rows,catalog);
 assert.deepEqual(data,{team:{name:'截图导入编队',onFieldSvts:[{supportType:'friend',svtId:1,equip1:{id:2}},null,null],backupSvts:[null,null,null]},actions:[]});
 assert.deepEqual(rows,before);
});
test('manual corrections support CE-only friend but reject owned CE without servant',()=>{
 const rows=slots();rows[0]={...rows[0],servantId:null,status:'unknown',equipId:2};
 assert.deepEqual(screenshotTeam(rows,catalog).team.onFieldSvts[0],{supportType:'friend',equip1:{id:2}});
 rows[0].support=false;assert.throws(()=>screenshotTeam(rows,catalog),/补选从者/);
});
test('manual correction rejects unsupported CE, unknown servant, repeated support and blank result',()=>{
 for(const key of ['servantId','equipId'] as const){const rows=slots();rows[0][key]=999;assert.throws(()=>screenshotTeam(rows,catalog));}
 const unsupported=slots();unsupported[0].equipId=3;assert.throws(()=>screenshotTeam(unsupported,catalog));
 const duplicate=slots();duplicate[1].support=true;assert.throws(()=>screenshotTeam(duplicate,catalog));
 const blank=slots().map(s=>({...s,servantId:null,support:false}));assert.throws(()=>screenshotTeam(blank,catalog));
});
