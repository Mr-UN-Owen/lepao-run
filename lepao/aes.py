# -*- coding: utf-8 -*-
# --- lepao-research-notice v1 (do not remove; see LICENSE) ---
# 乐跑协议研究（Lepao Research） · https://github.com/dan-cun/lepao3
# Copyright (c) 2026 dan-cun · 技术讨论 QQ 1224145544（仅作技术讨论，不提供代打卡）
# 许可证 LRL-1.0（乐跑研究协议 1.0）：仅供学习 · 不可牟利 · 再发布须署名引用原始仓库 · 声明不得删除
# 删除或篡改本块即依 LRL-1.0 第三条自动终止授权；衍生版须继续以 LRL-1.0 授权并标注修改说明。
# --- end lepao-research-notice ---
# Copyright (c) 2026 dan-cun · 许可协议见项目根目录 LICENSE
"""lepao.aes —— 纯 Python AES-128-CBC（无第三方依赖，供打包分发/免安装环境使用）

为什么要有这个文件：
  `crypto.py` 原本只依赖 pycryptodome。做成品应用（PyInstaller 单文件、绿色版）时，
  第三方 C 扩展是负担；这里用纯 Python 复刻同一套 AES-128-CBC + PKCS7，
  接口与 pycryptodome 的用法等价，`crypto.py` 优先用 pycryptodome，缺失时自动回退到这里。

性能：单次 v3 请求只加解密一次（几百字节~几十 KB），纯 Python 完全够用。
"""

# 标准 AES S-Box（FIPS-197 常量表）
_SBOX = bytes((
    0x63, 0x7c, 0x77, 0x7b, 0xf2, 0x6b, 0x6f, 0xc5, 0x30, 0x01, 0x67, 0x2b, 0xfe, 0xd7, 0xab, 0x76,
    0xca, 0x82, 0xc9, 0x7d, 0xfa, 0x59, 0x47, 0xf0, 0xad, 0xd4, 0xa2, 0xaf, 0x9c, 0xa4, 0x72, 0xc0,
    0xb7, 0xfd, 0x93, 0x26, 0x36, 0x3f, 0xf7, 0xcc, 0x34, 0xa5, 0xe5, 0xf1, 0x71, 0xd8, 0x31, 0x15,
    0x04, 0xc7, 0x23, 0xc3, 0x18, 0x96, 0x05, 0x9a, 0x07, 0x12, 0x80, 0xe2, 0xeb, 0x27, 0xb2, 0x75,
    0x09, 0x83, 0x2c, 0x1a, 0x1b, 0x6e, 0x5a, 0xa0, 0x52, 0x3b, 0xd6, 0xb3, 0x29, 0xe3, 0x2f, 0x84,
    0x53, 0xd1, 0x00, 0xed, 0x20, 0xfc, 0xb1, 0x5b, 0x6a, 0xcb, 0xbe, 0x39, 0x4a, 0x4c, 0x58, 0xcf,
    0xd0, 0xef, 0xaa, 0xfb, 0x43, 0x4d, 0x33, 0x85, 0x45, 0xf9, 0x02, 0x7f, 0x50, 0x3c, 0x9f, 0xa8,
    0x51, 0xa3, 0x40, 0x8f, 0x92, 0x9d, 0x38, 0xf5, 0xbc, 0xb6, 0xda, 0x21, 0x10, 0xff, 0xf3, 0xd2,
    0xcd, 0x0c, 0x13, 0xec, 0x5f, 0x97, 0x44, 0x17, 0xc4, 0xa7, 0x7e, 0x3d, 0x64, 0x5d, 0x19, 0x73,
    0x60, 0x81, 0x4f, 0xdc, 0x22, 0x2a, 0x90, 0x88, 0x46, 0xee, 0xb8, 0x14, 0xde, 0x5e, 0x0b, 0xdb,
    0xe0, 0x32, 0x3a, 0x0a, 0x49, 0x06, 0x24, 0x5c, 0xc2, 0xd3, 0xac, 0x62, 0x91, 0x95, 0xe4, 0x79,
    0xe7, 0xc8, 0x37, 0x6d, 0x8d, 0xd5, 0x4e, 0xa9, 0x6c, 0x56, 0xf4, 0xea, 0x65, 0x7a, 0xae, 0x08,
    0xba, 0x78, 0x25, 0x2e, 0x1c, 0xa6, 0xb4, 0xc6, 0xe8, 0xdd, 0x74, 0x1f, 0x4b, 0xbd, 0x8b, 0x8a,
    0x70, 0x3e, 0xb5, 0x66, 0x48, 0x03, 0xf6, 0x0e, 0x61, 0x35, 0x57, 0xb9, 0x86, 0xc1, 0x1d, 0x9e,
    0xe1, 0xf8, 0x98, 0x11, 0x69, 0xd9, 0x8e, 0x94, 0x9b, 0x1e, 0x87, 0xe9, 0xce, 0x55, 0x28, 0xdf,
    0x8c, 0xa1, 0x89, 0x0d, 0xbf, 0xe6, 0x42, 0x68, 0x41, 0x99, 0x2d, 0x0f, 0xb0, 0x54, 0xbb, 0x16,
))

_INV_SBOX = bytearray(256)
for _i, _v in enumerate(_SBOX):
    _INV_SBOX[_v] = _i
_INV_SBOX = bytes(_INV_SBOX)

_RCON = (0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36)


def _xtime(a: int) -> int:
    a <<= 1
    if a & 0x100:
        a = (a ^ 0x1B) & 0xFF
    return a


def _gmul(a: int, b: int) -> int:
    p = 0
    for _ in range(8):
        if b & 1:
            p ^= a
        hi = a & 0x80
        a = (a << 1) & 0xFF
        if hi:
            a ^= 0x1B
        b >>= 1
    return p & 0xFF


class AES128:
    """单块 AES-128 加解密 + CBC 模式（PKCS7 填充）。"""

    def __init__(self, key: bytes):
        if len(key) != 16:
            raise ValueError("AES-128 需要 16 字节密钥")
        self._rk = self._expand(key)

    @staticmethod
    def _expand(key: bytes):
        rk = list(key)
        for i in range(4, 44):
            t = rk[(i - 1) * 4:i * 4]
            if i % 4 == 0:
                t = t[1:] + t[:1]                      # RotWord
                t = [_SBOX[b] for b in t]              # SubWord
                t[0] ^= _RCON[i // 4 - 1]              # Rcon
            rk.extend(t[k] ^ rk[(i - 4) * 4 + k] for k in range(4))
        return bytes(rk)

    def encrypt_block(self, block: bytes) -> bytes:
        s = [b ^ self._rk[i] for i, b in enumerate(block)]
        for rnd in range(1, 11):
            s = [_SBOX[b] for b in s]
            s = self._shift_rows(s)
            if rnd != 10:
                s = self._mix_columns(s)
            base = rnd * 16
            s = [s[i] ^ self._rk[base + i] for i in range(16)]
        return bytes(s)

    def decrypt_block(self, block: bytes) -> bytes:
        base = 160
        s = [block[i] ^ self._rk[base + i] for i in range(16)]
        for rnd in range(9, -1, -1):
            s = self._inv_shift_rows(s)
            s = [_INV_SBOX[b] for b in s]
            base = rnd * 16
            s = [s[i] ^ self._rk[base + i] for i in range(16)]
            if rnd != 0:
                s = self._inv_mix_columns(s)
        return bytes(s)

    @staticmethod
    def _shift_rows(s):
        return [s[0], s[5], s[10], s[15],
                s[4], s[9], s[14], s[3],
                s[8], s[13], s[2], s[7],
                s[12], s[1], s[6], s[11]]

    @staticmethod
    def _inv_shift_rows(s):
        return [s[0], s[13], s[10], s[7],
                s[4], s[1], s[14], s[11],
                s[8], s[5], s[2], s[15],
                s[12], s[9], s[6], s[3]]

    @staticmethod
    def _mix_columns(s):
        out = [0] * 16
        for c in range(4):
            i = c * 4
            a0, a1, a2, a3 = s[i], s[i + 1], s[i + 2], s[i + 3]
            out[i] = _xtime(a0) ^ (_xtime(a1) ^ a1) ^ a2 ^ a3
            out[i + 1] = a0 ^ _xtime(a1) ^ (_xtime(a2) ^ a2) ^ a3
            out[i + 2] = a0 ^ a1 ^ _xtime(a2) ^ (_xtime(a3) ^ a3)
            out[i + 3] = (_xtime(a0) ^ a0) ^ a1 ^ a2 ^ _xtime(a3)
        return out

    @staticmethod
    def _inv_mix_columns(s):
        out = [0] * 16
        for c in range(4):
            i = c * 4
            a0, a1, a2, a3 = s[i], s[i + 1], s[i + 2], s[i + 3]
            out[i] = _gmul(a0, 14) ^ _gmul(a1, 11) ^ _gmul(a2, 13) ^ _gmul(a3, 9)
            out[i + 1] = _gmul(a0, 9) ^ _gmul(a1, 14) ^ _gmul(a2, 11) ^ _gmul(a3, 13)
            out[i + 2] = _gmul(a0, 13) ^ _gmul(a1, 9) ^ _gmul(a2, 14) ^ _gmul(a3, 11)
            out[i + 3] = _gmul(a0, 11) ^ _gmul(a1, 13) ^ _gmul(a2, 9) ^ _gmul(a3, 14)
        return out


def pkcs7_pad(data: bytes, block: int = 16) -> bytes:
    n = block - len(data) % block
    return data + bytes([n]) * n


def pkcs7_unpad(data: bytes, block: int = 16) -> bytes:
    if not data or len(data) % block:
        raise ValueError("PKCS7: 长度非法")
    n = data[-1]
    if not 1 <= n <= block or data[-n:] != bytes([n]) * n:
        raise ValueError("PKCS7: 填充非法")
    return data[:-n]


def aes_cbc_encrypt(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-128-CBC + PKCS7，返回密文（无 base64）。"""
    aes = AES128(key)
    data = pkcs7_pad(plaintext)
    prev = iv
    out = bytearray()
    for i in range(0, len(data), 16):
        block = bytes(a ^ b for a, b in zip(data[i:i + 16], prev))
        prev = aes.encrypt_block(block)
        out += prev
    return bytes(out)


def aes_cbc_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    """AES-128-CBC 解密并去 PKCS7 填充。"""
    if len(ciphertext) % 16:
        raise ValueError("CBC: 密文长度必须是 16 的倍数")
    aes = AES128(key)
    prev = iv
    out = bytearray()
    for i in range(0, len(ciphertext), 16):
        block = ciphertext[i:i + 16]
        dec = aes.decrypt_block(block)
        out += bytes(a ^ b for a, b in zip(dec, prev))
        prev = block
    return pkcs7_unpad(bytes(out))
