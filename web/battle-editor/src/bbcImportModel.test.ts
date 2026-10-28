import test from 'node:test';
import assert from 'node:assert/strict';
import {MAX_BBC_BYTES,bbcPreview,readBBCFile,readBBCImportResult} from './bbcImportModel';
import type {Catalog,Json} from './model';

const catalog:Catalog={servants:[{id:1,name:'阿尔托莉雅',aliases:[11],image:'/servant.webp'}],equips:[{id:20,name:'万华镜',image:'/equip.png'}],mysticCodes:[{id:210,name:'迦勒底战斗服'}]};
const data:Json={team:{name:'BBC 周回',onFieldSvts:[{svtId:11,supportType:'none',equip1:{id:20}},null,{supportType:'friend',equip1:{id:999}}],backupSvts:[null,null,null],mysticCode:{mysticCodeId:210}},actions:[{type:'skill',svt:0,skill:0},{type:'attack',attacks:[{svt:0,isTD:true},{isAuto:true}]},{type:'attack',attacks:[]}]};

test('BBC file reader accepts UTF-8 BOM and reads one JSON object without changing its fields',async()=>{
 const source={servant_0_name:'阿尔托莉雅',master_equip:0,round1_turns:1,round1_turn0_skill:[1],round1_turn0_np:[1],future:['保留']};
 const text='\uFEFF'+JSON.stringify(source);
 assert.deepEqual(await readBBCFile({size:new TextEncoder().encode(text).length,text:async()=>text}),source);
});

test('invalid or oversized BBC files fail before conversion',async()=>{
 for(const size of [0,MAX_BBC_BYTES+1])await assert.rejects(()=>readBBCFile({size,text:async()=>{throw new Error('must not read');}}),/为空或超过/);
 for(const text of ['{broken','null','[]','"配置"'])await assert.rejects(()=>readBBCFile({size:10,text:async()=>text}),/JSON/);
});

test('converted BBC response keeps data and all conversion warnings for explicit preview',()=>{
 const before=structuredClone(data),warnings=['策略按默认选卡补齐','特殊选项需要检查'];
 const converted=readBBCImportResult({data,warnings,validation:{valid:true,issues:[]},sourceName:'周回.json'});
 assert.deepEqual(converted,{data,warnings,validation:{valid:true,issues:[]},sourceName:'周回.json'});
 assert.deepEqual(data,before);assert.notEqual(converted.warnings,warnings);
 for(const value of [{data,warnings:[false],sourceName:'x'}, {data,sourceName:'x'}, {data,warnings:[]}, {data:{team:{},actions:'bad'},warnings:[],sourceName:'x'}, {data:{actions:[]},warnings:[],sourceName:'x'}])assert.throws(()=>readBBCImportResult(value));
});

test('BBC preview has six fixed positions, resolves alias names and retains CE-only support',()=>{
 const before=structuredClone(data),preview=bbcPreview(data,catalog);
 assert.equal(preview.title,'BBC 周回');assert.equal(preview.roster.length,6);
 assert.equal(preview.roster[0].name,'阿尔托莉雅');assert.equal(preview.roster[0].image,'/servant.webp');
 assert.equal(preview.roster[0].equips[0].name,'万华镜');assert.equal(preview.roster[1].name,'不要求此位置');
 assert.equal(preview.roster[2].name,'助战（仅要求礼装）');assert.equal(preview.roster[2].support,true);assert.equal(preview.roster[2].equips[0].name,'礼装 #999');
 assert.equal(preview.turns,2);assert.equal(preview.skills,1);assert.equal(preview.cards,1);assert.equal(preview.mystic,'迦勒底战斗服');
 assert.deepEqual(data,before);
});

test('BBC preview exposes OR candidates within their real grand slots and keeps all fetched data untouched',()=>{
 const source=structuredClone(data);source.team.onFieldSvts[2]={supportType:'npc',grandSvt:true,equip1:{id:20,limitBreak:true,candidates:[{id:999,limitBreak:false}]},equip2:{id:999},equip3:{id:20,candidates:[{id:998}]},unknown:{keep:null}};
 const before=structuredClone(source),member=bbcPreview(source,catalog).roster[2];
 assert.equal(member.support,true);
 assert.deepEqual(member.equips.map(e=>e.sourceKey),['equip1','equip1','equip2','equip3','equip3']);
 assert.deepEqual(member.equips.map(e=>e.id),[20,999,999,20,998]);
 assert.match(member.equips[0].name,/普通礼装 · 候选 1\/2.*万华镜.*满破/);
 assert.match(member.equips[1].name,/普通礼装 · 或 2\/2.*礼装 #999.*非满破/);
 assert.match(member.equips[4].name,/报酬礼装 · 或 2\/2/);
 assert.deepEqual(source,before);
});
