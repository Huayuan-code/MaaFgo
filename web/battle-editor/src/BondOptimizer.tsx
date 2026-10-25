import {useEffect,useMemo,useRef,useState} from 'react';
import {AlertTriangle,CheckCircle2,Heart,LoaderCircle,Play,Search,X} from 'lucide-react';
import {api} from './api';
import {Modal} from './EditorModal';
import {members} from './model';
import type {Catalog,Json} from './model';
import {reservedBondSupport} from './bondOptimizerModel';
import {validPartyCostLimit} from './partyCost';
import './bondOptimizer.css';

export function BondOptimizer({data,catalog,onApply,onClose,initialCostLimit,onCostLimitChange}:{data:Json;catalog:Catalog;onApply:(response:Json,snapshot:Json)=>void;onClose:()=>void;initialCostLimit:number;onCostLimitChange:(limit:number)=>void}) {
 const [settings,setSettings]=useState<Json|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[result,setResult]=useState<Json|null>(null);
 const [costLimit,setCostLimit]=useState(String(initialCostLimit)),[bondBase,setBondBase]=useState('1200'),[rarity,setRarity]=useState(5);
 const [ownedServants,setOwnedServants]=useState(true),[ownedEquips,setOwnedEquips]=useState(true),[modifyEquips,setModifyEquips]=useState(false),[confirmedMlb,setConfirmedMlb]=useState(false);
 const [reserved,setReserved]=useState<number|null>(()=>reservedBondSupport(data)),[currentCost,setCurrentCost]=useState('');
 const [excluded,setExcluded]=useState<number[]>([]),[query,setQuery]=useState('');
 const resultRef=useRef<HTMLDivElement>(null);
 useEffect(()=>{if(result)resultRef.current?.scrollIntoView({block:'nearest'});},[result]);
 const roster=members(data),support=roster.findIndex(m=>m&&['friend','npc','fixed'].includes(m.supportType));
 const grand=roster.some((m,i)=>i!==support&&m?.grandSvt);
 useEffect(()=>{let active=true;api('/bond/settings').then(value=>{if(active)setSettings(value);}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[]);
 const excludedChoices=useMemo(()=>catalog.servants.filter(s=>!query||`${s.name} ${s.nameJp??''} ${s.id} ${(s.searchAliases??[]).join(' ')}`.toLowerCase().includes(query.toLowerCase())),[catalog,query]);
 const inventory=settings?.inventory??{};
 const blocked=!!settings&&((ownedServants&&!inventory.servants?.available)||(ownedEquips&&!inventory.equips?.available));
 const validInteger=(value:string,min:number,max:number)=>/^\d+$/.test(value)&&Number(value)>=min&&Number(value)<=max;
 const invalid=!validInteger(costLimit,1,300)||!validInteger(bondBase,1,1000000)||(grand&&!validInteger(currentCost,0,1000))||reserved===null;
 const execute=async()=>{
  const snapshot=data;setBusy(true);setError('');setResult(null);
  try {
   const response=await api('/bond/optimize','POST',{data:snapshot,options:{costLimit:Number(costLimit),bondBase:Number(bondBase),preferredRarity:rarity,
    ownedServantsOnly:ownedServants,ownedEquipsOnly:ownedEquips,modifyEquips,confirmedMlbOnly:confirmedMlb,
    reservedSupportSlot:reserved,excludeServantIds:excluded,currentCost:grand?Number(currentCost):null}});
   onApply(response,snapshot);setResult(response);
  } catch(e){setError((e as Error).message);} finally {setBusy(false);}
 };
 return <Modal title="自动羁绊最大化" onClose={onClose} wide closeDisabled={busy}>
  <div className="bond-modal-body">
   <div className="bond-intro"><Heart size={21}/><div><strong>补齐空位，让剩余COST发挥作用</strong><p>保留已有从者及助战，使用工程现有羁绊算法搭配从者与常驻羁绊礼装。结果应用到当前草稿，可撤销。</p></div></div>
   {error&&<div className="bond-message error" role="alert"><AlertTriangle size={17}/><span>{error}</span></div>}
   {!settings&&!error&&<p className="muted" role="status">正在读取本地羁绊资料和库存…</p>}
   <fieldset disabled={busy} className="bond-options">
    <div className="bond-option-grid">
     <label className="field"><span>队伍COST上限</span><input aria-label="队伍COST上限" type="number" min={1} max={300} value={costLimit} onChange={e=>{const value=e.target.value;setCostLimit(value);if(/^\d+$/.test(value)&&validPartyCostLimit(Number(value)))onCostLimitChange(Number(value));}}/><small>与编队COST显示共用上限，当前浏览器记忆</small></label>
     <label className="field"><span>关卡基础羁绊</span><input aria-label="关卡基础羁绊" type="number" min={1} max={1000000} value={bondBase} onChange={e=>setBondBase(e.target.value)}/><small>用于比较固定点数与百分比礼装</small></label>
     <label className="field"><span>补齐从者优先星级</span><select aria-label="补齐从者优先星级" value={rarity} onChange={e=>setRarity(Number(e.target.value))}>{[5,4,3,2,1,0].map(n=><option value={n} key={n}>{n}星</option>)}</select><small>无合适候选时按5→0星回退</small></label>
    </div>
    <div className="bond-inventories">{([['servants','仅使用本地已持有从者',ownedServants,setOwnedServants],['equips','仅使用本地已持有礼装',ownedEquips,setOwnedEquips]] as const).map(([kind,label,checked,setter])=><div className="bond-inventory" key={kind}><label className="check-field"><input type="checkbox" checked={checked} onChange={e=>setter(e.target.checked)}/>{label}</label><small>{!settings?'正在读取…':inventory[kind]?.available?`${inventory[kind].count}项 · 扫描于 ${inventory[kind].generatedAt?new Date(inventory[kind].generatedAt).toLocaleString('zh-CN'):'未知时间'}`:'没有可用的完整扫描库存'}</small>{settings&&inventory[kind]?.catalogComplete===false&&<small>库存可能遗漏缺模板的对象</small>}</div>)}</div>
    {blocked&&<div className="bond-message" role="status"><AlertTriangle size={16}/><span>已启用的本地库不可用。请先在Maa构建个人从者礼装库，或取消对应选项，使用工程可识别范围规划。</span></div>}
    {(!ownedServants||!ownedEquips)&&<div className="bond-message"><AlertTriangle size={16}/><span>已取消部分持有限制，可能补入尚未持有的从者或礼装；礼装仍限工程可识别范围，请在执行后核对。</span></div>}
    <div className="bond-option-grid two">
     <label className="field"><span>助战槽位</span><select aria-label="助战槽位" value={reserved??''} disabled={support>=0} onChange={e=>setReserved(Number(e.target.value))}>{reserved===null&&<option value="">请先清出一个空位或指定助战</option>}{roster.map((m,i)=>(!m?.svtId||i===support)&&<option value={i} key={i}>第{i+1}槽{support===i?' · 沿用当前助战':' · 保留空位，稍后选择助战'}</option>)}</select></label>
     {grand&&<label className="field"><span>已有编队实际COST（冠位）</span><input aria-label="已有编队实际COST" type="number" min={0} max={1000} value={currentCost} onChange={e=>setCurrentCost(e.target.value)} placeholder="填写游戏中当前已用COST"/><small>冠位三礼装保持，以实际COST起算</small></label>}
    </div>
    <label className="check-field"><input type="checkbox" checked={modifyEquips} onChange={e=>setModifyEquips(e.target.checked)}/>允许更换已有普通礼装</label>
    <p className="bond-option-help">默认保留已选礼装，只填未要求礼装的位置。开启后会重新搭配普通礼装，请核对战斗所需礼装；冠位三礼装和助战始终保留。</p>
    <details className="bond-advanced"><summary>排除从者与满破设置</summary>
     <label className="check-field"><input type="checkbox" checked={confirmedMlb} onChange={e=>setConfirmedMlb(e.target.checked)}/>需满破的礼装只选库存已确认满破者</label>
     <p className="bond-option-help">新增礼装采用工程满破效果并写入满破要求。库存未记录满破时，勾选会排除这些候选；未勾选需自行确认实际满破情况。</p>
     <label className="field"><span>排除补入从者（如羁绊已满）</span><div className="search-field"><Search size={16}/><input aria-label="搜索排除从者" value={query} onChange={e=>setQuery(e.target.value)} placeholder="搜索名称或图鉴ID"/></div></label>
     {excluded.length>0&&<div className="bond-excluded-chips">{excluded.map(id=><button type="button" className="chip" key={id} onClick={()=>setExcluded(ids=>ids.filter(i=>i!==id))}>{catalog.servants.find(s=>s.id===id)?.name??`#${id}`}<X size={12}/></button>)}</div>}
     <div className="bond-exclusion-list" role="group" aria-label="排除补入从者">{excludedChoices.map(s=><label className="check-field" key={s.id}><input type="checkbox" checked={excluded.includes(s.id)} onChange={e=>setExcluded(ids=>e.target.checked?[...ids,s.id]:ids.filter(id=>id!==s.id))}/>{s.name}</label>)}</div>
    </details>
   </fieldset>
   <p className="bond-footnote">最多五名自有从者；助战不计入本地羁绊收益。库存不包含实时羁绊等级，满羁绊从者请在高级设置中排除。算法按星级优先进行有界优化，结果为估算。</p>
   {busy&&<div className="bond-running" role="status"><LoaderCircle size={18}/>正在规划从者与礼装组合，请稍候…</div>}
   {result&&<div ref={resultRef} className="bond-result" role="status"><h3><CheckCircle2 size={19}/>已应用到当前草稿</h3><div className="bond-result-grid"><span>COST<strong>{result.summary.beforeCost} → {result.summary.afterCost}<small> / {result.summary.costLimit}</small></strong></span><span>预估总羁绊<strong>{result.summary.beforeBond.toLocaleString()} → {result.summary.afterBond.toLocaleString()}</strong></span><span>预计增加<strong>+{result.summary.gain.toLocaleString()}</strong></span></div><p>补入{result.summary.addedServants}名从者，调整{result.summary.changedSlots}个槽位。关闭弹窗后可用Ctrl+Z撤销本次结果。</p><ul>{result.warnings.map((text:string)=><li key={text}>{text}</li>)}</ul></div>}
  </div>
  <div className="modal-bottom bond-modal-footer"><button className="button" disabled={busy} onClick={onClose}>{result?'完成':'取消'}</button><button className="button primary" disabled={!settings||busy||blocked||invalid} onClick={()=>void execute()}>{busy?<LoaderCircle size={16}/>:<Play size={16}/>}执行羁绊最大化</button></div>
 </Modal>;
}
