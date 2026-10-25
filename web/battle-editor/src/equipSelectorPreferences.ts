export const EQUIP_SELECTOR_STORAGE_KEY='maafgo.battleEditor.equipSelector.v1';

export interface EquipSelectorPreferences {
 version:1;
 rarity:string;
 common:boolean;
 owned:boolean;
}

export function defaultEquipSelectorPreferences():EquipSelectorPreferences {
 return {version:1,rarity:'',common:true,owned:false};
}

/** Keep only supported filter fields; selection and search belong to the current dialog. */
export function normalizeEquipSelectorPreferences(value:unknown):EquipSelectorPreferences {
 const defaults=defaultEquipSelectorPreferences();
 if(!value||typeof value!=='object'||Array.isArray(value))return defaults;
 const candidate=value as Record<string,unknown>;
 if(candidate.version!==1)return defaults;
 return {
  version:1,
  rarity:typeof candidate.rarity==='string'&&/^[0-5]$/.test(candidate.rarity)?candidate.rarity:'',
  common:typeof candidate.common==='boolean'?candidate.common:defaults.common,
  owned:typeof candidate.owned==='boolean'?candidate.owned:defaults.owned,
 };
}

function browserStorage():Storage|null {
 try{return typeof window==='undefined'?null:window.localStorage;}catch{return null;}
}

export function loadEquipSelectorPreferences(storage?:Pick<Storage,'getItem'>|null):EquipSelectorPreferences {
 try {
  const raw=(storage===undefined?browserStorage():storage)?.getItem(EQUIP_SELECTOR_STORAGE_KEY);
  return raw?normalizeEquipSelectorPreferences(JSON.parse(raw)):defaultEquipSelectorPreferences();
 }catch{return defaultEquipSelectorPreferences();}
}

/** A denied or full store must not interrupt selecting a craft essence. */
export function saveEquipSelectorPreferences(preferences:EquipSelectorPreferences,storage?:Pick<Storage,'setItem'>|null):boolean {
 try {
  const target=storage===undefined?browserStorage():storage;
  if(!target)return false;
  target.setItem(EQUIP_SELECTOR_STORAGE_KEY,JSON.stringify(normalizeEquipSelectorPreferences(preferences)));
  return true;
 }catch{return false;}
}
