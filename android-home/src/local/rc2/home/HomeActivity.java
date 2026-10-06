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
public final class HomeActivity extends Activity {
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView message;
    private int attempts;
    private final Runnable launch = new Runnable() {
        @Override public void run() { openWhenReady(); }
    };

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setGravity(Gravity.CENTER);
        int padding = (int) (24 * getResources().getDisplayMetrics().density);
        layout.setPadding(padding, padding, padding, padding);
        message = new TextView(this);
        message.setTextSize(20);
        message.setGravity(Gravity.CENTER);
        message.setText("Đang chờ Android sẵn sàng để mở Lawnchair…");
        layout.addView(message);
        Button retry = new Button(this);
        retry.setText("Mở Lawnchair");
        retry.setOnClickListener(new View.OnClickListener() {
            @Override public void onClick(View view) {
                attempts = 0;
                handler.removeCallbacks(launch);
                openWhenReady();
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
        attempts = 0;
        handler.removeCallbacks(launch);
        handler.post(launch);
    }

    private void openWhenReady() {
        UserManager users = getSystemService(UserManager.class);
        if (users == null || !users.isUserUnlocked()) {
            if (++attempts <= 120) handler.postDelayed(launch, 500);
            else message.setText("Android chưa mở khóa dữ liệu. Mở khóa tay rồi nhấn Mở Lawnchair.");
            return;
        }
        if (!open("app.lawnchair", "app.lawnchair.LawnchairLauncher")) {
            if (++attempts <= 40) handler.postDelayed(launch, 500);
            else message.setText("Chưa mở được Lawnchair. Kiểm tra Lawnchair đã được cài.");
        }
    }

    private boolean open(String packageName, String className) {
        try {
            Intent intent = new Intent(Intent.ACTION_MAIN);
            intent.setComponent(new ComponentName(packageName, className));
            intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);
            startActivity(intent);
            return true;
        } catch (ActivityNotFoundException | SecurityException exception) {
            return false;
        }
    }

    @Override public void onPause() {
        handler.removeCallbacks(launch);
        super.onPause();
    }

    @Override public void onDestroy() {
        handler.removeCallbacks(launch);
        super.onDestroy();
    }
}
