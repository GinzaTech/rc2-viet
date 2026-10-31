package android.content;
public interface DialogInterface { void dismiss(); interface OnDismissListener {void onDismiss(DialogInterface dialog);} interface OnClickListener {void onClick(DialogInterface dialog,int which);} }
