import test from 'node:test';
import assert from 'node:assert/strict';
import type {Json} from './model';
import {clearEquipRequirement,equipForDisplay,hasStoredEquipRequirement} from './equipRequirements';

test('clearing slot one removes the complete object and all legacy fallback fields only',()=>{
 const second={id:202,future:{keep:true}},third={id:303},board={grandBondEquipSkillChange:true,future:1};
 const member:Json={svtId:100,grandSvt:true,equip1:{id:101,lv:80,limitBreak:true,future:{drop:'whole object'}},
  equip2:second,equip3:third,ceId:999,ceLimitBreak:false,ceLv:55,classBoardData:board,future:{keep:['member']}};
 clearEquipRequirement(member,'equip1');
 assert.deepEqual(member,{svtId:100,grandSvt:true,equip2:second,equip3:third,classBoardData:board,future:{keep:['member']}});
 assert.equal(member.equip2,second);assert.equal(member.equip3,third);assert.equal(member.classBoardData,board);
 assert.equal(hasStoredEquipRequirement(member,'equip1'),false);assert.equal(equipForDisplay(member,'equip1'),undefined);
});

test('each grand slot is independent and clearing two or three preserves legacy slot one',()=>{
 for(const key of ['equip2','equip3']){
  const member:Json={svtId:100,grandSvt:true,equip1:{id:101},equip2:{id:202,future:'bond'},equip3:{id:303},
   ceId:999,ceLimitBreak:true,ceLv:80,classBoardData:{grandBondEquipSkillChange:false},future:{keep:1}};
  const expected=structuredClone(member);delete expected[key];
  clearEquipRequirement(member,key);assert.deepEqual(member,expected);
 }
});

test('own null, zero, empty and legacy-only records remain clearable without inherited placeholders',()=>{
 for(const value of [null,undefined,{id:null},{id:0},{}]){
  const member:Json={equip1:value,future:1};assert.equal(hasStoredEquipRequirement(member,'equip1'),true);
  clearEquipRequirement(member,'equip1');assert.deepEqual(member,{future:1});
 }
 for(const key of ['ceId','ceLimitBreak','ceLv']){
  const member:Json={[key]:null};assert.equal(hasStoredEquipRequirement(member,'equip1'),true);
  assert.equal(hasStoredEquipRequirement(member,'equip2'),false);clearEquipRequirement(member,'equip1');assert.deepEqual(member,{});
 }
 const inherited=Object.create({equip1:{id:101},ceId:999}) as Json;
 assert.equal(hasStoredEquipRequirement(inherited,'equip1'),false);
 assert.equal(hasStoredEquipRequirement(null,'equip1'),false);assert.equal(hasStoredEquipRequirement({},'equip1'),false);
});

test('display prefers a positive current ID, preserves explicit zero/false and copies unknown fields',()=>{
 const member:Json={equip1:{id:101,lv:0,limitBreak:false,future:{nested:['keep']}},ceId:999,ceLv:80,ceLimitBreak:true,future:'member'};
 const before=structuredClone(member),display=equipForDisplay(member,'equip1')!;
 assert.deepEqual(display,{id:101,lv:0,limitBreak:false,future:{nested:['keep']}});
 display.future.nested.push('display only');display.lv=100;assert.deepEqual(member,before);
});

test('null or absent current IDs display compatible legacy attributes without writing them back',()=>{
 for(const stored of [undefined,null,{}, {id:null,future:{keep:true}}, {id:undefined}]){
  const member:Json={ceId:101,ceLv:80,ceLimitBreak:true,future:'member'};
  if(stored!==undefined)member.equip1=stored;
  const before=structuredClone(member),display=equipForDisplay(member,'equip1')!;
  assert.deepEqual(display,{...(stored??{}),id:101,lv:80,limitBreak:true});assert.deepEqual(member,before);
 }
 assert.deepEqual(equipForDisplay({equip1:{id:101},ceLv:80,ceLimitBreak:true},'equip1'),{id:101,lv:80,limitBreak:true});
 assert.deepEqual(equipForDisplay({equip1:{id:101,lv:null,limitBreak:null},ceLv:80,ceLimitBreak:true},'equip1'),{id:101,lv:null,limitBreak:null});
});

test('zero or malformed current IDs never borrow a legacy ID, and grand slots never borrow slot one',()=>{
 for(const id of [0,-1,0.5,NaN,Infinity,Number.MAX_SAFE_INTEGER+1,true,false,'101','0']){
  const member:Json={equip1:{id},ceId:999},before=structuredClone(member);
  assert.equal(equipForDisplay(member,'equip1'),undefined);assert.deepEqual(member,before);
 }
 for(const member of [null,{}, {ceId:0},{ceId:-1},{ceId:'101'},{equip1:[]},{equip1:'bad'}])assert.equal(equipForDisplay(member,'equip1'),undefined);
 assert.equal(equipForDisplay({ceId:999,ceLv:80,ceLimitBreak:true,equip2:{id:null}},'equip2'),undefined);
 assert.deepEqual(equipForDisplay({ceId:999,ceLv:80,ceLimitBreak:true,equip3:{id:303}},'equip3'),{id:303});
});

test('invalid slot keys fail before mutating the member',()=>{
 for(const key of ['equip0','equip4','ceId','svtId','__proto__','']){
  const member:Json={svtId:100,equip1:{id:101},ceId:999},before=structuredClone(member);
  assert.throws(()=>clearEquipRequirement(member,key));assert.throws(()=>hasStoredEquipRequirement(member,key));assert.throws(()=>equipForDisplay(member,key));
  assert.deepEqual(member,before);
 }
});
