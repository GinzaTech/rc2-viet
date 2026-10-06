"""Explicit wording requested by the controller owner on 2026-10-06."""
import re

REPLACEMENTS=(
    (r'Tùy chọn bay vòng tránh','Tùy chọn tránh khi bay'),
    (r'Tinh chỉnh độ nhạy và đường cong đáp ứng của máy bay và gimbal',
     'Tinh chỉnh độ nhạy và đường cong của máy bay và gimbal'),
    (r'Điều chỉnh độ nhạy và đường cong đáp ứng','điều chỉnh độ nhạy và đường cong'),
    (r'Đường cong đáp ứng cần điều khiển','đường cong cần điều khiển'),
    (r'Hiển thị bản đồ ra\s*đa','Hiển thị bản đồ radar'),
    (r'quay về điểm đã đặt','quay về vị trí ban đầu'),
    (r'La bàn bình thường','La bàn hoạt động bình thường'),
    (r'Hệ mét\s*\(\s*km\s*\)','Hệ kilomet(Km)'),
    (r'quay mượt','quay phim'),
)

def apply_user_wording(text):
    for pattern,target in REPLACEMENTS:
        text=re.sub(pattern,lambda match:target,text,flags=re.I)
    return text
