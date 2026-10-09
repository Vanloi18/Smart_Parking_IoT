package com.smartparking.iot;

import android.app.Activity;
import android.content.Context;
import android.os.Build;
import android.os.Bundle;
import android.os.VibrationEffect;
import android.os.Vibrator;
import android.view.View;
import android.view.Window;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;

public class MainActivity extends Activity {

    private WebView webView;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Apple-like clean light status bar
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            Window window = getWindow();
            window.addFlags(WindowManager.LayoutParams.FLAG_DRAWS_SYSTEM_BAR_BACKGROUNDS);
            window.setStatusBarColor(0xFFFFFFFF);
            View decor = window.getDecorView();
            decor.setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
        }

        webView = new WebView(this);
        setContentView(webView);

        configureWebView();
        webView.loadUrl("file:///android_asset/index.html");
    }

    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setLoadsImagesAutomatically(true);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        }

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                view.loadUrl(url);
                return true;
            }
        });

        webView.setWebChromeClient(new WebChromeClient());

        // Native Android Bridge
        webView.addJavascriptInterface(new AndroidBridge(this), "AndroidNative");
    }

    public static class AndroidBridge {
        private final Context context;
        private final String backendUrl;

        public AndroidBridge(Context context) {
            this.context = context;
            // Asset được đồng bộ từ backend_config.json; không giữ IP riêng trong Java.
            try (BufferedReader reader = new BufferedReader(new InputStreamReader(
                    context.getAssets().open("backend_config.json"), StandardCharsets.UTF_8))) {
                StringBuilder json = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) {
                    json.append(line);
                }
                JSONObject config = new JSONObject(json.toString());
                backendUrl = "http://" + config.getString("host") + ":" + config.getInt("port");
            } catch (Exception error) {
                // Báo cấu hình đóng gói lỗi thay vì âm thầm gọi một IP cũ.
                throw new IllegalStateException("Cannot load backend_config.json", error);
            }
        }

        @JavascriptInterface
        public void vibrate() {
            try {
                Vibrator v = (Vibrator) context.getSystemService(Context.VIBRATOR_SERVICE);
                if (v != null) {
                    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                        v.vibrate(VibrationEffect.createOneShot(45, VibrationEffect.DEFAULT_AMPLITUDE));
                    } else {
                        v.vibrate(45);
                    }
                }
            } catch (Exception ignored) {
            }
        }

        @JavascriptInterface
        public void showToast(final String message) {
            if (context instanceof Activity) {
                ((Activity) context).runOnUiThread(() -> 
                    Toast.makeText(context, message, Toast.LENGTH_SHORT).show()
                );
            }
        }

        @JavascriptInterface
        public String getDefaultBackendUrl() {
            return backendUrl;
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
