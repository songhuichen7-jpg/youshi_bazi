"""Hepan (合盘) service: pair-relationship reading from two birth charts.

Built on top of paipan (排盘) + card (个人卡) services. The mapping engine
turns (A天干, B天干) → relationship category, and the payload composer
attaches the matching base copy (04a) and dynamic modifier (04b).
"""
