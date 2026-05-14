"""中心化 mechanism tag 词汇表（Plan 7.5a.1 §5.3）。

避免 xingyun.py 内部 f-string 散落；修改 tag 文案只改这一个文件。
所有 tag 字符串保持跟 Plan 7.4 ship 时 byte-for-byte 一致。
"""
from __future__ import annotations


# ===== 干 effect base scoring (5 outcomes) =====
GAN_SHENG = '干·相生'
GAN_KE = '干·相克'
GAN_BIZHU = '干·比助'
GAN_XIE = '干·相泄'
GAN_HAO = '干·相耗'


# ===== 支 effect base scoring (5 outcomes) =====
ZHI_SHENG = '支·相生'
ZHI_KE = '支·相克'
ZHI_BIZHU = '支·比助'
ZHI_XIE = '支·相泄'
ZHI_HAO = '支·相耗'


# ===== 合化 / 六合 modifier (4 builder functions, 后缀含 wuxing) =====

def gan_hehua_zhuanzhu(wx: str) -> str:
    """e.g. gan_hehua_zhuanzhu('木') → '干·合化转助·木'."""
    return f'干·合化转助·{wx}'


def gan_hehua_fanke(wx: str) -> str:
    """e.g. gan_hehua_fanke('金') → '干·合化反克·金'."""
    return f'干·合化反克·{wx}'


def zhi_liuhe_zhuanzhu(wx: str) -> str:
    """e.g. zhi_liuhe_zhuanzhu('木') → '支·六合化木·转助'."""
    return f'支·六合化{wx}·转助'


def zhi_liuhe_fanke(wx: str) -> str:
    """e.g. zhi_liuhe_fanke('火') → '支·六合化火·反克'."""
    return f'支·六合化{wx}·反克'
