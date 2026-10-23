"""Bounded synthetic smali verifies decrypt removal without changing other rows."""
import re

import pytest

from scripts.feature_host_patch import remove_record_decryption, feature_adjustments, parameters


UNRELATED = '.method public static untouched()V\n    .registers 1\n    const-string v0, "stock encryption and recording"\n    return-void\n.end method\n'


def settings_fixture():
    """Retain the inspected row boundaries, registers, listener and branch shape."""
    return '''.class public final Lflysettings/S;
.super Ljava/lang/Object;
.method private static tabAdvanced(Landroid/content/Context;)Lflysettings/Columns;
    .registers 7
    .line 859
    const-string v4, "Encrypted file logs"
    invoke-static {p0, v4, v5, v3}, Lflysettings/Ui;->switchRow(Landroid/content/Context;Ljava/lang/String;Ljava/lang/String;Landroid/widget/Switch;)Landroid/widget/LinearLayout;
    move-result-object v3
    invoke-virtual {v2, v3}, Landroid/widget/LinearLayout;->addView(Landroid/view/View;)V
    .line 864
    invoke-static {p0}, Lflysettings/Ui;->divider(Landroid/content/Context;)Landroid/view/View;
    move-result-object v3
    invoke-virtual {v2, v3}, Landroid/widget/LinearLayout;->addView(Landroid/view/View;)V
    .line 867
    invoke-static {p0}, Lflysettings/Ui;->switchView(Landroid/content/Context;)Landroid/widget/Switch;
    move-result-object v3
    .line 868
    invoke-static {}, Lflysettings/S;->frDecrypt()Z
    move-result v4
    invoke-virtual {v3, v4}, Landroid/widget/Switch;->setChecked(Z)V
    .line 869
    new-instance v4, Lflysettings/S$14;
    invoke-direct {v4}, Lflysettings/S$14;-><init>()V
    invoke-virtual {v3, v4}, Landroid/widget/Switch;->setOnCheckedChangeListener(Landroid/widget/CompoundButton$OnCheckedChangeListener;)V
    .line 873
    sget-boolean v4, Lflysettings/S;->RU:Z
    if-eqz v4, :cond_70
    const-string v4, "Расшифровка полётных логов"
    goto :goto_72
    :cond_70
    const-string v4, "Giải mã bản ghi chuyến bay"
    .line 874
    :goto_72
    sget-boolean v5, Lflysettings/S;->RU:Z
    if-eqz v5, :cond_79
    const-string v5, "Автоматически"
    goto :goto_7b
    :cond_79
    const-string v5, "A decrypted copy is created automatically"
    :goto_7b
    invoke-static {p0, v4, v5, v3}, Lflysettings/Ui;->switchRow(Landroid/content/Context;Ljava/lang/String;Ljava/lang/String;Landroid/widget/Switch;)Landroid/widget/LinearLayout;
    move-result-object v3
    invoke-virtual {v2, v3}, Landroid/widget/LinearLayout;->addView(Landroid/view/View;)V
    .line 877
    invoke-static {p0}, Lflysettings/Ui;->divider(Landroid/content/Context;)Landroid/view/View;
    move-result-object v3
    invoke-virtual {v2, v3}, Landroid/widget/LinearLayout;->addView(Landroid/view/View;)V
    .line 880
    const-string v4, "Start Fly automatically"
    invoke-static {p0, v4, v5, v3}, Lflysettings/Ui;->switchRow(Landroid/content/Context;Ljava/lang/String;Ljava/lang/String;Landroid/widget/Switch;)Landroid/widget/LinearLayout;
    return-object v1
.end method
.method public static frDecrypt()Z
    .registers 2
    const-string v0, "fr_decrypt"
    invoke-static {}, Lfixture/SideEffect;->run()V
    const/4 v0, 0x1
    return v0
.end method
.method public static setFrDecrypt(Z)V
    .registers 4
    const-string v0, "frtool.X"
    invoke-static {}, Lfixture/SideEffect;->run()V
    return-void
.end method
''' + UNRELATED


def settings_with_selector_fixture():
    return settings_fixture() + '''.method public static showSettings(Landroid/content/Context;)V
    .registers 3
    invoke-static {p0}, Lflysettings/S;->tabBasic(Landroid/content/Context;)Lflysettings/Columns;
    return-void
.end method
'''


def body(text, signature):
    match = re.search(r'(?ms)^\.method [^\n]* ' + re.escape(signature) + r'\n(.*?)^\.end method', text)
    assert match is not None
    return match.group(1)


def module_fixture(name):
    signatures = {
        'X': ['arm()V', 'ask(Landroid/app/Activity;)V', 'attach(Landroid/app/Activity;)V',
              'onSettingOn(Landroid/content/Context;)V', 'scan(Landroid/content/Context;)V',
              'startPoller(Landroid/content/Context;)V', 'enabled(Landroid/content/Context;)Z'],
        'Decryptor': ['decryptAllAsync(Landroid/content/Context;Lfrtool/Decryptor$Done;)V',
                      'decryptFilesAsync(Landroid/content/Context;Ljava/util/List;Lfrtool/Decryptor$Done;)V'],
    }[name]
    text = f'.class public final Lfrtool/{name};\n.super Ljava/lang/Object;\n'
    for signature in signatures:
        text += f'.method public static {signature}\n    .registers 5\n'
        text += '    invoke-static {}, Lfixture/SideEffect;->run()V\n'
        text += '    const/4 v0, 0x1\n    return v0\n' if signature.endswith('Z') else '    return-void\n'
        text += '.end method\n'
    return text + UNRELATED, signatures


def test_decrypt_row_removed_with_neighbor_rows_and_methods_preserved():
    source = settings_fixture()
    result = remove_record_decryption(source)
    tab = body(result, 'tabAdvanced(Landroid/content/Context;)Lflysettings/Columns;')
    assert 'Encrypted file logs' in tab and 'Start Fly automatically' in tab
    assert tab.count('->switchRow(') == 2
    assert 'Giải mã' not in tab and 'decrypted' not in tab
    assert 'frDecrypt()Z' not in tab and 'Lflysettings/S$14;' not in tab
    assert not any(label in tab for label in (':cond_70', ':goto_72', ':cond_79', ':goto_7b'))
    assert UNRELATED in result
    assert body(result, 'frDecrypt()Z').strip() == '.registers 1\n    const/4 v0, 0x0\n    return v0'
    assert body(result, 'setFrDecrypt(Z)V').strip() == '.registers 1\n    return-void'


@pytest.mark.parametrize('name', ['X', 'Decryptor'])
def test_all_scheduled_and_manual_decrypt_entrypoints_are_inert(name):
    source, signatures = module_fixture(name)
    result = remove_record_decryption(source)
    assert UNRELATED in result and 'SideEffect' not in result
    for signature in signatures:
        expected = ('.registers 1\n    const/4 v0, 0x0\n    return v0' if signature.endswith('Z') else
                    f'.registers {max(1, parameters(signature, True))}\n    return-void')
        assert body(result, signature).strip() == expected


@pytest.mark.parametrize('change', [
    lambda s: s.replace('.line 864', '.line 863'),
    lambda s: s.replace('.line 877', '.line 878'),
    lambda s: s.replace('Lflysettings/S;->frDecrypt()Z', 'Lflysettings/S;->other()Z'),
    lambda s: s.replace('invoke-static {}, Lflysettings/S;->frDecrypt()Z',
                        'invoke-static {}, Lflysettings/S;->frDecrypt()Z\n    invoke-static {}, Lflysettings/S;->frDecrypt()Z'),
    lambda s: s.replace('invoke-direct {v4}, Lflysettings/S$14;-><init>()V', 'nop'),
    lambda s: s.replace('    .line 874\n', '    invoke-static {}, Lfixture/Ui;->switchRow()V\n    .line 874\n'),
])
def test_unknown_or_ambiguous_menu_shape_fails_closed(change):
    with pytest.raises(ValueError, match='menu row differs'):
        remove_record_decryption(change(settings_fixture()))


@pytest.mark.parametrize('name', ['X', 'Decryptor'])
def test_missing_or_native_decrypt_method_fails_closed(name):
    source, signatures = module_fixture(name)
    with pytest.raises(ValueError, match='missing, native or ambiguous'):
        remove_record_decryption(source.replace(signatures[0], 'changed()V', 1))
    with pytest.raises(ValueError, match='missing, native or ambiguous'):
        remove_record_decryption(source.replace('.method public static ' + signatures[0],
                                                '.method public static native ' + signatures[0], 1))


def test_feature_builder_applies_removal_before_selected_menu_redirect():
    result, changes = feature_adjustments(settings_with_selector_fixture())
    assert 'flight_record_decryption_removed' in changes
    assert 'advanced_and_gimbal_menu' in changes
    assert 'AdvancedSectionMenu;->showSelector' in result
    assert 'Lflysettings/S;->tabBasic' not in result
    assert UNRELATED in result


def test_unrelated_feature_class_is_byte_identical():
    source = '.class public final Lflyctl/Other;\n.super Ljava/lang/Object;\n' + UNRELATED
    assert remove_record_decryption(source) == source
