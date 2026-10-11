import pytest

from scripts.feature_host_patch import entry, method, map_engine, map_style, feature_adjustments
from scripts.feature_host_patch import patch_host,map_builder
from scripts.feature_host_patch import ui_const_sites


def test_method_patch_is_exact_preserves_other_method_and_refuses_duplicate():
    sample = ".class public Lsample/A;\n.super Ljava/lang/Object;\n"
    body = ".method public a()V\n    .registers 2\n    return-void\n.end method\n"
    untouched = ".method public b()V\n    .registers 1\n    return-void\n.end method\n"
    result = method(sample + body + untouched, "a()V", lambda m: entry(m, "    invoke-static {}, Lsample/B;->onA()V\n"))
    assert untouched in result
    assert "Lsample/B;->onA()V" in result
    with pytest.raises(ValueError):
        method(sample + body + body, "a()V", lambda m: m)
    with pytest.raises(ValueError):
        method(sample + body, "missing()V", lambda m: m)


def test_map_hook_keeps_original_url_and_provider_as_fallback():
    sample = '    const-string v1, "https://example.test/style.json"\n'
    result = map_style(sample, [2], next_style=True)
    assert sample in result
    assert "{v1, v0}" not in result  # No clobbering another live local.
    assert "styleNext2(Ljava/lang/String;)Ljava/lang/String;" in result
    with pytest.raises(ValueError):
        map_style(sample, [0, 1], next_style=False)
    engine = "    invoke-virtual {v3, v1}, Lcom/uav/mapkit/core/MapkitOptions$Builder;->a(I)Lcom/uav/mapkit/core/MapkitOptions$Builder;\n"
    transformed = map_engine(engine, 1)
    assert transformed.endswith(engine)
    assert "mapEngine(I)I" in transformed


def test_gps_patch_removes_unverified_raw_udp_fallback_without_removing_sdk_write():
    sample = '.class public final Lflyctl/F;\n.super Ljava/lang/Object;\n'
    sample += '.method private static writeGps(Z)Z\n    .registers 4\n    const-string v0, "rc331"\n'
    sample += '    :cond_19\n    const-string v1, "FCGPSEnabled"\n'
    sample += '    invoke-static {v1, p0}, Lflyctl/F;->keySetBool(Ljava/lang/String;Z)Z\n    move-result v0\n'
    sample += '    invoke-static {p0}, Lcom/uav/component/fpv/widget/flightosd/gps/Flyc;->sendGps(Z)V\n'
    sample += '    return v0\n.end method\n'
    result, changes = feature_adjustments(sample)
    assert "FCGPSEnabled" in result and "keySetBool" in result
    assert "Flyc;->sendGps" not in result
    assert "sdk_gps_without_udp_spray" in changes


def test_entry_does_not_overwrite_parameter_when_no_scratch_local():
    with pytest.raises(ValueError):
        entry(".method public a()V\n    .registers 1\n    return-void\n.end method", "    move-result v0\n", scratch=1)


def test_map_json_builder_hook_keeps_uri_fallback_and_cast():
    text="    invoke-virtual {v0, v1}, Lcom/mapbox/mapboxsdk/maps/Style$Builder;->g(Ljava/lang/String;)Lcom/mapbox/mapboxsdk/maps/Style$Builder;\n\n    move-result-object v0\n"
    transformed=map_builder(text,[2])
    assert "{v0, v1}" in transformed and "styleBuilderCurrent2" in transformed
    assert "check-cast v0, Lcom/mapbox/mapboxsdk/maps/Style$Builder;" in transformed


def test_altitude_edit_returns_sdk_range_and_rejects_unknown_clamp():
    type_name="Lcom/uav/component/fpv/widget/setting/ui/safety/SettingAltitudeLimitViewModel;"
    text=f".class public {type_name}\n.super Ljava/lang/Object;\n"
    text+=".method public static synthetic N(Lcom/uav/flymodel/generated/api/common/IntMinMax;Ljava/lang/Boolean;)Lcom/uav/flymodel/generated/api/common/IntMinMax;\n    .registers 6\n"
    text+="    invoke-virtual {p0}, Lcom/uav/flymodel/generated/api/common/IntMinMax;->getMin()J\n"
    text+="    invoke-virtual {p0}, Lcom/uav/flymodel/generated/api/common/IntMinMax;->getMax()J\n    const-wide/16 v0, 0x78\n    return-object p0\n.end method\n"
    result,changes=patch_host(text,type_name)
    assert "return-object p0" in result and "0x78" not in result and len(changes)==1
    with pytest.raises(ValueError):patch_host(text.replace("0x78","0x7a"),type_name)


def test_ui_translation_does_not_alter_same_text_in_protocol_or_pref_method():
    text='.method public label()V\n    .registers 2\n    const-string v0, "\\u041b\\u0415\\u0414"\n    goto :done\n    :en\n    const-string v0, "LED"\n    :done\n    return-void\n.end method\n'
    text+='.method public key()V\n    .registers 1\n    const-string v0, "LED"\n    return-void\n.end method\n'
    sites=ui_const_sites(text)
    assert len(sites)==1 and list(sites.values())==['LED']


def test_actual_apk_resource_inventory_resolves_names_and_rejects_collisions():
    from scripts.build_feature_candidate import parse_resource_dump
    text="resource 0x7f0a0001 dji.go.v5:id/home\nresource 0x7f080004 drawable/tile\n"
    assert parse_resource_dump(text)=={('id','home'):0x7f0a0001,('drawable','tile'):0x7f080004}
    with pytest.raises(ValueError):parse_resource_dump(text+"resource 0x7f0a0002 dji.go.v5:id/home\n")


def test_context_translation_pair_is_localized_at_presentation_site():
    text='.method public text(Landroid/content/Context;)V\n    .registers 4\n'
    text+='    const-string v0, "\\u041f\\u0443\\u0441\\u043a"\n    const-string v1, "Start"\n'
    text+='    invoke-static {p0, v0, v1}, Lsample/Ui;->tr(Landroid/content/Context;Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;\n    return-void\n.end method\n'
    assert list(ui_const_sites(text).values())==['Start']


def test_reviewed_menu_preserves_diagnostic_tags_and_corrects_safety_text():
    import hashlib
    from scripts.build_feature_candidate import reviewed_menu_words
    words=reviewed_menu_words()
    def word(text):return words[hashlib.sha256(text.encode()).hexdigest()]
    assert word('paramedit-metadata')=='paramedit-metadata'
    assert word('.partial.dhp')=='.partial.dhp'
    assert word('Fan fault')=='Lỗi quạt'
    assert 'gimbal' in word('Do not move the aircraft or touch the gimbal.')


def test_power_guard_precedes_both_native_and_socket_transports():
    text='.class public final Lredfly/Power;\n.super Ljava/lang/Object;\n'
    for name in ['sendNative','sendRc2Bridge']:
        text+=f'.method private static {name}()V\n    .registers 1\n    invoke-static {{}}, Lsample/Transport;->send()V\n    return-void\n.end method\n'
    result,changes=feature_adjustments(text)
    assert result.count('PortHooks;->requireGround()V')==2
    assert 'power_ground_gate_before_each_transport' in changes
    for m in result.split('.method')[1:]:assert m.index('requireGround')<m.index('Transport;->send')
