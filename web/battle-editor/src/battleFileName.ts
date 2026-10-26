import {servantFor} from './model';
import type {Catalog,Json} from './model';

export type NamingSource='local'|'chaldea'|'bbc';

export function restoreNamingSource(value:unknown):NamingSource {
 return value==='chaldea'||value==='bbc'?value:'local';
}

/** Count UTF-16 units while keeping each complete Unicode code point. */
function truncate(value:string,limit:number):string {
 let result='';
 for(const character of value){if(result.length+character.length>limit)break;result+=character;}
 return result;
}

function cleanName(value:string):string {
 const cleaned=value.replace(/[<>:"/\\|?*]|\p{Cc}/gu,'-').replace(/^[\s.]+|[\s.]+$/gu,'');
 return truncate(cleaned,40).replace(/[\s.]+$/gu,'');
}

function frontName(data:Json,catalog:Catalog,index:number):string {
 const member=data.team?.onFieldSvts?.[index];
 if(member==null)return `空位${index+1}`;
 const id=member.svtId,fallback=cleanName(`从者${id??'未知'}`)||'未知从者';
 const name=id!=null?servantFor(catalog,id)?.name:undefined;
 return typeof name==='string'?cleanName(name)||fallback:fallback;
}

/** Suggest a basename only; provenance remains separate from the Chaldea tree. */
export function suggestBattleFileName(data:Json,catalog:Catalog,source:NamingSource,
 existingNames:readonly string[],makeSuffix:()=>string):string {
 const stem=`${restoreNamingSource(source)}_${[0,1,2].map(index=>frontName(data,catalog,index)).join('_')}`;
 const occupied=new Set(existingNames.filter(name=>typeof name==='string').map(name=>name.toLowerCase()));
 const candidate=(suffix:string)=>`${truncate(stem,160-5-suffix.length)}${suffix}.json`;
 const base=candidate('');
 if(!occupied.has(base.toLowerCase()))return base;
 // Only a collision consumes randomness, once per suggestion; arbitrary factory
 // output cannot introduce a path, an extension, or an unbounded suffix.
 const suffix=String(makeSuffix()).toLowerCase().replace(/[^0-9a-f]/g,'').slice(0,6).padEnd(6,'0');
 let ordinal=1;
 while(true){
  const name=candidate(`_${suffix}${ordinal===1?'':`_${ordinal}`}`);
  if(!occupied.has(name.toLowerCase()))return name;
  ordinal++;
 }
}
