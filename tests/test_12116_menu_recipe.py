"""Portable guards for the 1.21.16 recipe; no APKs or Android code executed."""
import pytest

from scripts.build_12116_menu_recipe import (
    assert_unique_methods,
    normalize_smali_encoding,
    preserve_method_metadata,
    remap_resource_literals,
)


def test_resource_rebinding_preserves_quoted_and_comment_tokens():
    source = '    const v0, 0x7f010001\n    const-string v1, "0x7f010001 \\\" quoted" # 0x7f010001\n'
    actual, refs = remap_resource_literals(source, {0x7f010001: 0x7f020034})
    assert refs == [{"line": 1, "old": "0x7f010001", "new": "0x7f020034"}]
    assert actual.splitlines()[0] == '    const v0, 0x7f020034'
    assert actual.splitlines()[1] == source.splitlines()[1]


def test_unknown_resource_binding_is_refused():
    with pytest.raises(ValueError, match='Unbound resource'):
        remap_resource_literals('    const v0, 0x7f010001\n', {})


def test_integer_max_is_not_treated_as_resource():
    source = '    const v0, 0x7fffffff\n'
    assert remap_resource_literals(source, {}) == (source, [])


def test_string_index_width_and_position_label_rename_preserve_semantics():
    source = '.method public a()V\n    if-eqz v0, :cond_3\n    const-string v1, "same"\n    :cond_3\n    return-void\n.end method\n'
    assembled = source.replace('const-string ', 'const-string/jumbo ').replace(':cond_3', ':cond_4')
    assert normalize_smali_encoding(source) == normalize_smali_encoding(assembled)


def test_retargeted_branch_is_refused():
    source = '.method public a()V\n    if-eqz v0, :cond_1\n    :cond_1\n    const/4 v0, 0x0\n    :cond_2\n    return-void\n.end method\n'
    changed = source.replace('if-eqz v0, :cond_1', 'if-eqz v0, :cond_2')
    assert normalize_smali_encoding(source) != normalize_smali_encoding(changed)


@pytest.mark.parametrize('old,new', [('"same"', '"changed"'), ('v0', 'v1'), ('return-void', 'throw v0')])
def test_literal_register_and_opcode_changes_remain_visible(old, new):
    source = '.method public a()V\n    const-string v0, "same"\n    return-void\n.end method\n'
    assert normalize_smali_encoding(source) != normalize_smali_encoding(source.replace(old, new))


def test_quoted_label_is_preserved_while_real_label_moves():
    source = '.method public a()V\n    const-string v0, ":cond_1"\n    goto :cond_1\n    :cond_1\n    return-void\n.end method\n'
    changed = source.replace('goto :cond_1', 'goto :cond_5').replace('    :cond_1\n', '    :cond_5\n')
    assert normalize_smali_encoding(source) == normalize_smali_encoding(changed)
    assert '":cond_1"' in normalize_smali_encoding(changed)


def test_label_bindings_are_local_to_each_method():
    body = '.method public {}()V\n    goto :cond_1\n    :cond_1\n    return-void\n.end method\n'
    assert normalize_smali_encoding(body.format('a') + body.format('b')).count(':label_0') == 4


def test_duplicate_label_within_one_method_is_refused():
    source = '.method public a()V\n    :cond_1\n    const/4 v0, 0x0\n    :cond_1\n    return-void\n.end method\n'
    with pytest.raises(ValueError, match='Duplicate smali label'):
        normalize_smali_encoding(source)


def test_packed_switch_entries_are_references_and_retargeting_stays_visible():
    source = ('.method public a()V\n    packed-switch v0, :pswitch_data_8\n'
              '    :pswitch_1\n    const/4 v1, 0x1\n    return-void\n'
              '    :pswitch_2\n    const/4 v1, 0x2\n    return-void\n'
              '    :pswitch_data_8\n    .packed-switch 0x0\n'
              '        :pswitch_1\n        :pswitch_2\n    .end packed-switch\n.end method\n')
    moved = source.replace(':pswitch_1', ':pswitch_3').replace(':pswitch_2', ':pswitch_4').replace(':pswitch_data_8', ':pswitch_data_a')
    assert normalize_smali_encoding(source) == normalize_smali_encoding(moved)
    retargeted = source.replace('        :pswitch_1\n        :pswitch_2', '        :pswitch_2\n        :pswitch_1')
    assert normalize_smali_encoding(source) != normalize_smali_encoding(retargeted)


def test_assembler_blank_line_formatting_does_not_change_code():
    before = '.method public a()V\n    .registers 1\n    const/4 v0, 0x1\n\n\n    return-void\n.end method\n'
    after = '.method public a()V\n    .registers 1\n\n    const/4 v0, 0x1\n\n    return-void\n.end method\n'
    assert normalize_smali_encoding(before) == normalize_smali_encoding(after)


def test_windows_smali_file_line_endings_are_only_formatting():
    source = '.method public a()V\n    .registers 1\n    return-void\n.end method\n'
    assert normalize_smali_encoding(source) == normalize_smali_encoding(source.replace('\n', '\r\n'))


def test_debug_line_moving_across_same_instruction_label_is_not_code_change():
    before = '.method public a()V\n    goto :cond_1\n    :cond_1\n    .line 12\n    return-void\n.end method\n'
    after = before.replace('    :cond_1\n    .line 12', '    .line 12\n    :cond_1')
    assert normalize_smali_encoding(before) == normalize_smali_encoding(after)


ANNOTATED = ('.method public a(Ljava/lang/String;)V\n    .registers 2\n'
             '    .param p1    # Ljava/lang/String;\n'
             '        .annotation build Lexample/NotNull;\n        .end annotation\n    .end param\n'
             '    .annotation system Ldalvik/annotation/Throws;\n'
             '        value = {Ljava/io/IOException;}\n    .end annotation\n'
             '    return-void\n.end method\n')


def test_metadata_relocation_keeps_parameter_and_method_annotations_exact():
    hook = '    invoke-static {}, Lexample/Hook;->run()V\n'
    inserted = ANNOTATED.replace('    .registers 2\n', '    .registers 2\n' + hook)
    expected = ANNOTATED.replace('    return-void\n', hook + '    return-void\n')
    assert preserve_method_metadata(ANNOTATED, inserted, ['a(Ljava/lang/String;)V']) == expected


@pytest.mark.parametrize('old,new', [('value = {Ljava/io/IOException;}', 'value = {Ljava/lang/Error;}'),
                                    ('.annotation build', '.annotation runtime'),
                                    ('.param p1 ', '.param p0 ')])
def test_changed_metadata_payload_visibility_or_parameter_target_is_refused(old, new):
    changed = ANNOTATED.replace(old, new)
    with pytest.raises(ValueError, match='metadata prefix changed'):
        preserve_method_metadata(ANNOTATED, changed, ['a(Ljava/lang/String;)V'])


def test_duplicate_method_signature_is_refused_before_assembly():
    assert_unique_methods(ANNOTATED)
    with pytest.raises(ValueError, match='Duplicate method'):
        assert_unique_methods(ANNOTATED + ANNOTATED)


def test_opcode_comparator_does_not_ignore_inserted_nops():
    source = '.method public a()V\n    .registers 1\n    return-void\n.end method\n'
    changed = source.replace('    return-void', '    nop\n    return-void')
    assert normalize_smali_encoding(source) != normalize_smali_encoding(changed)
