import type {Json} from './model';

const equipKeys=['equip1','equip2','equip3'] as const;
const legacyKeys=['ceId','ceLimitBreak','ceLv'] as const;
const own=(value:Json,key:string):boolean=>Object.prototype.hasOwnProperty.call(value,key);
const record=(value:unknown):value is Json=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const positiveId=(value:unknown):value is number=>typeof value==='number'&&Number.isSafeInteger(value)&&value>0;

function assertEquipKey(key:string):void {
 if(!(equipKeys as readonly string[]).includes(key))throw new Error('礼装槽位必须是 equip1、equip2 或 equip3。');
}

/** An explicit clear removes the requirement and the first slot's legacy fallback. */
export function clearEquipRequirement(member:Json,key:string):void {
 assertEquipKey(key);
 if(!record(member))throw new Error('请先选择有效的从者。');
 delete member[key];
 if(key==='equip1')for(const legacy of legacyKeys)delete member[legacy];
}

/** Even an imported null/zero requirement can be explicitly cleaned up. */
export function hasStoredEquipRequirement(member:Json|null,key:string):boolean {
 assertEquipKey(key);
 return record(member)&&(own(member,key)||(key==='equip1'&&legacyKeys.some(legacy=>own(member,legacy))));
}

/** Display compatibility only: never normalize or change an imported member. */
export function equipForDisplay(member:Json|null,key:string):Json|undefined {
 assertEquipKey(key);
 if(!record(member))return undefined;
 const stored=member[key];
 if(stored!=null&&!record(stored))return undefined;
 const id=stored?.id;
 // A zero ID explicitly disables a requirement; only an absent/null ID falls back.
 const selected=positiveId(id)?id:id==null&&key==='equip1'&&positiveId(member.ceId)?member.ceId:undefined;
 if(selected===undefined)return undefined;
 const display:Json=stored?structuredClone(stored):{};
 display.id=selected;
 if(key==='equip1')for(const [current,legacy] of [['lv','ceLv'],['limitBreak','ceLimitBreak']]){
  if(!own(display,current)&&own(member,legacy))display[current]=structuredClone(member[legacy]);
 }
 return display;
}
