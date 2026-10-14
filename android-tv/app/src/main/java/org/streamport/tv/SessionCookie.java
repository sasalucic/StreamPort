package org.streamport.tv;

/** Pure cookie parsing. The backend still validates and expires every session. */
final class SessionCookie {
    static final long LIFETIME_MS=7L*24*60*60*1000;
    static String token(String cookies){
        if(cookies==null)return "";
        for(String part:cookies.split(";")){
            String value=part.trim();
            if(value.startsWith("streamport=")){
                String token=value.substring(11);
                return token.matches("[A-Za-z0-9_-]{20,200}")?token:"";
            }
        }
        return "";
    }
    static String header(String token,long expires,long now,boolean secure){
        if(token==null||!token.matches("[A-Za-z0-9_-]{20,200}")||expires<=now)return "";
        return "streamport="+token+"; Path=/; HttpOnly; SameSite=Strict; Max-Age="+Math.max(1,(expires-now)/1000)+(secure?"; Secure":"");
    }
}
