import test from 'node:test';
import assert from 'node:assert/strict';
import type {Json} from './model';
import {removeAttackCard,swapAttackCardPositions} from './attackCards';

test('swaps whole records and preserves targets, recolor indexes, unknown fields and imported tail',()=>{
 const np={svt:0,isTD:true,card:-1,future:{x:1}},face={svt:1,isTD:false,card:4,cardType:2,future:['keep']},third={svt:2,card:0},tail={future:'fourth'};
 const attack={type:'attack',attacks:[np,face,third,tail],options:{enemyTarget:2},future:'action'};
 swapAttackCardPositions(attack,0,2);
 assert.deepEqual(attack,{type:'attack',attacks:[third,face,np,tail],options:{enemyTarget:2},future:'action'});
 assert.equal(attack.attacks[2],np);
 swapAttackCardPositions(attack,0,2);
 assert.deepEqual(attack.attacks,[np,face,third,tail]);
});
test('empty, malformed, fourth, out-of-range and noninteger drops fail without mutation',()=>{
 for(const [from,to] of [[0,3],[0,-1],[0,0.5],[NaN,1],[0,2]]){
  const attack={type:'attack',attacks:[{svt:0},null]},before=JSON.stringify(attack);
  assert.throws(()=>swapAttackCardPositions(attack,from,to));assert.equal(JSON.stringify(attack),before);
 }
 for(const attacks of [[{svt:0},null],[{svt:0},[]],[{svt:0},'unknown']]){
  const attack={type:'attack',attacks},before=JSON.stringify(attack);
  assert.throws(()=>swapAttackCardPositions(attack,0,1));assert.equal(JSON.stringify(attack),before);
 }
 assert.throws(()=>swapAttackCardPositions({type:'skill',attacks:[{},{}]},0,1));
});
test('same position is a no-op and two cards can swap without a third card',()=>{
 const first={svt:0},second={svt:2},attack={type:'attack',attacks:[first,second]};
 swapAttackCardPositions(attack,0,0);assert.deepEqual(attack.attacks,[first,second]);
 swapAttackCardPositions(attack,0,1);assert.deepEqual(attack.attacks,[second,first]);
});

test('removing a NP or face card shifts later complete records and preserves the imported tail and options',()=>{
 for(const index of [0,1,2]){
  const np={svt:0,isTD:true,card:-1,future:{np:1}},face={svt:1,isTD:false,card:4,cardType:2,future:['face']},
   third={svt:2,card:0},tail={future:'fourth'},extra={future:'fifth'},options={enemyTarget:2,future:{keep:1}};
  const cards=[np,face,third,tail,extra],attack:Json={type:'attack',attacks:[...cards],options,future:{action:1}};
  removeAttackCard(attack,index);
  assert.deepEqual(attack,{type:'attack',attacks:cards.filter((_,i)=>i!==index),options,future:{action:1}});
  assert.equal(attack.options,options);assert.equal(attack.attacks.at(-2),tail);assert.equal(attack.attacks.at(-1),extra);
 }
});

test('removing the final card leaves an empty attack action with its exact options',()=>{
 const options={enemyTarget:0,future:['keep']},attack:Json={type:'attack',attacks:[{svt:0,isTD:true,card:-1}],options,future:7};
 const originalArray=attack.attacks;
 removeAttackCard(attack,0);assert.deepEqual(attack,{type:'attack',attacks:[],options,future:7});
 assert.equal(attack.attacks,originalArray);assert.equal(attack.options,options);
 assert.throws(()=>removeAttackCard(attack,0));
});

test('invalid card removal never rewrites unsupported actions, automatic slots or malformed records',()=>{
 for(const attack of [null,{}, {type:'skill',attacks:[{}]}, {type:'attack'}, {type:'attack',attacks:null},
  {type:'attack',attacks:{}}, {type:'attack',attacks:[null]}, {type:'attack',attacks:[[]]},
  {type:'attack',attacks:['unknown']}, {type:'attack',attacks:[0]}]){
  const before=structuredClone(attack);assert.throws(()=>removeAttackCard(attack as Json,0));assert.deepEqual(attack,before);
 }
 for(const index of [-1,0.5,NaN,Infinity,3,4]){
  const attack:Json={type:'attack',attacks:[{svt:0},{svt:1},{svt:2},{future:'fourth'}]},before=structuredClone(attack);
  assert.throws(()=>removeAttackCard(attack,index));assert.deepEqual(attack,before);
 }
 const short:Json={type:'attack',attacks:[{svt:0}]};assert.throws(()=>removeAttackCard(short,1));assert.deepEqual(short.attacks,[{svt:0}]);
 const sparse:Json={type:'attack',attacks:Array(2)};assert.throws(()=>removeAttackCard(sparse,0));assert.equal(0 in sparse.attacks,false);
});
