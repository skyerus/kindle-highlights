-- Pure queue logic; acknowledgement applies only to the exact sent revision.
local Q = {}
local function scalar(v)
    if type(v) ~= "table" then return type(v)..":"..#tostring(v or "")..":"..tostring(v or "") end
    local keys, out = {}, {}
    for k in pairs(v) do keys[#keys+1] = k end
    table.sort(keys, function(a,b) return tostring(a)<tostring(b) end)
    for _, k in ipairs(keys) do out[#out+1] = scalar(k)..scalar(v[k]) end
    return table.concat(out, ";")
end
function Q.capture(state, annotations, props, file, hash, encode)
    for _, a in ipairs(annotations or {}) do
        if a.drawer and type(a.text)=="string" and a.text:match("%S") and #a.text <= 65536 then
            local title = props.title
            if not title or title == "" then title = file:match("([^/]+)$") or file end
            local author = props.authors or ""
            local id = hash(table.concat({title,author,a.datetime or "",scalar(a.pos0 or a.page),scalar(a.pos1)}, "\0"))
            local row = {id=id,book_title=title,author=author,text=a.text,note=a.note,
                created_at=a.datetime,location=type(a.page)=="table" and scalar(a.page) or tostring(a.page or "")}
            local revision = hash(scalar(row))
            if #title<=4096 and #author<=4096 and #(row.note or "")<=65536 and #row.location<=4096
                and #(row.created_at or "")<=128 and (state.pending[id] or state.sent[id] ~= revision) then
                state.pending[id] = {row=row,revision=revision}
            end
        end
    end
end
function Q.batch(state, encode)
    local rows, versions, size = {}, {}, 0
    for id, item in pairs(state.pending) do
        local n = #encode(item.row)
        if #rows < 16 and size+n < 524288 then
            rows[#rows+1], versions[id], size = item.row, item.revision, size+n
        end
    end
    return rows, versions
end
function Q.ack(state, accepted, versions)
    for _, id in ipairs(accepted or {}) do
        if type(id)=="string" and versions[id] then
            state.sent[id] = versions[id]
            if state.pending[id] and state.pending[id].revision == versions[id] then state.pending[id] = nil end
        end
    end
end
return Q
