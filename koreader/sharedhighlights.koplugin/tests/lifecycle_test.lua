-- Load the real plugin with small mocks for its exact KOReader module boundary.
local scheduled, captures, cancels={},0,0
local manager={
    scheduleIn=function(_,_,f) scheduled[f]=true end,
    unschedule=function(_,f) scheduled[f]=nil end,
}
local modules={
    ["ui/widget/container/widgetcontainer"]={extend=function(_,t) return t end},
    ["ui/uimanager"]=manager,["ui/widget/inputdialog"]={},
    ["ui/widget/infomessage"]={},["ui/network/manager"]={},
    ["datastorage"]={},["json"]={},["ffi/util"]={},["ffi/sha2"]={md5=function(s) return s end},
}
for name,module in pairs(modules) do package.preload[name]=function() return module end end
local Plugin=dofile(arg[0]:match("(.*/)").."../main.lua")
local function instance()
    local p=setmetatable({tick=function() end},{__index=Plugin})
    p.capture=function() captures=captures+1 end
    p.process={cancel=function() cancels=cancels+1 end}
    return p
end
local p=instance()
p:onReaderReady(); assert(captures==1 and scheduled[p.tick])
p:onSuspend(); assert(captures==2 and p.suspended and not scheduled[p.tick] and cancels==1)
p:onNetworkConnected(); assert(not scheduled[p.tick])
p:onResume(); assert(not p.suspended and scheduled[p.tick])
p:onCloseDocument(); assert(p.closed and captures==3 and not scheduled[p.tick])
p:onReaderReady(); p:onAnnotationsModified(); p:onNetworkConnected(); p:onResume()
assert(captures==3 and not scheduled[p.tick])
p:onCloseWidget(); assert(not scheduled[p.tick])
local new=instance(); new:onReaderReady(); assert(scheduled[new.tick] and not scheduled[p.tick])
-- A queued stale tick cannot reach capture or initiate a request after closure.
p:sync(false); assert(captures==4)
print("lifecycle tests passed: real suspend/resume/close handlers and stale sync guard")
