"""Offline, real-Tk diagnostics for typing latency and idle button flicker.

This creates and closes only its own editor. It never constructs the desktop
application, discovers a device, opens USB, exports, or calls an install action.
"""
from __future__ import annotations

from pathlib import Path
import math
import time
import traceback
import tkinter as tk

from . import desktop_theme as theme
from .animation_editor import AnimationEditor


def _latencies(values):
    values = sorted(values)
    if not values:
        return {'p50': None, 'p95': None, 'max': None}

    def percentile(fraction):
        return round(values[max(0, math.ceil(len(values) * fraction) - 1)], 2)

    return {'p50': percentile(.5), 'p95': percentile(.95), 'max': round(values[-1], 2)}


def run_ui_check(work) -> dict:
    """Exercise the packaged editor's real rendering and recurring poll loop.

    Inputs travel through the same StringVar traces as typing. The renderer is
    observed, never replaced: successful paints must create a new Tk image on
    the real preview canvas. A short idle interval then checks that unchanged
    install/export buttons retain their appearance, including hover color.
    """
    work = Path(work)
    work.mkdir(parents=True, exist_ok=True)
    report = {
        'status': 'FAILED',
        'usb_opened': False,
        'device_modified': False,
        'install_callback_calls': 0,
        'render_pipeline': 'Pillow render_frame -> ImageTk.PhotoImage -> Tk Canvas',
        'latency_limit_ms': 180,
        'typing': {},
        'idle': {},
        'errors': [],
    }
    root = None
    view = None
    state = {'phase': 'warmup', 'finished': False, 'sequence': None}
    sequences = []
    button_draws = {}
    idle_renders = 0
    started = time.perf_counter()

    def now_ms():
        return (time.perf_counter() - started) * 1000

    def finish():
        if state['finished']:
            return
        state['finished'] = True
        report['duration_ms'] = round(now_ms(), 2)
        report['status'] = 'PASS' if not report['errors'] else 'FAILED'
        if root is not None:
            root.quit()

    try:
        root = theme.ctk.CTk()
        root.withdraw()

        def install_was_called(*_args, **_kwargs):
            report['install_callback_calls'] += 1
            report['errors'].append('An install callback was unexpectedly invoked.')
            return False

        view = AnimationEditor(root, work / 'editor', install_callback=install_was_called)
        view.window.title('RC2 · Animation typing and idle diagnostic')
        view.window.geometry('1240x760+20+20')

        def callback_error(exc_type, exc_value, exc_traceback):
            report['errors'].append(''.join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
            finish()

        root.report_callback_exception = callback_error
        original_render = view._render_preview

        def observe_render():
            nonlocal idle_renders
            previous_photo = view._preview_photo
            original_render()
            if state['phase'] == 'idle':
                idle_renders += 1
            sequence = state['sequence']
            if state['phase'] != 'typing' or sequence is None:
                return
            if view._preview_photo is previous_photo or view._preview_item is None:
                return
            # Flush the completed canvas image to Tk before recording the time.
            # This processes idle paint/layout work, without dispatching inputs.
            view.preview_canvas.update_idletasks()
            sequence['frames'].append({
                'text': view.project['layers'][view.selected]['text'],
                'at_ms': now_ms(),
                'canvas_item': int(view._preview_item),
            })

        view._render_preview = observe_render

        observed_buttons = {
            'export': view.export_button,
            'install_boot': view.install_boot_button,
            'install_shutdown': view.install_shutdown_button,
            'restore_boot': view.restore_boot_button,
            'restore_shutdown': view.restore_shutdown_button,
        }
        for name, button in observed_buttons.items():
            button_draws[name] = 0
            original_draw = button._draw

            def observe_draw(*args, _name=name, _draw=original_draw, **kwargs):
                if state['phase'] == 'idle':
                    button_draws[_name] += 1
                return _draw(*args, **kwargs)

            button._draw = observe_draw

        def input_value(sequence, text):
            sequence['inputs'].append({'text': text, 'at_ms': now_ms()})
            view.layer_vars['text'].set(text)

        def summarize_sequence(sequence):
            inputs, frames = sequence['inputs'], sequence['frames']
            first_paints = {}
            for frame in frames:
                first_paints.setdefault(frame['text'], frame)
            values = [first_paints[item['text']]['at_ms'] - item['at_ms']
                      for item in inputs if item['text'] in first_paints]
            final_input = inputs[-1]
            final_paint = first_paints.get(final_input['text'])
            intermediate = [frame for frame in frames
                            if frame['at_ms'] < final_input['at_ms']
                            and frame['text'] != sequence['text']]
            latency = _latencies(values)
            latency['last'] = round(final_paint['at_ms'] - final_input['at_ms'], 2) if final_paint else None
            summary = {
                'name': sequence['name'],
                'key_interval_ms': sequence['interval'],
                'input_events': len(inputs),
                'presented_frames': len(frames),
                'painted_inputs': len(values),
                'coalesced_inputs': len(inputs) - len(values),
                'intermediate_frames_before_last_key': len(intermediate),
                'expected_last_text': sequence['text'],
                'presented_last_text': frames[-1]['text'] if frames else None,
                'latency_ms': latency,
                'preview_resolution': list(view._preview_bounds[2:]),
                'canvas_image_items': len(set(frame['canvas_item'] for frame in frames)),
            }
            if not intermediate:
                report['errors'].append(f"{sequence['name']}: no preview appeared while typing continued.")
            if summary['presented_last_text'] != sequence['text'] or final_paint is None:
                report['errors'].append(f"{sequence['name']}: the last typed text was not presented.")
            if not values or latency['max'] > report['latency_limit_ms']:
                report['errors'].append(f"{sequence['name']}: typing latency exceeded {report['latency_limit_ms']} ms.")
            return summary, values

        def begin_sequence(name, text, interval, continuation):
            sequence = {'name': name, 'text': text, 'interval': interval, 'inputs': [], 'frames': []}
            sequences.append(sequence)
            state['phase'] = 'typing'
            state['sequence'] = sequence
            for index in range(len(text)):
                root.after(index * interval, input_value, sequence, text[:index + 1])
            root.after((len(text) - 1) * interval + 300, continuation)

        def begin_fast_typing():
            begin_sequence('fast', 'DJI Modder12', 20, finish_typing)

        def finish_typing():
            state['phase'] = 'settling'
            state['sequence'] = None
            summaries, all_values = [], []
            for sequence in sequences:
                summary, values = summarize_sequence(sequence)
                summaries.append(summary)
                all_values.extend(values)
            aggregate = _latencies(all_values)
            aggregate['last'] = summaries[-1]['latency_ms']['last']
            report['typing'] = {
                'input_events': sum(item['input_events'] for item in summaries),
                'presented_frames': sum(item['presented_frames'] for item in summaries),
                'intermediate_frames_before_last_key': sum(item['intermediate_frames_before_last_key'] for item in summaries),
                'latency_ms': aggregate,
                'sequences': summaries,
            }
            view.set_device_panel(True)
            root.after(300, start_idle)

        def start_idle():
            if view.restore_boot_button.cget('state') != 'normal':
                report['errors'].append('The local fake callback did not enable the restore control.')
            # Exercise its normal hover binding; never invoke the action.
            view.restore_boot_button._canvas.event_generate('<Enter>')
            root.after_idle(measure_idle)

        def measure_idle():
            state['phase'] = 'idle'
            state['idle_start'] = now_ms()
            state['hover_before'] = view.restore_boot_button._text_label.cget('bg')
            state['hover_expected'] = view.restore_boot_button._apply_appearance_mode(
                view.restore_boot_button.cget('hover_color'))
            root.after(450, finish_idle)

        def finish_idle():
            state['phase'] = 'done'
            hover_after = view.restore_boot_button._text_label.cget('bg')
            preserved = state['hover_before'] == hover_after == state['hover_expected']
            report['idle'] = {
                'duration_ms': round(now_ms() - state['idle_start'], 2),
                'preview_renders': idle_renders,
                'button_redraws': dict(button_draws),
                'button_redraws_total': sum(button_draws.values()),
                'hover_expected': state['hover_expected'],
                'hover_before': state['hover_before'],
                'hover_after': hover_after,
                'hover_preserved': preserved,
            }
            if idle_renders:
                report['errors'].append('The idle preview rendered again without an edit or playback.')
            if any(button_draws.values()):
                report['errors'].append('An unchanged export/install/restore button redrew while idle.')
            if not preserved:
                report['errors'].append('The enabled restore button lost its hover color while idle.')
            finish()

        def timeout():
            report['errors'].append('The UI diagnostic exceeded its 12 second deadline.')
            finish()

        root.after(300, lambda: begin_sequence('normal', 'GinzaPro', 80, begin_fast_typing))
        root.after(12000, timeout)
        root.mainloop()
    except Exception as error:
        report['errors'].append(f'{type(error).__name__}: {error}')
        report['status'] = 'FAILED'
    finally:
        if view is not None and not view._destroyed:
            try:
                if not view.close():
                    report['errors'].append('The owned editor did not close cleanly.')
                    view._destroy()
            except Exception as error:
                report['errors'].append(f'Editor cleanup: {type(error).__name__}: {error}')
        if root is not None:
            try:
                for token in root.tk.splitlist(root.tk.call('after', 'info')):
                    root.after_cancel(token)
                root.destroy()
            except tk.TclError:
                pass
        if not state['finished'] or report['errors']:
            report['status'] = 'FAILED'
        report['duration_ms'] = round(now_ms(), 2)
    return report
