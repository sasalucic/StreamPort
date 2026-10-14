sub init()
    m.top.backgroundColor = "#090E10"
    m.top.backgroundUri = ""
    m.nav = m.top.FindNode("nav")
    m.grid = m.top.FindNode("grid")
    m.status = m.top.FindNode("status")
    m.heading = m.top.FindNode("heading")
    m.detail = m.top.FindNode("detail")
    m.buttons = m.top.FindNode("detailButtons")
    m.video = m.top.FindNode("video")
    m.timer = m.top.FindNode("progressTimer")
    m.nav.ObserveField("itemSelected", "navSelected")
    m.grid.ObserveField("itemSelected", "itemSelected")
    m.buttons.ObserveField("itemSelected", "detailSelected")
    m.video.ObserveField("state", "videoState")
    m.video.ObserveField("position", "videoPosition")
    m.video.notificationInterval = 0.25
    m.timer.ObserveField("fire", "saveProgress")
    m.registry = CreateObject("roRegistrySection", "StreamPort")
    m.server = m.registry.Read("server")
    m.cookie = m.registry.Read("cookie")
    m.username = m.registry.Read("username")
    m.library = []
    m.items = []
    m.tasks = {}
    m.seq = 0
    m.epoch = 0
    m.page = "Pocetna"
    m.query = ""
    m.sort = "name"
    m.cues = []
    m.subtitles = []
    m.playing = invalid
    m.ready = false
    m.detailGeneration = 0
    m.progressBusy = false
    m.progressPending = invalid
    m.recordedPlay = false
    m.detailItem = invalid
    m.showKey = ""
    m.selectedSeason = ""
    m.heading.text = "Dobro dosli"
    labels = ["Pocetna", "Filmovi", "Serije", "Nastavi gledati", "Favoriti", "Pretraga", "Osvjezi", "Postavke"]
    root = CreateObject("roSGNode", "ContentNode")
    for each title in labels
        c = root.CreateChild("ContentNode")
        c.title = title
    end for
    m.nav.content = root
    m.nav.SetFocus(true)
    if m.server = ""
        ask("server", "Adresa StreamPort servera", "http://your-server-host:8097")
    else if m.cookie = ""
        ask("username", "Korisnicko ime", m.username)
    else
        request("me", "/api/me")
    end if
end sub

function s(value as dynamic) as string
    if value = invalid then return ""
    return value.ToStr()
end function

function n(value as dynamic) as dynamic
    if value = invalid then return 0.0
    if type(value) = "Boolean" or type(value) = "roBoolean"
        if value then return 1.0
        return 0.0
    end if
    return Val(s(value))
end function

sub request(action as string, path as string, body = invalid as dynamic, mode = "json" as string)
    m.seq++
    key = m.seq.ToStr()
    t = CreateObject("roSGNode", "ApiTask")
    method = "GET"
    if body <> invalid then method = "POST"
    t.request = {detailGeneration:m.detailGeneration, action:action, path:path, method:method, body:body, server:m.server, cookie:m.cookie, mode:mode, requestId:key, epoch:m.epoch}
    t.ObserveField("result", "response")
    m.tasks[key] = t
    t.control = "RUN"
    if action <> "progress" and action <> "played" then m.status.text = "Ucitavanje..."
end sub

sub response(event as object)
    r = event.GetData()
    m.tasks.Delete(r.requestId)
    if r.epoch <> m.epoch then return
    if r.action = "progress"
        m.progressBusy = false
        if m.progressPending <> invalid
            pending = m.progressPending
            m.progressPending = invalid
            m.progressBusy = true
            request("progress", "/api/progress", pending)
        end if
    end if
    if r.action = "type" or r.action = "subtitles" or r.action = "caption" or r.action = "favorite"
        if r.detailGeneration <> m.detailGeneration then return
    end if
    if r.code = 401
        if r.action = "login"
            message("Prijava nije uspjela", "Pogresno korisnicko ime ili lozinka. Izaberi bilo koju biblioteku za novi pokusaj.")
            return
        end if
        m.epoch++
        m.progressBusy = false
        m.progressPending = invalid
        m.cookie = ""
        m.registry.Delete("cookie")
        m.registry.Flush()
        m.ready = false
        if m.video.visible
            m.recordedPlay = false
            stopVideo()
        end if
        m.detail.visible = false
        m.status.text = "Prijavi se ponovo."
        if m.top.dialog = invalid then ask("username", "Korisnicko ime", m.username)
        return
    end if
    if r.code < 200 or r.code >= 300
        if r.action = "progress" or r.action = "played"
            m.status.text = "Napredak nije sacuvan: provjeri vezu sa serverom."
            return
        end if
        message("Nije uspjelo", s(r.error) + " (HTTP " + s(r.code) + ")")
        return
    end if
    if r.action = "login"
        if r.cookie = ""
            message("Prijava", "Server nije poslao sesiju. Provjeri adresu servera.")
            return
        end if
        m.cookie = r.cookie
        m.registry.Write("server", m.server)
        m.registry.Write("cookie", m.cookie)
        m.registry.Write("username", m.username)
        m.registry.Flush()
        request("me", "/api/me")
    else if r.action = "me"
        m.ready = true
        m.top.FindNode("account").text = s(r.data.name)
        request("library", "/api/library")
    else if r.action = "library"
        if type(r.data) <> "roArray"
            message("Biblioteka", "Server nije vratio ocekivani format biblioteke.")
            return
        end if
        m.library = r.data
        renderPage()
    else if r.action = "favorite"
        m.detailItem.favorite = r.data.favorite
        request("library", "/api/library")
        showDetail(m.detailItem)
    else if r.action = "type"
        if m.detail.visible and m.detailItem <> invalid then startVideo(r.mime)
    else if r.action = "subtitles"
        m.subtitles = r.data
        choices = ["Iskljuceni"]
        if type(m.subtitles) = "roArray"
            for each subtrack in m.subtitles
                choices.Push(s(subtrack.label))
            end for
        else
            m.subtitles = []
        end if
        choose("subtitles", "Titlovi sa servera", choices)
    else if r.action = "caption"
        m.status.text = "Titlovi su spremni za reprodukciju."
        m.cues = parseVtt(r.data)
        if m.cues.Count() = 0
            message("Titlovi", "Nema tekstualnih WebVTT titlova za prikaz.")
        else
            message("Titlovi", "Titlovi su odabrani. Pokreni ili nastavi reprodukciju.")
        end if
    end if
end sub

sub ask(kind as string, title as string, value as string)
    d = CreateObject("roSGNode", "KeyboardDialog")
    d.title = title
    d.text = value
    d.buttons = ["Nastavi", "Odustani"]
    if kind = "password" then d.keyboard.textEditBox.secureMode = true
    d.ObserveField("buttonSelected", "keyboardDone")
    m.inputKind = kind
    m.top.dialog = d
end sub

sub keyboardDone(event as object)
    d = m.top.dialog
    if d = invalid then return
    value = d.text.Trim()
    if m.inputKind = "password" then value = d.text
    accepted = event.GetData() = 0
    d.close = true
    if not accepted then return
    if m.inputKind = "server"
        value = value.Trim()
        while Right(value, 1) = "/"
            value = Left(value, Len(value)-1)
        end while
        if Left(value,7) <> "http://" and Left(value,8) <> "https://"
            message("Adresa", "Unesi http:// ili https:// pa IP i port servera.")
            return
        end if
        m.epoch++
        m.progressBusy = false
        m.progressPending = invalid
        m.server = value
        m.cookie = ""
        m.ready = false
        m.library = []
        m.items = []
        m.grid.content = CreateObject("roSGNode", "ContentNode")
        m.top.FindNode("account").text = ""
        m.registry.Delete("cookie")
        m.registry.Write("server", value)
        m.registry.Flush()
        ask("username", "Korisnicko ime", m.username)
    else if m.inputKind = "username"
        m.username = value
        ask("password", "Lozinka za " + value, "")
    else if m.inputKind = "password"
        request("login", "/api/login", {name:m.username, password:value})
    else if m.inputKind = "search"
        m.query = value
        m.page = "Pretraga"
        renderPage()
    end if
end sub

sub message(title as string, text as string)
    d = CreateObject("roSGNode", "Dialog")
    d.title = title
    d.message = text
    d.buttons = ["OK"]
    d.ObserveField("buttonSelected", "closeDialog")
    m.top.dialog = d
end sub

sub closeDialog()
    if m.top.dialog <> invalid then m.top.dialog.close = true
end sub

sub choose(kind as string, title as string, buttons as object)
    m.choiceKind = kind
    d = CreateObject("roSGNode", "Dialog")
    d.title = title
    d.buttons = buttons
    d.ObserveField("buttonSelected", "choiceDone")
    m.top.dialog = d
end sub

sub choiceDone(event as object)
    index = event.GetData()
    closeDialog()
    if m.choiceKind = "settings"
        if index = 0
            ask("server", "Adresa StreamPort servera", m.server)
        else if index = 1
            m.epoch++
            m.progressBusy = false
            m.progressPending = invalid
            request("logout", "/api/logout", {})
            m.cookie = ""
            m.ready = false
            m.library = []
            m.items = []
            m.top.FindNode("account").text = ""
            m.grid.content = CreateObject("roSGNode", "ContentNode")
            m.registry.Delete("cookie")
            m.registry.Flush()
            ask("username", "Korisnicko ime", m.username)
        else if index = 2
            message("StreamPort Roku 1.0", "Native Roku klijent. Server: " + m.server + Chr(10) + "Direct Play zavisi od kodeka koje tvoj Roku podrzava.")
        end if
    else if m.choiceKind = "playback"
        if index = 0 and m.playing <> invalid
            m.video.seek = 0
            m.lastPosition = 0
            m.video.control = "resume"
        else if index = 1 and m.nextItem <> invalid
            target = m.nextItem
            stopVideo()
            m.cues = []
            showDetail(target)
            m.startAt = 0
            request("type", "/api/media/" + s(target.id) + "/stream", invalid, "type")
        end if
        if m.video.visible then m.video.SetFocus(true)
    else if m.choiceKind = "sort"
        sorts = ["name", "year", "rating", "added"]
        if index < sorts.Count()
            m.sort = sorts[index]
            renderPage()
        end if
    else if m.choiceKind = "subtitles"
        m.cues = []
        m.top.FindNode("caption").text = ""
        m.top.FindNode("captionBg").visible = false
        if index > 0 and index <= m.subtitles.Count()
            track = m.subtitles[index-1]
            request("caption", "/api/media/" + s(m.detailItem.id) + "/subtitle?index=" + s(track.index), invalid, "text")
        end if
    end if
end sub

sub navSelected()
    i = m.nav.itemSelected
    if i = 7
        choose("settings", "Postavke", ["Promijeni server", "Promijeni korisnika", "O aplikaciji", "Zatvori"])
        return
    end if
    if not m.ready
        ask("username", "Korisnicko ime", m.username)
        return
    end if
    if i = 6
        request("library", "/api/library")
        return
    end if
    if i = 5
        ask("search", "Pretrazi filmove i serije", m.query)
        return
    end if
    pages = ["Pocetna", "Filmovi", "Serije", "Nastavi gledati", "Favoriti"]
    m.page = pages[i]
    m.showKey = ""
    m.selectedSeason = ""
    renderPage()
    if m.items.Count() > 0 then m.grid.SetFocus(true)
end sub

function seriesKey(item as object) as string
    if s(item.show_key) <> "" then return s(item.show_key)
    return LCase(s(item.series))
end function

function movieKey(item as object) as string
    if n(item.tmdb_id) > 0 then return "tmdb:" + s(item.tmdb_id)
    if s(item.imdb) <> "" then return "imdb:" + s(item.imdb)
    return LCase(s(item.title)) + ":" + s(item.year)
end function

function selectItems(library as object, page as string, query as string, sort as string, showKey as string, selectedSeason as string) as object
    items = []
    seen = {}
    q = LCase(query.Trim())
    for each item in library
        include = false
        key = ""
        display = item
        if page = "Sezone"
            if item.kind = "episode" and seriesKey(item) = showKey
                key = "season:" + s(item.season)
                display = {kind:"season", title:"Sezona " + s(item.season), season:item.season, backdrop:item.backdrop, poster:item.poster}
                include = true
            end if
        else if page = "Epizode"
            if item.kind = "episode" and seriesKey(item) = showKey and s(item.season) = selectedSeason
                include = true
                key = "episode:" + s(item.season) + ":" + s(item.episode)
            end if
        else if page = "Nastavi gledati"
            if n(item.position) > 20 and (n(item.duration) = 0 or n(item.position) < n(item.duration)-45)
                include = true
                key = "media:" + s(item.id)
            end if
        else if item.kind = "movie"
            include = page = "Pocetna" or page = "Filmovi"
            if page = "Favoriti" then include = n(item.favorite) > 0
            if page = "Pretraga" then include = q <> "" and Instr(1,LCase(s(item.title)),q) > 0
            key = "movie:" + movieKey(item)
        else if item.kind = "episode"
            include = page = "Pocetna" or page = "Serije"
            if page = "Pretraga" then include = q <> "" and Instr(1,LCase(s(item.series)),q) > 0
            key = "show:" + seriesKey(item)
            display = {kind:"show", title:s(item.series), show_key:seriesKey(item), poster:item.poster, backdrop:item.backdrop, year:item.year, rating:item.rating, added:item.added}
        end if
        if include and not seen.DoesExist(key)
            seen[key] = true
            items.Push(display)
        end if
    end for
    ' Stable insertion sort; numeric season/episode ordering overrides global sorting.
    for i = 1 to items.Count()-1
        current = items[i]
        j = i-1
        while j >= 0
            if not comesBefore(current, items[j], page, sort) then exit while
            items[j+1] = items[j]
            j--
        end while
        items[j+1] = current
    end for
    return items
end function

sub renderPage()
    m.items = selectItems(m.library, m.page, m.query, m.sort, m.showKey, m.selectedSeason)
    content = CreateObject("roSGNode", "ContentNode")
    for each item in m.items
        c = content.CreateChild("ContentNode")
        c.title = s(item.title)
        if item.kind = "episode" then c.title = "E" + s(item.episode) + " · " + s(item.episode_title)
        c.description = s(item.year)
        if n(item.duration) > 0 then c.description += " · " + s(Int(n(item.duration)/60)) + " min"
        if item.kind = "show" then c.description += " · Serija"
        c.hdPosterUrl = artwork(item)
        c.AddFields({authCookie:""})
        if Left(c.hdPosterUrl,Len(m.server)+1) = m.server + "/" then c.authCookie = m.cookie
    end for
    m.grid.content = content
    m.heading.text = m.page
    if m.page = "Pretraga" then m.heading.text = "Rezultati: " + m.query
    m.status.text = s(m.items.Count()) + " naslova"
    if m.items.Count() = 0 then m.status.text = "Nema naslova za ovaj prikaz."
end sub

function comesBefore(a as object, b as object, page as string, sort as string) as boolean
    if page = "Sezone" then return n(a.season) < n(b.season)
    if page = "Epizode" then return n(a.episode) < n(b.episode)
    if page = "Nastavi gledati" then return n(a.updated) > n(b.updated)
    if sort = "year" then return n(a.year) > n(b.year)
    if sort = "rating" then return n(a.rating) > n(b.rating)
    if sort = "added" then return n(a.added) > n(b.added)
    return LCase(s(a.title)) < LCase(s(b.title))
end function

function artwork(item as object) as string
    url = s(item.backdrop)
    if url = "" then url = s(item.poster)
    if item.kind = "episode" then url = "/api/media/" + s(item.id) + "/thumbnail"
    if Left(url,1) = "/" and Left(url,2) <> "//" then url = m.server + url
    if url = "" then url = "pkg:/images/placeholder.png"
    return url
end function

sub itemSelected()
    i = m.grid.itemSelected
    if i < 0 or i >= m.items.Count() then return
    item = m.items[i]
    if item.kind = "show"
        m.showKey = item.show_key
        m.page = "Sezone"
        renderPage()
    else if item.kind = "season"
        m.selectedSeason = s(item.season)
        m.page = "Epizode"
        renderPage()
    else
        showDetail(item)
    end if
end sub

sub showDetail(item as object)
    m.detailGeneration++
    m.detailItem = item
    m.detail.visible = true
    title = s(item.title)
    if item.kind = "episode" then title = s(item.series) + " · S" + s(item.season) + " E" + s(item.episode)
    m.top.FindNode("detailTitle").text = title
    m.top.FindNode("detailMeta").text = s(item.year) + " · " + s(Int(n(item.duration)/60)) + " min · " + s(item.rating)
    m.top.FindNode("detailText").text = s(item.overview)
    p = m.top.FindNode("detailArt")
    url = artwork(item)
    agent = CreateObject("roHttpAgent")
    agent.SetCertificatesFile("common:/certs/ca-bundle.crt")
    if Left(url,Len(m.server)+1) = m.server + "/" then agent.AddHeader("Cookie",m.cookie)
    p.SetHttpAgent(agent)
    p.uri = url
    buttons = ["Gledaj od pocetka"]
    m.detailActions = ["play"]
    if n(item.position) > 20
        buttons.Push("Nastavi od " + s(Int(n(item.position)/60)) + ". minute")
        m.detailActions.Push("resume")
    end if
    if item.kind = "movie"
        label = "Dodaj u favorite"
        if n(item.favorite) > 0 then label = "Ukloni iz favorita"
        buttons.Push(label)
        m.detailActions.Push("favorite")
    end if
    buttons.Push("Titlovi")
    m.detailActions.Push("subtitles")
    content = CreateObject("roSGNode", "ContentNode")
    for each title in buttons
        button = content.CreateChild("ContentNode")
        button.title = title
    end for
    m.buttons.content = content
    m.buttons.SetFocus(true)
end sub

sub detailSelected()
    action = m.detailActions[m.buttons.itemSelected]
    if action = "play" or action = "resume"
        m.startAt = 0
        if action = "resume" then m.startAt = n(m.detailItem.position)
        request("type", "/api/media/" + s(m.detailItem.id) + "/stream", invalid, "type")
    else if action = "favorite"
        request("favorite", "/api/favorites", {id:m.detailItem.id, favorite:not (n(m.detailItem.favorite)>0)})
    else if action = "subtitles"
        request("subtitles", "/api/media/" + s(m.detailItem.id) + "/subtitles")
    end if
end sub

sub startVideo(mime as string)
    format = "mp4"
    if Instr(1,mime,"matroska") > 0 then format = "mkv"
    if Instr(1,mime,"avi") > 0 or Instr(1,mime,"webm") > 0
        message("Format videa", "Ovaj format nije ukljucen u Direct Play za Roku. Potrebna je konverzija na serveru u podrzan MP4/MKV.")
        return
    end if
    m.playing = m.detailItem
    m.recordedPlay = false
    m.lastPosition = m.startAt
    m.lastDuration = n(m.playing.duration)
    c = CreateObject("roSGNode", "ContentNode")
    c.title = s(m.playing.title)
    c.url = m.server + "/api/media/" + s(m.playing.id) + "/stream"
    c.streamFormat = format
    c.playStart = m.startAt
    agent = CreateObject("roHttpAgent")
    agent.SetCertificatesFile("common:/certs/ca-bundle.crt")
    agent.AddHeader("Cookie",m.cookie)
    m.video.SetHttpAgent(agent)
    m.video.content = c
    m.video.visible = true
    m.video.SetFocus(true)
    m.video.control = "play"
    m.timer.control = "start"
end sub

sub videoState()
    if m.playing = invalid then return
    state = m.video.state
    if state = "playing" and not m.recordedPlay
        m.recordedPlay = true
        request("played", "/api/played", {id:m.playing.id})
    else if state = "finished"
        m.lastPosition = m.lastDuration
        stopVideo()
    else if state = "error"
        reason = m.video.errorMsg
        stopVideo()
        message("Reprodukcija nije uspjela", reason + Chr(10) + "Provjeri vezu i podrsku Roku uredjaja za kodeke ovog fajla. Ova verzija koristi Direct Play.")
    end if
end sub

sub videoPosition()
    if m.playing = invalid then return
    m.lastPosition = m.video.position
    if m.video.duration > 0 then m.lastDuration = m.video.duration
    text = ""
    for each cue in m.cues
        if cue.start > m.lastPosition then exit for
        if m.lastPosition >= cue.start and m.lastPosition < cue.finish then text += cue.text + Chr(10)
    end for
    m.top.FindNode("caption").text = text.Trim()
    m.top.FindNode("captionBg").visible = text <> ""
end sub

sub saveProgress()
    if m.playing = invalid then return
    if not m.recordedPlay then return
    body = {id:m.playing.id, position:m.lastPosition, duration:m.lastDuration}
    if m.progressBusy
        m.progressPending = body
    else
        m.progressBusy = true
        request("progress", "/api/progress", body)
    end if
    m.playing.position = m.lastPosition
end sub

sub stopVideo()
    m.timer.control = "stop"
    saveProgress()
    m.video.control = "stop"
    m.video.visible = false
    m.playing = invalid
    m.top.FindNode("caption").text = ""
    m.top.FindNode("captionBg").visible = false
    m.buttons.SetFocus(true)
end sub

function timecode(value as string) as float
    parts = value.Trim().Split(":")
    total = 0.0
    for each part in parts
        total = total*60 + Val(part.Replace(",","."))
    end for
    return total
end function

function parseVtt(value as dynamic) as object
    cues = []
    if type(value) <> "roString" and type(value) <> "String" then return cues
    blocks = value.Replace(Chr(13), "").Split(Chr(10)+Chr(10))
    tags = CreateObject("roRegex", "<[^>]*>", "")
    for each block in blocks
        lines = block.Split(Chr(10))
        cue = invalid
        for each line in lines
            if Instr(1,line,"-->") > 0
                range = line.Split("-->")
                cue = {start:timecode(range[0]), finish:timecode(range[1].Trim().Split(" ")[0]), text:""}
            else if cue <> invalid
                clean = tags.ReplaceAll(line, "")
                clean = clean.Replace("&lt;","<").Replace("&gt;",">").Replace("&amp;","&").Replace("&nbsp;"," ")
                cue.text += clean + Chr(10)
            end if
        end for
        if cue <> invalid then cues.Push(cue)
    end for
    return cues
end function

function onKeyEvent(key as string, press as boolean) as boolean
    if not press then return false
    if key = "options" and m.video.visible
        m.nextItem = nextEpisode(m.playing, m.library)
        buttons = ["Start over"]
        if m.nextItem <> invalid then buttons.Push("Next episode")
        buttons.Push("Close")
        choose("playback", "Playback", buttons)
        return true
    end if
    if key = "back"
        if m.video.visible
            stopVideo()
            return true
        else if m.detail.visible
            m.detailGeneration++
            m.detail.visible = false
            renderPage()
            m.cues = []
            m.grid.SetFocus(true)
            return true
        else if m.page = "Epizode"
            m.page = "Sezone"
            renderPage()
            return true
        else if m.page = "Sezone"
            m.page = "Serije"
            renderPage()
            return true
        else if not m.nav.HasFocus()
            m.nav.SetFocus(true)
            return true
        end if
    else if key = "left" and m.grid.HasFocus()
        m.nav.SetFocus(true)
        return true
    else if key = "right" and m.nav.HasFocus() and m.items.Count() > 0
        m.grid.SetFocus(true)
        return true
    else if key = "options" and not m.video.visible and not m.detail.visible
        choose("sort", "Sortiranje", ["Naziv A-Z", "Godina: novije prvo", "Ocjena: vise prvo", "Datum dodavanja", "Zatvori"])
        return true
    end if
    return false
end function

function nextEpisode(item as dynamic, library as object) as dynamic
    if item = invalid then return invalid
    if item.kind <> "episode" then return invalid
    result = invalid
    for each candidate in library
        if candidate.kind = "episode" and seriesKey(candidate) = seriesKey(item)
            later = n(candidate.season) = n(item.season) and n(candidate.episode) > n(item.episode)
            later = later or (n(candidate.season) > n(item.season) and n(candidate.season) > 0)
            if later
                if result = invalid
                    result = candidate
                else if n(candidate.season) < n(result.season) or (n(candidate.season) = n(result.season) and n(candidate.episode) < n(result.episode))
                    result = candidate
                end if
            end if
        end if
    end for
    return result
end function
