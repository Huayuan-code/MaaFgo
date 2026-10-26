import {useEffect,useRef,useState} from 'react';
import {ArrowLeft,ChevronRight,Clipboard,FolderOpen,ImagePlus,Link,LoaderCircle,Upload,X} from 'lucide-react';
import {Modal} from './EditorModal';
import {apiImage} from './api';
import type {Catalog,Json} from './model';
import {clipboardImage,IMAGE_ACCEPT,imageMime,readScreenshotResult,screenshotTeam} from './screenshotImportModel';
import type {ScreenshotResult,ScreenshotSlot} from './screenshotImportModel';
import './importDialog.css';

export function ImportDialog({catalog,battleDirectory,onClose,onDirectory,onJSON,onShare,onImage}:{catalog:Catalog;battleDirectory?:string;onClose:()=>void;onDirectory:()=>void;onJSON:()=>void;onShare:(source:string)=>Promise<boolean>;onImage:(data:Json)=>Promise<boolean>}) {
 const [source,setSource]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false),[submitting,setSubmitting]=useState(false),[preview,setPreview]=useState(''),[result,setResult]=useState<ScreenshotResult|null>(null),[editing,setEditing]=useState<{slot:number;type:'servant'|'equip'}|null>(null),[query,setQuery]=useState('');
 const errorRef=useRef<HTMLParagraphElement>(null);
 const input=useRef<HTMLInputElement>(null),mounted=useRef(true),pending=useRef(false),request=useRef<AbortController|null>(null),currentFile=useRef<File|null>(null),url=useRef('');
 const loadRef=useRef<(file:File)=>Promise<void>>(async()=>{});
 useEffect(()=>{if(error)errorRef.current?.focus();},[error]);
 useEffect(()=>{mounted.current=true;const paste=(event:ClipboardEvent)=>{try{const file=clipboardImage(event.clipboardData?.items??[]);if(file){event.preventDefault();void loadRef.current(file);}}catch(cause){event.preventDefault();setError((cause as Error).message);}};document.addEventListener('paste',paste);return()=>{mounted.current=false;request.current?.abort();if(url.current)URL.revokeObjectURL(url.current);document.removeEventListener('paste',paste);};},[]);
 const recognize=async(file:File)=>{
  if(pending.current){setError('请等待当前识别完成后再选择图片。');return;}
  let mime:string;try{mime=imageMime(file);}catch(cause){setError((cause as Error).message);return;}
  pending.current=true;setBusy(true);setError('');setResult(null);setEditing(null);currentFile.current=file;
  if(url.current)URL.revokeObjectURL(url.current);url.current=URL.createObjectURL(file);setPreview(url.current);
  const controller=new AbortController();request.current=controller;
  try{const value=readScreenshotResult(await apiImage(file,mime,controller.signal));if(mounted.current&&!controller.signal.aborted)setResult(value);}
  catch(cause){if(mounted.current&&!controller.signal.aborted)setError((cause as Error).message||'截图识别失败，请重试。');}
  finally{pending.current=false;if(mounted.current)setBusy(false);}
 };
 loadRef.current=recognize;
 const pasteButton=async()=>{
  try{if(!navigator.clipboard?.read)throw new Error('请在本弹窗内按 Ctrl+V 粘贴图片。');const entries=await navigator.clipboard.read();const item=entries.find(entry=>entry.types.some(type=>type.startsWith('image/')));if(!item)throw new Error('剪贴板中没有图片，请先复制截图，再按 Ctrl+V。');const type=item.types.find(type=>['image/png','image/jpeg','image/webp'].includes(type));if(!type)throw new Error('支持 PNG、JPG/JPEG、WebP 静态图片。');const blob=await item.getType(type);if(mounted.current)await recognize(new File([blob],'剪贴板截图',{type}));}
  catch(cause){if(mounted.current)setError(`${(cause as Error).message} 若浏览器未允许读取，请直接按 Ctrl+V。`);}
 };
 const update=(index:number,changes:Partial<ScreenshotSlot>)=>setResult(old=>old?{...old,slots:old.slots.map((s,i)=>i===index?{...s,...changes}:s)}:old);
 const chooseSupport=(index:number,checked:boolean)=>setResult(old=>old?{...old,slots:old.slots.map((s,i)=>({...s,support:i===index?checked:false}))}:old);
 const commit=async()=>{
  if(!result||pending.current)return;
  try{const data=screenshotTeam(result.slots,catalog);pending.current=true;setSubmitting(true);setError('');const accepted=await onImage(data);if(mounted.current&&!accepted)setError('当前草稿尚未安全保存，已保留原方案。请处理提示后重试。');}
  catch(cause){if(mounted.current)setError((cause as Error).message);}
  finally{pending.current=false;if(mounted.current)setSubmitting(false);}
 };
 const importShare=async()=>{if(pending.current)return;pending.current=true;setSubmitting(true);setError('');try{const ok=await onShare(source.trim());if(mounted.current&&!ok)setError('未切换方案，请先处理当前草稿提示。');}catch(cause){if(mounted.current)setError((cause as Error).message);}finally{pending.current=false;if(mounted.current)setSubmitting(false);}};
 const items=editing?(editing.type==='servant'?catalog.servants:catalog.equips.filter(e=>e.recognizable===true)).filter(item=>`${item.name} ${item.id} ${item.nameJp??''}`.toLowerCase().includes(query.trim().toLowerCase())).slice(0,40):[];
 return <Modal title={result?'核对截图识别结果':'导入战斗方案'} wide={!!result} closeDisabled={submitting} onClose={onClose}><div className="modal-content import-dialog">
  {!result&&<><button className="import-config-entry" data-autofocus="" disabled={busy||submitting} onClick={onDirectory}><span className="import-entry-icon"><FolderOpen size={27}/></span><span><strong>从 config/Battle 选择</strong><small>导入工程中已有的战斗方案</small></span><ChevronRight size={22}/></button><p className="import-config-path">{battleDirectory??'当前 MaaFGO 实例的 config/Battle 目录'}</p></>}
  {result&&<button autoFocus className="text-button" disabled={submitting} onClick={()=>{setResult(null);setEditing(null);setError('');}}><ArrowLeft size={16}/>返回导入方式</button>}
  {!result&&<section className="import-image-section" aria-label="从编队截图导入"><div className="import-section-heading"><ImagePlus size={20}/><strong>从编队截图识别</strong><span>离线</span></div><div className="import-image-drop" tabIndex={0} aria-label="编队截图粘贴区，按 Ctrl+V 粘贴" onDragOver={e=>{e.preventDefault();}} onDrop={e=>{e.preventDefault();if(e.dataTransfer.files.length!==1){setError('请每次上传一张编队截图。');return;}void recognize(e.dataTransfer.files[0]);}}><p>拖入截图，或在本弹窗按 <kbd>Ctrl+V</kbd> 粘贴</p><div><button className="button" disabled={busy||submitting} onClick={()=>input.current?.click()}><Upload size={16}/>上传图片</button><button className="button" disabled={busy||submitting} onClick={()=>void pasteButton()}><Clipboard size={16}/>粘贴图片</button></div><small>PNG、JPG/JPEG、WebP · 静态图片 · 最大16 MiB</small></div><p className="import-help">请使用完整的游戏六人编队确认页截图，保留从者和礼装区域；支持不同分辨率和宽屏截图。</p></section>}
  {preview&&<figure className="import-image-preview"><img src={preview} alt="待识别的编队截图"/>{busy&&<figcaption role="status"><LoaderCircle size={18} className="local-import-spinner"/>正在定位并识别，首次加载模板可能稍久…</figcaption>}{!busy&&!result&&<button className="button" disabled={submitting} onClick={()=>currentFile.current&&void recognize(currentFile.current)}>重新识别</button>}</figure>}
  {error&&<p ref={errorRef} tabIndex={-1} className="import-error" role="alert">{error}</p>}
  {result&&<><p className="import-help">已完成识别（{((result.elapsedMs??0)/1000).toFixed(1)}秒）。请核对后导入，可在这里更换识别结果；未识别项目不会自动填写。</p><div className="screenshot-slot-grid">{result.slots.map((slot,i)=>{const servant=catalog.servants.find(s=>s.id===slot.servantId),equip=catalog.equips.find(e=>e.id===slot.equipId);return <article key={i} className={`screenshot-slot ${slot.support?'support':''}`}><header><strong>{i+1} · {i<3?'前排':'候补'}</strong><label><input type="checkbox" aria-label={`槽位 ${i+1} 为助战`} disabled={submitting} checked={slot.support} onChange={e=>chooseSupport(i,e.target.checked)}/>助战</label></header><div className="screenshot-person">{servant?.image?<img src={servant.image} alt={servant.name}/>:<span className="screenshot-placeholder">{slot.support?'助':slot.equipId?'?':slot.status==='empty'?'空':'?'}</span>}<div><strong>{servant?.name??(slot.support?'助战（仅要求礼装）':slot.equipId?'未选择从者':slot.status==='empty'?'不要求此位置':'未识别从者')}</strong><button className="text-button" disabled={submitting} onClick={()=>{setEditing({slot:i,type:'servant'});setQuery('');}}>选择 / 更换从者</button></div></div><div className="screenshot-equip">{equip?.image&&<img src={equip.image} alt={equip.name}/>}<span>{equip?.name??(slot.equipStatus==='unknown'?'未识别礼装':'不要求礼装')}</span>{slot.equipId&&<button className="icon" aria-label={`清除槽位 ${i+1} 截图礼装`} disabled={submitting} onClick={()=>update(i,{equipId:null,equipStatus:'empty'})}><X size={15}/></button>}</div><div className="screenshot-slot-tools"><button className="text-button" disabled={submitting} onClick={()=>{setEditing({slot:i,type:'equip'});setQuery('');}}>选择 / 更换礼装</button><button className="text-button" disabled={submitting} onClick={()=>update(i,{servantId:null,equipId:null,status:'empty',equipStatus:'empty',support:false})}>不要求此位置</button></div></article>;})}</div>
   {editing&&<section className="screenshot-picker" aria-label={`更正槽位 ${editing.slot+1} ${editing.type==='servant'?'从者':'礼装'}`}><div><strong>槽位 {editing.slot+1} · 选择{editing.type==='servant'?'从者':'礼装'}</strong><button className="icon" aria-label="关闭截图选择器" onClick={()=>setEditing(null)}><X size={17}/></button></div><input autoFocus aria-label="搜索截图识别图鉴" placeholder="名称 / ID" value={query} onChange={e=>setQuery(e.target.value)}/><div className="screenshot-picker-items">{items.map(item=><button key={item.id} disabled={submitting} onClick={()=>{update(editing.slot,editing.type==='servant'?{servantId:item.id,status:'identified'}:{equipId:item.id,equipStatus:'identified'});setEditing(null);}}>{item.image&&<img src={item.image} alt=""/>}<span>{item.name}<small>{item.id}</small></span></button>)}{!items.length&&<p>没有找到对应项目。</p>}</div><small>只展示前40项，请输入名称或ID缩小范围；礼装只列出工程可识别的资源。</small></section>}
   {result.warnings.length>0&&<p className="import-help">原始识别提示：{result.warnings.join(' ')} 已更正的项目以当前选择为准。</p>}<p className="import-help">仅导入从者、礼装和助战要求，不识别等级、技能、宝具、冠位或御主服；请在编队页补充。图片只在本机处理。</p><button className="button primary full" disabled={submitting} onClick={()=>void commit()}>{submitting?'正在导入…':'确认并导入编队草稿'}</button></>}
  {!result&&<><section className="import-share"><label className="field"><span>Chaldea 分享链接 / ID</span><div><input aria-label="Chaldea 分享链接 / ID" value={source} disabled={busy||submitting} onChange={e=>setSource(e.target.value)} placeholder="粘贴分享链接或 ID"/><button className="button" disabled={!source.trim()||busy||submitting} onClick={()=>void importShare()}><Link size={16}/>导入分享</button></div></label><small>线上分享需要联网；截图识别和本地方案无需联网。</small></section><details className="import-more"><summary>更多导入方式</summary><button className="button" disabled={busy||submitting} onClick={onJSON}><Upload size={16}/>选择本地 Chaldea JSON</button><small>导入独立草稿，不覆盖原文件。</small></details></>}
  <input ref={input} type="file" className="visually-hidden" accept={IMAGE_ACCEPT} aria-label="上传编队截图" onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void recognize(file);}}/>
 </div></Modal>;
}
