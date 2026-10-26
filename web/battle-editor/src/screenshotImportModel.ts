import type {Catalog,Json} from './model';

export const IMAGE_ACCEPT='image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp';
export const MAX_IMAGE_BYTES=16*1024*1024;
export interface ScreenshotSlot {slot:number;servantId:number|null;status:'empty'|'identified'|'unknown';support:boolean;equipId?:number|null;equipStatus?:'empty'|'identified'|'unknown';score?:number;equipScore?:number}
export interface ScreenshotResult {slots:ScreenshotSlot[];warnings:string[];elapsedMs?:number;sourceSize?:number[]}
export function imageMime(file:{type:string;name?:string;size:number}):string {
 if(file.size<=0||file.size>MAX_IMAGE_BYTES)throw new Error('图片为空或超过16 MiB，请换一张较小的截图。');
 const mime=file.type.toLowerCase();
 if(['image/png','image/jpeg','image/webp'].includes(mime))return mime;
 if(!mime){const ext=file.name?.split('.').pop()?.toLowerCase();if(ext==='png')return 'image/png';if(ext==='jpg'||ext==='jpeg')return 'image/jpeg';if(ext==='webp')return 'image/webp';}
 throw new Error('支持 PNG、JPG/JPEG、WebP 静态图片。');
}
export function clipboardImage(items:ArrayLike<{kind:string;type:string;getAsFile:()=>File|null}>):File|null {
 const images=Array.from(items).filter(item=>item.kind==='file'&&item.type.startsWith('image/'));
 if(images.length>1)throw new Error('请每次粘贴一张编队截图。');
 return images[0]?.getAsFile()??null;
}
export function readScreenshotResult(value:any):ScreenshotResult {
 const id=(v:any)=>v==null||(typeof v==='number'&&Number.isSafeInteger(v)&&v>0);
 if(!value||!Array.isArray(value.slots)||value.slots.length!==6||value.slots.some((s:any,i:number)=>!s||s.slot!==i||!id(s.servantId)||!id(s.equipId)||!['empty','identified','unknown'].includes(s.status)||typeof s.support!=='boolean'))throw new Error('识别结果不完整，请重新识别。');
 return {...value,slots:value.slots.map((s:ScreenshotSlot)=>({...s})),warnings:Array.isArray(value.warnings)?value.warnings.filter((s:any)=>typeof s==='string'):[]};
}
export function screenshotTeam(slots:ScreenshotSlot[],catalog:Catalog):Json {
 const result=readScreenshotResult({slots});
 if(result.slots.filter(s=>s.support).length>1)throw new Error('请选择至多一个助战位置。');
 let count=0;
 const roster=result.slots.map(s=>{
  if(s.servantId!=null&&!catalog.servants.some(m=>m.id===s.servantId))throw new Error(`槽位${s.slot+1}的从者不在当前图鉴中，请重新选择。`);
  if(s.equipId!=null&&!catalog.equips.some(e=>e.id===s.equipId&&e.recognizable===true))throw new Error(`槽位${s.slot+1}的礼装没有工程识别资源，请重新选择。`);
  if(!s.servantId&&!s.support){if(s.equipId)throw new Error(`槽位${s.slot+1}只选择了礼装，请补选从者或将它设为助战。`);return null;}
  const member:Json={supportType:s.support?'friend':'none'};
  if(s.servantId)member.svtId=s.servantId;
  if(s.equipId)member.equip1={id:s.equipId};
  count++;return member;
 });
 if(!count)throw new Error('请至少选择一位从者或一个助战要求。');
 return {team:{name:'截图导入编队',onFieldSvts:roster.slice(0,3),backupSvts:roster.slice(3)},actions:[]};
}
