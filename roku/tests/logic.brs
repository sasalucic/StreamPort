sub main()
    assertEqual(n(true),1,"boolean favorite")
    assertEqual(n(false),0,"removed favorite")
    assertEqual(n(invalid),0,"missing numeric metadata")
    library = [
        {id:1,kind:"movie",title:"Avengers",tmdb_id:100,year:2012,added:10,duration:7200,position:100,favorite:1,rating:8}
        {id:2,kind:"movie",title:"Avengers",tmdb_id:100,year:2012,added:20,duration:7200,position:0,favorite:0,rating:8}
        {id:3,kind:"movie",title:"Avengers: Endgame",tmdb_id:200,year:2019,added:30,duration:10800,position:10790,favorite:0,rating:9}
        {id:4,kind:"episode",title:"episode",series:"Supernatural",show_key:"show-1",season:2,episode:10,position:0}
        {id:5,kind:"episode",title:"episode",series:"Supernatural",show_key:"show-1",season:2,episode:2,position:0}
        {id:6,kind:"episode",title:"episode",series:"Supernatural",show_key:"show-1",season:1,episode:1,position:0}
    ]
    assertEqual(nextEpisode(library[5],library).id,5,"next episode across seasons")
    assertEqual(nextEpisode(library[4],library).id,4,"numeric next episode")
    assertEqual(nextEpisode(library[3],library),invalid,"last episode")
    assertEqual(nextEpisode(library[0],library),invalid,"movie has no next episode")
    rows=selectItems(library,"Pretraga","avengers","name","","")
    assertEqual(rows.Count(),2,"deduplicate search")
    rows=selectItems(library,"Serije","","name","","")
    assertEqual(rows.Count(),1,"group episodes into one series")
    assertEqual(rows[0].kind,"show","exclude movies from series")
    rows=selectItems(library,"Sezone","","name","show-1","")
    assertEqual(rows.Count(),2,"season grouping")
    assertEqual(rows[0].season,1,"numeric season sort")
    rows=selectItems(library,"Epizode","","name","show-1","2")
    assertEqual(rows[0].episode,2,"numeric episode sort")
    assertEqual(rows[1].episode,10,"episode 10 after 2")
    rows=selectItems(library,"Favoriti","","name","","")
    assertEqual(rows.Count(),1,"favorites filter")
    rows=selectItems(library,"Nastavi gledati","","name","","")
    assertEqual(rows.Count(),1,"hide completed content")
    rows=selectItems(library,"Filmovi","","year","","")
    assertEqual(rows[0].year,2019,"newest first")
    rows=selectItems(library,"Pretraga","absent","name","","")
    assertEqual(rows.Count(),0,"empty results")
    assertEqual(timecode("01:02:03.500"),3723.5,"VTT timestamp")
    text="WEBVTT"+Chr(10)+Chr(10)+"00:00:01.000 --> 00:00:03.000 align:center"+Chr(10)+"<i>Hello</i> &amp; hi"+Chr(10)+Chr(10)
    cues=parseVtt(text)
    assertEqual(cues.Count(),1,"VTT parse")
    assertEqual(cues[0].start,1,"cue start")
    assertEqual(cues[0].finish,3,"cue end with settings")
    assertEqual(cues[0].text.Trim(),"Hello & hi","caption tags stripped")
    print "PASS: Roku library and subtitle logic"
end sub
sub assertEqual(actual as dynamic, expected as dynamic, label as string)
    if actual <> expected
        print "FAIL: ";label;" expected=";expected;" actual=";actual
        stop
    end if
end sub
