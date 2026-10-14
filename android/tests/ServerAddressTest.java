import org.streamport.mobile.ServerAddress;
public class ServerAddressTest {
    static int tests;
    static void equal(String expected,String actual){tests++;if(!expected.equals(actual))throw new AssertionError(actual);}
    static void rejected(String value){tests++;try{ServerAddress.normalize(value);throw new AssertionError(value);}catch(IllegalArgumentException expected){}}
    static void same(boolean expected,String a,String b){tests++;if(ServerAddress.sameOrigin(a,b)!=expected)throw new AssertionError(a+" -> "+b);}
    public static void main(String[] args){
        equal("http://192.0.2.10:8097/",ServerAddress.normalize("192.0.2.10:8097"));
        equal("http://198.51.100.10:8097/",ServerAddress.normalize(" http://198.51.100.10:8097 "));
        equal("https://example.com/streamport/",ServerAddress.normalize("https://example.com/streamport"));
        equal("http://[::1]:8097/",ServerAddress.normalize("http://[::1]:8097"));
        rejected("");rejected("javascript:alert(1)");rejected("file:///etc/passwd");rejected("http://user:password@host");rejected("http://host:0");rejected("http://host:99999");rejected("http://host/?password=a");rejected("http://host/#x");rejected("http://foo bar");
        same(true,"http://HOST/","http://host:80/api");same(false,"http://host:8097/","http://host/");same(false,"https://host/","http://host/");same(false,"http://host/","http://host.evil/");same(false,"http://host/","http://u:p@host/");same(true,"https://host/","https://host/api");
        System.out.println(tests+" address/navigation tests passed.");
    }
}
