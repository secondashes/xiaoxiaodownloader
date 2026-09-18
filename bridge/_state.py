# -*- coding: utf-8 -*-
"""bridge 包的扁平命名空间状态器。

子模块开头调用 apply_prev(globals()) 注入"此前已加载模块的全部名字"
（等价于原单文件自上而下的名字可见性）；__init__.py 在每个子模块加载完
后调用 register 登记其名字；全部加载后调用 finalize 做全量交叉注入
（调用期的前向引用：后定义的名字对先定义模块的函数可见——与原单文件一致）。
"""
from __future__ import annotations

_names: dict = {}


def register(ns: dict) -> None:
    """子模块加载完成后登记其全部名字（跳过模块元数据 dunder）。"""
    for k, v in ns.items():
        if not k.startswith("__"):
            _names[k] = v


def apply_prev(ns: dict) -> None:
    """子模块开头调用：注入此前已加载模块的全部名字（模块级语句执行前）。"""
    ns.update(_names)


def finalize(mods: list, package_ns: dict) -> None:
    """全部子模块加载完成后：合并全量名字 → 注入每个子模块与包命名空间。"""
    merged = dict(_names)
    for m in mods:
        for k, v in vars(m).items():
            if not k.startswith("__"):
                merged[k] = v
    for m in mods:
        m.__dict__.update(merged)
    package_ns.update(merged)
    _names.clear()
    _names.update(merged)
