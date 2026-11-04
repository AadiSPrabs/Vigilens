import {describe,it,expect}from "vitest";
import {initialState,reducer}from "../app/vigilens/useVigilens";
describe("pending paid request",()=>{
 it("pins source/zones and never converts status unknown to a retry",()=>{
  const pending=reducer(initialState,{type:"fail",runId:0,message:"status unknown",pending:true});
  expect(pending.pendingAudit).toBe(true);
  expect(reducer(pending,{type:"start",runId:0})).toBe(pending);
  expect(reducer(pending,{type:"zones",zones:[]})).toBe(pending);
  expect(reducer(pending,{type:"runWithoutZones",value:true})).toBe(pending);
 });
});
