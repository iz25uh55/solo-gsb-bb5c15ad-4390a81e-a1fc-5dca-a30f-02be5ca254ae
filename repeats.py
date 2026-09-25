"""反复段解析、展开与排练时间轴核心逻辑。

输入格式（逐行）：
    [|:]小节编号[:|xN][拍数[@BPM]]
- 编号前的 |:     表示反复起点
- 编号后的 :|xN   表示反复终点，N 为重复次数（2~9）
- 末尾的 [拍数]   指定该小节拍数（正整数，默认 4）
- 末尾的 [拍数@BPM] 同时指定拍数与速度（BPM 为正整数，初始速度 120）
- 反复段允许嵌套

时间轴规则：小节按实际演奏顺序依次出现，带速度标记的小节每次出现时都先切换
速度，再按 拍数×60/BPM 秒累计时长；未标速度则沿用上一演奏小节的速度。
"""

import re

# 展开小节数上限
MAX_MEASURES = 5000

# 初始速度（BPM）与默认每小节拍数
DEFAULT_BPM = 120
DEFAULT_BEATS = 4

# 行格式：
#   可选 |: 前缀 + 编号 + 可选 :|xN 后缀（N 为 2~9）+ 可选 [拍数@BPM] 后缀
LINE_RE = re.compile(
    r"^\s*"
    r"(?:(\|:)\s*)?"
    r"(\d+)"
    r"(?:\s*(:\|)\s*[xX]\s*([2-9]))?"
    r"(?:\s*\[\s*(\d+)\s*(?:@\s*(\d+)\s*)?\])?"
    r"\s*$"
)

FORMAT_HINT = (
    "格式错误：应为 [|:]编号[:|xN][拍数[@BPM]]，N 为 2~9，"
    "拍数与 BPM 为正整数，例如 “|:12:|x3[4@100]”"
)
BEATS_HINT = "拍数必须为正整数"
BPM_HINT = "BPM 必须为正整数"


def _timing_error(lineno, message):
    """生成定位到源行的时间标记校验错误。"""
    return {"line": lineno, "message": message}


def parse(text):
    """解析输入文本，构建嵌套树并校验。

    返回 (root, errors)：
    - root  为 {"type": "group", "count": 1, "children": [...]} 形式的根节点；
      小节节点为
      {"type": "measure", "num": 编号, "line": 行号,
       "beats": 拍数, "bpm": BPM 或 None（未标速度时沿用上一速度）}。
    - errors 为 [{"line": 行号, "message": 错误描述}, ...]，按行号排序。
    """
    errors = []
    root = {"type": "group", "count": 1, "children": [], "line": None}
    stack = [root]  # 当前嵌套层级的分组栈，栈底为根
    seen = {}  # 小节编号 -> 首次出现的行号

    for lineno, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue  # 跳过空行

        m = LINE_RE.match(raw)
        if not m:
            errors.append({"line": lineno, "message": FORMAT_HINT})
            continue

        start, num_s, _end, count_s, beats_s, bpm_s = m.groups()
        num = int(num_s)
        beats = int(beats_s) if beats_s is not None else DEFAULT_BEATS
        bpm = int(bpm_s) if bpm_s is not None else None

        # 拍数与 BPM 必须为正整数
        if beats <= 0:
            errors.append(_timing_error(lineno, BEATS_HINT))
        if bpm_s is not None and bpm <= 0:
            errors.append(_timing_error(lineno, BPM_HINT))

        # 编号唯一性校验
        if num in seen:
            errors.append({
                "line": lineno,
                "message": f"小节编号 {num} 重复，首次出现在第 {seen[num]} 行",
            })
        else:
            seen[num] = lineno

        # 反复起点：新建分组并压栈，本行小节属于该分组
        if start:
            group = {"type": "group", "count": None, "children": [], "line": lineno}
            stack[-1]["children"].append(group)
            stack.append(group)

        stack[-1]["children"].append({
            "type": "measure", "num": num, "line": lineno,
            "beats": beats, "bpm": bpm,
        })

        # 反复终点：弹出当前分组并记录重复次数
        if count_s is not None:
            if len(stack) == 1:
                errors.append({
                    "line": lineno,
                    "message": "反复终点 :| 没有匹配的反复起点 |:",
                })
            else:
                group = stack.pop()
                group["count"] = int(count_s)
                group["end_line"] = lineno

    # 输入结束时仍未闭合的反复起点
    while len(stack) > 1:
        group = stack.pop()
        errors.append({
            "line": group["line"],
            "message": "反复起点 |: 没有匹配的反复终点 :|xN",
        })

    errors.sort(key=lambda e: e["line"])
    return root, errors


def expand(root, limit=MAX_MEASURES):
    """按嵌套层级展开为实际演奏顺序并累计排练时间轴。

    迭代实现，避免深嵌套递归溢出。返回 (rows, overflow)：
    - rows 为 [{"seq": 演奏序号, "num": 原小节编号, "line": 源行号,
                "beats": 拍数, "bpm": 本小节实际速度,
                "start_ms": 起（毫秒）, "end_ms": 止（毫秒）}, ...]
    - overflow 为导致超过 limit 的小节节点；未超限时为 None

    时间累计保留毫秒精度的浮点值，起止时间输出时四舍五入到最近毫秒。
    """
    rows = []
    bpm = DEFAULT_BPM  # 当前速度：未标速度的小节沿用上一演奏小节的速度
    elapsed_ms = 0.0  # 已累计时长（毫秒，浮点保留精度）
    # 帧结构：[子节点列表, 下一个待处理下标, 剩余重复次数]
    stack = [[root["children"], 0, 1]]
    while stack:
        frame = stack[-1]
        children, idx, _ = frame
        if idx >= len(children):
            # 当前分组一轮结束：剩余次数减一后从头再来
            stack.pop()
            frame[2] -= 1
            if frame[2] > 0:
                frame[1] = 0
                stack.append(frame)
            continue
        node = children[idx]
        frame[1] += 1
        if node["type"] == "measure":
            # 带速度标记的小节每次实际出现时都先切换速度
            if node["bpm"] is not None:
                bpm = node["bpm"]
            start_ms = elapsed_ms
            elapsed_ms += node["beats"] * 60_000.0 / bpm
            rows.append({
                "seq": len(rows) + 1,
                "num": node["num"],
                "line": node["line"],
                "beats": node["beats"],
                "bpm": bpm,
                "start_ms": int(start_ms + 0.5),
                "end_ms": int(elapsed_ms + 0.5),
            })
            if len(rows) > limit:
                return rows, node
        else:
            stack.append([node["children"], 0, node["count"]])
    return rows, None
