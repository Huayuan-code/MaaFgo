import test from 'node:test';
import assert from 'node:assert/strict';
import {bondResultTeam,reservedBondSupport} from './bondOptimizerModel';
import {newBattle} from './model';

test('reserve last empty slot but follow an explicitly selected support',()=>{
 const d=newBattle();assert.equal(reservedBondSupport(d),5);
 d.team.onFieldSvts[0]={svtId:100};d.team.backupSvts[2]={svtId:200};assert.equal(reservedBondSupport(d),4);
 d.team.onFieldSvts[1]={svtId:100,supportType:'friend'};assert.equal(reservedBondSupport(d),1);
});
test('a full local roster requires the user to fix its support slot',()=>{
 const d=newBattle();d.team.onFieldSvts=[{svtId:1},{svtId:2},{svtId:3}];d.team.backupSvts=[{svtId:4},{svtId:5},{svtId:6}];
 assert.equal(reservedBondSupport(d),null);
});
test('reject a result from a previous editor object including undo or reload',()=>{
 const snapshot=newBattle(),current=structuredClone(snapshot),response={data:snapshot};
 assert.throws(()=>bondResultTeam(current,snapshot,response),/方案已更改/);
});
test('return a cloned team without changing the snapshot or response',()=>{
 const snapshot=newBattle(),response={data:structuredClone(snapshot)};
 response.data.team.backupSvts[0]={svtId:9,future:{keep:1}};
 const team=bondResultTeam(snapshot,snapshot,response);team.backupSvts[0].future.keep=2;
 assert.equal(response.data.team.backupSvts[0].future.keep,1);
 assert.equal(snapshot.team.backupSvts[0],null);
});
test('malformed planning results are not committed',()=>{
 const d=newBattle();for(const r of [{},{data:{}},{data:{team:[]}}, {data:{team:null}}])assert.throws(()=>bondResultTeam(d,d,r),/有效编队/);
});
