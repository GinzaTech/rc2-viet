package local.rc2.home;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ComponentName;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.UserManager;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

/** Foreground Home bridge; no root, networking, flight or account access. */
public final class HomeActivity extends Activity implements HomeForwarder.Host {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView message;
    private HomeForwarder forwarder;
    private final Runnable launch = new Runnable() {
        @Override public void run() { forwarder.retry(); }
    };

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        forwarder = new HomeForwarder(this);
        forwarder.start();
    }

    @Override public void showFallback(boolean locked) {
        if (message != null) {
            message.setText(locked ? "Android chưa mở khóa dữ liệu. Mở khóa tay rồi nhấn Mở RC Launcher."
                    : "Chưa mở được launcher. Kiểm tra RC Launcher đã được cài.");
            return;
        }
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setGravity(Gravity.CENTER);
        int padding = (int) (24 * getResources().getDisplayMetrics().density);
        layout.setPadding(padding, padding, padding, padding);
        message = new TextView(this);
        message.setTextSize(20);
        message.setGravity(Gravity.CENTER);
        message.setText(locked ? "Android chưa mở khóa dữ liệu. Mở khóa tay rồi nhấn Mở RC Launcher."
                : "Chưa mở được launcher. Kiểm tra RC Launcher đã được cài.");
        layout.addView(message);
        Button retry = new Button(this);
        retry.setText("Mở RC Launcher");
        retry.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View view) {
                forwarder.start();
            }
        });
        layout.addView(retry);
        Button fly = new Button(this);
        fly.setText("Mở DJI Fly");
        fly.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View view) {
                open("dji.go.v5", "com.dji.component.application.activity.DJIPureLaunchActivity");
            }
        });
        layout.addView(fly);
        setContentView(layout);
    }

    @Override public void onResume() {
        super.onResume();
        if (!isFinishing()) forwarder.start();
    }

    @Override protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        if (!isFinishing()) forwarder.start();
    }

    @Override public boolean isUserUnlocked() {
        UserManager users = getSystemService(UserManager.class);
        return users != null && users.isUserUnlocked();
    }

    @Override public boolean openLauncher() {
        return LauncherDestination.open(new LauncherDestination.Starter() {
            @Override public boolean open(String packageName,String className) {
                return HomeActivity.this.open(packageName,className);
            }
        });
    }

    @Override public void scheduleRetry() {
        handler.removeCallbacks(launch);
        handler.postDelayed(launch, 500);
    }

    @Override public void cancelRetry() { handler.removeCallbacks(launch); }

    @Override public void complete() {
        finish();
        overridePendingTransition(0, 0);
    }

    private boolean open(String packageName, String className) {
        try {
            Intent intent = new Intent(Intent.ACTION_MAIN);
            intent.setComponent(new ComponentName(packageName, className));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED
                    | Intent.FLAG_ACTIVITY_NO_ANIMATION);
            startActivity(intent);
            return true;
        } catch (ActivityNotFoundException | SecurityException exception) {
            return false;
        }
    }

    @Override public void onPause() {
        forwarder.pause();
        super.onPause();
    }

    @Override public void onDestroy() {
        handler.removeCallbacks(launch);
        super.onDestroy();
    }
}
