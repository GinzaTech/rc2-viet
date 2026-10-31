package local.rc2.hud;

import java.lang.reflect.InvocationHandler;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

/** Observe touch delivery while forwarding every callback, original result and original exception. */
final class TouchDispatch implements InvocationHandler {
    interface Observer {
        void before(Object event); void after(Object event); void failed(RuntimeException error);
        default void focusChanged(boolean focused) { }
    }
    private volatile Observer observer;
    private Object target;
    TouchDispatch(Observer observer) { this.observer = observer; }
    <T> T wrap(Class<T> contract, T original) {
        if (!contract.isInterface() || original == null || target != null) throw new IllegalArgumentException("Callback contract");
        target = original;
        return contract.cast(Proxy.newProxyInstance(contract.getClassLoader(), new Class<?>[] { contract }, this));
    }
    void stop() { observer = null; }
    private void observe(Object event, boolean before) {
        Observer current = observer;
        if (current == null) return;
        try { if (before) current.before(event); else current.after(event); }
        catch (RuntimeException error) { report(current, error); }
    }
    private void report(Observer current, RuntimeException error) {
        try { current.failed(error); } catch (RuntimeException ignored) { observer = null; }
    }
    @Override public Object invoke(Object proxy, Method method, Object[] arguments) throws Throwable {
        boolean touch = method.getName().equals("dispatchTouchEvent") && arguments != null && arguments.length == 1;
        if (touch) observe(arguments[0], true);
        final Object result;
        try { result = method.invoke(target, arguments); }
        catch (InvocationTargetException failure) { throw failure.getCause(); }
        if (touch) observe(arguments[0], false);
        if (method.getName().equals("onWindowFocusChanged") && arguments != null && arguments.length == 1) {
            Observer current = observer;
            if (current != null) try { current.focusChanged((Boolean)arguments[0]); }
            catch (RuntimeException error) { report(current, error); }
        }
        return result;
    }
}
