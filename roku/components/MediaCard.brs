sub contentChanged()
    c = m.top.itemContent
    if c = invalid then return
    m.top.FindNode("title").text = c.title
    m.top.FindNode("meta").text = c.description
    p = m.top.FindNode("poster")
    agent = CreateObject("roHttpAgent")
    agent.SetCertificatesFile("common:/certs/ca-bundle.crt")
    if c.authCookie <> "" then agent.AddHeader("Cookie", c.authCookie)
    p.SetHttpAgent(agent)
    p.uri = c.hdPosterUrl
end sub
sub focusChanged()
    if m.top.focusPercent > 0.5
        m.top.FindNode("frame").color = "#D4FF00"
    else
        m.top.FindNode("frame").color = "#202B2D"
    end if
end sub
