import test from 'node:test';
import assert from 'node:assert/strict';
import {
 EQUIP_SELECTOR_STORAGE_KEY,defaultEquipSelectorPreferences,loadEquipSelectorPreferences,
 normalizeEquipSelectorPreferences,saveEquipSelectorPreferences,
} from './equipSelectorPreferences';
import type {EquipSelectorPreferences} from './equipSelectorPreferences';
import {
 SERVANT_SELECTOR_STORAGE_KEY,defaultServantSelectorPreferences,
 loadServantSelectorPreferences,saveServantSelectorPreferences,
} from './servantSelectorPreferences';

const preferences=(extra:Partial<EquipSelectorPreferences>={}):EquipSelectorPreferences=>({...defaultEquipSelectorPreferences(),...extra});
const storage=(raw:string|null=null)=>{
 const entries=new Map<string,string>();if(raw!==null)entries.set(EQUIP_SELECTOR_STORAGE_KEY,raw);
 return {getItem:(key:string)=>entries.get(key)??null,setItem:(key:string,value:string)=>{entries.set(key,value);},entries};
};

test('fresh equip preferences keep common essences enabled and other filters unrestricted',()=>{
 assert.deepEqual(defaultEquipSelectorPreferences(),{version:1,rarity:'',common:true,owned:false});
 const first=defaultEquipSelectorPreferences(),second=defaultEquipSelectorPreferences();
 first.common=false;assert.equal(second.common,true);
 assert.deepEqual(loadEquipSelectorPreferences(storage()),second);
});

test('all rarity choices and false toggles survive storage round-trips',()=>{
 const store=storage();
 for(const rarity of ['','0','1','2','3','4','5']){
  for(const common of [true,false])for(const owned of [true,false]){
   const selected=preferences({rarity,common,owned});
   assert.equal(saveEquipSelectorPreferences(selected,store),true);
   assert.deepEqual(loadEquipSelectorPreferences(store),selected);
  }
 }
});

test('invalid versions shapes and JSON reset to defaults',()=>{
 for(const raw of ['{','null','[]','"string"','3','true','{"version":2,"rarity":"5","common":false,"owned":true}','{"rarity":"5"}','{"version":"1"}']){
  assert.deepEqual(loadEquipSelectorPreferences(storage(raw)),defaultEquipSelectorPreferences());
 }
 for(const value of [undefined,null,[],true,3,'',{}])assert.deepEqual(normalizeEquipSelectorPreferences(value),defaultEquipSelectorPreferences());
});

test('invalid fields individually fall back while valid choices are preserved',()=>{
 for(const rarity of [0,5,'6','-1','05',' 5','5 ',null,true]){
  assert.deepEqual(normalizeEquipSelectorPreferences({version:1,rarity,common:false,owned:true}),preferences({common:false,owned:true}));
 }
 for(const invalid of ['false','true',0,1,null,[],{}]){
  assert.deepEqual(normalizeEquipSelectorPreferences({version:1,rarity:'0',common:invalid,owned:true}),preferences({rarity:'0',owned:true}));
  assert.deepEqual(normalizeEquipSelectorPreferences({version:1,rarity:'5',common:false,owned:invalid}),preferences({rarity:'5',common:false}));
 }
});

test('only filter preferences are serialized even when input contains plan and search data',()=>{
 const store=storage(),selected=preferences({rarity:'4',common:false,owned:true});
 assert.equal(saveEquipSelectorPreferences({...selected,query:'not stored',page:3,plan:{party:[100100]},sortKey:'id'} as EquipSelectorPreferences,store),true);
 assert.deepEqual(JSON.parse(store.entries.get(EQUIP_SELECTOR_STORAGE_KEY)!),selected);
 assert.deepEqual([...store.entries.keys()],[EQUIP_SELECTOR_STORAGE_KEY]);
});

test('missing storage read failures and quota failures never interrupt selection',()=>{
 assert.deepEqual(loadEquipSelectorPreferences(null),defaultEquipSelectorPreferences());
 assert.equal(saveEquipSelectorPreferences(preferences(),null),false);
 assert.deepEqual(loadEquipSelectorPreferences({getItem:()=>{throw new Error('SecurityError');}}),defaultEquipSelectorPreferences());
 assert.equal(saveEquipSelectorPreferences(preferences(),{setItem:()=>{throw new Error('QuotaExceededError');}}),false);
 assert.deepEqual(loadEquipSelectorPreferences(),defaultEquipSelectorPreferences());
 assert.equal(saveEquipSelectorPreferences(preferences()),false);
});

test('a blocked browser storage getter falls back safely for reading and writing',()=>{
 const original=Object.getOwnPropertyDescriptor(globalThis,'window');
 const browser=Object.defineProperty({},'localStorage',{get:()=>{throw new Error('SecurityError');}});
 try {
  Object.defineProperty(globalThis,'window',{value:browser,configurable:true});
  assert.deepEqual(loadEquipSelectorPreferences(),defaultEquipSelectorPreferences());
  assert.equal(saveEquipSelectorPreferences(preferences()),false);
 }finally {
  if(original)Object.defineProperty(globalThis,'window',original);
  else Reflect.deleteProperty(globalThis,'window');
 }
});

test('equip and servant preferences coexist without replacing each other',()=>{
 const store=storage(),equip=preferences({rarity:'3',common:false,owned:true});
 const servant={...defaultServantSelectorPreferences(),classKey:'saber',rarity:'5',direction:'desc' as const};
 assert.notEqual(EQUIP_SELECTOR_STORAGE_KEY,SERVANT_SELECTOR_STORAGE_KEY);
 assert.equal(saveServantSelectorPreferences(servant,store),true);
 assert.equal(saveEquipSelectorPreferences(equip,store),true);
 assert.deepEqual(loadServantSelectorPreferences(['saber'],store),servant);
 assert.deepEqual(loadEquipSelectorPreferences(store),equip);
 assert.equal(saveEquipSelectorPreferences(preferences(),store),true);
 assert.deepEqual(loadServantSelectorPreferences(['saber'],store),servant);
 assert.equal(saveServantSelectorPreferences(defaultServantSelectorPreferences(),store),true);
 assert.deepEqual(loadEquipSelectorPreferences(store),defaultEquipSelectorPreferences());
 assert.equal(store.entries.size,2);
});
