package org.streamport.mobile;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.Dialog;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ActivityInfo;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.os.Build;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.view.WindowManager;
import android.view.inputmethod.InputMethodManager;
import android.webkit.*;
import android.widget.*;
import org.json.JSONObject;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final int BG=0xff080b0d, PANEL=0xff141d1d, KIWI=0xffccff00, MUTED=0xffa8b5af;
    private FrameLayout root, content, fullscreen;
    private LinearLayout chrome, toolbar;
    private WebView web;
    private View customView;
    private WebChromeClient.CustomViewCallback fullscreenCallback;
    private SharedPreferences prefs;
    private String server="";
    private int generation=0, previousOrientation;
    private boolean pageFailed=false, resumed=false, playerMode=false;
    private int playerOrientation;
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private ProgressBar progress;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        prefs=getSharedPreferences("connection",MODE_PRIVATE);
        root=new FrameLayout(this);root.setBackgroundColor(BG);setContentView(root);
        root.setOnApplyWindowInsetsListener((v,insets)->{
            if (customView==null && !playerMode) {
                if (Build.VERSION.SDK_INT>=30) {
                    android.graphics.Insets i=insets.getInsets(WindowInsets.Type.systemBars()|WindowInsets.Type.displayCutout()|WindowInsets.Type.ime());
                    v.setPadding(i.left,i.top,i.right,i.bottom);
                } else v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());
            } else {int bottom=Build.VERSION.SDK_INT>=30?insets.getInsets(WindowInsets.Type.ime()).bottom:0;v.setPadding(0,0,0,bottom);}
            return insets.consumeSystemWindowInsets();
        });
        String saved=prefs.getString("server","");
        if (!saved.isEmpty()) openServer(saved); else showConnect("");
    }
    private int dp(float n){return Math.round(n*getResources().getDisplayMetrics().density);}
    private GradientDrawable panel(int color,int radius){GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(radius));return d;}
    private TextView text(String value,int size,int color){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(color);t.setLineSpacing(dp(3),1);return t;}
    private Button button(String label,boolean primary){Button b=new Button(this);b.setText(label);b.setAllCaps(false);b.setTextSize(15);b.setTextColor(primary?BG:Color.WHITE);b.setBackground(panel(primary?KIWI:PANEL,14));b.setMinHeight(dp(50));b.setPadding(dp(16),dp(8),dp(16),dp(8));return b;}
    private void spaced(LinearLayout box,View v,int top){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.topMargin=dp(top);box.addView(v,p);}
    private void disposeWeb(){
        setPlayerMode(false);
        if(web!=null){web.stopLoading();web.loadUrl("about:blank");if(web.getParent() instanceof ViewGroup)((ViewGroup)web.getParent()).removeView(web);web.destroy();web=null;}
    }
    private void showConnect(String message){
        generation++;hideFullscreen();disposeWeb();root.removeAllViews();
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);root.addView(scroll,new FrameLayout.LayoutParams(-1,-1));
        LinearLayout outer=new LinearLayout(this);outer.setGravity(Gravity.CENTER);outer.setPadding(dp(24),dp(24),dp(24),dp(24));scroll.addView(outer,new ScrollView.LayoutParams(-1,-1));
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);int width=Math.min(getResources().getDisplayMetrics().widthPixels-dp(48),dp(460));outer.addView(box,new LinearLayout.LayoutParams(width,-2));
        ImageView logo=new ImageView(this);logo.setImageResource(org.streamport.mobile.R.drawable.ic_launcher);box.addView(logo,new LinearLayout.LayoutParams(dp(78),dp(78)));
        TextView title=text("Tvoj server.\nApp settings.",32,Color.WHITE);title.setTypeface(null,Typeface.BOLD);spaced(box,title,20);
        spaced(box,text("Filmovi, serije i titlovi — povezani s tvojom kućnom bibliotekom.",16,MUTED),12);
        spaced(box,text("ADRESA SERVERA",12,KIWI),32);
        EditText input=new EditText(this);input.setSingleLine(true);input.setTextColor(Color.WHITE);input.setTextSize(16);input.setHintTextColor(MUTED);input.setBackground(panel(PANEL,14));input.setPadding(dp(16),dp(16),dp(16),dp(16));input.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_URI);input.setHint("http://IP_SERVERA:8097");input.setText(prefs.getString("server",""));spaced(box,input,10);
        LinearLayout presets=new LinearLayout(this);presets.setOrientation(LinearLayout.HORIZONTAL);spaced(box,presets,12);
        Button local=button("Kućna mreža",false),tail=button("Tailscale",false);LinearLayout.LayoutParams half=new LinearLayout.LayoutParams(0,-2,1);half.setMargins(0,0,dp(6),0);presets.addView(local,half);presets.addView(tail,new LinearLayout.LayoutParams(0,-2,1));
        local.setOnClickListener(v->{input.setText("");input.setHint("http://YOUR_LAN_HOST:8097");input.requestFocus();});tail.setOnClickListener(v->{input.setText("");input.setHint("http://YOUR_VPN_HOST:8097");input.requestFocus();});
        TextView status=text(message,14,MUTED);spaced(box,status,16);
        Button connect=button("Poveži se  →",true);spaced(box,connect,12);
        spaced(box,text("Kod kuće koristi lokalnu adresu. Za pristup preko Tailscalea uključi Tailscale na telefonu. Prijava slijedi na serveru.",13,MUTED),22);
        connect.setOnClickListener(v->{
            final String address;
            try{address=ServerAddress.normalize(input.getText().toString());}catch(IllegalArgumentException e){status.setText(e.getMessage());return;}
            ((InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(input.getWindowToken(),0);
            connect.setEnabled(false);status.setText("Provjeravam StreamPort server…");int ticket=++generation;
            worker.execute(()->{
                String failure=null;HttpURLConnection connection=null;
                try{
                    connection=(HttpURLConnection)new URL(address+"api/health").openConnection();connection.setConnectTimeout(8000);connection.setReadTimeout(8000);connection.setInstanceFollowRedirects(false);
                    int code=connection.getResponseCode();if(code!=200)throw new Exception("Server vraća HTTP "+code+". Provjeri adresu i port.");
                    java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();
                    try(java.io.InputStream stream=connection.getInputStream()){byte[] buffer=new byte[1024];int read;while((read=stream.read(buffer))!=-1){if(bytes.size()+read>8192)throw new Exception("Neispravan odgovor servera.");bytes.write(buffer,0,read);}}
                    JSONObject health=new JSONObject(new String(bytes.toByteArray(),StandardCharsets.UTF_8));
                    if(!"ok".equals(health.optString("status"))||!health.has("version"))throw new Exception("Na ovoj adresi nije pronađen StreamPort.");
                }catch(Exception e){failure=e.getMessage();if(failure==null||failure.isEmpty())failure="Veza nije uspjela.";}finally{if(connection!=null)connection.disconnect();}
                final String result=failure;runOnUiThread(()->{if(isFinishing()||isDestroyed()||ticket!=generation)return;connect.setEnabled(true);if(result!=null){status.setText("Ne mogu povezati server. Provjeri Wi-Fi/Tailscale i adresu.\n"+result);return;}prefs.edit().putString("server",address).apply();openServer(address);});
            });
        });
    }
    @SuppressLint("SetJavaScriptEnabled") private void openServer(String address){
        generation++;server=address;hideFullscreen();disposeWeb();root.removeAllViews();
        chrome=new LinearLayout(this);chrome.setOrientation(LinearLayout.VERTICAL);root.addView(chrome,new FrameLayout.LayoutParams(-1,-1));
        toolbar=new LinearLayout(this);toolbar.setGravity(Gravity.CENTER_VERTICAL);toolbar.setPadding(dp(14),0,dp(8),0);toolbar.setBackgroundColor(BG);chrome.addView(toolbar,new LinearLayout.LayoutParams(-1,dp(44)));
        TextView caption=text("●  STREAMPORT",12,KIWI);caption.setTypeface(null,Typeface.BOLD);toolbar.addView(caption,new LinearLayout.LayoutParams(0,-2,1));
        Button more=button("⋮",false);more.setContentDescription("App settings");more.setTextSize(24);more.setMinHeight(0);toolbar.addView(more,new LinearLayout.LayoutParams(dp(44),dp(40)));more.setOnClickListener(v->showOptions());
        progress=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);progress.setProgressTintList(android.content.res.ColorStateList.valueOf(KIWI));chrome.addView(progress,new LinearLayout.LayoutParams(-1,dp(2)));
        content=new FrameLayout(this);chrome.addView(content,new LinearLayout.LayoutParams(-1,0,1));
        web=new WebView(this);web.setBackgroundColor(BG);content.addView(web,new FrameLayout.LayoutParams(-1,-1));WebSettings s=web.getSettings();s.setJavaScriptEnabled(true);s.setTextZoom(100);s.setUseWideViewPort(true);s.setLoadWithOverviewMode(true);s.setCacheMode(WebSettings.LOAD_NO_CACHE);s.setDomStorageEnabled(true);s.setAllowFileAccess(false);s.setAllowContentAccess(false);s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);s.setMediaPlaybackRequiresUserGesture(false);s.setSupportMultipleWindows(false);s.setUserAgentString(s.getUserAgentString()+" StreamPortAndroid/1.7.0");CookieManager.getInstance().setAcceptCookie(true);CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);
        web.setWebViewClient(new WebViewClient(){
            @Override public WebResourceResponse shouldInterceptRequest(WebView view,WebResourceRequest request){
                String url=request.getUrl().toString();
                if(ServerAddress.sameOrigin(server,url)&&"/__streamport_android/mobile.css".equals(request.getUrl().getPath())){
                    try{return new WebResourceResponse("text/css","UTF-8",200,"OK",java.util.Collections.singletonMap("Cache-Control","no-store"),new java.io.ByteArrayInputStream((assetText("mobile.css")+"\n"+assetText("polish.css")+"\n"+assetText("modern.css")+"\n"+assetText("phone-compat.css")).getBytes(StandardCharsets.UTF_8)));}
                    catch(java.io.IOException e){return new WebResourceResponse("text/plain","UTF-8",404,"Not Found",java.util.Collections.emptyMap(),new java.io.ByteArrayInputStream(new byte[0]));}
                }return null;
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){return navigate(request.getUrl().toString());}
            @Override public boolean shouldOverrideUrlLoading(WebView view,String url){return navigate(url);}
            @Override public void onPageStarted(WebView view,String url,android.graphics.Bitmap icon){pageFailed=false;progress.setVisibility(View.VISIBLE);}
            @Override public void onPageFinished(WebView view,String url){progress.setVisibility(View.GONE);CookieManager.getInstance().flush();if(!pageFailed&&ServerAddress.sameOrigin(server,url))installMobileLayout(view);}
            @Override public void onReceivedError(WebView view,WebResourceRequest req,WebResourceError err){if(req.isForMainFrame())showLoadError("Server nije dostupan. Provjeri mrežu ili uključi Tailscale.");}
            @Override public void onReceivedHttpError(WebView view,WebResourceRequest req,WebResourceResponse res){if(req.isForMainFrame())showLoadError("Server vraća HTTP "+res.getStatusCode()+".");}
            @Override public void onReceivedSslError(WebView view,SslErrorHandler handler,android.net.http.SslError error){handler.cancel();showLoadError("HTTPS certifikat servera nije važeći. Provjeri adresu i certifikat.");}
            @Override public boolean onRenderProcessGone(WebView view,RenderProcessGoneDetail detail){showConnect("Prikaz je zaustavljen. Poveži server ponovo.");return true;}
        });
        web.setWebChromeClient(new WebChromeClient(){
            @Override public android.graphics.Bitmap getDefaultVideoPoster(){android.graphics.Bitmap b=android.graphics.Bitmap.createBitmap(2,2,android.graphics.Bitmap.Config.ARGB_8888);b.eraseColor(Color.BLACK);return b;}
            @Override public void onProgressChanged(WebView view,int p){progress.setProgress(p);}
            @Override public void onShowCustomView(View view,CustomViewCallback callback){showFullscreen(view,callback);}
            @Override public void onHideCustomView(){hideFullscreen();}
            @Override public View getVideoLoadingProgressView(){ProgressBar p=new ProgressBar(MainActivity.this);return p;}
        });
        web.loadUrl(server);if(!resumed)web.onPause();
    }
    private String assetText(String name) throws java.io.IOException {
        try(java.io.InputStream in=getAssets().open(name);java.io.ByteArrayOutputStream out=new java.io.ByteArrayOutputStream()){
            byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1)out.write(b,0,n);return new String(out.toByteArray(),StandardCharsets.UTF_8);
        }
    }
    private void installMobileLayout(WebView view){
        try {
            String script=assetText("search.js")+";\n"+assetText("mobile.js")+";\n"+assetText("polish.js")+";\n"+assetText("phone-compat.js");
            String stylesheet=Uri.parse(server).buildUpon().path("/__streamport_android/mobile.css").query("v=1.7.0").build().toString();
            String insert="(()=>{let s=document.getElementById('streamport-android-style');if(!s){s=document.createElement('link');s.id='streamport-android-style';s.rel='stylesheet';s.href="+JSONObject.quote(stylesheet)+";document.head.append(s);}})();";
            view.evaluateJavascript(insert+script,result->{if(view==web&&"true".equals(result))toolbar.setVisibility(View.GONE);});
        }catch(java.io.IOException e){Toast.makeText(this,"Mobile layout unavailable",Toast.LENGTH_SHORT).show();}
    }
    private void setPlayerMode(boolean enabled){
        if(playerMode==enabled)return;
        playerMode=enabled;
        if(enabled){
            playerOrientation=getRequestedOrientation();
            getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON|WindowManager.LayoutParams.FLAG_FULLSCREEN);
            getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN|View.SYSTEM_UI_FLAG_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY|View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN|View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
        }else{
            getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON|WindowManager.LayoutParams.FLAG_FULLSCREEN);
            getWindow().getDecorView().setSystemUiVisibility(0);setRequestedOrientation(playerOrientation);
        }root.requestApplyInsets();
    }
    private boolean navigate(String url){
        if(url.startsWith("streamport://")){
            if(web!=null&&ServerAddress.sameOrigin(server,web.getUrl())){
                if("streamport://player-open".equals(url))setPlayerMode(true);
                else if("streamport://player-close".equals(url))setPlayerMode(false);
                else if("streamport://rotate".equals(url)&&playerMode)setRequestedOrientation(getResources().getConfiguration().orientation==Configuration.ORIENTATION_LANDSCAPE?ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT:ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
                else if("streamport://settings".equals(url))showOptions();
            }return true;
        }

        if(ServerAddress.sameOrigin(server,url))return false;
        Uri uri=Uri.parse(url);if("https".equals(uri.getScheme())||"http".equals(uri.getScheme())){
            try{startActivity(new Intent(Intent.ACTION_VIEW,uri));}catch(Exception e){Toast.makeText(this,"Nema aplikacije za otvaranje linka.",Toast.LENGTH_SHORT).show();}
        }return true;
    }
    private void showLoadError(String message){
        if(pageFailed||content==null)return;pageFailed=true;progress.setVisibility(View.GONE);
        LinearLayout error=new LinearLayout(this);error.setOrientation(LinearLayout.VERTICAL);error.setGravity(Gravity.CENTER);error.setPadding(dp(24),dp(32),dp(24),dp(32));error.setBackgroundColor(BG);content.addView(error,new FrameLayout.LayoutParams(-1,-1));
        spaced(error,text("Veza je prekinuta",25,Color.WHITE),0);spaced(error,text(message,16,MUTED),16);
        Button retry=button("Pokušaj ponovo",true);spaced(error,retry,24);retry.setOnClickListener(v->openServer(server));Button change=button("Change server",false);spaced(error,change,12);change.setOnClickListener(v->showConnect(""));
    }
    private Dialog kiwiDialog(String title, String subtitle) {
        Dialog d=new Dialog(this);d.requestWindowFeature(android.view.Window.FEATURE_NO_TITLE);
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(false);
        LinearLayout box=new LinearLayout(this);box.setOrientation(LinearLayout.VERTICAL);box.setPadding(dp(24),dp(24),dp(24),dp(24));
        GradientDrawable surface=panel(PANEL,26);surface.setStroke(dp(1),0xff46552c);box.setBackground(surface);scroll.addView(box);
        TextView eyebrow=text("●  STREAMPORT",12,KIWI);eyebrow.setLetterSpacing(.12f);spaced(box,eyebrow,0);
        LinearLayout heading=new LinearLayout(this);heading.setGravity(Gravity.CENTER_VERTICAL);
        TextView label=text(title,26,Color.WHITE);label.setTypeface(null,Typeface.BOLD);heading.addView(label,new LinearLayout.LayoutParams(0,-2,1));
        Button close=button("×",false);close.setContentDescription("Close menu");close.setMinHeight(0);heading.addView(close,new LinearLayout.LayoutParams(dp(44),dp(44)));close.setOnClickListener(v->d.dismiss());spaced(box,heading,10);
        if(!subtitle.isEmpty())spaced(box,text(subtitle,13,MUTED),8);
        d.setContentView(scroll);d.show();android.view.Window w=d.getWindow();
        if(w!=null){w.setBackgroundDrawableResource(android.R.color.transparent);w.setLayout(Math.min(getResources().getDisplayMetrics().widthPixels-dp(24),dp(460)),ViewGroup.LayoutParams.WRAP_CONTENT);w.setGravity(Gravity.BOTTOM|Gravity.CENTER_HORIZONTAL);WindowManager.LayoutParams a=w.getAttributes();a.dimAmount=.72f;a.y=dp(12);w.setAttributes(a);w.addFlags(WindowManager.LayoutParams.FLAG_DIM_BEHIND);w.setNavigationBarColor(BG);}
        d.setCanceledOnTouchOutside(true);box.setTag(d);d.getWindow().getDecorView().setTag(box);return d;
    }
    private void menuAction(Dialog d,String icon,String title,String subtitle,Runnable action){
        LinearLayout box=(LinearLayout)d.getWindow().getDecorView().getTag();
        LinearLayout row=new LinearLayout(this);row.setGravity(Gravity.CENTER_VERTICAL);row.setPadding(dp(14),dp(16),dp(14),dp(16));row.setBackground(panel(0xff1d2924,15));
        TextView glyph=text(icon,25,KIWI);glyph.setGravity(Gravity.CENTER);row.addView(glyph,new LinearLayout.LayoutParams(dp(40),-2));
        LinearLayout copy=new LinearLayout(this);copy.setOrientation(LinearLayout.VERTICAL);TextView name=text(title,16,Color.WHITE);name.setTypeface(null,Typeface.BOLD);copy.addView(name);copy.addView(text(subtitle,12,MUTED));LinearLayout.LayoutParams cp=new LinearLayout.LayoutParams(0,-2,1);cp.leftMargin=dp(12);row.addView(copy,cp);row.addView(text("›",24,KIWI));
        row.setFocusable(true);row.setClickable(true);row.setContentDescription(title+". "+subtitle);row.setOnClickListener(v->{d.dismiss();action.run();});spaced(box,row,12);
    }
    private void showOptions(){
        Dialog d=kiwiDialog("App settings",server);
        menuAction(d,"◉","My account","Password and user management",()->{if(web!=null)web.evaluateJavascript("(()=>{if(typeof me!=='undefined'&&me&&window.streamportLibrarySort){page='account';search='';filter='';detailId=null;const i=document.querySelector('#search');if(i)i.value='';render().catch(error);}else alert('Sign in and update the server to v0.5.0.');})()",null);});
        menuAction(d,"♡","Favorites","Your saved movies",()->{if(web!=null)web.evaluateJavascript("(()=>{if(typeof me!=='undefined'&&me&&window.streamportLibrarySort){page='favorites';search='';filter='';detailId=null;browseMode='library';const i=document.querySelector('#search');if(i)i.value='';render().catch(error);}else alert('Sign in and update the server to v0.5.0.');})()",null);});
        menuAction(d,"↻","Refresh library","Load the latest library from the server",()->openServer(server));
        menuAction(d,"⇄","Change server","Connect to another StreamPort server",()->showConnect(""));
        menuAction(d,"↪","Sign out","Sign out on this phone",()->{Dialog confirm=kiwiDialog("Sign out on this phone?","Remove the saved session on this device.");menuAction(confirm,"✓","Sign out","Confirm sign out",()->CookieManager.getInstance().removeAllCookies(ok->{CookieManager.getInstance().flush();WebStorage.getInstance().deleteAllData();openServer(server);}));});
        menuAction(d,"ⓘ","About","StreamPort Android 1.7.0",()->kiwiDialog("StreamPort 1.7.0","Android client for your StreamPort server. The library and player use the server web interface.\n\n"+server));
    }
    private void showFullscreen(View view,WebChromeClient.CustomViewCallback callback){
        if(customView!=null){callback.onCustomViewHidden();return;}customView=view;fullscreenCallback=callback;previousOrientation=getRequestedOrientation();fullscreen=new FrameLayout(this);fullscreen.setBackgroundColor(Color.BLACK);fullscreen.addView(view,new FrameLayout.LayoutParams(-1,-1));root.addView(fullscreen,new FrameLayout.LayoutParams(-1,-1));chrome.setVisibility(View.GONE);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON|WindowManager.LayoutParams.FLAG_FULLSCREEN);getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN|View.SYSTEM_UI_FLAG_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY|View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN|View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION|View.SYSTEM_UI_FLAG_LAYOUT_STABLE);setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);root.requestApplyInsets();
    }
    private void hideFullscreen(){
        if(customView==null)return;root.removeView(fullscreen);fullscreen.removeAllViews();fullscreen=null;customView=null;if(chrome!=null)chrome.setVisibility(View.VISIBLE);getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON|WindowManager.LayoutParams.FLAG_FULLSCREEN);getWindow().getDecorView().setSystemUiVisibility(0);setRequestedOrientation(previousOrientation);WebChromeClient.CustomViewCallback callback=fullscreenCallback;fullscreenCallback=null;if(callback!=null)callback.onCustomViewHidden();if(web!=null)web.evaluateJavascript("if(window.streamportMobileInstalled){const v=document.querySelector('#video');if(v)v.controls=false;}",null);root.requestApplyInsets();
    }
    @Override public void onBackPressed(){
        if(customView!=null){hideFullscreen();return;}
        if(web==null){if(!prefs.getString("server","").isEmpty())openServer(prefs.getString("server",""));else super.onBackPressed();return;}
        if(!ServerAddress.sameOrigin(server,web.getUrl())){super.onBackPressed();return;}
        WebView active=web;
        web.evaluateJavascript("(()=>{if(window.streamportMobileBack&&window.streamportMobileBack())return true;const ds=[...document.querySelectorAll('dialog[open]')];if(ds.length){const d=ds[ds.length-1];if(d.id==='player'&&typeof closePlayer==='function')closePlayer();else d.close();return true;}if(typeof detailId!=='undefined'&&detailId){detailId=null;render();return true;}if(typeof filter!=='undefined'&&filter){filter='';render();return true;}if(window.streamportSearchBack&&window.streamportSearchBack())return true;if(typeof page!=='undefined'&&page!=='home'){page='home';render();return true;}return false;})()",value->{if(active!=web||isFinishing())return;if(!"true".equals(value)){if(web.canGoBack())web.goBack();else new AlertDialog.Builder(this).setMessage("Zatvoriti StreamPort?").setNegativeButton("Ostani",null).setPositiveButton("Zatvori",(d,n)->finish()).show();}});
    }
    @Override protected void onResume(){super.onResume();resumed=true;if(web!=null)web.onResume();}
    @Override protected void onPause(){resumed=false;if(web!=null){web.evaluateJavascript("document.querySelectorAll('video,audio').forEach(v=>v.pause())",null);web.onPause();CookieManager.getInstance().flush();}super.onPause();}
    @Override protected void onDestroy(){generation++;hideFullscreen();disposeWeb();worker.shutdownNow();super.onDestroy();}
    @Override public void onConfigurationChanged(Configuration config){super.onConfigurationChanged(config);root.requestApplyInsets();}
}
