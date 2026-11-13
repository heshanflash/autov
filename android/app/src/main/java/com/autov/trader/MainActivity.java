package com.autov.trader;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.View;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

/**
 * AutoV Trader — mobile client for the AutoV Trader analysis desk.
 * Loads the dashboard served by ./run.sh on your PC (same Wi-Fi network).
 */
public class MainActivity extends Activity {

    private static final String PREFS = "autov_prefs";
    private static final String KEY_URL = "server_url";
    private static final String C_BG = "#0B0F17";
    private static final String C_CARD = "#141B2C";
    private static final String C_LINE = "#232E47";
    private static final String C_TEXT = "#DBE4F5";
    private static final String C_MUTED = "#7F8DB0";
    private static final String C_ACCENT = "#4DA3FF";
    private static final String C_UP = "#2FD48F";
    private static final String C_DOWN = "#FF5C7A";

    private WebView web;
    private EditText urlBox;
    private TextView status;
    private TextView hint;
    private ProgressBar progress;
    private View connectPanel;

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // ---------- build UI in code (no resources needed) ----------
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.parseColor(C_BG));

        // top bar
        LinearLayout top = new LinearLayout(this);
        top.setOrientation(LinearLayout.HORIZONTAL);
        top.setGravity(Gravity.CENTER_VERTICAL);
        top.setBackgroundColor(Color.parseColor("#121A2C"));
        top.setPadding(dp(14), dp(14), dp(14), dp(10));
        TextView title = new TextView(this);
        title.setText("\u25B2 AutoV Trader");
        title.setTextColor(Color.parseColor(C_ACCENT));
        title.setTextSize(18f);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) { if (web != null) web.reload(); }
        });
        status = new TextView(this);
        status.setText("  \u25CB disconnected");
        status.setTextColor(Color.parseColor(C_MUTED));
        status.setTextSize(12f);
        status.setGravity(Gravity.END);
        LinearLayout.LayoutParams titleLp =
                new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f);
        top.addView(title);
        top.addView(status, titleLp);
        root.addView(top);

        // connect / offline panel
        connectPanel = buildConnectPanel();
        root.addView(connectPanel);

        // progress
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        progress.setVisibility(View.GONE);
        LinearLayout.LayoutParams progLp =
                new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(3));
        root.addView(progress, progLp);

        // webview
        web = new WebView(this);
        LinearLayout.LayoutParams webLp =
                new LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f);
        root.addView(web, webLp);
        setContentView(root);

        // ---------- webview setup ----------
        WebSettings ws = web.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setUseWideViewPort(true);
        ws.setLoadWithOverviewMode(true);
        ws.setSupportZoom(false);
        ws.setBuiltInZoomControls(false);
        ws.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        ws.setCacheMode(WebSettings.LOAD_DEFAULT);
        ws.setMediaPlaybackRequiresUserGesture(false);
        ws.setTextZoom(100);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                String s = u.toString();
                if (s.startsWith("http://") || s.startsWith("https://")) {
                    return false; // keep dashboard navigation inside the app
                }
                try {
                    startActivity(new Intent(Intent.ACTION_VIEW, u));
                } catch (Exception ignored) {
                    // no browser available for this scheme — ignore
                }
                return true;
            }

            @Override
            public void onPageStarted(WebView view, String url, Bitmap favicon) {
                progress.setVisibility(View.VISIBLE);
                status.setText("  loading " + hostOf(url) + " \u2026");
                status.setTextColor(Color.parseColor(C_MUTED));
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                progress.setVisibility(View.GONE);
                if (url.startsWith("http")) {
                    connectPanel.setVisibility(View.GONE);
                    status.setText("  \u25CF connected \u2014 " + hostOf(url));
                    status.setTextColor(Color.parseColor(C_UP));
                }
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request,
                                        WebResourceError error) {
                if (request == null || request.isForMainFrame()) {
                    progress.setVisibility(View.GONE);
                    status.setText("  \u25CB server unreachable");
                    status.setTextColor(Color.parseColor(C_DOWN));
                    showOffline(request == null ? "" : hostOf(request.getUrl().toString()));
                }
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progress.setProgress(newProgress);
            }
        });

        // ---------- restore / first run ----------
        if (savedInstanceState != null) {
            web.restoreState(savedInstanceState);
            connectPanel.setVisibility(View.GONE);
        } else {
            String saved = getSharedPreferences(PREFS, MODE_PRIVATE).getString(KEY_URL, "");
            if (saved != null && !saved.isEmpty()) {
                urlBox.setText(saved);
                connect(saved);
            }
        }
    }

    // ------------------------------------------------------------------
    private View buildConnectPanel() {
        LinearLayout panel = new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setBackgroundColor(Color.parseColor(C_CARD));
        panel.setPadding(dp(18), dp(18), dp(18), dp(18));

        TextView h = new TextView(this);
        h.setText("Connect to your AutoV Trader desk");
        h.setTextColor(Color.parseColor(C_TEXT));
        h.setTextSize(15f);
        h.setTypeface(Typeface.DEFAULT_BOLD);
        panel.addView(h);

        hint = new TextView(this);
        hint.setText("Start the server on your PC with  ./run.sh\n"
                + "then enter its address (same Wi-Fi):");
        hint.setTextColor(Color.parseColor(C_MUTED));
        hint.setTextSize(12.5f);
        hint.setPadding(0, dp(8), 0, dp(10));
        panel.addView(hint);

        urlBox = new EditText(this);
        urlBox.setHint("http://192.168.1.10:5000");
        urlBox.setHintTextColor(Color.parseColor("#4A5878"));
        urlBox.setTextColor(Color.parseColor(C_TEXT));
        urlBox.setTextSize(15f);
        urlBox.setSingleLine(true);
        urlBox.setBackgroundColor(Color.parseColor("#0E1526"));
        urlBox.setPadding(dp(12), dp(10), dp(12), dp(10));
        panel.addView(urlBox);

        LinearLayout row = new LinearLayout(this);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setPadding(0, dp(12), 0, 0);

        TextView connectBtn = new TextView(this);
        connectBtn.setText("  CONNECT  ");
        connectBtn.setTextColor(Color.WHITE);
        connectBtn.setTextSize(14f);
        connectBtn.setTypeface(Typeface.DEFAULT_BOLD);
        connectBtn.setBackgroundColor(Color.parseColor("#2567C0"));
        connectBtn.setPadding(dp(22), dp(12), dp(22), dp(12));
        connectBtn.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                String u = urlBox.getText().toString().trim();
                if (!u.isEmpty()) connect(u);
            }
        });
        row.addView(connectBtn);

        TextView demoBtn = new TextView(this);
        demoBtn.setText("  how it works  ");
        demoBtn.setTextColor(Color.parseColor(C_ACCENT));
        demoBtn.setTextSize(13f);
        demoBtn.setBackgroundColor(Color.parseColor("#1A2439"));
        demoBtn.setPadding(dp(16), dp(12), dp(16), dp(12));
        demoBtn.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View v) {
                hint.setText("1) On your PC:  ./run.sh\n"
                        + "2) Find your PC's LAN IP (e.g. 192.168.1.10)\n"
                        + "3) Keep phone & PC on the same Wi-Fi\n"
                        + "4) Enter http://<pc-ip>:5000 and CONNECT");
            }
        });
        LinearLayout.LayoutParams demoLp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.WRAP_CONTENT,
                LinearLayout.LayoutParams.WRAP_CONTENT);
        demoLp.leftMargin = dp(10);
        row.addView(demoBtn, demoLp);

        panel.addView(row);
        return panel;
    }

    private void showOffline(String host) {
        connectPanel.setVisibility(View.VISIBLE);
        hint.setText("Could not reach " + (host.isEmpty() ? "server" : host) + ".\n"
                + "Is ./run.sh running on your PC? Same Wi-Fi? Correct IP?");
        if (urlBox != null && urlBox.getText().length() > 0) {
            urlBox.setText(urlBox.getText());
        }
    }

    private void connect(String raw) {
        String url = raw.trim();
        if (!url.startsWith("http://") && !url.startsWith("https://")) {
            url = "http://" + url;
        }
        getSharedPreferences(PREFS, MODE_PRIVATE).edit().putString(KEY_URL, url).apply();
        hideKeyboard();
        status.setText("  connecting \u2026");
        status.setTextColor(Color.parseColor(C_MUTED));
        web.loadUrl(url);
    }

    private void hideKeyboard() {
        try {
            android.view.inputmethod.InputMethodManager imm =
                    (android.view.inputmethod.InputMethodManager)
                            getSystemService(INPUT_METHOD_SERVICE);
            if (imm != null && getCurrentFocus() != null) {
                imm.hideSoftInputFromWindow(getCurrentFocus().getWindowToken(), 0);
            }
        } catch (Exception ignored) {
        }
    }

    private static String hostOf(String url) {
        try {
            Uri u = Uri.parse(url);
            String h = u.getHost();
            return h == null ? "" : h;
        } catch (Exception e) {
            return "";
        }
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    // ---------- lifecycle ----------
    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        if (web != null) web.saveState(outState);
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK && web != null && web.canGoBack()) {
            web.goBack();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }
}
