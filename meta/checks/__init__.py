"""Pure checkers over akmon's own tree, reported through the shared finding envelope.

Not shipped to consumers: their only caller is ``meta/self_ci.py``. What a *consumer* must
satisfy lives in ``bin/verify.py``; what akmon must satisfy about its own declarations and
documentation lives here. Each module exposes one pure function taking a tree root and
returning ``list[Finding]``, so the same implementation runs over the real tree and over
synthetic fixtures with no branch between them.
"""
