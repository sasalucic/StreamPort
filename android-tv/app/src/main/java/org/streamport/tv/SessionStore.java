package org.streamport.tv;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.security.MessageDigest;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import org.json.JSONObject;

/** Encrypted, origin-bound recovery copy; never stores a username/password. */
final class SessionStore {
    private static final String KEY="streamport_tv_session_v1";
    private final SharedPreferences prefs;
    SessionStore(Context context){prefs=context.getSharedPreferences("tv_sessions",Context.MODE_PRIVATE);}
    private String id(String origin)throws Exception {
        byte[] digest=MessageDigest.getInstance("SHA-256").digest(origin.getBytes(StandardCharsets.UTF_8));
        return Base64.encodeToString(digest,Base64.NO_WRAP|Base64.URL_SAFE);
    }
    private SecretKey key()throws Exception{
        KeyStore store=KeyStore.getInstance("AndroidKeyStore");store.load(null);
        if(store.containsAlias(KEY))return (SecretKey)store.getKey(KEY,null);
        KeyGenerator generator=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(KEY,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
          .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
        return generator.generateKey();
    }
    private JSONObject read(String origin){
        try{
            String value=prefs.getString(id(origin),"");if(value.isEmpty())return null;
            String[] pieces=value.split(":");if(pieces.length!=2)return null;
            Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,Base64.decode(pieces[0],Base64.NO_WRAP)));
            cipher.updateAAD(origin.getBytes(StandardCharsets.UTF_8));
            JSONObject saved=new JSONObject(new String(cipher.doFinal(Base64.decode(pieces[1],Base64.NO_WRAP)),StandardCharsets.UTF_8));
            if(saved.optLong("expires")<=System.currentTimeMillis()){clear(origin);return null;}
            return saved;
        }catch(Exception e){clear(origin);return null;}
    }
    void save(String origin,String cookies){
        String token=SessionCookie.token(cookies);if(token.isEmpty())return;
        try{
            JSONObject previous=read(origin);
            // Repeated flushes do not extend the local deadline for the same token.
            long expiry=previous!=null&&token.equals(previous.optString("token"))?previous.getLong("expires"):System.currentTimeMillis()+SessionCookie.LIFETIME_MS;
            JSONObject data=new JSONObject().put("token",token).put("expires",expiry);
            Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,key());
            cipher.updateAAD(origin.getBytes(StandardCharsets.UTF_8));
            byte[] encrypted=cipher.doFinal(data.toString().getBytes(StandardCharsets.UTF_8));
            String value=Base64.encodeToString(cipher.getIV(),Base64.NO_WRAP)+":"+Base64.encodeToString(encrypted,Base64.NO_WRAP);
            prefs.edit().putString(id(origin),value).commit();
        }catch(Exception ignored){/* WebView's own persistent cookie store remains available. */}
    }
    String restore(String origin){
        JSONObject saved=read(origin);if(saved==null)return "";
        return SessionCookie.header(saved.optString("token"),saved.optLong("expires"),System.currentTimeMillis(),origin.startsWith("https://"));
    }
    void clear(String origin){try{prefs.edit().remove(id(origin)).commit();}catch(Exception ignored){}}
    void clearAll(){prefs.edit().clear().commit();}
}
