package org.streamport.tv;
public final class SessionCookieTest {
 public static void main(String[] args){
  String token="abcdefghijklmnopqrstuvwxyz_0123456789-TEST";
  check(SessionCookie.token("other=x; streamport="+token+"; flag=y").equals(token),"cookie extraction");
  check(SessionCookie.token(null).isEmpty(),"missing cookie");
  check(SessionCookie.token("streamport=bad\r\nInjected: y").isEmpty(),"reject malformed value");
  check(SessionCookie.header(token,10000,10000,false).isEmpty(),"expired session not restored");
  String plain=SessionCookie.header(token,11000,1000,false);
  check(plain.contains("Max-Age=10")&&plain.contains("HttpOnly")&&plain.contains("SameSite=Strict"),"remaining lifetime and attributes");
  check(!plain.contains("; Secure"),"LAN HTTP compatible");
  check(SessionCookie.header(token,11000,1000,true).endsWith("; Secure"),"HTTPS preserves secure cookie");
  System.out.println("PASS: cookie parsing, expired-session rejection, remaining lifetime, HTTP/HTTPS attributes");
 }
 static void check(boolean value,String message){if(!value)throw new AssertionError(message);}
}
