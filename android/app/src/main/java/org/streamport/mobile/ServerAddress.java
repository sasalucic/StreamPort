package org.streamport.mobile;

import java.net.URI;
import java.util.Locale;

/** Shared validation for native HTTP and WebView navigation. No credentials in URLs. */
public final class ServerAddress {
    private ServerAddress() {}
    public static String normalize(String text) {
        String value = text.trim();
        if (value.isEmpty()) throw new IllegalArgumentException("Unesi adresu servera.");
        if (!value.contains("://")) value = "http://" + value;
        try {
            URI u = new URI(value);
            String scheme = u.getScheme().toLowerCase(Locale.ROOT);
            if ((!scheme.equals("http") && !scheme.equals("https")) || u.getHost() == null || u.getRawUserInfo() != null || u.getRawQuery() != null || u.getRawFragment() != null || u.getPort() > 65535 || u.getPort() == 0 || value.contains("\\"))
                throw new IllegalArgumentException("Koristi http:// ili https:// adresu bez lozinke i parametara.");
            String path = u.getRawPath();
            if (path == null || path.isEmpty()) path = "/";
            if (!path.endsWith("/")) path += "/";
            return new URI(scheme + "://" + u.getRawAuthority() + path).normalize().toASCIIString();
        } catch (java.net.URISyntaxException e) { throw new IllegalArgumentException("Adresa nije ispravna. Primjer: http://your-server-host:8097"); }
    }
    public static boolean sameOrigin(String a, String b) {
        try {
            URI x = new URI(a), y = new URI(b);
            return x.getHost() != null && y.getHost() != null && x.getScheme().equalsIgnoreCase(y.getScheme()) && x.getHost().equalsIgnoreCase(y.getHost()) && port(x) == port(y) && y.getRawUserInfo() == null;
        } catch (Exception e) { return false; }
    }
    private static int port(URI u) { return u.getPort() >= 0 ? u.getPort() : "https".equalsIgnoreCase(u.getScheme()) ? 443 : 80; }
}
