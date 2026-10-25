import {ArrowLeft,ArrowRight,GripVertical,X} from 'lucide-react';
import {colorName,rosterAt,servantFor} from './model';
import type {Catalog,Entry,Json} from './model';
import {npAt} from './battlePreview';
import {CardArtwork} from './NPCardPreview';
import type {CardPreviewConfig} from './npCardRequest';
import {cardPreviewRegion} from './npCardRequest';
import {useAttackCardDrag} from './useAttackCardDrag';

export function AttackCardGroup({data,catalog,entry,entryIndex,region,config,onSelect,onSwapCards,onRemoveCard}:{data:Json;catalog:Catalog;entry:Entry;entryIndex:number;region?:string;config?:CardPreviewConfig;onSelect:(index:number)=>void;onSwapCards?:(entryIndex:number,from:number,to:number)=>void;onRemoveCard?:(entryIndex:number,cardIndex:number)=>void}) {
 const cards=Array.isArray(entry.raw?.attacks)?entry.raw.attacks:[],roster=rosterAt(data,entry.index),occupied=[0,1,2].map(index=>!!cards[index]&&typeof cards[index]==='object');
 const drag=useAttackCardDrag({occupied,onSwap:(from,to)=>onSwapCards?.(entryIndex,from,to),resetKey:data,enabled:!!onSwapCards});
 return <div className="attack-card-group" data-attack-group="" aria-label="本回合出卡顺序">{[0,1,2].map(index=>{
  const card=cards[index],validSlot=Number.isInteger(card?.svt)&&card.svt>=0&&card.svt<3,member=validSlot?roster[card.svt]:undefined,svt=servantFor(catalog,member?.svtId),np=card?.isTD?npAt(member,svt):undefined,label=card?.isTD?'宝具 NP':card?colorName(card.cardType):'默认选卡补齐';
  return <article key={index} className={`attack-card-slot ${card?'filled':'empty'} ${drag.dragged===index?'attack-drag-placeholder':''} ${drag.target===index&&drag.dragged!==index?'attack-drop-target':''}`} data-attack-card={index} draggable={occupied[index]&&!!onSwapCards} {...drag.bindCard(index)}>
   <div className="attack-card-topline"><span className="attack-card-order">{index+1}</span>{occupied[index]&&onSwapCards&&<span className="attack-card-grip" onPointerDown={event=>drag.start(index,event)} title="拖动交换卡片"><GripVertical size={15}/></span>}{occupied[index]&&onRemoveCard&&<button type="button" className="attack-card-remove" data-no-drag="" draggable={false} aria-label={`移除第 ${index+1} 张${card.isTD?'宝具':'色卡'}`} title={`移除第 ${index+1} 张出卡；后续卡片前移`} onPointerDown={event=>event.stopPropagation()} onDragStart={event=>{event.preventDefault();event.stopPropagation();}} onClick={event=>{event.stopPropagation();drag.cancel();onRemoveCard(entryIndex,index);}}><X size={18} strokeWidth={2.5} aria-hidden="true"/></button>}</div>
   <button className="attack-card-select" aria-label={`编辑第 ${index+1} 张卡：${label}`} onPointerDown={event=>{if(occupied[index])drag.start(index,event);}} onClick={()=>onSelect(entryIndex)}>
    {card?<><CardArtwork member={member} np={np} color={card.cardType} kind={card.isTD?'np':'face'} region={cardPreviewRegion(region,config)} config={config}/><strong>{label}</strong><small>{validSlot?`前排 ${card.svt+1}`:'无效前排'} · {svt?.name??(member?`从者 #${member.svtId}`:'未知从者')}</small></>:<span className="attack-card-empty">默认选卡补齐</span>}
   </button>
   {occupied[index]&&onSwapCards&&<div className="attack-card-swap-tools"><button className="icon" aria-label={`将第 ${index+1} 张卡与左侧交换`} disabled={index===0||!occupied[index-1]} onClick={()=>onSwapCards(entryIndex,index,index-1)}><ArrowLeft size={16}/></button><button className="icon" aria-label={`将第 ${index+1} 张卡与右侧交换`} disabled={index===2||!occupied[index+1]} onClick={()=>onSwapCards(entryIndex,index,index+1)}><ArrowRight size={16}/></button></div>}
  </article>;
 })}</div>;
}
