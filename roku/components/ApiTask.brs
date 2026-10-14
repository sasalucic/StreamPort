sub init()
    m.top.functionName = "runRequest"
end sub

sub runRequest()
    r = m.top.request
    u = CreateObject("roUrlTransfer")
    port = CreateObject("roMessagePort")
    u.SetMessagePort(port)
    u.SetUrl(r.server + r.path)
    u.SetCertificatesFile("common:/certs/ca-bundle.crt")
    u.InitClientCertificates()
    u.AddHeader("X-StreamPort", "1")
    if r.cookie <> "" then u.AddHeader("Cookie", r.cookie)
    if r.mode = "type" then u.AddHeader("Range", "bytes=0-0")
    if r.method = "POST"
        u.AddHeader("Content-Type", "application/json")
        started = u.AsyncPostFromString(FormatJson(r.body))
    else
        started = u.AsyncGetToString()
    end if
    result = {detailGeneration:r.detailGeneration, action:r.action, requestId:r.requestId, epoch:r.epoch, code:0, data:invalid, cookie:"", error:"Server nije dostupan.", mime:""}
    if started
        e = wait(20000, port)
        if type(e) = "roUrlEvent"
            result.code = e.GetResponseCode()
            result.error = e.GetFailureReason()
            for each header in e.GetResponseHeadersArray()
                for each k in header
                    if LCase(k) = "set-cookie"
                        value = header[k]
                        if Left(value,11) = "streamport=" then result.cookie = value.Split(";")[0]
                    else if LCase(k) = "content-type"
                        result.mime = LCase(header[k])
                    end if
                end for
            end for
            if r.mode = "text"
                result.data = e.GetString()
            else if r.mode <> "type"
                result.data = ParseJson(e.GetString())
            end if
            if result.code >= 400 and type(result.data) = "roAssociativeArray"
                if result.data.error <> invalid then result.error = result.data.error
            end if
        else
            u.AsyncCancel()
            result.error = "Server nije odgovorio u roku od 20 sekundi."
        end if
    end if
    m.top.result = result
end sub
