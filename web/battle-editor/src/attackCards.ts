import type {Json} from './model';

/** Swap complete card records; never rewrite deck indexes, targets, or imported fields. */
export function swapAttackCardPositions(attack:Json,from:number,to:number):void {
 const cards=attack?.attacks;
 if(attack?.type!=='attack'||!Array.isArray(cards))throw new Error('这个动作没有可交换的出卡。');
 if(!Number.isInteger(from)||!Number.isInteger(to)||from<0||to<0||from>=3||to>=3||from>=cards.length||to>=cards.length)throw new Error('请在前三个已设定的出卡位之间交换。');
 if(!cards[from]||typeof cards[from]!=='object'||Array.isArray(cards[from])||!cards[to]||typeof cards[to]!=='object'||Array.isArray(cards[to]))throw new Error('自动补齐空位不能参与交换。');
 if(from===to)return;
 [cards[from],cards[to]]=[cards[to],cards[from]];
}

/** Remove one recorded first-three card; later imported cards retain their order. */
export function removeAttackCard(attack:Json,index:number):void {
 const cards=attack?.attacks;
 if(attack?.type!=='attack'||!Array.isArray(cards))throw new Error('这个动作没有可删除的出卡。');
 if(!Number.isInteger(index)||index<0||index>=3||index>=cards.length)throw new Error('请选择前三个已设定的出卡位。');
 if(!cards[index]||typeof cards[index]!=='object'||Array.isArray(cards[index]))throw new Error('自动补齐空位不能删除。');
 cards.splice(index,1);
}
