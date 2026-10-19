"""Candidate-only host hooks. Each edit keeps the actual source method as fallback."""
from pathlib import Path
import json
import re

HOOK = "Llocal/rc2/hud/PortHooks;"


def ui_const_sites(text):
    """Only literal sites used in the reference's Russian/English UI pairs.

    Exact same words can also be preference/protocol keys. Never replace them
    globally; pair branches and explicit two-string translation calls instead.
    """
    sites={}
    pattern=re.compile(r'^    const-string(?:/jumbo)? ([vp]\d+), ("(?:[^"\\]|\\.)*")$',re.M)
    for body in re.finditer(r"(?ms)^\.method [^\n]+\n(.*?)^\.end method",text):
        constants=[]
        for match in pattern.finditer(body[1]):
            try:value=json.loads(match[2].replace("\\'","'"))
            except json.JSONDecodeError:continue
            constants.append((match,value))
        for i,(match,value) in enumerate(constants):
            if not re.search(r"[A-Za-z]",value) or re.search(r"[^\x00-\x7F]",value):continue
            paired=[(other,v) for other,v in constants[max(0,i-4):i]
                    if re.search(r"[\u0400-\u04FF]",v) and match.start()-other.end()<600]
            if not paired:continue
            same=any(other[1]==match[1] for other,v in paired)
            tail=body[1][match.end():match.end()+600]
            explicit=re.search(r"invoke-(?:static|direct) \{(?:[vp]\d+, ){1,3}"+re.escape(match[1])+r"\}, L[^;]+;->tr\((?:Landroid/content/Context;)?Ljava/lang/String;Ljava/lang/String;\)Ljava/lang/String;",tail)
            if same or explicit:sites[body.start(1)+match.start()]=value
    return sites


def method(text, signature, transform):
    pattern = re.compile(r"(?ms)^\.method ([^\n]* " + re.escape(signature) + r")\n.*?^\.end method")
    matches = list(pattern.finditer(text))
    if len(matches) != 1 or " native " in matches[0][1]:
        raise ValueError("Host method missing, native or ambiguous: " + signature)
    match = matches[0]
    replacement = transform(match[0])
    if replacement == match[0]:
        raise ValueError("Host transform made no change: " + signature)
    return text[:match.start()] + replacement + text[match.end():]


def parameters(signature, static):
    types = re.findall(r"\[*L[^;]+;|\[*[ZBSCIFJD]", signature[signature.index("(") + 1:signature.index(")")])
    return (0 if static else 1) + sum(2 if t in ("J", "D") else 1 for t in types)


def entry(text, code, scratch=0):
    if "rc2port_" in text:
        raise ValueError("Host already patched")
    regs = list(re.finditer(r"(?m)^    \.(registers|locals) (\d+)[ \t]*$", text))
    if len(regs) != 1:
        raise ValueError("Invalid register declaration")
    reg = regs[0]
    local_count = int(reg[2])
    if reg[1] == "registers":
        header = text.splitlines()[0]
        local_count -= parameters(header[header.rindex(" ") + 1:], " static " in header)
    if local_count < scratch:
        raise ValueError("Insufficient scratch locals")
    return text[:reg.end()] + "\n" + code + text[reg.end():]


def substitute(text, pattern, replace, count):
    result, actual = re.subn(pattern, replace, text, flags=re.M)
    if actual != count:
        raise ValueError(f"Host anchor count differs: expected {count}, found {actual}")
    return result


def void_call(name, registers, prototype):
    return f"    invoke-static {{{registers}}}, {HOOK}->{name}({prototype})V\n"


def map_engine(text, count):
    pattern = r"^    invoke-virtual \{([vp]\d+), ([vp]\d+)\}, Lcom/uav/mapkit/core/MapkitOptions\$Builder;->a\(I\)Lcom/uav/mapkit/core/MapkitOptions\$Builder;$"
    return substitute(text, pattern, lambda m:
                      f"    invoke-static {{{m[2]}}}, {HOOK}->mapEngine(I)I\n    move-result {m[2]}\n" + m[0], count)


def map_style(text, slots, next_style=False):
    pattern = re.compile(r'^    const-string(?:/jumbo)? ([vp]\d+), "https?://[^\n]+"$', re.M)
    matches = list(pattern.finditer(text))
    if len(matches) != len(slots):
        raise ValueError("Map style anchors differ")
    result = text
    for match, slot in reversed(list(zip(matches, slots))):
        name = "styleNext" if next_style else "styleCurrent"
        code = match[0] + f"\n    invoke-static {{{match[1]}}}, {HOOK}->{name}{slot}(Ljava/lang/String;)Ljava/lang/String;\n    move-result-object {match[1]}"
        result = result[:match.start()] + code + result[match.end():]
    return result


def return_hook(text, name, count=1):
    return substitute(text, r"^    return-object ([vp]\d+)$", lambda m:
                      f"    invoke-static {{{m[1]}}}, {HOOK}->{name}(Ljava/lang/String;)Ljava/lang/String;\n    move-result-object {m[1]}\n" + m[0], count)


def after_super(text, name):
    code = f"    invoke-static {{p0}}, {HOOK}->{name}(Landroid/app/Activity;)Z\n    move-result v0\n    if-eqz v0, :rc2port_startup_continue\n    return-void\n    :rc2port_startup_continue\n"
    try:
        entry(text, "", scratch=1)
    except ValueError:
        # This exact source method uses only p aliases. Growing registers cannot
        # change an absolute v alias of a parameter; reject any method that does.
        if re.search(r"\bv\d+\b", text):
            raise
        text=substitute(text,r"^    \.registers (\d+)$",lambda hit:f"    .registers {int(hit[1])+1}",1)
        entry(text, "", scratch=1)
    return substitute(text, r"^    invoke-super \{p0, p1\}, L[^;]+;->onCreate\(Landroid/os/Bundle;\)V$", lambda m:m[0]+"\n"+code, 1)


def map_builder(text, slots, next_style=False):
    pattern=re.compile(r"^    invoke-virtual \{([vp]\d+), ([vp]\d+)\}, Lcom/mapbox/mapboxsdk/maps/Style\$Builder;->g\(Ljava/lang/String;\)Lcom/mapbox/mapboxsdk/maps/Style\$Builder;\n(?:\n|    \.line \d+\n)*    move-result-object ([vp]\d+)$",re.M)
    matches=list(pattern.finditer(text))
    if len(matches)!=len(slots):raise ValueError("Map builder anchors differ")
    for match,slot in reversed(list(zip(matches,slots))):
        name="styleBuilderNext" if next_style else "styleBuilderCurrent"
        code=f"    invoke-static {{{match[1]}, {match[2]}}}, {HOOK}->{name}{slot}(Ljava/lang/Object;Ljava/lang/String;)Ljava/lang/Object;\n    move-result-object {match[3]}\n    check-cast {match[3]}, Lcom/mapbox/mapboxsdk/maps/Style$Builder;"
        text=text[:match.start()]+code+text[match.end():]
    return text


def feature_adjustments(text):
    changes = []
    if text.splitlines()[0].endswith("Lflysettings/S;"):
        text=method(text,"showSettings(Landroid/content/Context;)V",lambda m:
            ".method public static showSettings(Landroid/content/Context;)V\n    .registers 1\n"
            "    invoke-static {p0}, Llocal/rc2/hud/AdvancedSectionMenu;->showSelector(Landroid/content/Context;)V\n"
            "    return-void\n.end method")
        changes.append("advanced_and_gimbal_menu")
    if text.splitlines()[0].endswith("Lflyctl/F;"):
        def gps(m):
            # Stock SDK already receives this request. Never spray unverified raw
            # FC frames after the SDK call (the old LED issue dropped the link).
            marker = "    :cond_19\n"
            if marker not in m or m.count("Flyc;->sendGps(Z)V") != 1:
                raise ValueError("Reference GPS fallback differs")
            return m[:m.index(marker)] + marker + '    const-string v1, "FCGPSEnabled"\n' + \
                '    invoke-static {v1, p0}, Lflyctl/F;->keySetBool(Ljava/lang/String;Z)Z\n    move-result v0\n    return v0\n.end method'
        text = method(text, "writeGps(Z)Z", gps)
        changes.append("sdk_gps_without_udp_spray")
    if text.splitlines()[0].endswith("Lcleanview/CleanView;"):
        text = method(text, "installDoubleTapEnter(Landroid/app/Activity;Landroid/view/ViewGroup;)V", lambda m:
                      ".method public static installDoubleTapEnter(Landroid/app/Activity;Landroid/view/ViewGroup;)V\n    .registers 2\n    return-void\n.end method")
        changes.append("retain_single_rc2_double_tap")
    if text.splitlines()[0].endswith("Lflyctl/Q;"):
        pattern = r'(^    const-string ([vp]\d+), "qt_led"\n)([\s\S]*?^    move-result ([vp]\d+)$)'
        text = substitute(text, pattern, lambda m:m[0] + f"\n    const/4 {m[4]}, 0x0", 1)
        changes.append("led_only_in_home_menu")
    # Preserve the original RU selector. Vietnamese must not select the Russian
    # branch; audited labels in both branches are localized independently.
    if text.splitlines()[0].endswith("Lredfly/Power;"):
        for signature in ["sendNative()V","sendRc2Bridge()V"]:
            text=method(text,signature,lambda m:entry(m,void_call("requireGround","","")))
        changes.append("power_ground_gate_before_each_transport")
        def power_position(m):
            pair=(r'^    invoke-virtual \{p0, ([vp]\d+)\}, Lredfly/Power;->setX\(F\)V\n'
                  r'(?:\n|    \.line \d+\n)*'
                  r'    invoke-virtual \{p0, ([vp]\d+)\}, Lredfly/Power;->setY\(F\)V$')
            m=substitute(m,pair,lambda hit:void_call("placePower",f"p0, {hit[1]}, {hit[2]}","Landroid/view/View;FF").rstrip(),1)
            return substitute(m,r'^    return ([vp]\d+)$',
                lambda hit:void_call("finishPowerVisibility","p0","Landroid/view/View;")+hit[0],1)
        text=method(text,"onPreDraw()Z",power_position)
        changes.append("power_target_left_of_home_menu")
    return text, changes


def patch_host(text, type_name):
    changes = []

    def edit(signature, transform):
        nonlocal text
        text = method(text, signature, transform)
        changes.append(signature)

    if type_name.endswith("/SimpleEncryption;") or type_name == "Luav/midware/sdr/log/CommonLogEncryption;" or type_name == "Luav/core/log/crypto/LogCrypto;":
        for signature in re.findall(r"^\.method [^\n]* ((?:encrypt|decrypt|a)\((?:Ljava/lang/String;|\[B)\)(?:Ljava/lang/String;|\[B))$", text, re.M):
            code = f"    invoke-static {{}}, {HOOK}->encryptLogs()Z\n    move-result v0\n    if-nez v0, :rc2port_encrypt\n    return-object p1\n    :rc2port_encrypt\n"
            edit(signature, lambda m:entry(m,code,scratch=1))
    elif type_name == "Luav/services/areacode/impl/AreaCodeServiceImpl;":
        edit("I0()Ljava/lang/String;",lambda m:return_hook(m,"region",2))
    elif type_name == "Luav/infra/flymodel/api/business/areacode/AppAreaCodeEvent;":
        edit("a()Ljava/lang/String;",lambda m:return_hook(m,"region"))
    elif type_name == "Lc/d;":
        edit("f(Lcom/uav/mapkit/core/maps/UAVAppMap$MapType;)V",lambda m:map_builder(m,[2,1,0],True))
    elif type_name == "Lc/e;":
        edit("getMapboxStyle()Lcom/mapbox/mapboxsdk/maps/Style$Builder;",lambda m:map_builder(m,[0,2,1,0]))
    elif type_name == "Lcom/dji/mainpageui/device/DJIDeviceActivity;":
        edit("onCreate$$a61123df0714b7f7f704e87c4042aa7f$$AndroidAOP(Landroid/os/Bundle;)V",lambda m:after_super(m,"stopMainPage"))
        if " onNewIntent(Landroid/content/Intent;)V" in text:
            raise ValueError("Unexpected existing new-intent override")
        parent=re.search(r"^\.super (L[^\n]+)$",text,re.M)[1]
        text += f"\n.method protected onNewIntent(Landroid/content/Intent;)V\n    .registers 2\n    invoke-super {{p0, p1}}, {parent}->onNewIntent(Landroid/content/Intent;)V\n" + \
            void_call("noteIntent","p0, p1","Landroid/app/Activity;Landroid/content/Intent;") + "    return-void\n.end method\n"
        changes.append("onNewIntent(Landroid/content/Intent;)V")
    elif type_name == "Lcom/uav/component/application/activity/PureLaunchActivity;":
        edit("onCreate$$b6ecf4d3c52df87623e346399bce628b$$AndroidAOP(Landroid/os/Bundle;)V",lambda m:after_super(m,"stopSystemLaunch"))
    elif type_name == "Lcom/uav/component/fpv/widget/map/MapShell;":
        edit("onFinishInflate()V",lambda m:substitute(m,r"^    iput-object ([vp]\d+), p0, L[^;]+;->mLayerBtn:Landroid/widget/ImageView;$",lambda hit:hit[0]+"\n"+void_call("wireMap",hit[1],"Landroid/view/View;"),1))
    elif type_name == "Lcom/uav/component/fpv/widget/map/MapShellGate;":
        edit("requestMapView(Landroid/content/Context;Ljava/lang/Boolean;)Lcom/uav/mapkit/core/maps/UAVAppMapView;",lambda m:map_engine(m,1))
    elif type_name == "Lcom/uav/findmydrone/ui/FindMyDroneActivity;":
        edit("init(Landroid/os/Bundle;)V",lambda m:substitute(m,r"^    iput-object ([vp]\d+), p0, L[^;]+;->mLayerBtn:Landroid/widget/ImageButton;$",lambda hit:hit[0]+"\n"+void_call("wireFindMap",hit[1],"Landroid/view/View;"),1))
    elif type_name == "Lcom/uav/flightrecordui/map/FlightRecordMapActivity;":
        edit("requestMapView(Landroid/content/Context;Z)Lcom/uav/mapkit/core/maps/UAVAppMapView;",lambda m:map_engine(m,3))
        edit("onCreate$$7c074b293b63c92a3bc1ae01c0b28ce3$$AndroidAOP(Landroid/os/Bundle;)V",lambda m:substitute(m,r"^    invoke-virtual \{p0, [vp]\d+\}, L[^;]+;->setContentView\(I\)V$",lambda hit:hit[0]+"\n"+void_call("wireFlightRecord","p0","Ljava/lang/Object;"),1))
    elif type_name == "Luav/gs/manager/UAVMapManager;":
        edit("r(Landroid/app/Activity;Ljava/lang/Boolean;)Lcom/uav/mapkit/core/maps/UAVAppMapView;",lambda m:map_engine(m,3))
    elif type_name == "Lcom/uavapp/mapkit/osm/offlinemap/dataimpl/maptiler/MaptilerOfflineDownloadManager;":
        def offline(m):
            m=map_style(m,[0])
            return substitute(m,r"^    invoke-direct/range \{v1 \.\. v8\}, Lcom/mapbox/mapboxsdk/offline/OfflineTilePyramidRegionDefinition;-><init>[^\n]+$",lambda hit:
                              f"    invoke-static/range {{v3 .. v7}}, {HOOK}->estimate(Ljava/lang/Object;DD)V\n"+hit[0],1)
        edit("B0(Lcom/uavapp/mapkit/osm/offlinemap/dataimpl/maptiler/MaptilerOfflineDownloadManager;Lcom/uavapp/mapkit/osm/offlinemap/dataInterface/OfflineRegionInfo;Lio/reactivex/CompletableEmitter;)V",offline)
        edit("u0(Lcom/uavapp/mapkit/osm/offlinemap/dataimpl/maptiler/MaptilerOfflineDownloadManager;)Lcom/mapbox/mapboxsdk/offline/OfflineManager;",lambda m:substitute(m,r"^    return-object ([vp]\d+)$",lambda hit:void_call("tuneManager",hit[1],"Ljava/lang/Object;")+hit[0],1))
    elif type_name == "Lcom/uavapp/mapkit/osm/offlinemap/view/OverSeaOfflineMapDownloadContainerView;":
        edit("t()Lcom/uav/mapkit/core/maps/UAVAppMapView;",lambda m:substitute(m,r"^    invoke-virtual \{([vp]\d+)\}, Lcom/uav/mapkit/core/MapkitOptions\$Builder;->b\(\)Lcom/uav/mapkit/core/MapkitOptions;$",lambda hit:void_call("tuneBuilder",hit[1],"Ljava/lang/Object;")+hit[0],1))
    elif type_name == "Lcom/uavapp/mapkit/osm/offlinemap/view/RegionSelectPageView;":
        edit("<init>(Landroid/content/Context;Lcom/uavapp/mapkit/osm/offlinemap/viewmodel/OverSeaOfflineViewModel;Lcom/uav/mapkit/core/maps/UAVAppMapView;)V",lambda m:substitute(m,r"^    return-void$",lambda hit:void_call("wireOffline","p0","Landroid/view/View;")+hit[0],1))
        edit("subscribeCameraPosition$lambda$16(Lcom/uavapp/mapkit/osm/offlinemap/view/RegionSelectPageView;Lcom/uav/mapkit/core/maps/UAVAppMap;Lcom/uav/rx/csdk/Recall;)Lkotlin/Unit;",lambda m:substitute(m,r"^    invoke-direct \{p0\}, L[^;]+;->showIdleState\(\)V$",lambda hit:hit[0]+"\n"+void_call("offlineHint","p0, p1","Ljava/lang/Object;Ljava/lang/Object;"),1))
    elif type_name == "Lcom/uav/component/fpv/widget/setting/ui/control/rc/buttoncustomization/ResourceUtilKt;":
        code=f"    invoke-static {{p0}}, {HOOK}->buttonName(I)Ljava/lang/String;\n    move-result-object v0\n    if-eqz v0, :rc2port_button_name\n    return-object v0\n    :rc2port_button_name\n"
        edit("a(ILandroid/content/Context;)Ljava/lang/String;",lambda m:entry(m,code,scratch=1))
    elif type_name == "Lcom/uav/service/actioncompletable/ActionCompletableRouterKt;":
        signature=next(iter(re.findall(r"^\.method [^\n]* (h\([^\n]+)$",text,re.M)))
        code=f"    invoke-static {{p0, p3}}, {HOOK}->runButton(Ljava/lang/Object;Landroid/app/Activity;)Z\n    move-result v0\n    if-eqz v0, :rc2port_button_original\n    invoke-static {{}}, Lio/reactivex/Completable;->s()Lio/reactivex/Completable;\n    move-result-object v0\n    return-object v0\n    :rc2port_button_original\n"
        edit(signature,lambda m:entry(m,code,scratch=1))
    elif type_name == "Lcom/uav/component/fpv/widget/setting/ui/liveview/livestreaming/SettingLiveStreamingAdvanceViewModel;":
        edit("R()Ljava/util/ArrayList;",lambda m:substitute(m,r"^    return-object ([vp]\d+)$",lambda hit:void_call("appendLanTile",hit[1],"Ljava/util/ArrayList;")+hit[0],1))
    elif type_name == "Lcom/uav/component/fpv/widget/setting/ui/liveview/livestreaming/SettingLiveStreamingRecyclerViewAdapter;":
        signature="onBindViewHolder(Lcom/uav/component/fpv/widget/setting/ui/liveview/livestreaming/SettingLiveStreamingItemViewHolder;I)V"
        code=f"    invoke-static {{p0, p1, p2}}, {HOOK}->bindLanTile(Ljava/lang/Object;Ljava/lang/Object;I)Z\n    move-result v0\n    if-eqz v0, :rc2port_lan_original\n    return-void\n    :rc2port_lan_original\n"
        edit(signature,lambda m:entry(m,code,scratch=1))
    elif type_name == "Luav/infra/performance/monitor/AppPerformanceMonitor$startScreenRecordForidTimerTask$1;":
        code=f"    invoke-static {{}}, {HOOK}->recordStartupGuard()Z\n    move-result v0\n    if-nez v0, :rc2port_guard_original\n    sget-object v0, Lkotlin/Unit;->INSTANCE:Lkotlin/Unit;\n    return-object v0\n    :rc2port_guard_original\n"
        edit("invokeSuspend(Ljava/lang/Object;)Ljava/lang/Object;",lambda m:entry(m,code,scratch=1))
    elif type_name == "Luav/containers/fpv/takeofflandgohome/landandgohome/LandAndGoHomeVM;":
        edit("j()V",lambda m:entry(m,void_call("manualRth","","")))
    elif type_name == "Lcom/uavapp/fullscreennotificaion/submodel/returntohome/ReturnToHomeCountDownNotification;":
        code=f"    invoke-static {{p0, p1}}, {HOOK}->suppressNotification(Ljava/lang/Object;Landroid/content/Context;)Z\n    move-result v0\n    if-eqz v0, :rc2port_rth_original\n    invoke-virtual {{p0}}, {type_name}->onDestroy()V\n    return-void\n    :rc2port_rth_original\n"
        edit("c(Landroid/content/Context;Landroid/content/Intent;)V",lambda m:entry(m,code,scratch=1))
    elif type_name == "Luav/containers/fullscreen/submodel/returntohome/ReturnToHomeCountDownNotificationVM;":
        code=f"    invoke-static {{p1}}, {HOOK}->suppressRth(Ljava/lang/Object;)Z\n    move-result v0\n    if-eqz v0, :rc2port_rth_original\n    new-instance v0, Lkotlin/Pair;\n    sget-object v1, Ljava/lang/Boolean;->FALSE:Ljava/lang/Boolean;\n    invoke-direct {{v0, v1, p1}}, Lkotlin/Pair;-><init>(Ljava/lang/Object;Ljava/lang/Object;)V\n    return-object v0\n    :rc2port_rth_original\n"
        edit("z(Luav/containers/fullscreen/submodel/returntohome/ReturnToHomeCountDownNotificationVM;Luav/infra/flymodel/generated/api/flight/StartRTHCountdownInfo;)Lkotlin/Pair;",lambda m:entry(m,code,scratch=2))
    elif type_name == "Lcom/uav/component/fpv/widget/setting/ui/safety/SettingAltitudeLimitViewModel;":
        signature="N(Lcom/uav/flymodel/generated/api/common/IntMinMax;Ljava/lang/Boolean;)Lcom/uav/flymodel/generated/api/common/IntMinMax;"
        def altitude(m):
            if m.count("const-wide/16 v0, 0x78")!=1 or "IntMinMax;->getMin()J" not in m or "IntMinMax;->getMax()J" not in m:
                raise ValueError("Altitude UI clamp differs from the inspected source")
            # Reference returns the actual SDK-reported range. No firmware cap,
            # min/max SDK value or aircraft command is changed by this UI edit.
            return m.splitlines()[0]+"\n    .registers 2\n    return-object p0\n.end method"
        edit(signature,altitude)
    return text, changes


def prepare_hosts(source, destination):
    destination.mkdir()
    reports=[]
    for line in (source/"classes.tsv").read_text("utf-8").splitlines():
        type_name,filename,dex=line.split("\t")
        original=(source/filename).read_text("utf-8")
        patched,changes=patch_host(original,type_name)
        if changes:
            (destination/filename).write_text(patched,"utf-8")
            reports.append({"class":type_name,"dex":dex,"methods":changes})
    return reports
